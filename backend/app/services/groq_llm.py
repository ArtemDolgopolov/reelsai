"""Free Groq LLM helpers (chat) for overview + remix structuring."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
# llama-3.1-8b-instant was decommissioned Aug 2026; gpt-oss-20b is the free replacement.
DEFAULT_CHAT_MODEL = "openai/gpt-oss-20b"
CHAT_MODEL_FALLBACKS = (
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
)


def _api_key() -> str:
    settings = get_settings()
    return (settings.groq_api_key or os.getenv("GROQ_API_KEY") or "").strip()


def _model_candidates(preferred: str | None = None) -> list[str]:
    ordered: list[str] = []
    for name in (preferred, *CHAT_MODEL_FALLBACKS):
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def _retry_after_seconds(response: httpx.Response) -> float:
    header = response.headers.get("retry-after")
    if header:
        try:
            return min(12.0, max(1.0, float(header)))
        except ValueError:
            pass
    match = re.search(r"try again in\s+([0-9.]+)\s*s", response.text or "", flags=re.I)
    if match:
        try:
            return min(12.0, max(1.0, float(match.group(1))))
        except ValueError:
            pass
    return 2.0


def groq_chat(
    *,
    system: str,
    user: str,
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 700,
    allow_wait: bool = False,
) -> str | None:
    """
    Call Groq chat.

    allow_wait=False (default): fail fast on 429 / try next model — safe for request threads.
    allow_wait=True: short sleeps ok — use only from background workers.
    """
    api_key = _api_key()
    if not api_key:
        return None

    last_error = ""
    for candidate in _model_candidates(model or DEFAULT_CHAT_MODEL):
        attempts = 2 if allow_wait else 1
        for attempt in range(attempts):
            try:
                response = httpx.post(
                    GROQ_CHAT_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": candidate,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    },
                    timeout=45.0,
                )
                if response.status_code == 429:
                    last_error = f"HTTP 429: {response.text[:240]}"
                    if allow_wait and attempt + 1 < attempts:
                        wait_s = _retry_after_seconds(response)
                        logger.warning(
                            "Groq chat rate-limited on %s, sleeping %.1fs",
                            candidate,
                            wait_s,
                        )
                        time.sleep(wait_s)
                        continue
                    logger.warning("Groq chat rate-limited on %s, trying next model", candidate)
                    break

                if response.status_code >= 400:
                    last_error = f"HTTP {response.status_code}: {response.text[:240]}"
                    body = (response.text or "").lower()
                    if response.status_code in {400, 404} and (
                        "decommission" in body
                        or "does not exist" in body
                        or "model_not_found" in body
                    ):
                        logger.warning("Groq chat model %s unavailable: %s", candidate, last_error)
                        break
                    logger.warning("Groq chat %s failed: %s", candidate, last_error)
                    return None

                payload = response.json()
                content = (
                    (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
                    .strip()
                )
                if content:
                    return content
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                logger.warning("Groq chat failed with %s: %s", candidate, exc)
                break

    if last_error:
        logger.warning("Groq chat exhausted models: %s", last_error)
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


def _clean_prose(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"(?:(?<=^)|(?<=[.!?…]\s))\d{1,2}[.)]\s+", "", text).strip()
    return text[:limit]


def analyze_reel_bundle(
    *,
    author: str,
    handle: str,
    duration_label: str,
    views_label: str,
    transcript: str | None,
    caption: str | None,
    title: str | None,
    need_overview: bool = True,
    allow_wait: bool = False,
) -> dict[str, str] | None:
    """One Groq call → overview (RU) + hook/script/cta."""
    spoken = (transcript or "").strip()
    context_bits: list[str] = []
    if spoken:
        context_bits.append(f"Расшифровка речи:\n{spoken[:2200]}")
    if caption:
        context_bits.append(f"Подпись Instagram:\n{caption[:800]}")
    if title:
        context_bits.append(f"Заголовок:\n{title[:300]}")
    if not context_bits:
        return None

    keys = "overview, hook, script, cta" if need_overview else "hook, script, cta"
    system = (
        "Ты редактор Reels-аналитики и сценарист коротких вертикальных видео. "
        f"Верни ТОЛЬКО JSON-объект с ключами {keys}. "
        "overview — 2–4 коротких абзаца по-русски: что происходит в ролике и о чём он "
        "(стиль ChatGPT, без дословной расшифровки, без markdown и без списков). "
        "hook — цепляющее начало (1–2 предложения, до 200 символов), язык как в речи. "
        "script — основной текст СПЛОШНЯКОМ одним абзацем без нумерации 1. 2. 3. и без переносов-списков. "
        "cta — только финальный призыв к действию (комментарий, подписка, сохранение, ссылка). "
        "Если явного CTA в речи нет — сформулируй короткий уместный. "
        "Не повторяй hook внутри script. Не клади сюжет в cta."
    )
    meta = ""
    if author or handle:
        meta += f"Автор: {author} ({handle})\n"
    if duration_label:
        meta += f"Длительность: {duration_label}\n"
    if views_label:
        meta += f"Просмотры: {views_label}\n"
    user = meta + "\n" + "\n\n".join(context_bits)

    raw = groq_chat(
        system=system,
        user=user,
        temperature=0.25,
        max_tokens=1100,
        allow_wait=allow_wait,
    )
    if not raw:
        return None
    data = _extract_json_object(raw)
    if not data:
        return None

    result = {
        "hook": _clean_prose(data.get("hook"), 200),
        "script": _clean_prose(data.get("script"), 2000),
        "cta": _clean_prose(data.get("cta"), 500),
    }
    if need_overview:
        overview = str(data.get("overview") or "").strip()
        overview = re.sub(r"\n{3,}", "\n\n", overview)
        result["overview"] = overview[:1600]
    if not result["hook"] or not result["script"]:
        return None
    return result


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
    analysis = analyze_reel_bundle(
        author=author,
        handle=handle,
        duration_label=duration_label,
        views_label=views_label,
        transcript=transcript,
        caption=caption,
        title=title,
        allow_wait=False,
    )
    if analysis and analysis.get("overview"):
        return str(analysis["overview"])
    return None


def structure_remix_sections(transcript: str, caption: str | None = None) -> tuple[str, str, str] | None:
    analysis = analyze_reel_bundle(
        author="",
        handle="",
        duration_label="",
        views_label="",
        transcript=transcript,
        caption=caption,
        title=None,
        need_overview=False,
        allow_wait=False,
    )
    if not analysis:
        return None
    hook = analysis.get("hook") or ""
    script = analysis.get("script") or ""
    cta = analysis.get("cta") or ""
    if not hook or not script:
        return None
    return str(hook), str(script), str(cta)
