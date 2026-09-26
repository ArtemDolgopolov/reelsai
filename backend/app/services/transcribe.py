"""Speech-to-text from reel audio using free Google Web Speech via SpeechRecognition.

Works from spoken audio (no Instagram captions/subtitles required).
Language is auto-detected by probing the first audio chunk across common locales.
Long clips are split into ~50s chunks to stay within free recognizer limits.
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Probe order matters for speed: Cyrillic/English first (common for this product),
# then other Instagram-heavy locales. Google Web Speech needs an explicit code —
# omitting language silently defaults to en-US only.
DETECT_LANGUAGES = (
    "ru-RU",
    "en-US",
    "uk-UA",
    "es-ES",
    "pt-BR",
    "de-DE",
    "fr-FR",
    "it-IT",
    "tr-TR",
    "pl-PL",
    "ar",
    "hi-IN",
    "id-ID",
    "ja-JP",
    "ko-KR",
    "zh-CN",
)


def _hint_languages(hint_text: str | None) -> tuple[str, ...]:
    """Reorder probe list using caption/title script as a soft prior — not as transcript."""
    text = (hint_text or "").strip()
    if not text:
        return DETECT_LANGUAGES

    preferred: list[str] = []
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

    ordered: list[str] = []
    for code in preferred + list(DETECT_LANGUAGES):
        if code not in ordered:
            ordered.append(code)
    return tuple(ordered)


def _score_google_result(result: object) -> tuple[float, str]:
    """Return (score, transcript) from recognize_google(..., show_all=True)."""
    if isinstance(result, str):
        text = result.strip()
        return (min(len(text), 240) / 24.0, text) if text else (-1.0, "")

    if not isinstance(result, dict):
        return -1.0, ""

    alternatives = result.get("alternative") or []
    if not alternatives:
        return -1.0, ""

    top = alternatives[0] if isinstance(alternatives[0], dict) else {}
    text = str(top.get("transcript") or "").strip()
    if not text:
        return -1.0, ""

    confidence = top.get("confidence")
    try:
        conf = float(confidence) if confidence is not None else 0.0
    except (TypeError, ValueError):
        conf = 0.0

    # Confidence dominates; length breaks ties for locales that omit confidence.
    score = conf * 12.0 + min(len(text), 240) / 30.0 + min(text.count(" "), 40) / 20.0
    return score, text


def _detect_language(recognizer, audio_data, hint_text: str | None = None) -> tuple[str, str]:
    """Probe languages on a short clip; return (language_code, first_transcript)."""
    best_lang = "en-US"
    best_score = -1.0
    best_text = ""

    for language in _hint_languages(hint_text):
        try:
            raw = recognizer.recognize_google(audio_data, language=language, show_all=True)
        except Exception:  # noqa: BLE001
            continue
        score, text = _score_google_result(raw)
        if score > best_score:
            best_score = score
            best_lang = language
            best_text = text
        # Strong match — stop early to save free-API quota / latency.
        if score >= 8.5 and len(text) >= 24:
            break

    if best_text:
        logger.info("Detected speech language %s (score=%.2f)", best_lang, best_score)
    else:
        logger.warning("Language probe produced no speech text; falling back to en-US")
    return best_lang, best_text


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
    recognizer = sr.Recognizer()
    chunk_ms = 50_000
    parts: list[str] = []
    detected_language = language

    with tempfile.TemporaryDirectory(prefix="reelsai-chunks-") as tmp:
        tmp_path = Path(tmp)
        for index, start in enumerate(range(0, len(audio), chunk_ms)):
            chunk = audio[start : start + chunk_ms]
            chunk_file = tmp_path / f"chunk-{index}.wav"
            chunk.export(chunk_file, format="wav")
            try:
                with sr.AudioFile(str(chunk_file)) as source:
                    data = recognizer.record(source)

                if detected_language is None and index == 0:
                    # Use a shorter probe when the first chunk is long.
                    probe = data
                    if len(chunk) > 18_000:
                        probe_file = tmp_path / "probe.wav"
                        chunk[:18_000].export(probe_file, format="wav")
                        with sr.AudioFile(str(probe_file)) as probe_source:
                            probe = recognizer.record(probe_source)
                    detected_language, probe_text = _detect_language(
                        recognizer, probe, hint_text=hint_text
                    )
                    if probe_text:
                        # If probe was the full first chunk, keep that text.
                        if len(chunk) <= 18_000:
                            parts.append(probe_text)
                            continue

                text = recognizer.recognize_google(data, language=detected_language or "en-US")
                if text and text.strip():
                    parts.append(text.strip())
            except sr.UnknownValueError:
                continue
            except sr.RequestError as exc:
                logger.warning("Google speech request failed: %s", exc)
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("Chunk transcription failed: %s", exc)
                continue

    result = " ".join(parts).strip()
    if not result:
        return None
    logger.info(
        "Transcribed %s (%s chars, lang=%s)",
        path.name,
        len(result),
        detected_language or "unknown",
    )
    return result
