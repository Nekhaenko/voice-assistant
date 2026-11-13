"""Audio capture module using sounddevice (PortAudio ctypes binding)."""

from __future__ import annotations

import io
import logging
import wave
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_SAMPLE_RATE: int = 16000
_CHANNELS: int = 1
_DTYPE = np.int16


def enumerate_sources() -> List[Tuple[str, int]]:
    """Return a list of ``(name, index)`` tuples for all available audio devices.

    Uses sounddevice's portaudio binding which is available on all platforms
    that ship with CoreAudio (macOS) or equivalent.
    """
    import sounddevice as sd

    devices = sd.query_devices()
    sources: List[Tuple[str, int]] = []
    for i, dev in enumerate(devices):
        name = f"{dev['name']} (in={dev['max_input_channels']}, out={dev['max_output_channels']})"
        sources.append((name, i))
        logger.debug("Discovered device %d: %s", i, name)

    if not sources:
        logger.warning("No audio devices found — ensure a loopback driver is installed")
    return sources


def open_stream(
    device_name_or_index: Optional[str] = None,
    sample_rate: int = _SAMPLE_RATE,
    channels: int = _CHANNELS,
    chunk_frames: int = 1024,
) -> "StreamHandle":
    """Open a sounddevice callback stream reading raw PCM from *device_name_or_index*.

    Parameters
    ----------
    device_name_or_index : str | int | None
        If ``None``, uses the default input device.  Accepts either an index
        returned by :func:`enumerate_sources` or a partial match against device
        names (case-insensitive substring match).
    sample_rate : int
        Desired sample rate in Hz (default 16 kHz).
    channels : int
        Number of audio channels (default 1 = mono).
    chunk_frames : int
        Number of frames per read call (default 1024).

    Returns
    -------
    StreamHandle
        A context-managed handle with ``.read()`` and ``.close()`` methods.

    Raises
    ------
    OSError
        If the device cannot be opened (typically indicates a missing
        virtual-audio driver such as BlackHole on macOS).
    """
    import sounddevice as sd

    device_index = _resolve_device(device_name_or_index)
    info = sd.query_devices(device_index)
    logger.info(
        "Opening device %d (%s) at %d Hz / %d ch",
        device_index, info["name"], sample_rate, channels,
    )

    # Use a callback-free stream for simplicity (we read in chunks)
    stream = sd.InputStream(
        device=device_index,
        samplerate=sample_rate,
        channels=channels,
        blocksize=chunk_frames,
        dtype="int16",
        callback=None,  # we'll read manually via .read()
    )
    return StreamHandle(stream)


def _resolve_device(name_or_idx):
    """Return the device index matching *name_or_idx*.

    If *name_or_idx* is ``None`` return the default input device.
    If it is an integer, use it directly.
    Otherwise perform a case-insensitive substring search over device names.
    """
    import sounddevice as sd

    if name_or_idx is None:
        devices = sd.query_devices()
        return int(devices[sd.default.device[0]]["index"])  # default input
    if isinstance(name_or_idx, int):
        return name_or_idx
    target = str(name_or_idx).lower()
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        dev_name = dev["name"].lower()
        if target in dev_name:
            return i
    raise ValueError(
        f"Device '{name_or_idx}' not found. Available devices:\n"
        + "\n".join(f"  {i}: {dev['name']}" for i, dev in enumerate(devices))
    )


# ---------------------------------------------------------------------------
# Stream handle — thin wrapper around a sounddevice InputStream
# ---------------------------------------------------------------------------

class StreamHandle:
    """Context-managed wrapper around a sounddevice input stream.

    Provides :meth:`read` returning raw bytes, :meth:`read_numpy` returning
    a numpy array, and :meth:`to_wav` which captures frames into an in-memory
    WAV file.
    """

    def __init__(self, stream):
        self._stream = stream

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()

    def read(self, num_frames: int = 1024) -> bytes:
        """Read *num_frames* frames as raw bytes."""
        data, overflowed = self._stream.read(num_frames)
        if overflowed:
            logger.warning("Input stream overflow detected")
        return data.tobytes()

    def read_numpy(self, num_frames: int = 1024) -> np.ndarray:
        """Read *num_frames* frames and decode them into a numpy array."""
        data, _ = self._stream.read(num_frames)
        return data.flatten()

    def to_wav(self, duration_sec: float = 3.0) -> bytes:
        """Capture audio for *duration_sec* seconds and return WAV bytes."""
        total_frames = int(_SAMPLE_RATE * duration_sec)
        frames: List[bytes] = []
        frames_read = 0

        self.start()
        try:
            while frames_read < total_frames:
                count = min(1024, total_frames - frames_read)
                data, _ = self._stream.read(count)
                frames.append(data.tobytes())
                frames_read += count
        finally:
            self.stop()
            self.close()

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(_CHANNELS)
            wf.setsampwidth(2)          # 16-bit
            wf.setframerate(_SAMPLE_RATE)
            wf.writeframes(b"".join(frames))

        return buf.getvalue()

    def close(self) -> None:
        self._stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()
