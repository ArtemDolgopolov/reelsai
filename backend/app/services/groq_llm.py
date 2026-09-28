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


def _latin_share(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    latin = sum(1 for ch in letters if "a" <= ch.lower() <= "z")
    return latin / len(letters)


def translate_transcript_to_russian(transcript: str, *, allow_wait: bool = True) -> str | None:
    """Plain Russian translation of the spoken transcript (no structure)."""
    spoken = (transcript or "").strip()
    if not spoken:
        return None
    # Already mostly Russian — keep as the "translation" base.
    if _latin_share(spoken) < 0.35:
        return re.sub(r"\s+", " ", spoken)[:2000]

    system = (
        "Ты переводчик Reels. Переведи расшифровку речи на русский язык. "
        "Сохрани смысл, тон и разговорный стиль устной речи. "
        "Не сокращай содержание. Не добавляй заголовки, пояснения, кавычки и markdown. "
        "Верни ТОЛЬКО текст перевода."
    )
    raw = groq_chat(
        system=system,
        user=f"Оригинал:\n{spoken[:1800]}",
        temperature=0.15,
        max_tokens=900,
        allow_wait=allow_wait,
    )
    if not raw:
        return None
    cleaned = re.sub(r"\s+", " ", raw).strip().strip("\"'«»")
    min_len = 6 if len(spoken) < 120 else 16
    if len(cleaned) < min_len:
        return None
    # Reject if model echoed English.
    if _latin_share(cleaned) > 0.45:
        return None
    return cleaned[:2000]


def _is_placeholder_cta(text: str | None) -> bool:
    """True for empty / generic stock CTAs that are not a real translation."""
    from app.services.transcript_sections import DEFAULT_CTA

    low = re.sub(r"\s+", " ", (text or "")).strip().lower()
    if not low:
        return True
    if low == DEFAULT_CTA.lower():
        return True
    if "сохрани и попробуй этот формат" in low:
        return True
    if low in {"подпишись", "ставь лайк", "сохрани", "напиши в комментарии"}:
        return True
    return False


def translate_cta_to_russian(original_cta: str, *, allow_wait: bool = True) -> str | None:
    """Dedicated CTA translation — never invent a generic stock line."""
    spoken = (original_cta or "").strip()
    if not spoken:
        return None
    if _latin_share(spoken) < 0.35:
        return re.sub(r"\s+", " ", spoken)[:500]

    system = (
        "Ты переводчик финального призыва к действию в Reels. "
        "Переведи ТОЛЬКО этот CTA на русский, сохранив конкретный смысл "
        "(какой комментарий написать, на что подписаться, что сделать). "
        "Запрещено подставлять общие фразы вроде «сохрани и попробуй этот формат». "
        "Верни только текст перевода, без кавычек и пояснений."
    )
    raw = groq_chat(
        system=system,
        user=f"CTA оригинал:\n{spoken[:500]}",
        temperature=0.1,
        max_tokens=220,
        allow_wait=allow_wait,
    )
    if not raw:
        return None
    cleaned = re.sub(r"\s+", " ", raw).strip().strip("\"'«»")
    if len(cleaned) < 6 or _latin_share(cleaned) > 0.45 or _is_placeholder_cta(cleaned):
        return None
    return cleaned[:500]


def remix_bilingual_bundle(
    *,
    transcript: str | None,
    caption: str | None = None,
    title: str | None = None,
    author: str = "",
    handle: str = "",
) -> dict[str, str] | None:
    """
    Split original into hook/script/cta, then translate EACH piece 1:1.
    Original boundaries are fixed (heuristic) — LLM never invents different originals.
    """
    from app.services.transcript_sections import DEFAULT_CTA, continuous_text, split_transcript_into_sections

    spoken = (transcript or "").strip()
    source = spoken or (caption or "").strip() or (title or "").strip()
    if not source:
        return None

    orig_hook, orig_script, orig_cta = split_transcript_into_sections(
        spoken if spoken else None,
        caption or title,
        use_llm=False,
    )
    orig_hook = continuous_text(orig_hook)[:200]
    orig_script = continuous_text(orig_script)[:2000]
    orig_cta = continuous_text(orig_cta)[:500]
    # If CTA is just the default placeholder (no real closing line), leave original empty.
    cta_is_real = bool(orig_cta) and orig_cta != DEFAULT_CTA and _latin_share(orig_cta) > 0.2
    if not cta_is_real:
        orig_cta = ""

    def _translate_piece(text: str, *, limit: int) -> str | None:
        if not text.strip():
            return None
        return translate_transcript_to_russian(text, allow_wait=True)

    # Prefer one structured call that translates the FIXED original pieces (no re-split).
    system = (
        "Ты переводчик Reels. Ниже даны три готовых фрагмента оригинала: hook, script, cta. "
        "Переведи каждый на русский, сохраняя смысл и разговорный стиль. "
        "Не меняй границы фрагментов и не добавляй новый смысл. "
        "Верни ТОЛЬКО JSON с ключами hook_ru, script_ru, cta_ru, overview. "
        "overview — 2 коротких абзаца по-русски: о чём ролик. "
        "cta_ru обязан быть переводом именно CTA-фрагмента (комментарий / подписка / действие), "
        "а не общей фразой «сохрани и попробуй этот формат». "
        "В hook_ru / script_ru / cta_ru не оставляй английский."
    )
    user_parts = [f"HOOK:\n{orig_hook}", f"SCRIPT:\n{orig_script}"]
    if orig_cta:
        user_parts.append(f"CTA:\n{orig_cta}")
    else:
        user_parts.append("CTA:\n(нет явного призыва — сформулируй короткий уместный cta_ru на русском)")
    if author or handle:
        user_parts.insert(0, f"Автор: {author} ({handle})")
    raw = groq_chat(
        system=system,
        user="\n\n".join(user_parts),
        temperature=0.1,
        max_tokens=1000,
        allow_wait=True,
    )

    hook_ru = ""
    script_ru = ""
    cta_ru = ""
    overview = ""
    if raw:
        data = _extract_json_object(raw) or {}
        maybe_hook = _clean_prose(data.get("hook_ru"), 200)
        maybe_script = _clean_prose(data.get("script_ru"), 2000)
        maybe_cta = _clean_prose(data.get("cta_ru"), 500)
        maybe_overview = str(data.get("overview") or "").strip()
        if maybe_hook and _latin_share(maybe_hook) < 0.45:
            hook_ru = maybe_hook
        if maybe_script and _latin_share(maybe_script) < 0.45:
            script_ru = maybe_script
        # Reject stock CTA placeholders even if the model returned Russian.
        if maybe_cta and _latin_share(maybe_cta) < 0.45 and not _is_placeholder_cta(maybe_cta):
            cta_ru = maybe_cta
        if maybe_overview and _latin_share(maybe_overview) < 0.45:
            overview = maybe_overview[:1600]

    # Strict 1:1 fallback — translate each fixed original piece on its own.
    if not hook_ru and orig_hook:
        hook_ru = (_translate_piece(orig_hook, limit=200) or "")[:200]
    if not script_ru and orig_script:
        script_ru = (_translate_piece(orig_script, limit=2000) or "")[:2000]

    # CTA: if we have a real original, ALWAYS force a real translation of THAT text.
    if orig_cta:
        if _is_placeholder_cta(cta_ru):
            cta_ru = ""
        if not cta_ru:
            cta_ru = translate_cta_to_russian(orig_cta, allow_wait=True) or ""
        if not cta_ru:
            cta_ru = (_translate_piece(orig_cta, limit=500) or "")[:500]
        if _is_placeholder_cta(cta_ru):
            # Still better to retry once more with dedicated CTA prompt than stock line.
            cta_ru = translate_cta_to_russian(orig_cta, allow_wait=True) or cta_ru
        if _is_placeholder_cta(cta_ru):
            # Last resort: keep a literal-ish RU attempt marker rather than wrong stock CTA.
            # Prefer empty-ish failure → try one more plain translate.
            cta_ru = (_translate_piece(orig_cta, limit=500) or "")[:500]
        if _is_placeholder_cta(cta_ru):
            return None
    else:
        if _is_placeholder_cta(cta_ru):
            cta_ru = DEFAULT_CTA

    if not hook_ru or not script_ru:
        return None
    if not overview:
        overview = explain_reel_in_russian(
            author=author or "Автор",
            handle=handle or "",
            duration_label="",
            views_label="",
            transcript=spoken or None,
            caption=caption,
            title=title,
            allow_wait=True,
        ) or (
            "Этот рилс адаптирован под русскоязычную съёмку. "
            "Сверьте оригинал и перевод в каждом блоке."
        )

    return {
        "original_hook": orig_hook,
        "original_script": orig_script,
        "original_cta": orig_cta,
        "hook": hook_ru[:200],
        "script": script_ru[:2000],
        "cta": cta_ru[:500] if orig_cta else (cta_ru or DEFAULT_CTA)[:500],
        "overview": overview[:1600],
        "translation": script_ru[:2000],
    }
