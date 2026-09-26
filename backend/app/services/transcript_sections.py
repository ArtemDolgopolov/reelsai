"""Split spoken transcript into Hook / Script / CTA for the Remix analysis UI."""

from __future__ import annotations

import re

CTA_HINTS = (
    "подпис",
    "лайк",
    "сохран",
    "коммент",
    "напиш",
    "ссылк",
    "описан",
    "попробуй",
    "попробуйте",
    "переход",
    "смотри",
    "жми",
    "follow",
    "like",
    "comment",
    "save",
    "subscribe",
    "link in bio",
    "check out",
)

DEFAULT_CTA = "Сохрани и попробуй этот формат в своём следующем рилсе."


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?…])\s+|\n+", cleaned)
    return [part.strip(" \t\"«»") for part in parts if part and part.strip()]


def _looks_like_cta(sentence: str) -> bool:
    low = sentence.lower()
    return any(hint in low for hint in CTA_HINTS)


def split_transcript_into_sections(
    spoken: str | None,
    caption: str | None = None,
) -> tuple[str, str, str]:
    """
    Distribute speech (or caption fallback) across Remix sections.

    Hook  — opening line(s) that stop the scroll
    Script — middle beats as separate lines
    CTA   — closing ask / call to action
    """
    source = (spoken or "").strip() or (caption or "").strip()
    if not source:
        return "", "", DEFAULT_CTA

    sentences = _sentences(source)
    if not sentences:
        body = source[:2000]
        return body[:200], body, DEFAULT_CTA

    if len(sentences) == 1:
        body = sentences[0]
        return body[:200], body[:2000], DEFAULT_CTA

    hook_parts = [sentences[0]]
    if len(sentences[0]) < 70 and len(sentences) > 2:
        hook_parts.append(sentences[1])
    hook = " ".join(hook_parts)[:200]

    cta = sentences[-1]
    for sentence in reversed(sentences):
        if _looks_like_cta(sentence):
            cta = sentence
            break
    cta = cta[:500] if cta else DEFAULT_CTA

    hook_set = set(hook_parts)
    middle = [sentence for sentence in sentences if sentence not in hook_set]
    if cta in middle and len(middle) > 1:
        middle = [sentence for sentence in middle if sentence != cta]
    if not middle:
        middle = [sentence for sentence in sentences if sentence not in hook_set] or sentences

    script = "\n".join(middle)[:2000]
    return hook, script, cta or DEFAULT_CTA
