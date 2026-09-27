"""Free Groq LLM helpers (chat) for overview + remix structuring."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_CHAT_MODEL = "llama-3.1-8b-instant"


def _api_key() -> str:
    settings = get_settings()
    return (settings.groq_api_key or os.getenv("GROQ_API_KEY") or "").strip()


def groq_chat(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 700,
) -> str | None:
    api_key = _api_key()
    if not api_key:
        return None

    try:
        response = httpx.post(
            GROQ_CHAT_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model or DEFAULT_CHAT_MODEL,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=45.0,
        )
        if response.status_code >= 400:
            logger.warning("Groq chat HTTP %s: %s", response.status_code, response.text[:240])
            return None
        payload = response.json()
        content = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        return content or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Groq chat failed: %s", exc)
        return None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def explain_reel_in_russian(
    *,
    author: str,
    handle: str,
    duration_label: str,
    views_label: str,
    transcript: str | None,
    caption: str | None,
    title: str | None,
) -> str | None:
    """ChatGPT-style explanation of what happens in the reel — not a raw transcript dump."""
    context_bits = []
    if transcript:
        context_bits.append(f"Расшифровка речи:\n{transcript[:3500]}")
    if caption:
        context_bits.append(f"Подпись Instagram:\n{caption[:1200]}")
    if title:
        context_bits.append(f"Заголовок:\n{title[:400]}")
    if not context_bits:
        return None

    system = (
        "Ты редактор Reels-аналитики. Пиши по-русски, ясно и по делу, в стиле ответа ChatGPT. "
        "Объясни, что происходит в ролике и о чём он, без дословной расшифровки. "
        "Не копируй длинные куски речи. 2–4 коротких абзаца. Без markdown-заголовков и без списков."
    )
    user = (
        f"Автор: {author} ({handle})\n"
        f"Длительность: {duration_label}\n"
        f"Просмотры: {views_label}\n\n"
        + "\n\n".join(context_bits)
        + "\n\nСформулируй понятное объяснение: о чём рилс, что показывает автор и какой главный посыл."
    )
    return groq_chat(system=system, user=user, temperature=0.35, max_tokens=550)


def structure_remix_sections(transcript: str, caption: str | None = None) -> tuple[str, str, str] | None:
    """Split speech into Hook / continuous Script / end CTA via Groq."""
    spoken = (transcript or "").strip()
    if len(spoken) < 25:
        return None

    system = (
        "Ты сценарист коротких вертикальных видео. "
        "Верни ТОЛЬКО JSON-объект с ключами hook, script, cta. "
        "hook — цепляющее начало (1–2 предложения, до 200 символов). "
        "script — основной текст ролика СПЛОШНЯКОМ одним абзацем без нумерации и без переносов-списков. "
        "cta — только финальный призыв к действию в самом конце (комментарий, подписка, сохранение, ссылка и т.п.). "
        "Не повторяй hook внутри script. Не оставляй куски сюжета внутри cta."
    )
    user = f"Расшифровка речи:\n{spoken[:3500]}"
    if caption:
        user += f"\n\nПодпись (контекст):\n{caption[:800]}"

    raw = groq_chat(system=system, user=user, temperature=0.2, max_tokens=900)
    if not raw:
        return None
    data = _extract_json_object(raw)
    if not data:
        return None

    hook = re.sub(r"\s+", " ", str(data.get("hook") or "")).strip()[:200]
    script = re.sub(r"\s+", " ", str(data.get("script") or "")).strip()[:2000]
    cta = re.sub(r"\s+", " ", str(data.get("cta") or "")).strip()[:500]
    if not hook or not script:
        return None
    return hook, script, cta
