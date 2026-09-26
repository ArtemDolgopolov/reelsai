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


def _chunk_words(text: str, size: int = 12) -> list[str]:
    words = text.split()
    if not words:
        return []
    return [" ".join(words[index : index + size]) for index in range(0, len(words), size)]


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
    words = source.split()

    # Speech-to-text often returns one long run without punctuation.
    if len(sentences) <= 1 and len(words) > 14:
        hook_n = min(16, max(8, len(words) // 5))
        cta_n = min(12, max(6, len(words) // 6))
        hook = " ".join(words[:hook_n])[:200]
        cta = " ".join(words[-cta_n:])[:500]
        middle = words[hook_n : len(words) - cta_n]
        if len(middle) < 4:
            middle = words[hook_n:] or words
        script = "\n".join(_chunk_words(" ".join(middle), 12))[:2000]
        return hook, script, cta or DEFAULT_CTA

    if len(sentences) <= 1:
        body = sentences[0] if sentences else source
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
