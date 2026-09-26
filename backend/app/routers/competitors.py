from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.config import get_settings
from app.db import get_session
from app.models import Competitor, CompetitorStatus, Reel, ReelStatus
from app.schemas import CompetitorLoadRequest, CompetitorLoadResponse, CompetitorRead, ReelListItem
from app.services.apify import ApifyClient, ApifyNotConfiguredError
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

    settings = get_settings()
    client = ApifyClient(settings)

    if client.configured:
        existing_competitor = session.exec(
            select(Competitor).where(Competitor.username == username)
        ).first()
        if (
            existing_competitor is not None
            and existing_competitor.last_scraped_at is not None
            and not payload.force_refresh
            and datetime.now(timezone.utc) - existing_competitor.last_scraped_at
            < CACHE_TTL
        ):
            cached_reels = get_latest_reels(session, existing_competitor.id)
            return CompetitorLoadResponse(
                competitor=competitor_to_read(existing_competitor),
                reels=[
                    reel_to_list_item(reel, existing_competitor.username)
                    for reel in cached_reels
                ],
                source="cache",
                message="Загружено из PostgreSQL-кэша без расхода Apify-кредитов",
            )

        try:
            data = await client.fetch_competitor(username, limit=20)
        except ApifyNotConfiguredError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Apify request failed: {exc}") from exc

        competitor = existing_competitor or session.exec(
            select(Competitor).where(Competitor.username == data.username.lower())
        ).first()
        if competitor is None:
            competitor = Competitor(username=data.username.lower())

        competitor.username = data.username.lower()
        competitor.full_name = data.full_name or competitor.full_name
        competitor.bio = data.bio or competitor.bio
        competitor.avatar_url = data.avatar_url or competitor.avatar_url
        competitor.posts_count = data.posts_count or competitor.posts_count
        competitor.followers_count = data.followers_count or competitor.followers_count
        competitor.following_count = data.following_count or competitor.following_count
        competitor.status = CompetitorStatus.ready
        competitor.last_error = None
        competitor.apify_run_id = data.run_id
        competitor.last_scraped_at = datetime.now(timezone.utc)
        session.add(competitor)
        session.commit()
        session.refresh(competitor)

        for item in data.reels:
            existing = None
            if item.external_id:
                existing = session.exec(
                    select(Reel).where(Reel.external_id == item.external_id)
                ).first()
            reel = existing or Reel(competitor_id=competitor.id, external_id=item.external_id)
            reel.competitor_id = competitor.id
            reel.title = item.title
            reel.caption = item.caption
            reel.transcript = item.transcript
            reel.instagram_url = item.instagram_url
            reel.thumbnail_url = item.thumbnail_url
            reel.video_url = item.video_url
            reel.duration_seconds = item.duration_seconds
            reel.views_count = item.views_count
            reel.likes_count = item.likes_count
            reel.comments_count = item.comments_count
            reel.shares_count = item.shares_count
            reel.overlay_text = item.overlay_text
            reel.posted_at = item.posted_at
            reel.status = ReelStatus.ready
            if not reel.hook:
                reel.hook = (item.caption or item.title or "")[:200]
            if not reel.script:
                reel.script = item.caption or item.title or ""
            if not reel.cta:
                reel.cta = "Сохрани и попробуй этот формат в своём следующем рилсе."
            session.add(reel)

        session.commit()
        reels = get_latest_reels(session, competitor.id)
        return CompetitorLoadResponse(
            competitor=competitor_to_read(competitor),
            reels=[reel_to_list_item(reel, competitor.username) for reel in reels],
            source="apify",
            message="Успешно загружено через Apify",
        )

    # Until APIFY_TOKEN is provided, keep the demo flow working with seeded data.
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
        message="Apify ещё не подключён — показаны демо-данные. Добавьте APIFY_TOKEN для live-парсинга.",
    )
