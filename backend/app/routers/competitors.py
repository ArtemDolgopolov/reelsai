from datetime import datetime, timedelta, timezone
import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, col, select

from app.db import engine, get_session
from app.deps import get_current_user
from app.models import (
    Competitor,
    CompetitorStatus,
    ContentPlanItem,
    Reel,
    ReelStatus,
    User,
)
from app.schemas import CompetitorLoadRequest, CompetitorLoadResponse, CompetitorRead, ReelListItem
from app.services.instagram_free import (
    FreeReelPayload,
    InstagramFreeClient,
    InstagramFreeError,
    looks_like_real_transcript,
)
from app.services.serializers import competitor_to_read, reel_to_list_item
from app.services import tenancy
from app.services.transcript_sections import DEFAULT_CTA, split_transcript_into_sections

router = APIRouter(
    prefix="/competitors",
    tags=["competitors"],
    dependencies=[Depends(get_current_user)],
)
CACHE_TTL = timedelta(hours=6)
logger = logging.getLogger(__name__)


def normalize_username(raw: str) -> str:
    value = raw.strip()
    if "instagram.com/" in value:
        value = value.rstrip("/").split("instagram.com/")[-1]
        value = value.split("?")[0].split("/")[0]
    return value.lstrip("@").lower()


def get_latest_reels(session: Session, competitor_id: UUID) -> list[Reel]:
    return list(
        session.exec(
            select(Reel)
            .where(Reel.competitor_id == competitor_id)
            .order_by(col(Reel.views_count).desc(), col(Reel.posted_at).desc().nulls_last())
            .limit(20)
        ).all()
    )


def apply_reel_payload(session: Session, competitor: Competitor, item: FreeReelPayload) -> Reel:
    existing = None
    if item.external_id:
        existing = session.exec(select(Reel).where(Reel.external_id == item.external_id)).first()
    reel = existing or Reel(competitor_id=competitor.id, external_id=item.external_id)
    reel.competitor_id = competitor.id
    reel.title = item.title
    reel.caption = item.caption
    if item.transcript:
        reel.transcript = item.transcript
    reel.instagram_url = item.instagram_url or reel.instagram_url
    reel.thumbnail_url = item.thumbnail_url or reel.thumbnail_url
    # Keep a usable media URL for background STT when Instagram later rate-limits yt-dlp.
    if item.video_url:
        reel.video_url = item.video_url
    reel.duration_seconds = item.duration_seconds or reel.duration_seconds
    reel.views_count = item.views_count or reel.views_count
    reel.likes_count = item.likes_count or reel.likes_count
    reel.comments_count = item.comments_count or reel.comments_count
    reel.shares_count = item.shares_count
    reel.overlay_text = item.overlay_text
    reel.posted_at = item.posted_at or reel.posted_at
    reel.status = ReelStatus.ready

    spoken = (item.transcript or reel.transcript or "").strip()
    caption = (item.caption or reel.caption or item.title or reel.title or "").strip()
    if spoken and looks_like_real_transcript(spoken):
        hook, script, cta = split_transcript_into_sections(spoken, caption)
        reel.hook = hook
        reel.script = script
        reel.cta = cta
    elif not looks_like_real_transcript(reel.transcript):
        # Do not invent Hook/Script from Instagram captions/subtitles —
        # analysis must come from spoken audio once STT finishes.
        if not reel.hook:
            reel.hook = ""
        if not reel.script:
            reel.script = ""
        if not reel.cta:
            reel.cta = DEFAULT_CTA
    session.add(reel)
    return reel


