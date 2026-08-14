"""模块一 隐患图片 AI 识别客户端（H01 视觉分析）。

走 OpenAI 兼容 chat.completions 多模态（image_url content part），与 llm_client 同协议、
同重试/JSON 解析风格。VISION_BASE_URL / VISION_API_KEY / VISION_MODEL_NAME 在 backend/.env
独立配置（与 E02/A01 的 LLM 隔离），任一为空即未配置：analyze_image 抛 VisionError，
api 层转 503 提示「视觉识别不可用」，不阻断上报主流程。

输出经 _sanitize 收敛到合法枚举（type 走中文候选表 / level 四档 / confidence 夹到 [0,1] /
bbox 归一化坐标校验），前端把 type_suggest/level_suggest/bbox 回显进表单，确认后随上报提交
（落 hazard.risk_report）。annotate_image() 把 bbox 画到原图上生成标注图，供用户/审核直观定位隐患。

坐标校正：发送前把图居中 pad 成正方形（DashScope 对非正方形输入存在 y 轴坐标错位，
见 _square_b64image），模型返回的画布坐标经 _remap_detections 反算回原图归一化坐标。
"""
from __future__ import annotations

import base64
import io
import logging
import time
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    OpenAIError,
    RateLimitError,
)

from ..core.config import get_settings
from .llm_client import _extract_json

logger = logging.getLogger("vision")

# 可重试的网络/限流类错误（指数退避），同 llm_client 约定
_RETRYABLE = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    APIStatusError,
    httpx.HTTPError,
)


class VisionError(Exception):
    """视觉识别失败（未配置 / 调用失败 / 响应解析失败）。"""


# 隐患类型中文候选（对齐 model/hazard.py HazardType）
_TYPE_CANDIDATES = ("高处作业", "用电安全", "机械伤害", "消防", "临边防护", "其他")
# 合法等级（对齐 model/hazard.py HazardLevel）
_LEVELS = ("CRITICAL", "MAJOR", "GENERAL", "MINOR")

_PROMPT = """你是蜀道集团安全生产隐患图片识别助手。请依据国家标准《高处作业分级 GB/T 3608-2008》和施工现场常见隐患判定标准，分析用户上传的图片，识别其中【所有】真实存在的安全隐患（可能有多处）。

隐患类型候选及严格判定标准（逐条核对画面证据，不得想当然）：
- 高处作业：作业人员脚下是「明显多层高（约 2 层楼及以上）」的高空结构或建筑——如屋顶/屋脊、高层脚手架顶部、塔吊/吊篮、高架桥/桥墩、烟囱/高塔、高层建筑外墙等，且存在坠落风险（未系安全带、无护栏、无防护网）。
  判定要点：只认「一眼就能看出是高空结构的场景」，不靠估算米数。
  反例（一律不算高处作业，即使未系安全带）：站在离地约 1 米的金属架/操作平台/台阶/脚手架底层、站在货车车厢边、地面及一层以内高度的任何作业。
  若作业结构不属于上述明显高空场景、或无法确认，一律不判「高处作业」。
- 用电安全：电线绝缘破损裸露、私拉乱接、配电箱敞开未锁、电动工具线缆破损、积水带电等。
- 机械伤害：设备传动部位无防护罩、运转中清理、裸露钢筋端头、锯/钻/卷扬等卷入危险。
- 消防：明火/电焊/切割作业无监护、火花飞溅无遮挡、可燃物堆积、灭火器材缺失或遮挡等。
- 临边防护：临边、洞口、深基坑边缘无防护栏杆/盖板/安全网，人员靠近无防护边缘（与「高处作业」区别：高差不大或属地面开口，主要风险是坠落面有开口）。
- 其他：不属于以上类型，或画面信息不足无法确认。

输出要求：
1. 找出画面中每一处独立的安全隐患，每处为一个检测项 detection，分别给出 bbox 精确框住对应区域（归一化坐标 [x1,y1,x2,y2]，(x1,y1) 左上、(x2,y2) 右下）。框边要贴紧隐患主体，不要包含无关背景，也不要只框住主体的一部分。画面有几处就列几处。
2. 每个 detection 含字段：type（类型）、level（等级 CRITICAL/MAJOR/GENERAL/MINOR）、description（≤40 字，该处隐患表现）、reason（≤30 字，判断依据）、bbox、confidence（0~1）。
3. 隐患最多列出 4 处，按严重程度从高到低排序；没有明显隐患时 detections 为空数组。
4. 保守原则：拿不准的隐患不要列，整体把握度低时 detections 可为空；绝不臆测。

只输出一个 JSON 对象，不要任何多余文字或解释，格式如下：
{"detections": [
  {"type": "高处作业", "level": "MAJOR", "description": "工人在约3米高的屋顶边缘作业，未系安全带", "reason": "屋顶高空、未系安全带", "bbox": [0.2, 0.3, 0.6, 0.8], "confidence": 0.9},
  {"type": "消防", "level": "GENERAL", "description": "电焊火花飞溅，周围有可燃物", "reason": "明火切割无遮挡", "bbox": [0.7, 0.4, 0.95, 0.6], "confidence": 0.7}
]}"""


