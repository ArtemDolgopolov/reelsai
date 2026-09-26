from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.db import get_session
from app.models import Competitor, CompetitorStatus, Reel, ReelStatus
from app.schemas import CompetitorLoadRequest, CompetitorLoadResponse, CompetitorRead, ReelListItem
from app.services.instagram_free import (
    FreeReelPayload,
    InstagramFreeClient,
    InstagramFreeError,
    looks_like_real_transcript,
)
from app.services.seed import ensure_seed_data
from app.services.serializers import competitor_to_read, reel_to_list_item

router = APIRouter(prefix="/competitors", tags=["competitors"])
CACHE_TTL = timedelta(hours=6)


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
            .order_by(col(Reel.posted_at).desc().nulls_last())
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
    reel.video_url = item.video_url
    reel.duration_seconds = item.duration_seconds or reel.duration_seconds
    reel.views_count = item.views_count or reel.views_count
    reel.likes_count = item.likes_count or reel.likes_count
    reel.comments_count = item.comments_count or reel.comments_count
    reel.shares_count = item.shares_count
    reel.overlay_text = item.overlay_text
    reel.posted_at = item.posted_at or reel.posted_at
    reel.status = ReelStatus.ready

    spoken = (item.transcript or "").strip()
    caption = (item.caption or item.title or "").strip()
    if spoken:
        if not reel.hook or not looks_like_real_transcript(reel.hook):
            reel.hook = spoken[:200]
        if not reel.script or not looks_like_real_transcript(reel.script):
            reel.script = spoken
    else:
        if not reel.hook:
            reel.hook = caption[:200]
        if not reel.script:
            reel.script = caption
    if not reel.cta:
        reel.cta = "Сохрани и попробуй этот формат в своём следующем рилсе."
    session.add(reel)
    return reel


@router.get("", response_model=list[CompetitorRead])
def list_competitors(session: Session = Depends(get_session)) -> list[CompetitorRead]:
    competitors = session.exec(select(Competitor).order_by(col(Competitor.updated_at).desc())).all()
    return [competitor_to_read(item) for item in competitors]


@router.get("/{competitor_id}", response_model=CompetitorRead)
def get_competitor(competitor_id: UUID, session: Session = Depends(get_session)) -> CompetitorRead:
    competitor = session.get(Competitor, competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    return competitor_to_read(competitor)


@router.get("/{competitor_id}/reels", response_model=list[ReelListItem])
def list_competitor_reels(
    competitor_id: UUID,
    session: Session = Depends(get_session),
) -> list[ReelListItem]:
    competitor = session.get(Competitor, competitor_id)
    if competitor is None:
        raise HTTPException(status_code=404, detail="Competitor not found")

    reels = get_latest_reels(session, competitor_id)
    return [reel_to_list_item(reel, competitor.username) for reel in reels]


@router.post("/load", response_model=CompetitorLoadResponse)
async def load_competitor(
    payload: CompetitorLoadRequest,
    session: Session = Depends(get_session),
) -> CompetitorLoadResponse:
    username = normalize_username(payload.username)
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")

    client = InstagramFreeClient()
    existing_competitor = session.exec(
        select(Competitor).where(Competitor.username == username)
    ).first()
    existing_reels = get_latest_reels(session, existing_competitor.id) if existing_competitor else []

    if (
        existing_competitor is not None
        and existing_competitor.last_scraped_at is not None
        and not payload.force_refresh
        and datetime.now(timezone.utc) - existing_competitor.last_scraped_at < CACHE_TTL
        and existing_reels
        and all(looks_like_real_transcript(reel.transcript) for reel in existing_reels)
    ):
        return CompetitorLoadResponse(
            competitor=competitor_to_read(existing_competitor),
            reels=[reel_to_list_item(reel, existing_competitor.username) for reel in existing_reels],
            source="cache",
            message="Загружено из PostgreSQL-кэша без новых запросов к Instagram",
        )

    # Prefer refreshing transcripts for already-known reel URLs (no Apify, free tools).
    if existing_competitor and existing_reels and (
        payload.force_refresh
        or any(not looks_like_real_transcript(reel.transcript) for reel in existing_reels)
    ):
        try:
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
                for reel in existing_reels
                if reel.instagram_url or reel.external_id
            ]
            refreshed = client.refresh_transcripts(items, only_missing=not payload.force_refresh)
            for item in refreshed:
                apply_reel_payload(session, existing_competitor, item)
            existing_competitor.status = CompetitorStatus.ready
            existing_competitor.last_error = None
            existing_competitor.last_scraped_at = datetime.now(timezone.utc)
            session.add(existing_competitor)
            session.commit()
            reels = get_latest_reels(session, existing_competitor.id)
            return CompetitorLoadResponse(
                competitor=competitor_to_read(existing_competitor),
                reels=[reel_to_list_item(reel, existing_competitor.username) for reel in reels],
                source="free",
                message="Расшифровка речи через yt-dlp + бесплатный Speech-to-Text (без Apify)",
            )
        except InstagramFreeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Free ingest failed: {exc}") from exc

    try:
        data = client.fetch_competitor(username, limit=20, transcribe=True)
    except InstagramFreeError as exc:
        # Keep demo seed as last resort for empty DB only.
        if existing_competitor is None and not existing_reels:
            competitor = ensure_seed_data(session)
            competitor.status = CompetitorStatus.ready
            session.add(competitor)
            session.commit()
            session.refresh(competitor)
            reels = session.exec(
                select(Reel)
                .where(Reel.competitor_id == competitor.id)
                .order_by(col(Reel.views_count).desc())
            ).all()
            return CompetitorLoadResponse(
                competitor=competitor_to_read(competitor),
                reels=[reel_to_list_item(reel, competitor.username) for reel in reels],
                source="seed",
                message=f"Бесплатный парсер Instagram недоступен ({exc}). Показаны демо-данные.",
            )
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Free ingest failed: {exc}") from exc

    competitor = existing_competitor or Competitor(username=username)
    competitor.username = username
    competitor.full_name = data.full_name or competitor.full_name
    competitor.bio = data.bio or competitor.bio
    competitor.avatar_url = data.avatar_url or competitor.avatar_url
    competitor.posts_count = data.posts_count or competitor.posts_count
    competitor.followers_count = data.followers_count or competitor.followers_count
    competitor.following_count = data.following_count or competitor.following_count
    competitor.status = CompetitorStatus.ready
    competitor.last_error = None
    competitor.apify_run_id = None
    competitor.last_scraped_at = datetime.now(timezone.utc)
    session.add(competitor)
    session.commit()
    session.refresh(competitor)

    for item in data.reels:
        apply_reel_payload(session, competitor, item)
    session.commit()

    reels = get_latest_reels(session, competitor.id)
    return CompetitorLoadResponse(
        competitor=competitor_to_read(competitor),
        reels=[reel_to_list_item(reel, competitor.username) for reel in reels],
        source="free",
        message="Загружено бесплатно: Instagram web + yt-dlp + Speech-to-Text",
    )
