"""Speech transcription engine using Vosk (offline, no torch dependency)."""

from __future__ import annotations

import logging
import threading
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model paths
# ---------------------------------------------------------------------------
_DEFAULT_MODEL_DIR = Path.home() / ".voice-assist" / "vosk-model"
_MODEL_URL = (
    "https://alphacephei.com/vosk/models/vosk-model-small-en-0.15.zip"
)  # placeholder; actual download handled by init

_model = None
_lock = threading.Lock()
_LOADED = False


def _ensure_loaded():
    """Lazily initialize and cache the Vosk Recognizer on first use."""
    global _model, _LOCKED
    if _LOCKED:
        return _model
    with _lock:
        if _LOCKED:
            return _model
        try:
            import vosk
            # Determine model path — try default, then fall back to env var
            model_path = str(_DEFAULT_MODEL_DIR)
            from os import environ
            if environ.get("VOSK_MODEL_PATH"):
                model_path = environ["VOSK_MODEL_PATH"]
                logger.debug("Using VOSK_MODEL_PATH=%s", model_path)

            _model = vosk.KaldiRecognizer(vosk.Model(model_path), 16000)
            _LOCKED = True
            logger.info("Vosk model loaded from %s", model_path)
        except ImportError:
            logger.error(
                "vosk not installed. Install with: pip install vosk"
            )
            raise
        except Exception as exc:
            logger.error(
                "Failed to load Vosk model at %s: %s. "
                "Download manually: vosk-downloader --target . vosk-model-small-en-0.15",
                model_path, exc,
            )
            raise
    return _model


class WhisperEngine:
    """Wraps a Vosk recognizer instance with a familiar transcribe API.

    Despite the name, this engine uses Vosk (not Whisper) under the hood
    to avoid the torch dependency that is unavailable on certain platforms
    (Intel macOS without compatible wheels).
    """

    def __init__(self, model_path: Optional[str] = None):
        if model_path:
            import os
            os.environ.setdefault("VOSK_MODEL_PATH", model_path)
        self._recognizer_ref = None  # will be set in transcribe via ensure

    # ---- public API -------------------------------------------------------

    def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe WAV-encoded *audio_bytes* and return plain English text.

        Parameters
        ----------
        audio_bytes : bytes
            Raw WAV or 16-bit PCM audio at 16 kHz mono.

        Returns
        -------
        str
            Transcribed English text, stripped of leading/trailing whitespace.
            Returns ``""`` if no speech was detected.
        """
        import io

        stream = io.BytesIO(audio_bytes)
        try:
            wf = wave.open(stream, "rb")
        except Exception:
            # Fallback: treat as raw PCM if wave.open fails
            wf = None

        # Lazy load on first call
        _ensure_loaded()
        import vosk

        # Create a fresh recognizer per call (Vosk KaldiRecognizer isn't thread-safe)
        model_path = str(_DEFAULT_MODEL_DIR)
        from os import environ
        if environ.get("VOSK_MODEL_PATH"):
            model_path = environ["VOSK_MODEL_PATH"]
        recognizer = vosk.KaldiRecognizer(vosk.Model(model_path), 16000)

        if wf is not None and wf.getnchannels() == 1 and wf.getsampwidth() == 2:
            # Proper WAV — stream chunks
            chunk_size = 4000  # ~250ms at 16kHz mono 16-bit
            while True:
                data = wf.readframes(chunk_size)
                if not data:
                    break
                if not recognizer.AcceptWaveform(data):
                    continue
            text = recognizer.FinalResult()
        else:
            # Raw PCM buffer
            recognizer.AcceptWaveform(audio_bytes)
            text = recognizer.FinalResult()

        # Parse JSON result → extract text field
        import json
        try:
            result = json.loads(text)
            return result.get("text", "").strip()
        except (json.JSONDecodeError, TypeError):
            return ""

    def reset(self) -> None:
        """Reset internal state for a new utterance."""
        _ensure_loaded()
        # New recognizer created on next transcribe call; nothing to reset


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def transcribe(audio_bytes: bytes, model_path: Optional[str] = None) -> str:
    """One-shot transcription convenience function.

    Not ideal for repeated calls under a running application — use
    :class:`WhisperEngine` instead.
    """
    engine = WhisperEngine(model_path)
    return engine.transcribe(audio_bytes)
