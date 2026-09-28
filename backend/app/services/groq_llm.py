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
    """Cap waits tightly — long sleeps make remix feel multi-minute."""
    header = response.headers.get("retry-after")
    if header:
        try:
            return min(2.5, max(0.4, float(header)))
        except ValueError:
            pass
    match = re.search(r"try again in\s+([0-9.]+)\s*s", response.text or "", flags=re.I)
    if match:
        try:
            return min(2.5, max(0.4, float(match.group(1))))
        except ValueError:
            pass
    return 0.8


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

    allow_wait=False: fail fast / next model (request threads).
    allow_wait=True: at most one short pause, then rotate models quickly.
    """
    api_key = _api_key()
    if not api_key:
        return None

    last_error = ""
    waited_once = False
    for candidate in _model_candidates(model or DEFAULT_CHAT_MODEL):
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
                timeout=25.0,
            )
            if response.status_code == 429:
                last_error = f"HTTP 429: {response.text[:240]}"
                if allow_wait and not waited_once:
                    wait_s = _retry_after_seconds(response)
                    waited_once = True
                    logger.warning(
                        "Groq chat rate-limited on %s, brief sleep %.1fs then rotate",
                        candidate,
                        wait_s,
                    )
                    time.sleep(wait_s)
                    # Retry the same model once after the short pause.
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
                        timeout=25.0,
                    )
                    if response.status_code < 400:
                        payload = response.json()
                        content = (
                            (
                                ((payload.get("choices") or [{}])[0].get("message") or {}).get(
                                    "content"
                                )
                                or ""
                            ).strip()
                        )
                        if content:
                            return content
                logger.warning("Groq chat rate-limited on %s, trying next model", candidate)
                continue

            if response.status_code >= 400:
                last_error = f"HTTP {response.status_code}: {response.text[:240]}"
                body = (response.text or "").lower()
                if response.status_code in {400, 404} and (
                    "decommission" in body
                    or "does not exist" in body
                    or "model_not_found" in body
                ):
                    logger.warning("Groq chat model %s unavailable: %s", candidate, last_error)
                    continue
                logger.warning("Groq chat %s failed: %s", candidate, last_error)
                return None

            payload = response.json()
            content = (
                (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
                .strip()
            )
            if content:
                return content
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            logger.warning("Groq chat failed with %s: %s", candidate, exc)
            continue

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
        context_bits.append(f"Расшифровка речи:\n{spoken[:1400]}")
    if caption:
        context_bits.append(f"Подпись Instagram:\n{caption[:500]}")
    if title:
        context_bits.append(f"Заголовок:\n{title[:200]}")
    if not context_bits:
        return None

    keys = "overview, hook, script, cta" if need_overview else "hook, script, cta"
    system = (
        "Ты сценарист вертикальных Reels для русскоязычного автора. "
        "Задача — адаптировать зарубежный ролик: перевести смысл на русский и собрать "
        "готовый сценарий для съёмки, а не дословный машинный перевод. "
        f"Верни ТОЛЬКО JSON-объект с ключами {keys}. "
        "overview — ОБЯЗАТЕЛЬНО по-русски, 2–3 коротких абзаца: "
        "«Этот рилс про … Автор показывает … Главный посыл — …». "
        "Нельзя вставлять дословную расшифровку речи и длинные английские цитаты. "
        "hook — цепляющее начало НА РУССКОМ (1–2 предложения, до 200 символов). "
        "script — основной текст НА РУССКОМ сплошным абзацем без нумерации 1. 2. 3. "
        "cta — финальный призыв НА РУССКОМ (комментарий, подписка, сохранение). "
        "Если явного CTA в оригинале нет — сформулируй короткий уместный на русском. "
        "Не повторяй hook внутри script. Не клади сюжет в cta. "
        "Пиши естественно для устной русской речи в Reels."
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
        temperature=0.2,
        max_tokens=750,
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
    allow_wait: bool = False,
) -> str | None:
    """Dedicated Russian explanation — used when the full JSON bundle fails."""
    spoken = (transcript or "").strip()
    context_bits: list[str] = []
    if spoken:
        context_bits.append(f"Расшифровка речи:\n{spoken[:1400]}")
    if caption:
        context_bits.append(f"Подпись Instagram:\n{caption[:500]}")
    if title:
        context_bits.append(f"Заголовок:\n{title[:200]}")
    if not context_bits:
        return None

    system = (
        "Ты редактор Reels-аналитики. Пиши ТОЛЬКО по-русски, ясно и по делу. "
        "Сделай общее summary ролика в 2–3 абзацах формата: "
        "«Этот рилс про … Автор показывает … Главный посыл — …». "
        "Запрещено копировать расшифровку речи и вставлять длинные английские цитаты. "
        "Без markdown-заголовков и без списков."
    )
    user = (
        f"Автор: {author} ({handle})\n"
        f"Длительность: {duration_label}\n"
        f"Просмотры: {views_label}\n\n"
        + "\n\n".join(context_bits)
        + "\n\nНапиши понятное объяснение на русском: о чём рилс в целом, что происходит на экране "
        "и какой главный вывод для зрителя."
    )
    return groq_chat(
        system=system,
        user=user,
        temperature=0.3,
        max_tokens=450,
        allow_wait=allow_wait,
    )


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