async def analyze_image(image_path: str | Path) -> dict:
    """识别单张图片，返回 {type_suggest, level_suggest, description, reason, confidence, bbox, report}。

    - 发送前把图片居中 pad 成正方形画布（DashScope 对非正方形输入存在 y 轴坐标错位，
      见 _square_b64image），返回的 bbox 已反算回原图归一化坐标；
    - bbox 为归一化 [x1,y1,x2,y2]（无隐患时为 None），经 _sanitize 收敛到合法取值；
    - 网络/限流错误指数退避重试（base 2s，最多 2 次重试）；单次调用上限 240s，外层 wait_for 再封顶；
    - 响应剥围栏后仍非合法 JSON → VisionError（不重试，提示前端换图或跳过识别）。
    """
    settings = get_settings()
    if not (settings.vision_base_url and settings.vision_api_key and settings.vision_model_name):
        raise VisionError("视觉模型未配置：请填写 .env 的 VISION_BASE_URL / VISION_API_KEY / VISION_MODEL_NAME")

    b64, geom = _square_b64image(image_path)
    client = AsyncOpenAI(
        base_url=settings.vision_base_url,
        api_key=settings.vision_api_key,
        timeout=240.0,
        max_retries=0,  # 重试策略由本函数统一控制
    )
    last_exc: Exception | None = None
    try:
        for attempt in range(3):
            try:
                t0 = time.perf_counter()
                resp = await client.chat.completions.create(
                    model=settings.vision_model_name,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": b64}},
                            {"type": "text", "text": _PROMPT},
                        ],
                    }],
                    temperature=0.1,
                    stream=False,
                )
                if not resp.choices:
                    raise VisionError("视觉模型响应没有 choices")
                content = (resp.choices[0].message.content or "").strip()
                if not content:
                    raise VisionError("视觉模型响应内容为空")
                logger.info("视觉识别完成（第 %s 次）耗时 %.1fs", attempt + 1, time.perf_counter() - t0)
                return _remap_detections(_sanitize(_extract_json(content)), geom)
            except VisionError:
                raise
            except _RETRYABLE as exc:
                last_exc = exc
                logger.warning("视觉识别调用失败（第 %s 次）：%s", attempt + 1, exc)
                if attempt < 2:
                    await _sleep(2 ** (attempt + 1))  # 2s、4s
            except OpenAIError as exc:
                # 鉴权/参数/模型名错误（如 qwen3.8-max 不存在）属不可重试，直接失败
                raise VisionError(f"视觉识别调用失败：{exc}") from exc
        raise VisionError(f"视觉识别多次失败（已重试 2 次）：{last_exc}")
    finally:
        await client.close()


def _sanitize(raw: dict) -> dict:
    """把模型输出收敛为 detections 列表（每处一个 bbox），并保留主检测的顶层字段。

    兼容两种模型输出：新格式 {"detections": [...]}；旧格式单个对象 {"type", ...}。
    检测按 confidence 降序，第一条即主检测（顶层 type_suggest/bbox 等向后兼容）。
    """
    dets = raw.get("detections")
    if not isinstance(dets, list):
        if isinstance(raw, dict) and ("type" in raw or "bbox" in raw or "level" in raw):
            dets = [raw]  # 兼容：模型直接返回单个对象
        else:
            dets = []

    detections: list[dict] = []
    for d in dets[:4]:
        if isinstance(d, dict):
            det = _sanitize_detection(d)
            if det:
                detections.append(det)
    detections.sort(key=lambda x: x["confidence"], reverse=True)

    primary = detections[0] if detections else {}
    return {
        "detections": detections,              # 全部检测项（每处含 type/level/bbox/description/reason/confidence）
        "type_suggest": primary.get("type", "其他"),
        "level_suggest": primary.get("level", "MINOR"),
        "description": primary.get("description", ""),
        "reason": primary.get("reason", ""),   # 识别依据，供前端/调试回显
        "confidence": primary.get("confidence", 0.0),
        "bbox": primary.get("bbox"),           # 主检测归一化框；无隐患为 None
        "report": raw,  # 原始模型输出透传，落 hazard.risk_report
    }


