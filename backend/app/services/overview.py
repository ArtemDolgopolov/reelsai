"""ChatGPT-style overview text for the Remix analysis panel."""

from __future__ import annotations

import re

from app.models import Competitor, Reel
from app.services.groq_llm import explain_reel_in_russian
from app.services.instagram_free import looks_like_real_transcript


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _clip(text: str, limit: int = 280) -> str:
    text = _clean(text)
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].strip() or text[: limit - 1]
    return f"{cut}…"


def build_reel_overview(reel: Reel, competitor: Competitor, *, views_label: str, duration_label: str) -> str:
    """Conversational explanation of what happens in the reel (not a transcript dump)."""
    author = competitor.full_name or f"@{competitor.username}"
    handle = f"@{competitor.username}"
    spoken = _clean(reel.transcript)
    caption = _clean(reel.caption)
    title = _clean(reel.title)
    has_speech = looks_like_real_transcript(spoken)

    llm_overview = explain_reel_in_russian(
        author=author,
        handle=handle,
        duration_label=duration_label,
        views_label=views_label,
        transcript=spoken if has_speech else None,
        caption=caption or None,
        title=title or None,
    )
    if llm_overview:
        header = (
            f"Разбираю рилс {author} ({handle}). "
            f"Длительность {duration_label}, охват около {views_label} просмотров."
        )
        return f"{header}\n\n{llm_overview.strip()}"

    # Offline fallback — still explain, do not paste raw speech.
    parts: list[str] = [
        f"Разбираю рилс {author} ({handle}). Длительность {duration_label}, охват около {views_label} просмотров."
    ]
    if has_speech:
        gist = _clip(spoken, 180)
        parts.append(
            f"По речи автора ролик roughly про следующее: {gist} "
            "Ниже собрал Hook, Script и Call to Action для ремикса — уже как структуру, а не простыню расшифровки."
        )
    elif caption and caption.lower() not in {title.lower(), "instagram reel"}:
        parts.append(f"По описанию тема ролика roughly: {_clip(caption, 220)}.")
        parts.append("Ниже — стартовые Hook / Script / CTA, их можно копировать и править.")
    elif title and title.lower() != "instagram reel":
        parts.append(f"Судя по заголовку, ролик про: {_clip(title, 180)}.")
        parts.append("Hook / Script / CTA ниже можно сразу копировать или отредактировать.")
    else:
        parts.append(
            "Пока мало контекста. Ниже — рабочие заготовки Hook / Script / CTA, которые можно править вручную."
        )

    return "\n\n".join(parts).replace("roughly:", "примерно:")
