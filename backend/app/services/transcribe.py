"""High-quality speech-to-text for reel audio.

Providers (first success wins):
1. Groq Whisper large-v3 — free tier, excellent on noisy / accented speech
2. faster-whisper (local) — free, offline, multilingual auto-detect
3. Google Web Speech — last-resort fallback

No Instagram captions/subtitles are used; audio only.
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
from pathlib import Path

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_whisper_model = None
_whisper_lock = threading.Lock()

GARBAGE_PHRASES = (
    "hello google",
    "english conversation",
    "thank you for watching",
    "subscribe to my channel",
    "thanks for watching",
    "www.",
    "http",
)


def _is_garbage(text: str) -> bool:
    low = text.lower().strip()
    if not low:
        return True
    if any(phrase in low for phrase in GARBAGE_PHRASES) and len(low) < 90:
        return True
    words = low.split()
    if len(words) >= 4 and len(set(words)) <= 2:
        return True
    return False


def _looks_usable(text: str | None) -> bool:
    if not text:
        return False
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) < 20:
        return False
    if cleaned.count(" ") < 3:
        return False
    return not _is_garbage(cleaned)


def _hint_language_code(hint_text: str | None) -> str | None:
    """Soft language prior from caption/title script — never used as transcript."""
    text = (hint_text or "").strip()
    if not text:
        return None
    if re.search(r"[\u0400-\u04FF]", text):
        return "ru"
    if re.search(r"[\u0600-\u06FF]", text):
        return "ar"
    if re.search(r"[\u3040-\u30FF]", text):
        return "ja"
    if re.search(r"[\uAC00-\uD7AF]", text):
        return "ko"
    if re.search(r"[\u4E00-\u9FFF]", text):
        return "zh"
    if re.search(r"[äöüßÄÖÜ]", text):
        return "de"
    if re.search(r"[àâçéèêëîïôùûüÿœ]", text, re.I):
        return "fr"
    if re.search(r"[áéíóúñ¿¡]", text, re.I):
        return "es"
    if re.search(r"[A-Za-z]{4,}", text):
        return "en"
    return None


def _wav_for_providers(path: Path) -> Path:
    """Normalize to mono 16 kHz WAV when needed (Groq/Whisper prefer clean PCM)."""
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return path
    try:
        from pydub import AudioSegment
    except ImportError:
        return path
    try:
        audio = AudioSegment.from_file(path)
        audio = audio.set_channels(1).set_frame_rate(16000)
        # Cap very long reels to keep free-tier / micro latency sane.
        if len(audio) > 180_000:
            audio = audio[:180_000]
        out = path.with_suffix(".norm.wav")
        audio.export(out, format="wav")
        return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("Audio normalize failed, using original: %s", exc)
        return path


def _transcribe_groq(path: Path, hint_text: str | None = None) -> str | None:
    settings = get_settings()
    api_key = (settings.groq_api_key or os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        return None

    wav = _wav_for_providers(path)
    language = _hint_language_code(hint_text)
    data: dict[str, str] = {
        "model": settings.groq_whisper_model,
        "response_format": "text",
        "temperature": "0",
    }
    if language:
        data["language"] = language

    try:
        with wav.open("rb") as handle:
            files = {"file": (wav.name, handle, "audio/wav")}
            response = httpx.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                data=data,
                files=files,
                timeout=120.0,
            )
        if response.status_code >= 400:
            logger.warning("Groq STT HTTP %s: %s", response.status_code, response.text[:240])
            return None
        text = (response.text or "").strip().strip('"')
        if _looks_usable(text):
            logger.info("Groq transcribed %s (%s chars)", path.name, len(text))
            return text
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Groq STT failed: %s", exc)
        return None


def _get_faster_whisper():
    global _whisper_model
    with _whisper_lock:
        if _whisper_model is not None:
            return _whisper_model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            logger.warning("faster-whisper not installed: %s", exc)
            return None

        settings = get_settings()
        model_name = settings.whisper_model
        logger.info("Loading faster-whisper model=%s compute=int8", model_name)
        _whisper_model = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
            cpu_threads=max(1, min(2, os.cpu_count() or 1)),
        )
        return _whisper_model


def _transcribe_faster_whisper(path: Path, hint_text: str | None = None) -> str | None:
    model = _get_faster_whisper()
    if model is None:
        return None

    wav = _wav_for_providers(path)
    language = _hint_language_code(hint_text)
    try:
        segments, info = model.transcribe(
            str(wav),
            language=language,
            task="transcribe",
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400},
            beam_size=5,
            best_of=5,
            patience=1.0,
            condition_on_previous_text=True,
            temperature=[0.0, 0.2, 0.4],
        )
        parts = [segment.text.strip() for segment in segments if segment.text and segment.text.strip()]
        text = " ".join(parts).strip()
        detected = getattr(info, "language", None) or language or "auto"
        if _looks_usable(text):
            logger.info(
                "faster-whisper transcribed %s (%s chars, lang=%s)",
                path.name,
                len(text),
                detected,
            )
            return text
        logger.warning("faster-whisper returned weak text for %s", path.name)
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("faster-whisper failed: %s", exc)
        return None


def _transcribe_google_fallback(path: Path, hint_text: str | None = None) -> str | None:
    """Last resort — low quality, but better than empty."""
    try:
        import speech_recognition as sr
        from pydub import AudioSegment
    except ImportError:
        return None

    try:
        audio = AudioSegment.from_file(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Google fallback could not read audio: %s", exc)
        return None

    audio = audio.set_channels(1).set_frame_rate(16000)
    if len(audio) > 90_000:
        audio = audio[:90_000]

    language = {
        "ru": "ru-RU",
        "en": "en-US",
        "uk": "uk-UA",
        "es": "es-ES",
        "pt": "pt-BR",
        "de": "de-DE",
        "fr": "fr-FR",
        "it": "it-IT",
        "tr": "tr-TR",
        "pl": "pl-PL",
        "ar": "ar",
        "hi": "hi-IN",
        "id": "id-ID",
        "ja": "ja-JP",
        "ko": "ko-KR",
        "zh": "zh-CN",
    }.get(_hint_language_code(hint_text) or "", "en-US")

    recognizer = sr.Recognizer()
    parts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="reelsai-google-") as tmp:
        tmp_path = Path(tmp)
        for index, start in enumerate(range(0, len(audio), 40_000)):
            chunk = audio[start : start + 40_000]
            if len(chunk) < 800:
                continue
            chunk_file = tmp_path / f"chunk-{index}.wav"
            chunk.export(chunk_file, format="wav")
            try:
                with sr.AudioFile(str(chunk_file)) as source:
                    data = recognizer.record(source)
                text = recognizer.recognize_google(data, language=language)
                if text and text.strip():
                    parts.append(text.strip())
            except Exception:  # noqa: BLE001
                continue

    result = " ".join(parts).strip()
    if _looks_usable(result):
        logger.info("Google fallback transcribed %s (%s chars)", path.name, len(result))
        return result
    return None


def transcribe_audio_file(
    path: Path,
    language: str | None = None,
    hint_text: str | None = None,
) -> str | None:
    """Transcribe spoken audio. `language` kept for API compat; auto-detect preferred."""
    _ = language
    if not path.exists():
        return None

    for name, runner in (
        ("groq", _transcribe_groq),
        ("faster-whisper", _transcribe_faster_whisper),
        ("google", _transcribe_google_fallback),
    ):
        try:
            text = runner(path, hint_text=hint_text)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s STT crashed: %s", name, exc)
            continue
        if text:
            return text

    logger.warning("All STT providers failed for %s", path.name)
    return None