def _sanitize_detection(d: dict) -> dict | None:
    """收敛单个检测项的枚举（type/level/confidence）并校验 bbox。"""
    t = str(d.get("type", "其他")).strip()
    if t not in _TYPE_CANDIDATES:
        t = "其他"
    lvl = str(d.get("level", "GENERAL")).strip().upper()
    if lvl not in _LEVELS:
        lvl = "GENERAL"
    bbox = _sanitize_bbox(d.get("bbox"))
    desc = str(d.get("description", "")).strip()[:200]
    reason = str(d.get("reason", "")).strip()[:200]
    try:
        conf = float(d.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        conf = 0.0
    conf = min(max(conf, 0.0), 1.0)
    # 纯"其他"且无框的项视为无效检测（模型兜底输出），丢弃
    if t == "其他" and bbox is None:
        return None
    return {
        "type": t,
        "level": lvl,
        "description": desc,
        "reason": reason,
        "confidence": round(conf, 4),
        "bbox": bbox,
    }


def _sanitize_bbox(value) -> list[float] | None:
    """归一化 bbox 校验：4 个 [0,1] 数字、宽高 > 阈值；非法一律 None（不阻断识别）。"""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(v) for v in value]
    except (TypeError, ValueError):
        return None
    x1, y1 = min(max(x1, 0.0), 1.0), min(max(y1, 0.0), 1.0)
    x2, y2 = min(max(x2, 0.0), 1.0), min(max(y2, 0.0), 1.0)
    left, top = min(x1, x2), min(y1, y2)
    right, bottom = max(x1, x2), max(y1, y2)
    # 宽/高过小视为无效框（可能是模型瞎给的点）
    if right - left < 0.02 or bottom - top < 0.02:
        return None
    return [round(left, 4), round(top, 4), round(right, 4), round(bottom, 4)]


# 多框配色（红/蓝/橙/绿/紫），编号与颜色一一对应
_BOX_COLORS = ((220, 30, 30), (30, 80, 220), (240, 140, 20), (40, 160, 60), (160, 40, 180))


