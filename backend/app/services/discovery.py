"""Home feed discovery: absolute-random public Instagram reels."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import Session, col, select

from app.models import Competitor, CompetitorStatus, Reel
from app.schemas import ReelListItem
from app.services.instagram_free import FreeReelPayload, InstagramFreeClient
from app.services.serializers import reel_to_list_item

logger = logging.getLogger(__name__)

# Soft cache so refreshing home every second does not hammer Instagram.
_CACHE_TTL_SECONDS = 90
_cache_items: list[ReelListItem] = []
_cache_at: float = 0.0


def _upsert_discovery_competitor(session: Session, item: FreeReelPayload) -> Competitor | None:
    username = (item.author_username or "").lstrip("@").lower()
    if not username:
        return None

    competitor = session.exec(select(Competitor).where(Competitor.username == username)).first()
    if competitor is None:
        competitor = Competitor(username=username)

    if item.author_full_name:
        competitor.full_name = item.author_full_name
    if item.author_avatar_url:
        competitor.avatar_url = item.author_avatar_url
    competitor.status = CompetitorStatus.ready
    competitor.last_scraped_at = datetime.now(timezone.utc)
    if not competitor.bio:
        competitor.bio = "Автозагрузка для случайной ленты Instagram"
    session.add(competitor)
    session.flush()
    return competitor


def persist_discovery_reels(session: Session, payloads: list[FreeReelPayload]) -> list[UUID]:
    """Save discovered reels and return their IDs in payload order."""
    from app.routers.competitors import apply_reel_payload

    ordered_ids: list[UUID] = []
    for item in payloads:
        competitor = _upsert_discovery_competitor(session, item)
        if competitor is None:
            continue
        reel = apply_reel_payload(session, competitor, item)
        session.flush()
        ordered_ids.append(reel.id)
    session.commit()
    # Do not mass-queue STT here — it starves Groq while the open reel needs analysis.
    # Speech is transcribed on reel open / competitor load instead.
    return ordered_ids


def items_from_ids(session: Session, ordered_ids: list[UUID]) -> list[ReelListItem]:
    if not ordered_ids:
        return []
    by_id: dict[UUID, ReelListItem] = {}
    rows = session.exec(
        select(Reel, Competitor)
        .where(Reel.competitor_id == Competitor.id)
        .where(col(Reel.id).in_(ordered_ids))
    ).all()
    for reel, competitor in rows:
        by_id[reel.id] = reel_to_list_item(reel, competitor.username)
    return [by_id[reel_id] for reel_id in ordered_ids if reel_id in by_id]


def fetch_home_discover_reels(session: Session, limit: int = 20) -> list[ReelListItem]:
    """Live Instagram random mix, with a short in-process cache and DB fallback."""
    global _cache_items, _cache_at

    now = time.monotonic()
    if _cache_items and (now - _cache_at) < _CACHE_TTL_SECONDS:
        return _cache_items[:limit]

    client = InstagramFreeClient()
    try:
        payloads = client.fetch_discover_reels(limit=max(limit, 20))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Live Instagram discovery failed: %s", exc)
        payloads = []

    if payloads:
        try:
            ordered_ids = persist_discovery_reels(session, payloads)
            items = items_from_ids(session, ordered_ids)[:limit]
            if items:
                _cache_items = items
                _cache_at = now
                return items
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to persist discovery reels: %s", exc)

    # Fallback: random from anything already in DB (including prior discovery).
    from sqlalchemy import text

    rows = session.execute(
        text(
            """
            SELECT r.id
            FROM reels r
            JOIN competitors c ON c.id = r.competitor_id
            WHERE c.username <> 'vibecoding_creator'
            ORDER BY RANDOM()
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).all()
    items = items_from_ids(session, [row[0] for row in rows])
    if items:
        _cache_items = items
        _cache_at = now
    return items
