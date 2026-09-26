from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import text
from sqlmodel import Session, col, select

from app.config import get_settings
from app.db import get_session
from app.models import Competitor, Reel
from app.schemas import ReelDetail, ReelListItem, ReelUpdateRequest
from app.services.serializers import reel_to_detail, reel_to_list_item

router = APIRouter(prefix="/reels", tags=["reels"])

SECTION_LIMITS = {
    "hook": 200,
    "script": 2000,
    "cta": 500,
}
SEED_USERNAME = "vibecoding_creator"
PER_CREATOR_HOME = 4


def require_editor(request: Request) -> None:
    settings = get_settings()
    if not settings.editor_ip:
        return
    forwarded = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else ""
    )
    client_ip = client_ip.replace("::ffff:", "")
    if client_ip != settings.editor_ip:
        raise HTTPException(status_code=403, detail="Editing is not allowed from this IP address")


@router.get("", response_model=list[ReelListItem])
def list_reels(
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[ReelListItem]:
    """Home feed: most-viewed reels, capped per creator so one mega-account can't fill the grid."""
    # Window function keeps the top N by views for each competitor, then we merge by views.
    rows = session.execute(
        text(
            """
            WITH ranked AS (
                SELECT
                    r.id AS id,
                    r.views_count AS views_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY r.competitor_id
                        ORDER BY r.views_count DESC, r.posted_at DESC NULLS LAST
                    ) AS rn
                FROM reels r
                JOIN competitors c ON c.id = r.competitor_id
                WHERE c.username <> :seed_username
            )
            SELECT id
            FROM ranked
            WHERE rn <= :per_creator
            ORDER BY views_count DESC
            LIMIT :limit
            """
        ),
        {
            "seed_username": SEED_USERNAME,
            "per_creator": PER_CREATOR_HOME,
            "limit": limit,
        },
    ).all()

    ordered_ids = [row[0] for row in rows]
    if not ordered_ids:
        # Fallback for empty DB / only seed data.
        statement = (
            select(Reel, Competitor)
            .where(Reel.competitor_id == Competitor.id)
            .order_by(col(Reel.views_count).desc())
            .limit(limit)
        )
        fallback = session.exec(statement).all()
        items = [reel_to_list_item(reel, competitor.username) for reel, competitor in fallback]
    else:
        by_id: dict[UUID, ReelListItem] = {}
        statement = (
            select(Reel, Competitor)
            .where(Reel.competitor_id == Competitor.id)
            .where(col(Reel.id).in_(ordered_ids))
        )
        for reel, competitor in session.exec(statement).all():
            by_id[reel.id] = reel_to_list_item(reel, competitor.username)
        items = [by_id[reel_id] for reel_id in ordered_ids if reel_id in by_id]

    query = (q or "").strip().lower()
    if not query:
        return items
    return [
        item
        for item in items
        if query in item.title.lower() or query in item.author.lower()
    ]


@router.get("/{reel_id}", response_model=ReelDetail)
def get_reel(reel_id: UUID, session: Session = Depends(get_session)) -> ReelDetail:
    reel = session.get(Reel, reel_id)
    if reel is None:
        raise HTTPException(status_code=404, detail="Reel not found")
    competitor = session.get(Competitor, reel.competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    return reel_to_detail(reel, competitor)


@router.patch("/{reel_id}", response_model=ReelDetail)
def update_reel(
    reel_id: UUID,
    payload: ReelUpdateRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> ReelDetail:
    require_editor(request)

    reel = session.get(Reel, reel_id)
    if reel is None:
        raise HTTPException(status_code=404, detail="Reel not found")

    value = payload.value.strip()
    limit = SECTION_LIMITS[payload.section]
    if not value:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    if len(value) > limit:
        raise HTTPException(status_code=400, detail=f"Text exceeds the {limit} character limit")

    setattr(reel, payload.section, value)
    session.add(reel)
    session.commit()
    session.refresh(reel)

    competitor = session.get(Competitor, reel.competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    return reel_to_detail(reel, competitor)
