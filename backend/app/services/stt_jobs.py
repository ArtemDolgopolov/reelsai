"""Background and on-demand speech transcription for reels."""

from __future__ import annotations

import logging
import threading
from uuid import UUID

from sqlmodel import Session

from app.db import engine
from app.models import Competitor, Reel
from app.services.instagram_free import (
    FreeReelPayload,
    InstagramFreeClient,
    enrich_reel_from_url,
    looks_like_real_transcript,
)

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_events: dict[str, threading.Event] = {}


def _payload_from_reel(reel: Reel) -> FreeReelPayload:
    return FreeReelPayload(
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
    )


def _refresh_video_url(client: InstagramFreeClient, reel: Reel, username: str | None) -> str | None:
    """CDN links expire — pull a fresh media URL from the creator feed when possible."""
    if not username or not reel.external_id:
        return reel.video_url
    try:
        fresh_items = client.fetch_account_reels_light(username, limit=16)
    except Exception as exc:  # noqa: BLE001
        logger.info("Fresh media lookup failed for @%s: %s", username, exc)
        return reel.video_url

    for item in fresh_items:
        if item.external_id == reel.external_id and item.video_url:
            return item.video_url
    return reel.video_url


def ensure_reel_transcript(session: Session, reel: Reel, competitor: Competitor | None = None) -> Reel:
    """Run STT for one reel if spoken text is missing. Prefer CDN audio over yt-dlp."""
    if looks_like_real_transcript(reel.transcript):
        return reel

    key = str(reel.id)
    owner = False
    with _lock:
        event = _events.get(key)
        if event is None:
            event = threading.Event()
            _events[key] = event
            owner = True

    if not owner:
        # Another worker is already transcribing this reel — wait for it.
        logger.info("Waiting for in-flight STT for %s", reel.external_id or key)
        event.wait(timeout=100)
        session.expire(reel)
        session.refresh(reel)
        if looks_like_real_transcript(reel.transcript):
            return reel
        # Previous worker failed — take ownership and try again.
        with _lock:
            event = _events.get(key)
            if event is None:
                event = threading.Event()
                _events[key] = event
                owner = True
            else:
                owner = False
        if not owner:
            event.wait(timeout=100)
            session.expire(reel)
            session.refresh(reel)
            return reel

    try:
        from app.routers.competitors import apply_reel_payload

        if competitor is None:
            competitor = session.get(Competitor, reel.competitor_id)
        if competitor is None:
            return reel

        client = InstagramFreeClient()
        video_url = _refresh_video_url(client, reel, competitor.username)
        payload = _payload_from_reel(reel)
        payload.video_url = video_url
        payload.author_username = competitor.username

        url = reel.instagram_url or (
            f"https://www.instagram.com/reel/{reel.external_id}/" if reel.external_id else ""
        )
        if not url and not video_url:
            logger.warning("No media URL for STT on reel %s", reel.external_id or reel.id)
            return reel

        updated = enrich_reel_from_url(url or "https://www.instagram.com/", transcribe=True, existing=payload)
        if not looks_like_real_transcript(updated.transcript):
            logger.warning("STT produced no speech for reel %s", reel.external_id or reel.id)
            return reel

        apply_reel_payload(session, competitor, updated)
        session.commit()
        session.refresh(reel)
        logger.info(
            "STT ready for %s (%s chars)",
            reel.external_id or reel.id,
            len(reel.transcript or ""),
        )
        return reel
    except Exception as exc:  # noqa: BLE001
        logger.warning("ensure_reel_transcript failed for %s: %s", reel.id, exc)
        try:
            session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return reel
    finally:
        event.set()
        with _lock:
            _events.pop(key, None)


def _transcribe_ids_worker(reel_ids: list[UUID]) -> None:
    for reel_id in reel_ids:
        try:
            with Session(engine) as session:
                reel = session.get(Reel, reel_id)
                if reel is None or looks_like_real_transcript(reel.transcript):
                    continue
                competitor = session.get(Competitor, reel.competitor_id)
                ensure_reel_transcript(session, reel, competitor)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Background STT failed for %s: %s", reel_id, exc)


def schedule_transcripts(reel_ids: list[UUID]) -> None:
    """Fire-and-forget STT for a batch of reel IDs (home discovery)."""
    pending = [reel_id for reel_id in reel_ids if reel_id]
    if not pending:
        return
    thread = threading.Thread(
        target=_transcribe_ids_worker,
        args=(pending,),
        name="home-stt",
        daemon=True,
    )
    thread.start()
    logger.info("Scheduled STT for %s home/discovery reels", len(pending))
