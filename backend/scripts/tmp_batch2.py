"""临时：批量测剩余图片的识别+标注（用当前 Prompt）。用后即删。用法：python scripts/tmp_batch2.py 08 09 10 12 13"""
from __future__ import annotations

import os
import sys
import time

import io

import httpx
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000/api/v1"
ORIGIN = "http://127.0.0.1:8000"
IMG_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "施工现场隐患图片"))

PICKS = sys.argv[1:] or ["08", "09", "10", "12", "13"]


def main() -> None:
    c = httpx.Client(base_url=BASE, trust_env=False, timeout=300)
    r = c.post("/auth/login", data={"username": "admin", "password": "Admin@123456"})
    r.raise_for_status()
    tok = r.json()["data"]["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    ok_cnt = 0
    for i in PICKS:
        path = os.path.join(IMG_DIR, f"hazard_{i}.jpg")
        with open(path, "rb") as f:
            data = f.read()
        t0 = time.time()
        rr = c.post("/hazards/analyze", files={"file": (f"hazard_{i}.jpg", data, "image/jpeg")}, headers=h)
        dt = time.time() - t0
        if rr.status_code != 200:
            print(f"[{i}] ✗ HTTP {rr.status_code}（{dt:.1f}s）：{rr.text[:80]}")
            continue
        d = rr.json()["data"]
        ok_cnt += 1
        dets = d.get("detections") or []
        print(f"[{i}] ✓ {dt:6.1f}s | 主检 {d['type_suggest']:4s}/{d['level_suggest']:8s} 置信 {d.get('confidence')} | 共 {len(dets)} 处")
        for idx, det in enumerate(dets, 1):
            print(f"     #{idx} {det['type_suggest']:4s} {det['level_suggest']:8s} 置信 {det.get('confidence')} "
                  f"bbox {det.get('bbox')} | {det.get('description', '')[:30]}")
        if d.get("annotated_url"):
            img = c.get(f"{ORIGIN}{d['annotated_url']}")
            if img.status_code != 200:
                print(f"     ⚠ 标注图 HTTP {img.status_code}")
            else:
                pil = Image.open(io.BytesIO(img.content)).convert("RGB")
                iw, ih = pil.size
                colors: set[tuple[int, int, int]] = set()
                for det in dets:
                    b = det.get("bbox")
                    if not b:
                        continue
                    x1, y1, x2, y2 = [int(v * dim) for v, dim in zip(b, (iw, ih, iw, ih))]
                    for yy in (y1, y2):
                        yy = min(max(yy, 0), ih - 1)
                        for xx in range(x1, x2 + 1, max(2, (x2 - x1) // 20)):
                            colors.add(pil.getpixel((min(max(xx, 0), iw - 1), yy)))
                print(f"     标注图 {iw}x{ih} 框线颜色数≈{len(colors)}（期望={len(dets)} 种不同颜色）")

    print(f"\n===== 本批完成：成功 {ok_cnt}/{len(PICKS)} =====")


if __name__ == "__main__":
    main()
