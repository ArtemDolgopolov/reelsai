"""ChatGPT-style overview text for the Remix analysis panel."""

from __future__ import annotations

import hashlib
import re
import time

from app.models import Competitor, Reel
from app.services.groq_llm import analyze_reel_bundle
from app.services.instagram_free import looks_like_real_transcript
from app.services.transcript_sections import (
    DEFAULT_CTA,
    continuous_text,
    split_transcript_into_sections,
)

# reel_id + transcript fingerprint → (expires_at, overview, hook, script, cta)
_ANALYSIS_CACHE: dict[str, tuple[float, str, str, str, str]] = {}
_CACHE_TTL_S = 60 * 60


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _clip(text: str, limit: int = 280) -> str:
    text = _clean(text)
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].strip() or text[: limit - 1]
    return f"{cut}…"


def _cache_key(reel: Reel) -> str:
    spoken = continuous_text(reel.transcript)
    digest = hashlib.sha1(spoken.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{reel.id}:{digest}"


def get_cached_analysis(reel: Reel) -> tuple[str, str, str, str] | None:
    key = _cache_key(reel)
    hit = _ANALYSIS_CACHE.get(key)
    if not hit:
        return None
    expires_at, overview, hook, script, cta = hit
    if expires_at < time.time():
        _ANALYSIS_CACHE.pop(key, None)
        return None
    return overview, hook, script, cta


def store_cached_analysis(reel: Reel, overview: str, hook: str, script: str, cta: str) -> None:
    _ANALYSIS_CACHE[_cache_key(reel)] = (
        time.time() + _CACHE_TTL_S,
        overview,
        hook,
        script,
        cta,
    )


def build_header(author: str, handle: str, duration_label: str, views_label: str) -> str:
    return (
        f"Разбираю рилс {author} ({handle}). "
        f"Длительность {duration_label}, охват около {views_label} просмотров."
    )


def offline_overview(
    *,
    author: str,
    handle: str,
    duration_label: str,
    views_label: str,
    spoken: str,
    caption: str,
    title: str,
    has_speech: bool,
) -> str:
    parts: list[str] = [build_header(author, handle, duration_label, views_label)]
    if has_speech:
        parts.append(
            "По речи автора собрал понятную структуру ремикса: Hook, сплошной Script и Call to Action в финале — "
            "без простыни дословной расшифровки."
        )
    elif caption and caption.lower() not in {title.lower(), "instagram reel"}:
        parts.append(f"По описанию тема ролика примерно: {_clip(caption, 220)}.")
        parts.append("Ниже — стартовые Hook / Script / CTA, их можно копировать и править.")
    elif title and title.lower() != "instagram reel":
        parts.append(f"Судя по заголовку, ролик про: {_clip(title, 180)}.")
        parts.append("Hook / Script / CTA ниже можно сразу копировать или отредактировать.")
    else:
        parts.append(
            "Пока мало контекста. Ниже — рабочие заготовки Hook / Script / CTA, которые можно править вручную."
        )
    return "\n\n".join(parts)


def enrich_reel_analysis(
    reel: Reel,
    competitor: Competitor,
    *,
    views_label: str,
    duration_label: str,
) -> tuple[str, str, str, str]:
    """
    Return overview, hook, script, cta.

    Prefers one Groq bundle call (cached). Falls back to local continuous split.
    """
    author = competitor.full_name or f"@{competitor.username}"
    handle = f"@{competitor.username}"
    spoken = continuous_text(reel.transcript)
    caption = continuous_text(reel.caption)
    title = continuous_text(reel.title)
    has_speech = looks_like_real_transcript(spoken)

    cached = get_cached_analysis(reel)
    if cached:
        return cached

    stored_hook = continuous_text(reel.hook)
    stored_script = continuous_text(reel.script)
    stored_cta = continuous_text(reel.cta)
    script_ok = bool(
        stored_script
        and stored_script != spoken
        and "\n" not in (reel.script or "")
        and not re.search(r"(?m)^\d{1,2}[.)]\s+", reel.script or "")
        and len(stored_script) <= len(spoken) * 0.98
    ) if has_speech else bool(stored_hook and stored_script)
    cta_ok = bool(stored_cta) and not (
        len(stored_cta.split()) > 22
        and not any(
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
        )
    )

    if has_speech:
        bundle = analyze_reel_bundle(
            author=author,
            handle=handle,
            duration_label=duration_label,
            views_label=views_label,
            transcript=spoken,
            caption=caption or None,
            title=title or None,
            need_overview=True,
        )
        if bundle and bundle.get("overview") and bundle.get("hook") and bundle.get("script"):
            overview = f"{build_header(author, handle, duration_label, views_label)}\n\n{bundle['overview'].strip()}"
            hook = bundle["hook"]
            script = continuous_text(bundle["script"])
            cta = continuous_text(bundle.get("cta")) or DEFAULT_CTA
            store_cached_analysis(reel, overview, hook, script, cta)
            return overview, hook, script, cta

        if script_ok and cta_ok:
            overview = offline_overview(
                author=author,
                handle=handle,
                duration_label=duration_label,
                views_label=views_label,
                spoken=spoken,
                caption=caption,
                title=title,
                has_speech=True,
            )
            return overview, stored_hook[:200], stored_script[:2000], stored_cta[:500] or DEFAULT_CTA

        hook, script, cta = split_transcript_into_sections(spoken, caption, use_llm=False)
        overview = offline_overview(
            author=author,
            handle=handle,
            duration_label=duration_label,
            views_label=views_label,
            spoken=spoken,
            caption=caption,
            title=title,
            has_speech=True,
        )
        store_cached_analysis(reel, overview, hook, script, cta)
        return overview, hook, script, cta

    if script_ok:
        overview = offline_overview(
            author=author,
            handle=handle,
            duration_label=duration_label,
            views_label=views_label,
            spoken=spoken,
            caption=caption,
            title=title,
            has_speech=False,
        )
        return overview, stored_hook[:200], stored_script[:2000], stored_cta[:500] or DEFAULT_CTA

    hook, script, cta = split_transcript_into_sections(None, caption or title, use_llm=False)
    overview = offline_overview(
        author=author,
        handle=handle,
        duration_label=duration_label,
        views_label=views_label,
        spoken=spoken,
        caption=caption,
        title=title,
        has_speech=False,
    )
    return overview, hook, script, cta


def build_reel_overview(reel: Reel, competitor: Competitor, *, views_label: str, duration_label: str) -> str:
    """Kept for callers that only need the overview text."""
    overview, _, _, _ = enrich_reel_analysis(
        reel,
        competitor,
        views_label=views_label,
        duration_label=duration_label,
    )
    return overview
