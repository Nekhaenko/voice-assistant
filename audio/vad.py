"""Voice Activity Detection using Google WebRTC VAD."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SR: int = 16000          # sample rate expected by webrtcvad
_FRAME_MS: int = 30       # frame size in milliseconds
_BYTES_PER_FRAME: int = _SR * _FRAME_MS // 1000 * 2  # 16-bit mono = 960 bytes


def _make_vad(mode: int = 1) -> "WebRTCVad":
    """Create a WebRTCVad instance with the given aggressiveness mode."""
    try:
        import webrtcvad
    except ImportError:
        logger.error(
            "webrtcvad not installed. Install with: pip install webrtcvad"
        )
        raise
    vad = webrtcvad.Vad()
    vad.set_mode(mode)       # 0=off, 1=low, 2=medium (default), 3=high
    return vad


@dataclass
class VadState:
    """Per-stream VAD state using WebRTC VAD.

    Attributes
    ----------
    is_speech : bool
        Decision for the most recent frame (True = speech detected).
    mode : int
        Aggressiveness mode (0–3). Higher = more aggressive at flagging speech.
    _chunks_speech : int
        Count of consecutive speech frames used for smoothing.
    _chunks_threshold : int
        Minimum consecutive speech frames to flip from silence→speech.
    """

    mode: int = 1
    _chunks_speech: int = 0
    _chunks_threshold: int = 2          # require 2 consecutive frames
    is_speech: bool = False

    def update(self, audio_chunk: bytes) -> bool:
        """Process one audio frame and return the smoothed speech decision.

        Parameters
        ----------
        audio_chunk : bytes
            Raw 16-bit LE PCM audio frame (_BYTES_PER_FRAME bytes at 16 kHz).

        Returns
        -------
        bool
            ``True`` if speech is detected for this frame.
        """
        import webrtcvad

        try:
            raw_vad = webrtcvad.Vad()
            raw_vad.set_mode(self.mode)
            detected = raw_vad.is_speech(audio_chunk, _SR)
        except (ValueError, OSError):
            # Invalid frame size or format — treat as silence
            detected = False

        if detected:
            self._chunks_speech += 1
        else:
            self._chunks_speech = max(0, self._chunks_speech - 1)

        # Hysteresis: only flip to "speech" after consecutive frames,
        # and stay in speech state even through brief gaps.
        self.is_speech = self._chunks_speech >= self._chunks_threshold
        return self.is_speech

    def reset(self) -> None:
        """Clear accumulated state so a new utterance starts fresh."""
        self._chunks_speech = 0
        self.is_speech = False


def detect_speech(
    audio_data: bytes,
    sample_rate: int = _SR,
    threshold_frames: int = 2,
) -> bool:
    """Return ``True`` if *audio_data* contains speech regions exceeding
    the threshold of consecutive detected frames.

    Parameters
    ----------
    audio_data : bytes
        Raw PCM samples at *sample_rate* Hz (16-bit signed LE).
    sample_rate : int
        Expected sample rate. Defaults to 16 kHz.
    threshold_frames : int
        Minimum consecutive VAD-positive frames required to confirm speech.
    """
    if len(audio_data) % _BYTES_PER_FRAME != 0:
        logger.warning(
            "Audio data length (%d bytes) is not a multiple of frame size (%d)",
            len(audio_data), _BYTES_PER_FRAME,
        )
        # Trim to nearest frame boundary
        audio_data = audio_data[: (len(audio_data) // _BYTES_PER_FRAME) * _BYTES_PER_FRAME]
        if len(audio_data) == 0:
            return False

    import webrtcvad

    vad = webrtcvad.Vad()
    vad.set_mode(1)

    consecutive_speech = 0
    for i in range(0, len(audio_data), _BYTES_PER_FRAME):
        chunk = audio_data[i : i + _BYTES_PER_FRAME]
        if len(chunk) < _BYTES_PER_FRAME:
            break
        if vad.is_speech(chunk, sample_rate):
            consecutive_speech += 1
            if consecutive_speech >= threshold_frames:
                return True
        else:
            consecutive_speech = 0
    return False


def frame_to_numpy(frame_bytes: bytes) -> np.ndarray:
    """Decode a raw PCM frame into a numpy array of int16 samples."""
    return np.frombuffer(frame_bytes, dtype=np.int16)
