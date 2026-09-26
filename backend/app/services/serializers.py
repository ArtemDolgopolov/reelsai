from datetime import datetime

from app.models import Competitor, Reel
from app.schemas import CompetitorRead, ReelDetail, ReelListItem
from app.services.instagram_free import looks_like_real_transcript
from app.services.transcript_sections import split_transcript_into_sections


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


def analysis_sections(reel: Reel) -> tuple[str, str, str]:
    """Hook / Script / CTA from spoken audio only — never Instagram captions."""
    spoken = (reel.transcript or "").strip()
    if looks_like_real_transcript(spoken):
        stored_script = (reel.script or "").strip()
        # Re-split legacy rows where the whole transcript was dumped into script.
        if not stored_script or stored_script == spoken:
            return split_transcript_into_sections(spoken)
        return (
            (reel.hook or "").strip(),
            stored_script,
            (reel.cta or "").strip() or split_transcript_into_sections(spoken)[2],
        )
    return "", "", (reel.cta or "").strip()


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
        has_transcript=len(transcript) >= 40,
        status=reel.status,
    )


def reel_to_detail(reel: Reel, competitor: Competitor) -> ReelDetail:
    hook, script, cta = analysis_sections(reel)
    return ReelDetail(
        id=reel.id,
        competitor_id=reel.competitor_id,
        title=reel.title,
        caption=reel.caption,
        author=f"@{competitor.username}",
        author_name=competitor.full_name,
        avatar_url=competitor.avatar_url,
        duration=format_duration(reel.duration_seconds),
        duration_seconds=reel.duration_seconds,
        views_count=reel.views_count,
        likes_count=reel.likes_count,
        comments_count=reel.comments_count,
        shares_count=reel.shares_count,
        instagram_url=reel.instagram_url,
        thumbnail_url=reel.thumbnail_url,
        video_url=reel.video_url,
        overlay_text=reel.overlay_text,
        hook=hook,
        script=script,
        cta=cta,
        transcript=reel.transcript,
        why_it_works=reel.why_it_works,
        posted_at=reel.posted_at,
        status=reel.status,
        updated_at=reel.updated_at or datetime.utcnow(),
    )
