"""Content plan CRUD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.database import get_db
from app.models.content_plan_item import ContentPlanItem, CONTENT_PLAN_STATUSES
from app.models.user import User
from app.routers.deps import get_user_channel
from app.services.audit_service import log_audit
from app.utils.errors import AppError
from app.utils.security import check_csrf

router = APIRouter(prefix="/content-plan", tags=["content-plan"])


def _item_dict(i: ContentPlanItem) -> dict:
    return {
        "id": i.id,
        "channel_id": i.channel_id,
        "title": i.title,
        "description": i.description,
        "idea": i.idea,
        "target_keyword": i.target_keyword,
        "status": i.status,
        "planned_date": i.planned_date.isoformat() if i.planned_date else None,
        "publish_date": i.publish_date.isoformat() if i.publish_date else None,
        "notes": i.notes,
        "created_at": i.created_at.isoformat() if i.created_at else None,
        "updated_at": i.updated_at.isoformat() if i.updated_at else None,
    }


class PlanCreate(BaseModel):
    channel_id: str
    title: str
    description: str | None = None
    idea: str | None = None
    target_keyword: str | None = None
    planned_date: str | None = None
    notes: str | None = None


class PlanUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    idea: str | None = None
    target_keyword: str | None = None
    status: str | None = None
    planned_date: str | None = None
    publish_date: str | None = None
    notes: str | None = None


@router.get("")
def list_plan(channel_id: str | None = None, status: str = "",
              user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    q = db.query(ContentPlanItem)
    if channel_id:
        get_user_channel(db, user, channel_id)
        q = q.filter(ContentPlanItem.channel_id == channel_id)
    if status:
        q = q.filter(ContentPlanItem.status == status)
    q = q.order_by(ContentPlanItem.planned_date.asc().nullslast(), ContentPlanItem.created_at.desc())
    items = q.limit(500).all()
    return {"items": [_item_dict(i) for i in items], "total": len(items)}


@router.post("", status_code=201)
def create_plan(payload: PlanCreate, request: Request, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    ch = get_user_channel(db, user, payload.channel_id)
    from datetime import date

    planned = None
    if payload.planned_date:
        try:
            planned = date.fromisoformat(payload.planned_date)
        except ValueError:
            raise AppError(422, "VALIDATION_ERROR", "planned_date must be YYYY-MM-DD.")
    item = ContentPlanItem(
        channel_id=ch.id,
        title=payload.title,
        description=payload.description,
        idea=payload.idea,
        target_keyword=payload.target_keyword,
        planned_date=planned,
        notes=payload.notes,
        status="IDEA",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    log_audit(db, user_id=user.id, channel_id=ch.id, action="content_plan_created",
              target=item.title, result="ok")
    return _item_dict(item)


@router.patch("/{item_id}")
def update_plan(item_id: str, payload: PlanUpdate, request: Request,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    from datetime import date

    item = db.get(ContentPlanItem, item_id)
    if item is None:
        raise AppError(404, "NOT_FOUND", "Plan item not found.")
    data = payload.model_dump(exclude_none=True)
    if "status" in data and data["status"] not in CONTENT_PLAN_STATUSES:
        raise AppError(422, "VALIDATION_ERROR", f"status must be one of {', '.join(CONTENT_PLAN_STATUSES)}.")
    for key in ("planned_date", "publish_date"):
        if data.get(key):
            try:
                data[key] = date.fromisoformat(str(data[key]))
            except ValueError:
                raise AppError(422, "VALIDATION_ERROR", f"{key} must be YYYY-MM-DD.")
    for k, v in data.items():
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    log_audit(db, user_id=user.id, channel_id=item.channel_id, action="content_plan_updated",
              target=item.title, result="ok")
    return _item_dict(item)


@router.delete("/{item_id}")
def delete_plan(item_id: str, request: Request, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
    check_csrf(request)
    item = db.get(ContentPlanItem, item_id)
    if item is None:
        raise AppError(404, "NOT_FOUND", "Plan item not found.")
    title = item.title
    channel_id = item.channel_id
    db.delete(item)
    db.commit()
    log_audit(db, user_id=user.id, channel_id=channel_id, action="content_plan_deleted",
              target=title, result="ok")
    return {"success": True}
