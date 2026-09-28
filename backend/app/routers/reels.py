from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlmodel import Session, col, select

from app.config import get_settings
from app.db import get_session
from app.models import Competitor, ContentPlanItem, Reel
from app.schemas import ReelDetail, ReelListItem, ReelUpdateRequest
from app.services.instagram_free import looks_like_real_transcript
from app.services.overview import prepare_russian_remix, schedule_analysis
from app.services.serializers import reel_to_detail, reel_to_list_item
from app.services.stt_jobs import ensure_reel_transcript, schedule_transcripts
from app.services.transcript_sections import DEFAULT_CTA
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


def _plan_map(session: Session, reel_ids: list[UUID]) -> dict[UUID, ContentPlanItem]:
    if not reel_ids:
        return {}
    rows = session.exec(
        select(ContentPlanItem).where(col(ContentPlanItem.reel_id).in_(reel_ids))
    ).all()
    return {item.reel_id: item for item in rows}


@router.get("", response_model=list[ReelListItem])
def list_reels(
    limit: int = Query(default=40, ge=1, le=100),
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[ReelListItem]:
    """Home feed: reels from saved (tracked) competitors only — no random discovery."""
    rows = session.exec(
        select(Reel, Competitor)
        .where(Reel.competitor_id == Competitor.id)
        .where(Competitor.tracked.is_(True))
        .order_by(col(Reel.views_count).desc(), col(Reel.posted_at).desc().nulls_last())
        .limit(limit)
    ).all()

    plans = _plan_map(session, [reel.id for reel, _ in rows])
    items = [
        reel_to_list_item(reel, competitor.username, plan_item=plans.get(reel.id))
        for reel, competitor in rows
    ]

    query = (q or "").strip().lower()
    if not query:
        return items
    return [
        item
        for item in items
        if query in item.title.lower() or query in item.author.lower()
    ]


@router.get("/{reel_id}", response_model=ReelDetail)
def get_reel(
    reel_id: UUID,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> ReelDetail:
    reel = session.get(Reel, reel_id)
    if reel is None:
        raise HTTPException(status_code=404, detail="Reel not found")
    competitor = session.get(Competitor, reel.competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")

    # Instant response — refine Hook/Script/CTA from speech in the background.
    if reel.transcript is None:
        background_tasks.add_task(schedule_transcripts, [reel.id])

    detail = reel_to_detail(reel, competitor, session=session)
    if detail.analysis_pending or detail.speech_pending:
        background_tasks.add_task(schedule_analysis, reel.id)
    return detail


@router.post("/{reel_id}/remix", response_model=ReelDetail)
def remix_reel(
    reel_id: UUID,
    session: Session = Depends(get_session),
) -> ReelDetail:
    """Build a Russian remix script from the original transcript for filming."""
    reel = session.get(Reel, reel_id)
    if reel is None:
        raise HTTPException(status_code=404, detail="Reel not found")
    competitor = session.get(Competitor, reel.competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")

    # Need spoken transcript (or empty marker) before adapting.
    if reel.transcript is None:
        ensure_reel_transcript(session, reel, competitor)
        session.refresh(reel)

    overview, hook, script, cta, originals, used_llm = prepare_russian_remix(reel, competitor)
    if not used_llm or not script:
        raise HTTPException(
            status_code=503,
            detail="Не удалось получить русский перевод. Попробуйте ещё раз через минуту.",
        )
    reel.hook = hook or reel.hook or ""
    reel.script = script
    reel.cta = cta or reel.cta or DEFAULT_CTA
    if overview:
        reel.analysis_overview = overview[:4000]
    session.add(reel)
    session.commit()
    session.refresh(reel)

    detail = reel_to_detail(reel, competitor, session=session)
    return detail.model_copy(
        update={
            "hook": hook,
            "script": script,
            "cta": cta,
            "original_hook": originals.get("hook") or None,
            "original_script": originals.get("script") or None,
            "original_cta": originals.get("cta") or None,
            "overview": overview or detail.overview,
            "analysis_pending": False,
        }
    )

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
    competitor = session.get(Competitor, reel.competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")

    limit = SECTION_LIMITS[payload.section]
    value = payload.value.strip()[:limit]
    if payload.section == "hook":
        reel.hook = value
    elif payload.section == "script":
        reel.script = value
    else:
        reel.cta = value
    session.add(reel)
    session.commit()
    session.refresh(reel)
    return reel_to_detail(reel, competitor, session=session)
