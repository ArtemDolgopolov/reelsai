from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session

from app.config import get_settings
from app.db import get_session
from app.models import Competitor, Reel
from app.schemas import ReelDetail, ReelListItem, ReelUpdateRequest
from app.services.discovery import fetch_home_discover_reels
from app.services.instagram_free import looks_like_real_transcript
from app.services.serializers import reel_to_detail
from app.services.stt_jobs import ensure_reel_transcript

router = APIRouter(prefix="/reels", tags=["reels"])

SECTION_LIMITS = {
    "hook": 200,
    "script": 2000,
    "cta": 500,
}


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
    """Home feed: absolute-random public Instagram reels (live discovery)."""
    items = fetch_home_discover_reels(session, limit=limit)

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

    # On open: finish speech recognition before returning Hook/Script/CTA.
    if not looks_like_real_transcript(reel.transcript):
        reel = ensure_reel_transcript(session, reel, competitor)
        session.refresh(reel)

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
