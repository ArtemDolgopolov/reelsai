"""Local speech-to-text via faster-whisper (tiny model, free, no API key)."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_model():
    from faster_whisper import WhisperModel

    # tiny/int8 fits t3.micro memory budget and is fully free/offline after download.
    return WhisperModel("tiny", device="cpu", compute_type="int8")


def transcribe_audio_file(path: Path, language: str | None = None) -> str | None:
    try:
        model = _get_model()
        segments, info = model.transcribe(
            str(path),
            language=language,
            beam_size=1,
            vad_filter=True,
        )
        parts = [segment.text.strip() for segment in segments if segment.text and segment.text.strip()]
        text = " ".join(parts).strip()
        if not text:
            return None
        logger.info(
            "Transcribed %s (lang=%s, duration=%.1fs, chars=%s)",
            path.name,
            getattr(info, "language", None),
            getattr(info, "duration", 0) or 0,
            len(text),
        )
        return text
    except Exception as exc:  # noqa: BLE001
        logger.warning("Whisper transcription failed for %s: %s", path, exc)
        return None
