"""Speech-to-text from reel audio using free Google Web Speech via SpeechRecognition.

Works from spoken audio (no Instagram captions/subtitles required).
Language is auto-detected by scoring the first audio chunk across common locales.
Long clips are split into ~45s chunks to stay within free recognizer limits.
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Google Web Speech needs an explicit language code (default is en-US only).
DETECT_LANGUAGES = (
    "en-US",
    "en-GB",
    "ru-RU",
    "uk-UA",
    "es-ES",
    "pt-BR",
    "de-DE",
    "fr-FR",
    "it-IT",
    "tr-TR",
    "pl-PL",
    "nl-NL",
    "ar",
    "hi-IN",
    "id-ID",
    "ja-JP",
    "ko-KR",
    "zh-CN",
)

GARBAGE_PHRASES = (
    "hello google",
    "english conversation",
    "thank you for watching",
    "subscribe to my channel",
    "thanks for watching",
    "www.",
    "http",
)


def _hint_languages(hint_text: str | None) -> tuple[str, ...]:
    """Reorder probe list using caption/title script as a soft prior — not as transcript."""
    text = (hint_text or "").strip()
    preferred: list[str] = []
    if text:
        if re.search(r"[\u0400-\u04FF]", text):
            preferred.extend(["ru-RU", "uk-UA"])
        if re.search(r"[\u0600-\u06FF]", text):
            preferred.append("ar")
        if re.search(r"[\u3040-\u30FF]", text):
            preferred.append("ja-JP")
        if re.search(r"[\uAC00-\uD7AF]", text):
            preferred.append("ko-KR")
        if re.search(r"[\u4E00-\u9FFF]", text):
            preferred.append("zh-CN")
        if re.search(r"[äöüßÄÖÜ]", text):
            preferred.append("de-DE")
        if re.search(r"[àâçéèêëîïôùûüÿœ]", text, re.I):
            preferred.append("fr-FR")
        if re.search(r"[áéíóúñ¿¡]", text, re.I):
            preferred.extend(["es-ES", "pt-BR"])
        # Latin captions — try both US/UK English early.
        if re.search(r"[A-Za-z]{3,}", text) and not preferred:
            preferred.extend(["en-GB", "en-US"])

    ordered: list[str] = []
    for code in preferred + list(DETECT_LANGUAGES):
        if code not in ordered:
            ordered.append(code)
    return tuple(ordered)


def _is_garbage(text: str) -> bool:
    low = text.lower().strip()
    if not low:
        return True
    if any(phrase in low for phrase in GARBAGE_PHRASES):
        return True
    # Extremely repetitive single-token spam.
    words = low.split()
    if len(words) >= 4 and len(set(words)) <= 2:
        return True
    return False


def _score_google_result(result: object) -> tuple[float, str]:
    """Return (score, transcript) from recognize_google(..., show_all=True)."""
    if isinstance(result, str):
        text = result.strip()
        if not text or _is_garbage(text):
            return -1.0, ""
        return min(len(text), 400) / 20.0 + min(text.count(" "), 50) / 10.0, text

    if not isinstance(result, dict):
        return -1.0, ""

    alternatives = result.get("alternative") or []
    if not alternatives:
        return -1.0, ""

    top = alternatives[0] if isinstance(alternatives[0], dict) else {}
    text = str(top.get("transcript") or "").strip()
    if not text or _is_garbage(text):
        return -1.0, ""

    confidence = top.get("confidence")
    try:
        conf = float(confidence) if confidence is not None else 0.35
    except (TypeError, ValueError):
        conf = 0.35

    score = conf * 15.0 + min(len(text), 400) / 25.0 + min(text.count(" "), 50) / 12.0
    return score, text


def _recognize_best(recognizer, audio_data, languages: tuple[str, ...]) -> tuple[str, str]:
    """Try languages and return (best_language, best_text)."""
    ranked: list[tuple[float, str, str]] = []
    for language in languages:
        try:
            raw = recognizer.recognize_google(audio_data, language=language, show_all=True)
        except Exception:  # noqa: BLE001
            continue
        score, text = _score_google_result(raw)
        if score > 0 and text:
            ranked.append((score, language, text))
            # Good enough — stop burning free quota.
            if score >= 10 and len(text) >= 40:
                break

    if not ranked:
        return "", ""
    ranked.sort(key=lambda item: item[0], reverse=True)
    _, language, text = ranked[0]
    return language, text


def _recognize_chunk(recognizer, audio_data, languages: tuple[str, ...]) -> str:
    language, text = _recognize_best(recognizer, audio_data, languages)
    return text


def transcribe_audio_file(
    path: Path,
    language: str | None = None,
    hint_text: str | None = None,
) -> str | None:
    try:
        import speech_recognition as sr
        from pydub import AudioSegment
    except ImportError as exc:
        logger.warning("SpeechRecognition/pydub missing: %s", exc)
        return None

    try:
        audio = AudioSegment.from_file(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read audio %s: %s", path, exc)
        return None

    # Mono 16kHz WAV is what the free recognizer expects.
    audio = audio.set_channels(1).set_frame_rate(16000)
    # Keep clips shorter for more reliable free Google recognition.
    if len(audio) > 90_000:
        audio = audio[:90_000]

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 200
    chunk_ms = 40_000
    parts: list[str] = []
    language_order = (language,) if language else _hint_languages(hint_text)
    detected_language = language or ""

    with tempfile.TemporaryDirectory(prefix="reelsai-chunks-") as tmp:
        tmp_path = Path(tmp)
        for index, start in enumerate(range(0, len(audio), chunk_ms)):
            chunk = audio[start : start + chunk_ms]
            if len(chunk) < 800:
                continue
            chunk_file = tmp_path / f"chunk-{index}.wav"
            chunk.export(chunk_file, format="wav")
            try:
                with sr.AudioFile(str(chunk_file)) as source:
                    data = recognizer.record(source)

                if index == 0 and not detected_language:
                    detected_language, text = _recognize_best(recognizer, data, language_order)
                    if detected_language:
                        language_order = (detected_language,) + tuple(
                            code for code in language_order if code != detected_language
                        )
                        logger.info(
                            "Detected speech language %s (%s chars)",
                            detected_language,
                            len(text),
                        )
                    if text:
                        parts.append(text)
                        continue

                # Prefer detected language, then a couple of fallbacks.
                try_langs = language_order[:4] if language_order else DETECT_LANGUAGES[:4]
                text = _recognize_chunk(recognizer, data, try_langs)
                if text:
                    parts.append(text)
            except sr.RequestError as exc:
                logger.warning("Google speech request failed: %s", exc)
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("Chunk transcription failed: %s", exc)
                continue

    result = " ".join(parts).strip()
    if not result or _is_garbage(result):
        return None
    logger.info(
        "Transcribed %s (%s chars, lang=%s)",
        path.name,
        len(result),
        detected_language or "unknown",
    )
    return result
