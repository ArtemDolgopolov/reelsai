"""ChatGPT-style overview text for the Remix analysis panel."""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from uuid import UUID

from sqlmodel import Session

from app.db import engine
from app.models import Competitor, Reel
from app.services.groq_llm import analyze_reel_bundle, explain_reel_in_russian, remix_bilingual_bundle
from app.services.instagram_free import looks_like_real_transcript
from app.services.transcript_sections import (
    DEFAULT_CTA,
    continuous_text,
    split_transcript_into_sections,
)

logger = logging.getLogger(__name__)

# reel_id + transcript fingerprint → (expires_at, overview, hook, script, cta, from_llm)
_ANALYSIS_CACHE: dict[str, tuple[float, str, str, str, str, bool]] = {}
_CACHE_TTL_S = 60 * 60
_enrich_lock = threading.Lock()
_enrich_inflight: set[str] = set()

_PLACEHOLDER_MARKERS = (
    "собираю объяснение",
    "собираю разбор",
    "собрал структуру ремикса",
    "через пару секунд",
    "готовлю короткое объяснение",
    "пока мало контекста",
    "ниже — стартовые",
    "ниже — рабочие заготовки",
    "кратко по речи автора",
    "появится summary",
)

_TOPIC_HINTS = (
    (r"\bfigma\b", "дизайн в Figma"),
    (r"\b(website|websites|сайт|лендинг)\b", "сборку сайта"),
    (r"\b(ai|chatgpt|claude|cursor|нейросет)\b", "AI-инструменты"),
    (r"\b(python|code|coding|код|программ)\b", "код и автоматизацию"),
    (r"\b(scrape|парс|данные)\b", "сбор данных"),
    (r"\b(reel|instagram|контент)\b", "контент и Reels"),
    (r"\b(money|доход|заработ|business|бизнес)\b", "рост и монетизацию"),
    (r"\b(fitness|workout|тренир)\b", "тренировки"),
    (r"\b(recipe|cook|рецепт|готов)\b", "еду и рецепты"),
    (r"\b(seedance|cloud code)\b", "генерацию сайта через AI"),
)


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _clip(text: str, limit: int = 280) -> str:
    text = _clean(text)
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].strip() or text[: limit - 1]
    return f"{cut}…"


def _latin_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    latin = sum(1 for ch in letters if "a" <= ch.lower() <= "z")
    return latin / len(letters)


def _is_ai_overview(text: str | None) -> bool:
    """True when overview looks like a real Russian explanation, not a stub/transcript dump."""
    cleaned = (text or "").strip()
    if len(cleaned) < 90:
        return False
    low = cleaned.lower()
    if any(marker in low for marker in _PLACEHOLDER_MARKERS):
        return False
    # Drop transcript dumps pasted into the overview body.
    body = re.sub(r"^разбираю рилс.*?(?:\n\n|$)", "", cleaned, count=1, flags=re.I | re.S)
    if _latin_ratio(body) > 0.35:
        return False
    return True


def _theme_labels(caption: str, title: str, spoken: str) -> list[str]:
    blob = f"{title} {caption} {spoken[:800]}".lower()
    found: list[str] = []
    for pattern, label in _TOPIC_HINTS:
        if re.search(pattern, blob, flags=re.I) and label not in found:
            found.append(label)
        if len(found) >= 3:
            break
    return found


def _local_russian_explanation(
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
    """Conceptual RU summary without pasting transcript/script text."""
    header = build_header(author, handle, duration_label, views_label)
    themes = _theme_labels(caption, title, spoken)
    if themes:
        about = f"Этот рилс про {', '.join(themes)}."
    elif caption and caption.lower() not in {title.lower(), "instagram reel"}:
        about = f"Этот рилс про тему из описания: {_clip(caption, 110)}."
    elif title and title.lower() != "instagram reel":
        about = f"Этот рилс по заголовку про: {_clip(title, 110)}."
    else:
        about = "Этот рилс — практический разбор приёма автора для быстрого результата."

    if has_speech:
        flow = (
            "По речи видно структуру: сначала сильный хук с обещанием результата, "
            "затем пошаговый показ процесса, в финале — призыв к действию."
        )
    else:
        flow = (
            "По кадру и описанию ролик строится как короткая демонстрация: "
            "внимание → процесс → призыв."
        )
    closer = (
        "Ниже — Hook, сплошной Script и Call to Action для ремикса, "
        "уже как структура, а не дословная расшифровка."
    )
    return "\n\n".join([header, f"{about} {flow}", closer])


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
    waiting: bool = False,
) -> str:
    if waiting:
        return "\n\n".join(
            [
                build_header(author, handle, duration_label, views_label),
                "Готовлю короткое объяснение: о чём рилс, что показывает автор и какой главный посыл. "
                "Через пару секунд появится summary.",
            ]
        )
    return _local_russian_explanation(
        author=author,
        handle=handle,
        duration_label=duration_label,
        views_label=views_label,
        spoken=spoken,
        caption=caption,
        title=title,
        has_speech=has_speech,
    )