def _background_transcribe(competitor_id: UUID, force: bool = False) -> None:
    """Fill missing spoken transcripts without blocking the load API."""
    client = InstagramFreeClient()
    with Session(engine) as session:
        competitor = session.get(Competitor, competitor_id)
        if competitor is None:
            return
        # Most-viewed first so remix-ready speech lands on the best reels.
        reels = list(
            session.exec(
                select(Reel)
                .where(Reel.competitor_id == competitor_id)
                .order_by(col(Reel.views_count).desc())
                .limit(20)
            ).all()
        )
        if force:
            for reel in reels:
                reel.transcript = None
                reel.hook = ""
                reel.script = ""
                session.add(reel)
            session.commit()

        missing = [
            reel
            for reel in reels
            if not looks_like_real_transcript(reel.transcript)
            and (reel.video_url or reel.instagram_url or reel.external_id)
        ]
        if not missing:
            return

        items = [
            (
                reel.instagram_url or f"https://www.instagram.com/reel/{reel.external_id}/",
                FreeReelPayload(
                    external_id=reel.external_id or "",
                    title=reel.title,
                    caption=reel.caption,
                    transcript=reel.transcript,
                    instagram_url=reel.instagram_url,
                    thumbnail_url=reel.thumbnail_url,
                    video_url=reel.video_url,
                    duration_seconds=reel.duration_seconds,
                    views_count=reel.views_count,
                    likes_count=reel.likes_count,
                    comments_count=reel.comments_count,
                    shares_count=reel.shares_count,
                    overlay_text=reel.overlay_text,
                    posted_at=reel.posted_at,
                ),
            )
            for reel in missing
        ]
        try:
            # Commit per reel so one failure doesn't wipe progress for the account.
            for url, payload in items[:12]:
                try:
                    refreshed = client.refresh_transcripts(
                        [(url, payload)],
                        only_missing=True,
                        max_items=1,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("STT failed for %s/%s: %s", competitor.username, url, exc)
                    continue
                for item in refreshed:
                    apply_reel_payload(session, competitor, item)
                    session.commit()
            competitor.last_error = None
            session.add(competitor)
            session.commit()
        except Exception as exc:  # noqa: BLE001
            competitor.last_error = f"Transcript background job: {exc}"
            session.add(competitor)
            session.commit()

def backfill_missing_transcripts() -> None:
    """Refresh CDN media URLs, then STT across every competitor with missing speech."""
    client = InstagramFreeClient()
    with Session(engine) as session:
        competitors = list(session.exec(select(Competitor)).all())

    for competitor in competitors:
        if competitor.username == "vibecoding_creator":
            continue
        # Refresh feed metadata so video_url CDN links are fresh before STT.
        try:
            data = client.fetch_competitor_metadata(competitor.username, limit=20)
            with Session(engine) as session:
                row = session.get(Competitor, competitor.id)
                if row is None:
                    continue
                for item in data.reels:
                    apply_reel_payload(session, row, item)
                session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Metadata refresh before STT failed for @%s: %s", competitor.username, exc)
        _background_transcribe(competitor.id)


@router.get("", response_model=list[CompetitorRead])
def list_competitors(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[CompetitorRead]:
    competitors = tenancy.list_tracked_competitors(session, user.id)
    return [
        competitor_to_read(item, reels_count=len(get_latest_reels(session, item.id)))
        for item in competitors
    ]


@router.get("/{competitor_id}", response_model=CompetitorRead)
def get_competitor(
    competitor_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CompetitorRead:
    competitor = session.get(Competitor, competitor_id)
    if competitor is None or not tenancy.user_tracks_competitor(session, user.id, competitor_id):
        raise HTTPException(status_code=404, detail="Competitor not found")
    return competitor_to_read(
        competitor,
        reels_count=len(get_latest_reels(session, competitor_id)),
    )


@router.get("/{competitor_id}/reels", response_model=list[ReelListItem])
def list_competitor_reels(
    competitor_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ReelListItem]:
    competitor = session.get(Competitor, competitor_id)
    if competitor is None or not tenancy.user_tracks_competitor(session, user.id, competitor_id):
        raise HTTPException(status_code=404, detail="Competitor not found")

    reels = get_latest_reels(session, competitor_id)
    plan_rows = (
        session.exec(
            select(ContentPlanItem).where(
                ContentPlanItem.user_id == user.id,
                col(ContentPlanItem.reel_id).in_([reel.id for reel in reels]),
            )
        ).all()
        if reels
        else []
    )
    plans = {item.reel_id: item for item in plan_rows}
    return [
        reel_to_list_item(reel, competitor.username, plan_item=plans.get(reel.id))
        for reel in reels
    ]


@router.delete("/{competitor_id}")
def delete_competitor(
    competitor_id: UUID,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Remove competitor from this user's list (shared scrape cache stays)."""
    if not tenancy.untrack_competitor(session, user.id, competitor_id):
        raise HTTPException(status_code=404, detail="Competitor not found")
    return {"status": "ok"}


@router.post("/load", response_model=CompetitorLoadResponse)
async def load_competitor(
    payload: CompetitorLoadRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> CompetitorLoadResponse:
    username = normalize_username(payload.username)
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    client = InstagramFreeClient()
    existing_competitor = session.exec(
        select(Competitor).where(Competitor.username == username)
    ).first()
    existing_reels = get_latest_reels(session, existing_competitor.id) if existing_competitor else []

    # Soft cache: return instantly whenever we already have reels for this handle.
    if (
        existing_competitor is not None
        and existing_reels
        and existing_competitor.last_scraped_at is not None
        and not payload.force_refresh
        and datetime.now(timezone.utc) - existing_competitor.last_scraped_at < CACHE_TTL
    ):
        tenancy.ensure_user_tracks_competitor(session, user, existing_competitor)
        existing_competitor.posts_count = len(existing_reels)
        session.add(existing_competitor)
        session.commit()
        session.refresh(existing_competitor)
        needs_speech = any(not looks_like_real_transcript(reel.transcript) for reel in existing_reels)
        if needs_speech:
            background_tasks.add_task(_background_transcribe, existing_competitor.id)
        return CompetitorLoadResponse(
            competitor=competitor_to_read(existing_competitor, reels_count=len(existing_reels)),
            reels=[reel_to_list_item(reel, existing_competitor.username) for reel in existing_reels],
            source="cache",
            message=(
                "Мгновенно из кэша. Расшифровка речи догружается в фоне."
                if needs_speech
                else "Загружено из кэша"
            ),
        )

    try:
        data = client.fetch_competitor_metadata(username, limit=20)
    except InstagramFreeError as exc:
        # Never substitute another creator / seed demo for the requested handle.
        if existing_competitor is not None and existing_reels:
            tenancy.ensure_user_tracks_competitor(session, user, existing_competitor)
            existing_competitor.posts_count = len(existing_reels)
            session.add(existing_competitor)
            session.commit()
            session.refresh(existing_competitor)
            return CompetitorLoadResponse(
                competitor=competitor_to_read(existing_competitor, reels_count=len(existing_reels)),
                reels=[
                    reel_to_list_item(reel, existing_competitor.username) for reel in existing_reels
                ],
                source="cache",
                message=f"Instagram временно недоступен ({exc}). Показаны сохранённые рилсы.",
            )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Не удалось загрузить конкурента: {exc}") from exc

    competitor = existing_competitor or Competitor(username=username)
    competitor.username = username
    competitor.full_name = data.full_name or competitor.full_name
    competitor.bio = data.bio or competitor.bio
    competitor.avatar_url = data.avatar_url or competitor.avatar_url
    competitor.posts_count = data.posts_count or competitor.posts_count
    competitor.followers_count = data.followers_count or competitor.followers_count
    competitor.following_count = data.following_count or competitor.following_count
    competitor.status = CompetitorStatus.ready
    competitor.tracked = True
    competitor.last_error = None
    competitor.apify_run_id = None
    competitor.last_scraped_at = datetime.now(timezone.utc)
    session.add(competitor)
    session.commit()
    session.refresh(competitor)
    tenancy.ensure_user_tracks_competitor(session, user, competitor)

    for item in data.reels:
        apply_reel_payload(session, competitor, item)
    session.commit()

    reels = get_latest_reels(session, competitor.id)
    competitor.posts_count = len(reels)
    session.add(competitor)
    session.commit()
    session.refresh(competitor)

    background_tasks.add_task(_background_transcribe, competitor.id, payload.force_refresh)

    return CompetitorLoadResponse(
        competitor=competitor_to_read(competitor, reels_count=len(reels)),
        reels=[reel_to_list_item(reel, competitor.username) for reel in reels],
        source="free",
        message=(
            "Рилсы загружены. Речь распознаётся автоматически на любом языке — обновите карточку через минуту."
            if not payload.force_refresh
            else "Принудительное обновление: речь перераспознаётся с автоопределением языка."
        ),
    )