def annotate_image(image_path: str | Path, detections: list[dict]) -> str | None:
    """把每处隐患的归一化 bbox 画到原图上（多框不同色+编号标签），标注图落盘 uploads/{day}/annotated/。

    - detections 为 _sanitize 输出的检测项列表（每项含 bbox/type_suggest），无有效框 → 返回 None；
    - 每个框一个颜色，标签如「1 高处作业」；字体缺失则只画框，不抛错；
    - 标注图是运行期产物（uploads 已 gitignore），PNG 格式保证框线清晰。
    """
    boxes = [(d["bbox"], d.get("type", "")) for d in detections if d.get("bbox")]
    if not boxes:
        return None
    try:
        # 与 _square_b64image 保持一致：应用 EXIF 旋转后再画框，保证标注图朝向与模型所见一致
        img = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
        w, h = img.size
        draw = ImageDraw.Draw(img)
        line_w = max(2, min(w, h) // 200)
        font = _cjk_font(line_w * 4)

        for idx, (bbox, label) in enumerate(boxes):
            color = _BOX_COLORS[idx % len(_BOX_COLORS)]
            left, top, right, bottom = [v * dim for v, dim in zip(bbox, (w, h, w, h))]
            draw.rectangle([left, top, right, bottom], outline=color, width=line_w)

            text = f"{idx + 1} {(label or '').strip()[:10]}"
            if font and text.strip():
                tb = draw.textbbox((0, 0), text, font=font)
                tw, th = tb[2] - tb[0], tb[3] - tb[1]
                pad = line_w
                # 标签栏放框正上方；上方超界则放进框内左上角
                lx1, ly1 = left, top - th - pad * 2
                if ly1 < 0:
                    ly1 = top
                draw.rectangle([lx1, ly1, lx1 + tw + pad * 2, ly1 + th + pad * 2], fill=color)
                draw.text((lx1 + pad, ly1 + pad - tb[1]), text, fill=(255, 255, 255), font=font)

        rel = f"{datetime.now().strftime('%Y%m%d')}/annotated/{uuid.uuid4().hex}.png"
        target = Path(get_settings().upload_dir) / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        img.save(target, format="PNG")
        return rel
    except Exception:  # noqa: BLE001  画框失败不应阻断识别主流程
        logger.exception("标注图片生成失败：%s", image_path)
        return None


_FONT_CANDIDATES = (
    r"C:/Windows/Fonts/simhei.ttf",
    r"C:/Windows/Fonts/msyh.ttc",
    r"C:/Windows/Fonts/msyhbd.ttc",
    r"C:/Windows/Fonts/simsun.ttc",
)


def _cjk_font(size: int) -> ImageFont.FreeTypeFont | None:
    """找系统 CJK 字体渲染中文标签；找不到返回 None（调用方降级为只画框）。"""
    for p in _FONT_CANDIDATES:
        try:
            if Path(p).exists():
                return ImageFont.truetype(p, size)
        except Exception:  # noqa: BLE001
            continue
    return None


def _square_b64image(image_path: str | Path) -> tuple[str, tuple[int, int, int, int, int]]:
    """读图 → 居中 pad 成正方形画布 → base64 data URI，返回 (data_uri, 画布几何信息)。

    geom = (W, H, S, x_off, y_off)：W/H 为原图宽高、S 为正方形边长、x_off/y_off 为
    内容在画布中的左上偏移。实测 DashScope(qwen3.8-max) 对非正方形输入存在 y 轴坐标错位
    （y 约被按 W/H 拉长、框整体偏下），pad 成正方形后模型坐标严格相对画布，可精确反算回原图。
    画布统一存 JPEG（RGB 无透明通道，体积小）；EXIF 旋转先归一，保证模型所见与标注一致。
    PIL 打不开 → VisionError（不发起无效请求）。
    """
    try:
        img = ImageOps.exif_transpose(Image.open(image_path)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise VisionError(f"图片解析失败：{exc}") from exc
    W, H = img.size
    S = max(W, H)
    canvas = Image.new("RGB", (S, S), (0, 0, 0))
    x_off, y_off = (S - W) // 2, (S - H) // 2
    canvas.paste(img, (x_off, y_off))
    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=92)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}", (W, H, S, x_off, y_off)


def _to_original_bbox(bbox, W: int, H: int, S: int, x_off: int, y_off: int) -> list[float] | None:
    """正方形画布归一化坐标 → 原图归一化坐标（居中 pad 的逆映射）。

    越界部分钳到 [0,1]，映射后宽/高过小的框视为无效返回 None（可能被画布边缘裁掉）。
    """
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        x1, y1, x2, y2 = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return None
    left = (min(x1, x2) * S - x_off) / W
    right = (max(x1, x2) * S - x_off) / W
    top = (min(y1, y2) * S - y_off) / H
    bottom = (max(y1, y2) * S - y_off) / H
    left, top = min(max(left, 0.0), 1.0), min(max(top, 0.0), 1.0)
    right, bottom = min(max(right, 0.0), 1.0), min(max(bottom, 0.0), 1.0)
    if right - left < 0.02 or bottom - top < 0.02:
        return None
    return [round(left, 4), round(top, 4), round(right, 4), round(bottom, 4)]


def _remap_detections(result: dict, geom: tuple[int, int, int, int, int]) -> dict:
    """把模型输出的画布坐标批量映射回原图坐标（原地修改并返回）。

    顶层 detections/bbox 与 report 内嵌的 detections/bbox 一并校正，保证标注图、
    前端展示与落库 risk_report 三处坐标一致（report 虽为原始输出透传，坐标用校正值）。
    """
    W, H, S, x_off, y_off = geom

    def _remap_list(items: list) -> None:
        for det in items:
            if isinstance(det, dict) and det.get("bbox"):
                det["bbox"] = _to_original_bbox(det["bbox"], W, H, S, x_off, y_off)

    _remap_list(result.get("detections", []))
    if result.get("bbox"):
        result["bbox"] = _to_original_bbox(result["bbox"], W, H, S, x_off, y_off)
    report = result.get("report")
    if isinstance(report, dict):
        _remap_list(report.get("detections", []))
        if report.get("bbox"):
            report["bbox"] = _to_original_bbox(report["bbox"], W, H, S, x_off, y_off)
    return result


async def _sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
