from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlmodel import Session, col, select

from app.config import get_settings
from app.db import get_session
from app.deps import get_current_user
from app.models import Competitor, ContentPlanItem, Reel, User, UserCompetitorTrack
from app.schemas import ReelDetail, ReelListItem, ReelUpdateRequest
from app.services.instagram_free import looks_like_real_transcript
from app.services.overview import prepare_russian_remix, schedule_analysis
from app.services.groq_llm import last_groq_failure
from app.services.serializers import reel_to_detail, reel_to_list_item
from app.services.stt_jobs import ensure_reel_transcript, schedule_transcripts
from app.services import tenancy
from app.services.transcript_sections import DEFAULT_CTA

router = APIRouter(
    prefix="/reels",
    tags=["reels"],
    dependencies=[Depends(get_current_user)],
)

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


def _plan_map(
    session: Session,
    user_id: UUID,
    reel_ids: list[UUID],
) -> dict[UUID, ContentPlanItem]:
    if not reel_ids:
        return {}
    rows = session.exec(
        select(ContentPlanItem).where(
            ContentPlanItem.user_id == user_id,
            col(ContentPlanItem.reel_id).in_(reel_ids),
        )
    ).all()
    return {item.reel_id: item for item in rows}


def _require_tracked_reel(
    session: Session,
    user: User,
    reel_id: UUID,
) -> tuple[Reel, Competitor]:
    reel = session.get(Reel, reel_id)
    if reel is None:
        raise HTTPException(status_code=404, detail="Reel not found")
    competitor = session.get(Competitor, reel.competitor_id)
    if competitor is None or not tenancy.user_tracks_competitor(
        session, user.id, competitor.id
    ):
        raise HTTPException(status_code=404, detail="Reel not found")
    return reel, competitor


@router.get("", response_model=list[ReelListItem])
def list_reels(
    limit: int = Query(default=40, ge=1, le=100),
    q: str | None = Query(default=None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ReelListItem]:
    """Home feed: reels from this user's saved competitors only."""
    rows = session.exec(
        select(Reel, Competitor)
        .join(
            UserCompetitorTrack,
            col(UserCompetitorTrack.competitor_id) == Competitor.id,
        )
        .where(Reel.competitor_id == Competitor.id)
        .where(UserCompetitorTrack.user_id == user.id)
        .order_by(col(Reel.views_count).desc(), col(Reel.posted_at).desc().nulls_last())
        .limit(limit)
    ).all()

    plans = _plan_map(session, user.id, [reel.id for reel, _ in rows])
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
    user: User = Depends(get_current_user),
) -> ReelDetail:
    reel, competitor = _require_tracked_reel(session, user, reel_id)

    # Instant response — refine Hook/Script/CTA from speech in the background.
    if reel.transcript is None:
        background_tasks.add_task(schedule_transcripts, [reel.id])

    detail = reel_to_detail(reel, competitor, session=session)
    if detail.analysis_pending or detail.speech_pending:
        background_tasks.add_task(schedule_analysis, reel.id)
    return detail


@router.post("/{reel_id}/refresh-video", response_model=ReelDetail)
def refresh_reel_video(
    reel_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ReelDetail:
    """Refresh expired Instagram CDN video_url for in-app playback."""
    from app.services.instagram_free import InstagramFreeClient
    from app.services.stt_jobs import _refresh_video_url

    reel, competitor = _require_tracked_reel(session, user, reel_id)

    client = InstagramFreeClient()
    fresh = _refresh_video_url(client, reel, competitor.username)
    if fresh and fresh != reel.video_url:
        reel.video_url = fresh
        session.add(reel)
        session.commit()
        session.refresh(reel)
    if not reel.video_url:
        raise HTTPException(status_code=404, detail="Video URL is not available for this reel")
    return reel_to_detail(reel, competitor, session=session)


@router.post("/{reel_id}/remix", response_model=ReelDetail)
def remix_reel(
    reel_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ReelDetail:
    """Build a Russian remix script from the original transcript for filming."""
    reel, competitor = _require_tracked_reel(session, user, reel_id)

    # Need spoken transcript (or empty marker) before adapting.
    if reel.transcript is None:
        ensure_reel_transcript(session, reel, competitor)
        session.refresh(reel)

    overview, hook, script, cta, originals, used_llm = prepare_russian_remix(reel, competitor)
    if not used_llm or not script:
        fail = last_groq_failure()
        reason = fail.get("reason") or ""
        if reason == "rate_limited":
            detail = (
                "Лимит бесплатного Groq исчерпан (слишком много запросов/токенов сегодня). "
                "Подождите 1–2 минуты — или до завтра, если кончился дневной лимит — и нажмите Remix снова."
            )
        elif reason == "no_api_key":
            detail = "На сервере не задан GROQ_API_KEY — перевод недоступен."
        else:
            detail = (
                "Не удалось получить русский перевод. "
                "Чаще всего это лимит Groq или временный сбой — попробуйте через минуту."
            )
        raise HTTPException(status_code=503, detail=detail)
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
    user: User = Depends(get_current_user),
) -> ReelDetail:
    require_editor(request)
    reel, competitor = _require_tracked_reel(session, user, reel_id)

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
