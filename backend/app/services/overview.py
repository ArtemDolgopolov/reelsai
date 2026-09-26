"""ChatGPT-style overview text for the Remix analysis panel."""

from __future__ import annotations

import re

from app.models import Competitor, Reel
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
    """Conversational summary shown above Hook / Script / CTA."""
    author = competitor.full_name or f"@{competitor.username}"
    handle = f"@{competitor.username}"
    spoken = _clean(reel.transcript)
    caption = _clean(reel.caption)
    title = _clean(reel.title)
    has_speech = looks_like_real_transcript(spoken)

    topic = ""
    if has_speech:
        topic = _clip(spoken, 320)
    elif caption and caption.lower() not in {title.lower(), "instagram reel"}:
        topic = _clip(caption, 280)
    elif title and title.lower() != "instagram reel":
        topic = _clip(title, 220)

    parts: list[str] = [
        f"Разбираю рилс {author} ({handle}). Длительность {duration_label}, охват около {views_label} просмотров."
    ]

    if has_speech:
        parts.append(f"По речи автора ролик roughly про это:\n\n«{topic}»")
        parts.append(
            "Ниже разложил материал на Hook, Script и Call to Action — можно копировать в свой рилс или править."
        )
    elif topic:
        parts.append(f"По описанию и контексту ролик про это:\n\n«{topic}»")
        parts.append(
            "Пока собрал стартовые Hook / Script / CTA по тексту ролика. "
            "Если распознаем речь — блоки обновятся точнее. Их уже можно копировать и редактировать."
        )
    else:
        parts.append(
            "Текстового контекста мало, поэтому ниже — рабочие заготовки Hook / Script / CTA. "
            "Отредактируй под свой формат или дождись уточнения по речи."
        )

    # Keep the overview in Russian; avoid the accidental English word above.
    return "\n\n".join(parts).replace("roughly про", "в целом про")