def build_header(author: str, handle: str, duration_label: str, views_label: str) -> str:
    return (
        f"Разбираю рилс {author} ({handle}). "
        f"Длительность {duration_label}, охват около {views_label} просмотров."
    )


def _cache_key(reel: Reel) -> str:
    spoken = continuous_text(reel.transcript)
    digest = hashlib.sha1(spoken.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{reel.id}:{digest}"


def get_cached_analysis(reel: Reel) -> tuple[str, str, str, str, bool] | None:
    key = _cache_key(reel)
    hit = _ANALYSIS_CACHE.get(key)
    if not hit:
        return None
    expires_at, overview, hook, script, cta, from_llm = hit
    if expires_at < time.time():
        _ANALYSIS_CACHE.pop(key, None)
        return None
    return overview, hook, script, cta, from_llm


def store_cached_analysis(
    reel: Reel,
    overview: str,
    hook: str,
    script: str,
    cta: str,
    *,
    from_llm: bool,
) -> None:
    _ANALYSIS_CACHE[_cache_key(reel)] = (
        time.time() + _CACHE_TTL_S,
        overview,
        hook,
        script,
        cta,
        from_llm,
    )


def _sections_look_structured(spoken: str, reel: Reel) -> bool:
    stored_script = continuous_text(reel.script)
    stored_cta = continuous_text(reel.cta)
    if not stored_script:
        return False
    # Persisted Russian remix/translation is intentional — keep it.
    if _latin_ratio(stored_script) < 0.4:
        return True
    if stored_script == spoken:
        return False
    if "\n" in (reel.script or "") or re.search(r"(?m)^\d{1,2}[.)]\s+", reel.script or ""):
        return False
    if len(stored_script) > len(spoken) * 0.98:
        return False
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
        return False
    return True


def enrich_reel_analysis(
    reel: Reel,
    competitor: Competitor,
    *,
    views_label: str,
    duration_label: str,
    sync_llm: bool = False,
) -> tuple[str, str, str, str, bool]:
    """
    Return overview, hook, script, cta, analysis_pending.

    Instant path (sync_llm=False): never blocks on Groq — local/cached/persisted only.
    Full path (sync_llm=True): may call Groq with waits — background only.
    """
    author = competitor.full_name or f"@{competitor.username}"
    handle = f"@{competitor.username}"
    spoken = continuous_text(reel.transcript)
    caption = continuous_text(reel.caption)
    title = continuous_text(reel.title)
    has_speech = looks_like_real_transcript(spoken)
    stored_overview = (reel.analysis_overview or "").strip()

    cached = get_cached_analysis(reel)
    if cached and cached[4] and _is_ai_overview(cached[0]):
        overview, hook, script, cta, _ = cached
        return overview, hook, script, cta, False

    if _is_ai_overview(stored_overview):
        if has_speech and _sections_look_structured(spoken, reel):
            hook = continuous_text(reel.hook)[:200]
            script = continuous_text(reel.script)[:2000]
            cta = continuous_text(reel.cta)[:500] or DEFAULT_CTA
        elif has_speech:
            hook, script, cta = split_transcript_into_sections(spoken, caption, use_llm=False)
        else:
            hook, script, cta = split_transcript_into_sections(None, caption or title, use_llm=False)
        store_cached_analysis(reel, stored_overview, hook, script, cta, from_llm=True)
        return stored_overview, hook, script, cta, False

    if sync_llm and (has_speech or caption or title):
        bundle = analyze_reel_bundle(
            author=author,
            handle=handle,
            duration_label=duration_label,
            views_label=views_label,
            transcript=spoken if has_speech else None,
            caption=caption or None,
            title=title or None,
            need_overview=True,
            allow_wait=True,
        )
        if bundle and bundle.get("overview") and bundle.get("hook") and bundle.get("script"):
            overview = (
                f"{build_header(author, handle, duration_label, views_label)}\n\n"
                f"{bundle['overview'].strip()}"
            )
            hook = bundle["hook"]
            script = continuous_text(bundle["script"])
            cta = continuous_text(bundle.get("cta")) or DEFAULT_CTA
            store_cached_analysis(reel, overview, hook, script, cta, from_llm=True)
            return overview, hook, script, cta, False

        # Bundle failed (rate limit / bad JSON) — still get a real AI explanation.
        explained = explain_reel_in_russian(
            author=author,
            handle=handle,
            duration_label=duration_label,
            views_label=views_label,
            transcript=spoken if has_speech else None,
            caption=caption or None,
            title=title or None,
            allow_wait=True,
        )
        if has_speech:
            hook, script, cta = split_transcript_into_sections(spoken, caption, use_llm=False)
        else:
            hook, script, cta = split_transcript_into_sections(None, caption or title, use_llm=False)
        if explained and _is_ai_overview(explained):
            overview = f"{build_header(author, handle, duration_label, views_label)}\n\n{explained.strip()}"
            store_cached_analysis(reel, overview, hook, script, cta, from_llm=True)
            return overview, hook, script, cta, False

        # LLM unavailable — unblock UI with heuristic sections (pending=False).
        overview = offline_overview(
            author=author,
            handle=handle,
            duration_label=duration_label,
            views_label=views_label,
            spoken=spoken,
            caption=caption,
            title=title,
            has_speech=has_speech,
            waiting=False,
        )
        store_cached_analysis(reel, overview, hook, script, cta, from_llm=False)
        return overview, hook, script, cta, False

    if cached:
        overview, hook, script, cta, from_llm = cached
        needs_ai = has_speech and not from_llm and not _is_ai_overview(overview)
        return overview, hook, script, cta, needs_ai

    if has_speech and _sections_look_structured(spoken, reel):
        overview = offline_overview(
            author=author,
            handle=handle,
            duration_label=duration_label,
            views_label=views_label,
            spoken=spoken,
            caption=caption,
            title=title,
            has_speech=True,
            waiting=True,
        )
        hook = continuous_text(reel.hook)[:200]
        script = continuous_text(reel.script)[:2000]
        cta = continuous_text(reel.cta)[:500] or DEFAULT_CTA
        store_cached_analysis(reel, overview, hook, script, cta, from_llm=False)
        return overview, hook, script, cta, True

    if has_speech:
        hook, script, cta = split_transcript_into_sections(spoken, caption, use_llm=False)
    else:
        stored_hook = continuous_text(reel.hook)
        stored_script = continuous_text(reel.script)
        if stored_hook and stored_script:
            hook, script, cta = (
                stored_hook[:200],
                stored_script[:2000],
                continuous_text(reel.cta)[:500] or DEFAULT_CTA,
            )
        else:
            hook, script, cta = split_transcript_into_sections(None, caption or title, use_llm=False)

    overview = offline_overview(
        author=author,
        handle=handle,
        duration_label=duration_label,
        views_label=views_label,
        spoken=spoken,
        caption=caption,
        title=title,
        has_speech=has_speech,
        waiting=has_speech,
    )
    store_cached_analysis(reel, overview, hook, script, cta, from_llm=False)
    # Pending only while we still expect an AI pass for spoken reels.
    return overview, hook, script, cta, has_speech


def _analysis_worker(reel_id: UUID) -> None:
    key = str(reel_id)
    try:
        with Session(engine) as session:
            reel = session.get(Reel, reel_id)
            if reel is None:
                return
            competitor = session.get(Competitor, reel.competitor_id)
            if competitor is None:
                return
            if reel.transcript is None:
                # STT still running — wait for speech or empty marker.
                return

            from app.services.serializers import format_duration, format_views

            overview, hook, script, cta, pending = enrich_reel_analysis(
                reel,
                competitor,
                views_label=format_views(reel.views_count),
                duration_label=format_duration(reel.duration_seconds),
                sync_llm=True,
            )
            reel.hook = hook[:200]
            reel.script = script[:2000]
            reel.cta = (cta or DEFAULT_CTA)[:500]
            # Persist both real Groq summaries and local fallback so the UI
            # never stays forever on "через пару секунд появится summary".
            cleaned = (overview or "").strip()
            if cleaned and not any(marker in cleaned.lower() for marker in _PLACEHOLDER_MARKERS):
                reel.analysis_overview = cleaned[:4000]
            session.add(reel)
            session.commit()
            if pending:
                logger.info(
                    "LLM remix still pending for %s — will retry on next open",
                    reel.external_id or reel.id,
                )
            else:
                logger.info("LLM remix analysis ready for %s", reel.external_id or reel.id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Background analysis failed for %s: %s", reel_id, exc)
    finally:
        with _enrich_lock:
            _enrich_inflight.discard(key)


def schedule_analysis(reel_id: UUID) -> None:
    """Fire-and-forget Groq explanation + Hook/Script/CTA refinement."""
    key = str(reel_id)
    with _enrich_lock:
        if key in _enrich_inflight:
            return
        _enrich_inflight.add(key)
    thread = threading.Thread(
        target=_analysis_worker,
        args=(reel_id,),
        name=f"remix-analysis-{key[:8]}",
        daemon=True,
    )
    thread.start()


def prepare_russian_remix(reel: Reel, competitor: Competitor) -> tuple[str, str, str, str, bool]:
    """
    Force a Russian adaptation: overview + hook/script/cta for filming.
    Returns overview, hook, script, cta, used_llm.
    script holds the Russian translation shown opposite the original transcript.
    """
    from app.services.serializers import format_duration, format_views

    views_label = format_views(reel.views_count)
    duration_label = format_duration(reel.duration_seconds)
    author = competitor.full_name or f"@{competitor.username}"
    handle = f"@{competitor.username}"
    spoken = continuous_text(reel.transcript)
    caption = continuous_text(reel.caption)
    title = continuous_text(reel.title)
    has_speech = looks_like_real_transcript(spoken)

    source = spoken if has_speech else (caption or title)
    if not source:
        overview = offline_overview(
            author=author,
            handle=handle,
            duration_label=duration_label,
            views_label=views_label,
            spoken=spoken,
            caption=caption,
            title=title,
            has_speech=False,
            waiting=False,
        )
        return overview, "", "", DEFAULT_CTA, False

    bundle = remix_bilingual_bundle(
        transcript=spoken if has_speech else None,
        caption=caption or None,
        title=title or None,
        author=author,
        handle=handle,
    )
    if bundle and bundle.get("translation"):
        # Prefer full translation in script so UI can show original | перевод.
        translation = continuous_text(bundle["translation"])[:2000]
        hook = continuous_text(bundle.get("hook"))[:200] or translation[:200]
        script = translation
        cta = continuous_text(bundle.get("cta"))[:500] or DEFAULT_CTA
        overview_body = (bundle.get("overview") or "").strip()
        overview = (
            f"{build_header(author, handle, duration_label, views_label)}\n\n"
            f"{overview_body}"
        ).strip()
        store_cached_analysis(reel, overview, hook, script, cta, from_llm=True)
        return overview, hook, script, cta, True

    # Do not fall back to English transcript chunks — that looks like "no translation".
    overview = offline_overview(
        author=author,
        handle=handle,
        duration_label=duration_label,
        views_label=views_label,
        spoken=spoken,
        caption=caption,
        title=title,
        has_speech=has_speech,
        waiting=False,
    )
    return overview, continuous_text(reel.hook)[:200], continuous_text(reel.script)[:2000], (
        continuous_text(reel.cta) or DEFAULT_CTA
    )[:500], False


def build_reel_overview(reel: Reel, competitor: Competitor, *, views_label: str, duration_label: str) -> str:
    overview, _, _, _, _ = enrich_reel_analysis(
        reel,
        competitor,
        views_label=views_label,
        duration_label=duration_label,
        sync_llm=False,
    )
    return overview
