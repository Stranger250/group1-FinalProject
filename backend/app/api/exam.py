"""考试工坊接口（E01 题库管理先落地；E02-E05 后续 Phase 追加）。

E01 为管理类接口：仅 安全管理员(SAFETY)/系统管理员(ADMIN) 可访问。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import get_current_user, require_roles
from ..model.user import RoleId, User
from ..schema.ai import ReviewIn
from ..schema.question import (
    QuestionCreate,
    QuestionDifficulty,
    QuestionSource,
    QuestionStatus,
    QuestionType,
    QuestionUpdate,
)
from ..service.question_service import QuestionService
from ..utils.response import resp

router = APIRouter(prefix="/api/v1", tags=["考试工坊"])

# 管理类接口允许的角色
_MANAGE = require_roles(RoleId.SAFETY, RoleId.ADMIN)


@router.get("/questions", summary="题库列表（筛选 + 分页；普通用户仅见已审核 APPROVED 题）")
def list_questions(
    type: QuestionType | None = Query(default=None, description="题型 SINGLE/MULTIPLE/JUDGE/FILL"),
    difficulty: QuestionDifficulty | None = Query(default=None, description="难度 EASY/MEDIUM/HARD"),
    knowledge_point: str | None = Query(default=None),
    status: QuestionStatus | None = Query(default=None, description="PENDING/APPROVED/REJECTED/DISABLED"),
    source: QuestionSource | None = Query(default=None, description="manual/ai"),
    batch_id: str | None = Query(default=None),
    keyword: str | None = Query(default=None, description="题干模糊搜索"),
    page: int = Query(default=1, ge=1, le=100000),  # 上限防 MySQL OFFSET 溢出（#13）
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """O8 权限模型：普通用户仅查询 APPROVED 题（忽略传入 status 过滤）；管理端全量可筛选。"""
    from ..model.question import QuestionStatus as _QS
    is_manager = user.role_id in (RoleId.SAFETY, RoleId.ADMIN)
    eff_status = status if is_manager else _QS.APPROVED
    data = QuestionService.list_page(
        db,
        type_=type,
        difficulty=difficulty,
        knowledge_point=knowledge_point,
        status=eff_status,
        source=source if is_manager else None,
        batch_id=batch_id if is_manager else None,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return resp(data)


# ---------- Excel 批量导入/导出（任务书 §2.10）----------
# 注意：静态前缀路由（export/template/import）必须注册在 /questions/{qid} 动态路由之前，
# 否则 "export" 等会被 int 型 {qid} 拦截返回 422。

@router.get("/questions/export", summary="导出全部题目（xlsx）")
def export_questions(db: Session = Depends(get_db), _=Depends(_MANAGE)):
    """导出题库为 .xlsx（type/content/options|answer/analysis/knowledge_point/difficulty）。"""
    from fastapi.responses import Response
    from ..utils.question_excel import export_questions_to_xlsx
    items = QuestionService.export_all(db)
    return Response(
        content=export_questions_to_xlsx(items),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="questions.xlsx"'},
    )


@router.get("/questions/export/template", summary="下载导入模板（xlsx）")
def export_template(_=Depends(_MANAGE)):
    """空模板（表头 + 四题型示例行）。"""
    from fastapi.responses import Response
    from ..utils.question_excel import build_import_template
    return Response(
        content=build_import_template(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="questions_template.xlsx"'},
    )


@router.post("/questions/import", summary="批量导入题目（xlsx）")
def import_questions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(_MANAGE),
):
    """解析 .xlsx 批量入库：行级校验（错误逐行返回，不中断整批）；答案格式全校验通过才入库。

    支持列：type/content/options(用 | 分隔)/answer/analysis/knowledge_point/difficulty。
    """
    from ..utils.audit import write_audit
    from ..utils.question_excel import parse_import_rows
    data = file.file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件过大（上限 5MB）")
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 文件")
    valid, errors = parse_import_rows(data)
    result = QuestionService.import_rows(db, valid, operator_id=user.id)
    write_audit(db, user, "question_import", target_type="question",
                detail=f"imported={result['imported']} errors={len(result['errors'])}")
    if errors:
        result["errors"] = errors + result["errors"]
    return resp(result)


@router.get("/questions/{qid}", summary="题库详情（普通用户仅 APPROVED 或本人创建的题目）")
def get_question(
    qid: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from ..model.question import Question, QuestionStatus as _QS
    from sqlalchemy import select

    q = db.scalar(select(Question).where(Question.id == qid))
    if q is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    if user.role_id not in (RoleId.SAFETY, RoleId.ADMIN):
        if q.status != _QS.APPROVED and q.creator_id != user.id:
            raise HTTPException(status_code=404, detail="题目不存在")
    return resp(QuestionService.get(db, qid))


@router.post("/questions", summary="录入题目（O8：普通用户提交待审核 PENDING，管理端直接 APPROVED）")
def create_question(
    payload: QuestionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pending = user.role_id not in (RoleId.SAFETY, RoleId.ADMIN)
    return resp(QuestionService.create(db, payload, operator_id=user.id, pending=pending))


@router.post("/questions/{qid}/review", summary="O8 审核用户提交的题目（SAFETY/ADMIN：通过/驳回）")
def review_question(
    qid: int,
    payload: ReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(_MANAGE),
):
    """审核普通用户提交的题目：APPROVED 入库 / REJECTED 驳回（含意见，回流反例库）。"""
    from ..service.review_service import ReviewService
    return resp(ReviewService.review_one(db, qid, payload, user.id))


@router.put("/questions/{qid}", summary="编辑题目")
def update_question(qid: int, payload: QuestionUpdate, db: Session = Depends(get_db), user=Depends(_MANAGE)):
    return resp(QuestionService.update(db, qid, payload, operator_id=user.id))


@router.delete("/questions/{qid}", summary="删除题目")
def delete_question(qid: int, db: Session = Depends(get_db), _=Depends(_MANAGE)):
    QuestionService.delete(db, qid)
    return resp(message="删除成功")
