"""Split spoken transcript into Hook / Script / CTA for the Remix analysis UI."""

from __future__ import annotations

import re

from app.services.groq_llm import structure_remix_sections

# Phrase-level CTA signals only — bare "like" matches too much ordinary speech.
CTA_HINTS = (
    "подпис",
    "лайкните",
    "лайкай",
    "поставь лайк",
    "сохран",
    "коммент",
    "напиш",
    "ссылк",
    "описан",
    "попробуй",
    "попробуйте",
    "переход",
    "жми",
    "follow",
    "subscribe",
    "comment",
    "i'll send",
    "ill send",
    "send them",
    "send it",
    "want my",
    "my exact",
    "save this",
    "save it",
    "link in bio",
    "check out",
    "dm me",
    "drop a",
    "comment down",
    "link below",
    "hit like",
    "like and",
    "like this",
    "give it a like",
    "smash like",
)

DEFAULT_CTA = "Сохрани и попробуй этот формат в своём следующем рилсе."


def continuous_text(text: str | None) -> str:
    """Collapse whitespace and strip numbered list markers into one prose paragraph."""
    cleaned = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    # "1. foo\n2. bar" or "1) foo" → plain sentences.
    cleaned = re.sub(r"(?m)^\s*\d{1,2}[.)]\s+", "", cleaned)
    cleaned = re.sub(r"(?<=[.!?…])\s*\d{1,2}[.)]\s+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _sentences(text: str) -> list[str]:
    cleaned = continuous_text(text)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?…])\s+", cleaned)
    return [part.strip(" \t\"«»") for part in parts if part and part.strip()]


def _looks_like_cta(sentence: str) -> bool:
    low = sentence.lower()
    return any(hint in low for hint in CTA_HINTS)


def split_transcript_into_sections(
    spoken: str | None,
    caption: str | None = None,
    *,
    use_llm: bool = True,
) -> tuple[str, str, str]:
    """
    Distribute speech (or caption fallback) across Remix sections.

    Hook  — opening that stops the scroll
    Script — continuous middle body (no numbered lines)
    CTA   — closing call to action only
    """
    source = continuous_text(spoken) or continuous_text(caption)
    if not source:
        return "", "", DEFAULT_CTA

    # Prefer free Groq structuring when available (skip if caller already tried).
    if use_llm:
        structured = structure_remix_sections(source, caption)
        if structured:
            hook, script, cta = structured
            script = continuous_text(script)
            cta = continuous_text(cta)
            if cta and not _looks_like_cta(cta) and len(cta.split()) > 18:
                # Model returned story fragment as CTA — keep script, use default CTA.
                cta = DEFAULT_CTA
            return hook, script, cta or DEFAULT_CTA

    sentences = _sentences(source)
    words = source.split()

    if len(sentences) <= 1 and len(words) > 14:
        hook_n = min(16, max(8, len(words) // 5))
        hook = " ".join(words[:hook_n])[:200]
        # CTA only if the ending actually asks for an action.
        tail = " ".join(words[-(min(18, max(8, len(words) // 5))) :])
        if _looks_like_cta(tail):
            cta = tail[:500]
            middle = words[hook_n : len(words) - len(tail.split())]
        else:
            cta = DEFAULT_CTA
            middle = words[hook_n:]
        if len(middle) < 4:
            middle = words[hook_n:] or words
        script = continuous_text(" ".join(middle))[:2000]
        return hook, script, cta

    if len(sentences) <= 1:
        body = sentences[0] if sentences else source
        return body[:200], body[:2000], DEFAULT_CTA

    hook_parts = [sentences[0]]
    if len(sentences[0]) < 70 and len(sentences) > 2:
        hook_parts.append(sentences[1])
    hook = continuous_text(" ".join(hook_parts))[:200]

    cta = ""
    for sentence in reversed(sentences):
        if _looks_like_cta(sentence):
            cta = sentence
            break
    if not cta:
        cta = DEFAULT_CTA

    hook_set = set(hook_parts)
    middle = [sentence for sentence in sentences if sentence not in hook_set]
    if cta != DEFAULT_CTA and cta in middle and len(middle) > 1:
        middle = [sentence for sentence in middle if sentence != cta]
    if not middle:
        middle = [sentence for sentence in sentences if sentence not in hook_set] or sentences

    script = continuous_text(" ".join(middle))[:2000]
    return hook, script, continuous_text(cta)[:500] or DEFAULT_CTA
