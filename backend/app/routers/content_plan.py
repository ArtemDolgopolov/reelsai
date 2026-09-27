from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import Competitor, ContentPlanItem, Reel, ShootStatus
from app.schemas import (
    ContentPlanCreateRequest,
    ContentPlanItemRead,
    ContentPlanUpdateRequest,
)
from app.services.serializers import format_duration

router = APIRouter(prefix="/content-plan", tags=["content-plan"])


def _to_read(item: ContentPlanItem, reel: Reel, username: str) -> ContentPlanItemRead:
    return ContentPlanItemRead(
        id=item.id,
        reel_id=reel.id,
        shoot_status=item.shoot_status,
        title=reel.title,
        author=f"@{username}",
        duration=format_duration(reel.duration_seconds),
        thumbnail_url=reel.thumbnail_url,
        instagram_url=reel.instagram_url,
        overlay_text=reel.overlay_text,
        views_count=reel.views_count,
        likes_count=reel.likes_count,
        comments_count=reel.comments_count,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=list[ContentPlanItemRead])
def list_content_plan(session: Session = Depends(get_session)) -> list[ContentPlanItemRead]:
    rows = session.exec(
        select(ContentPlanItem, Reel, Competitor)
        .where(ContentPlanItem.reel_id == Reel.id)
        .where(Reel.competitor_id == Competitor.id)
        .order_by(col(ContentPlanItem.updated_at).desc())
    ).all()
    return [_to_read(item, reel, competitor.username) for item, reel, competitor in rows]


@router.post("", response_model=ContentPlanItemRead)
def add_to_content_plan(
    payload: ContentPlanCreateRequest,
    session: Session = Depends(get_session),
) -> ContentPlanItemRead:
    reel = session.get(Reel, payload.reel_id)
    if reel is None:
        raise HTTPException(status_code=404, detail="Reel not found")
    competitor = session.get(Competitor, reel.competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")

    existing = session.exec(
        select(ContentPlanItem).where(ContentPlanItem.reel_id == payload.reel_id)
    ).first()
    if existing is not None:
        return _to_read(existing, reel, competitor.username)

    item = ContentPlanItem(reel_id=payload.reel_id, shoot_status=ShootStatus.todo)
    session.add(item)
    session.commit()
    session.refresh(item)
    return _to_read(item, reel, competitor.username)


@router.patch("/{item_id}", response_model=ContentPlanItemRead)
def update_content_plan_item(
    item_id: UUID,
    payload: ContentPlanUpdateRequest,
    session: Session = Depends(get_session),
) -> ContentPlanItemRead:
    item = session.get(ContentPlanItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Content plan item not found")
    reel = session.get(Reel, item.reel_id)
    if reel is None:
        raise HTTPException(status_code=404, detail="Reel not found")
    competitor = session.get(Competitor, reel.competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")

    item.shoot_status = payload.shoot_status
    item.updated_at = datetime.now(timezone.utc)
    session.add(item)
    session.commit()
    session.refresh(item)
    return _to_read(item, reel, competitor.username)


@router.delete("/{item_id}")
def remove_content_plan_item(
    item_id: UUID,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    item = session.get(ContentPlanItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Content plan item not found")
    session.delete(item)
    session.commit()
    return {"status": "ok"}
