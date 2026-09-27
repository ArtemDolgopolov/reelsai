import re
from datetime import datetime

from app.models import Competitor, Reel
from app.schemas import CompetitorRead, ReelDetail, ReelListItem
from app.services.instagram_free import looks_like_real_transcript
from app.services.overview import build_reel_overview
from app.services.transcript_sections import DEFAULT_CTA, continuous_text, split_transcript_into_sections


def format_duration(seconds: int) -> str:
    minutes, sec = divmod(max(seconds, 0), 60)
    return f"{minutes}:{sec:02d}"


def format_views(count: int) -> str:
    if count >= 1_000_000:
        value = count / 1_000_000
        return f"{value:.1f}".rstrip("0").rstrip(".") + "M"
    if count >= 1_000:
        value = count / 1_000
        return f"{value:.1f}".rstrip("0").rstrip(".") + "K"
    return str(count)


def competitor_to_read(competitor: Competitor) -> CompetitorRead:
    return CompetitorRead.model_validate(competitor, from_attributes=True)


def _needs_restructure(spoken: str, script: str | None, cta: str | None) -> bool:
    stored_script = continuous_text(script)
    stored_cta = continuous_text(cta)
    if not stored_script or stored_script == continuous_text(spoken):
        return True
    if "\n" in (script or "") or re.search(r"(?m)^\d{1,2}[.)]\s+", script or ""):
        return True
    if len(stored_script) > len(spoken) * 0.98:
        return True
    # CTA should be a short action ask — story fragments need a fresh split.
    if stored_cta and len(stored_cta.split()) > 22 and not any(
        hint in stored_cta.lower()
        for hint in (
            "подпис",
            "сохран",
            "коммент",
            "напиш",
            "ссылк",
            "follow",
            "subscribe",
            "comment",
            "save",
            "dm me",
            "link",
            "попробуй",
        )
    ):
        return True
    return False


def analysis_sections(reel: Reel) -> tuple[str, str, str]:
    """Hook / Script / CTA: prefer spoken audio, otherwise caption-based drafts."""
    spoken = continuous_text(reel.transcript)
    caption = continuous_text(reel.caption or reel.title)

    if looks_like_real_transcript(spoken):
        if _needs_restructure(spoken, reel.script, reel.cta):
            return split_transcript_into_sections(spoken, caption)
        return (
            continuous_text(reel.hook)[:200],
            continuous_text(reel.script)[:2000],
            continuous_text(reel.cta)[:500] or split_transcript_into_sections(spoken, caption)[2],
        )

    stored_hook = continuous_text(reel.hook)
    stored_script = continuous_text(reel.script)
    stored_cta = continuous_text(reel.cta)
    if stored_hook and stored_script:
        return stored_hook[:200], stored_script[:2000], stored_cta[:500] or DEFAULT_CTA

    return split_transcript_into_sections(None, caption)


def reel_to_list_item(reel: Reel, username: str) -> ReelListItem:
    transcript = (reel.transcript or "").strip()
    return ReelListItem(
        id=reel.id,
        competitor_id=reel.competitor_id,
        title=reel.title,
        author=f"@{username}",
        duration=format_duration(reel.duration_seconds),
        thumbnail_url=reel.thumbnail_url,
        instagram_url=reel.instagram_url,
        overlay_text=reel.overlay_text,
        views_count=reel.views_count,
        likes_count=reel.likes_count,
        comments_count=reel.comments_count,
        has_transcript=looks_like_real_transcript(transcript),
        status=reel.status,
    )


def reel_to_detail(reel: Reel, competitor: Competitor) -> ReelDetail:
    hook, script, cta = analysis_sections(reel)
    duration = format_duration(reel.duration_seconds)
    views_label = format_views(reel.views_count)
    spoken = (reel.transcript or "").strip()
    return ReelDetail(
        id=reel.id,
        competitor_id=reel.competitor_id,
        title=reel.title,
        caption=reel.caption,
        author=f"@{competitor.username}",
        author_name=competitor.full_name,
        avatar_url=competitor.avatar_url,
        duration=duration,
        duration_seconds=reel.duration_seconds,
        views_count=reel.views_count,
        likes_count=reel.likes_count,
        comments_count=reel.comments_count,
        shares_count=reel.shares_count,
        instagram_url=reel.instagram_url,
        thumbnail_url=reel.thumbnail_url,
        video_url=reel.video_url,
        overlay_text=reel.overlay_text,
        overview=build_reel_overview(
            reel,
            competitor,
            views_label=views_label,
            duration_label=duration,
        ),
        hook=hook,
        script=script,
        cta=cta or DEFAULT_CTA,
        transcript=reel.transcript,
        speech_pending=not looks_like_real_transcript(spoken),
        why_it_works=reel.why_it_works,
        posted_at=reel.posted_at,
        status=reel.status,
        updated_at=reel.updated_at or datetime.utcnow(),
    )
