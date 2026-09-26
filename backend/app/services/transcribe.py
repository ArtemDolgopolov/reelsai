"""Speech-to-text from reel audio using free Google Web Speech via SpeechRecognition.

Audio is downloaded with yt-dlp/ffmpeg first; no Apify and no heavy local models.
Long clips are split into ~50s chunks to stay within free recognizer limits.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def transcribe_audio_file(path: Path, language: str | None = None) -> str | None:
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

    with tempfile.TemporaryDirectory(prefix="reelsai-chunks-") as tmp:
        tmp_path = Path(tmp)
        for index, start in enumerate(range(0, len(audio), chunk_ms)):
            chunk = audio[start : start + chunk_ms]
            chunk_file = tmp_path / f"chunk-{index}.wav"
            chunk.export(chunk_file, format="wav")
            try:
                with sr.AudioFile(str(chunk_file)) as source:
                    data = recognizer.record(source)
                # language=None lets Google auto-detect when possible; pass explicit if known.
                kwargs = {}
                if language:
                    kwargs["language"] = language
                text = recognizer.recognize_google(data, **kwargs)
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
    logger.info("Transcribed %s (%s chars)", path.name, len(result))
    return result
