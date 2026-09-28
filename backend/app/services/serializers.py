from datetime import datetime

from sqlmodel import Session

from app.models import Competitor, ContentPlanItem, Reel
from app.schemas import CompetitorRead, ReelDetail, ReelListItem
from app.services.instagram_free import looks_like_real_transcript
from app.services.overview import _is_ai_overview, enrich_reel_analysis
from app.services.transcript_sections import DEFAULT_CTA, continuous_text


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


def competitor_to_read(competitor: Competitor, *, reels_count: int = 0) -> CompetitorRead:
    payload = CompetitorRead.model_validate(competitor, from_attributes=True)
    return payload.model_copy(update={"reels_count": reels_count})


def reel_to_list_item(
    reel: Reel,
    username: str,
    *,
    plan_item: ContentPlanItem | None = None,
) -> ReelListItem:
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
        posted_at=reel.posted_at,
        in_plan=plan_item is not None,
        plan_item_id=plan_item.id if plan_item else None,
        shoot_status=plan_item.shoot_status if plan_item else None,
    )


def reel_to_detail(
    reel: Reel,
    competitor: Competitor,
    *,
    session: Session | None = None,
) -> ReelDetail:
    duration = format_duration(reel.duration_seconds)
    views_label = format_views(reel.views_count)
    # Instant path — never block the request thread on Groq.
    overview, hook, script, cta, analysis_pending = enrich_reel_analysis(
        reel,
        competitor,
        views_label=views_label,
        duration_label=duration,
        sync_llm=False,
    )

    changed = False
    if hook and continuous_text(reel.hook) != continuous_text(hook):
        reel.hook = hook[:200]
        changed = True
    if script and continuous_text(reel.script) != continuous_text(script):
        reel.script = script[:2000]
        changed = True
    if cta and continuous_text(reel.cta) != continuous_text(cta):
        reel.cta = (cta or DEFAULT_CTA)[:500]
        changed = True
    if overview and overview != (reel.analysis_overview or "") and _is_ai_overview(overview):
        reel.analysis_overview = overview[:4000]
        changed = True
    if changed and session is not None:
        session.add(reel)
        try:
            session.commit()
            session.refresh(reel)
        except Exception:  # noqa: BLE001
            session.rollback()

    # Prefer persisted AI overview; drop transcript-dump overviews from DB.
    stored = (reel.analysis_overview or "").strip()
    if stored and not _is_ai_overview(stored):
        if session is not None:
            reel.analysis_overview = None
            try:
                session.add(reel)
                session.commit()
                session.refresh(reel)
            except Exception:  # noqa: BLE001
                session.rollback()
        stored = ""
    if stored and _is_ai_overview(stored):
        if not _is_ai_overview(overview) or not overview:
            overview = stored
            analysis_pending = False

    speech_pending = reel.transcript is None
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
        overview=overview,
        hook=hook,
        script=continuous_text(script),
        cta=continuous_text(cta) or DEFAULT_CTA,
        transcript=reel.transcript,
        speech_pending=speech_pending,
        analysis_pending=analysis_pending,
        why_it_works=reel.why_it_works,
        posted_at=reel.posted_at,
        status=reel.status,
        updated_at=reel.updated_at or datetime.utcnow(),
    )
