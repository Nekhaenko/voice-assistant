"""Sliding window audio buffer with VAD-driven flushing.

Accumulates raw audio frames, detects speech boundaries via VAD, and flushes
complete utterances to a transcription callback. Silence-only windows are
discarded.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Callable, Optional

from voice_assist.audio.vad import VadState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SAMPLE_RATE: int = 16000
_FRAME_SIZE: int = _SAMPLE_RATE * 0.030  # 30 ms frames at 16 kHz → 480 bytes
_MAX_BUFFER_SEC: float = 3.0              # max buffer duration before forced flush
_SILENCE_GAP_SEC: float = 0.5             # silence gap to trigger flush


class SlidingWindowBuffer:
    """Ring buffer that accumulates audio and flushes utterances on speech boundaries.

    Usage::

        buffer = SlidingWindowBuffer(on_utterance=transcribe_callback)
        # In your audio read loop:
        for frame in audio_stream:
            buffer.push(frame)
        buffer.flush()  # call on shutdown or long silence
    """

    def __init__(
        self,
        on_utterance: Callable[[bytes], None],
        sample_rate: int = _SAMPLE_RATE,
        max_buffer_sec: float = _MAX_BUFFER_SEC,
        silence_gap_sec: float = _SILENCE_GAP_SEC,
    ):
        self._on_utterance = on_utterance
        self._sample_rate = sample_rate
        self._max_buffer_sec = max_buffer_sec
        self._silence_gap_sec = silence_gap_sec

        self._frames: deque[bytes] = deque()
        self._total_samples: int = 0
        self._silence_since: int = 0       # frame count since last speech
        self._lock = threading.Lock()
        self._vad_state = VadState(window_size=3, threshold=0.6)

    # ---- public API -------------------------------------------------------

    def push(self, frame: bytes) -> None:
        """Push one raw PCM frame into the buffer.

        Parameters
        ----------
        frame : bytes
            Raw 16-bit PCM audio at *sample_rate* Hz, mono.
        """
        with self._lock:
            self._frames.append(frame)
            self._total_samples += len(frame) // 2  # 16-bit = 2 bytes per sample

            vad_result = self._vad_state.update(frame)
            if vad_result:
                self._silence_since = 0
            else:
                self._silence_since += 1

            # Check if we should flush
            silence_frames = int(self._silence_gap_sec / 0.030)  # ~30ms per frame
            buffer_frames = self._total_samples // self._sample_rate

            if vad_result is False and self._silence_since >= silence_frames:
                # VAD silence gap detected — flush accumulated speech
                self._flush_locked()
            elif buffer_frames >= int(self._max_buffer_sec):
                # Buffer full — forced flush
                logger.debug("Max buffer duration reached (%.1fs), forcing flush", self._max_buffer_sec)
                self._flush_locked()

    def flush(self) -> None:
        """Force-flush any remaining buffered frames."""
        with self._lock:
            self._flush_locked()

    def reset(self) -> None:
        """Clear all buffered frames and reset VAD state."""
        with self._lock:
            self._frames.clear()
            self._total_samples = 0
            self._silence_since = 0
            self._vad_state.reset()

    @property
    def is_speech_active(self) -> bool:
        return self._vad_state.is_speech

    # ---- internal ---------------------------------------------------------

    def _flush_locked(self) -> None:
        """Flush buffered frames to the transcription callback. Must be called
        with *self._lock* held.

        Silences-only flushes are discarded (no callback invoked).
        """
        if not self._frames:
            return

        # Check if any of the buffered frames contained speech
        has_speech = any(
            self._vad_state.update(f) for f in list(self._frames)[:5]
        )

        if not has_speech and self._vad_state._chunks_speech == 0:
            logger.debug("Silence-only buffer flushed — discarding")
            self._frames.clear()
            self._total_samples = 0
            self._silence_since = 0
            self._vad_state.reset()
            return

        # Concatenate all frames into a single WAV-like blob
        raw_audio = b"".join(self._frames)
        num_frames = len(raw_audio) // 2

        if num_frames < self._sample_rate * 0.1:  # less than 100ms — too short
            logger.debug("Flushing <100ms segment — discarding")
            self._frames.clear()
            self._total_samples = 0
            self._silence_since = 0
            self._vad_state.reset()
            return

        try:
            self._on_utterance(raw_audio)
            logger.debug("Flushed %d samples (%.2fs) to transcription callback", num_frames, num_frames / self._sample_rate)
        except Exception as exc:
            logger.error("Transcription callback failed: %s", exc)
        finally:
            self._frames.clear()
            self._total_samples = 0
            self._silence_since = 0
            self._vad_state.reset()
