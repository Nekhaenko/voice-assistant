"""Entry point and full pipeline wiring for the Voice Interview Assistant."""

from __future__ import annotations

import logging
import signal
import sys
import threading
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("voice_assist")

# Globals for lifecycle management
_stream = None                # audio.StreamHandle
_overlay = None               # overlay.OverlayWindow
_memory = None                # memory.SessionMemory
_translator = None            # translator.TranslatorEngine
_buffer = None                # speech.SlidingWindowBuffer
_settings = None              # config.AppSettings
_running = False


def _on_utterance(audio_bytes: bytes) -> None:
    """Callback invoked by the sliding window buffer when an utterance is ready.

    Runs on the audio thread — does transcription + translation synchronously,
    then dispatches UI updates via after() to stay on the Tk event loop thread.
    """
    global _overlay, _memory, _translator

    if not audio_bytes:
        return

    try:
        # 1. Transcribe via Vosk
        from voice_assist.speech import WhisperEngine
        engine = WhisperEngine()
        english_text = engine.transcribe(audio_bytes)

        if not english_text:
            logger.debug("No speech detected in utterance, skipping")
            return

        # 2. Translate to Russian
        russian_text = _translator.translate_en_ru(english_text) if _translator else english_text

        # 3. Store in session memory
        if _memory:
            _memory.add(english_text, russian_text)

        logger.info("Translated: %s → %s", english_text[:60], russian_text[:60])

        # 4. Dispatch to overlay on Tkinter event thread
        if _overlay:
            _overlay.after(0, lambda e=english_text, r=russian_text: _overlay.add_entry(e, r))

    except Exception as exc:
        logger.error("Pipeline error in _on_utterance: %s", exc)


def _start_capture() -> None:
    """Start the audio capture pipeline."""
    global _stream, _running, _buffer

    if _running:
        return

    from voice_assist.audio.capture import open_stream
    from voice_assist.speech import SlidingWindowBuffer

    device_idx = _settings.audio_source_index if _settings else -1
    device_name = str(device_idx) if device_idx >= 0 else None

    try:
        _stream = open_stream(device_name_or_index=device_name)
        _stream.start()
    except Exception as exc:
        logger.error("Failed to open audio stream: %s", exc)
        sys.stderr.write(
            f"ERROR: Could not open audio device.\n"
            f"Install a loopback driver (e.g., BlackHole on macOS).\n"
            f"Details: {exc}\n"
        )
        return

    # Create buffer with transcription callback
    _buffer = SlidingWindowBuffer(on_utterance=_on_utterance)
    _running = True
    logger.info("Audio capture started")

    # Read loop — process frames on the main thread via after() to keep Tkinter responsive
    _read_loop()


def _read_loop() -> None:
    """Read audio frames and push them into the sliding window buffer.

    Runs on the Tkinter event loop thread to avoid threading issues with
    overlay updates. Uses after() for non-blocking reads.
    """
    global _stream, _running

    if not _running or not _stream:
        return

    try:
        frame = _stream.read(1024)
        if _buffer:
            _buffer.push(frame)
    except Exception as exc:
        logger.error("Error reading audio stream: %s", exc)
        _stop_capture()
        return

    # Schedule next read (non-blocking)
    _stream._root.after(10, _read_loop)  # noqa: SLF001 — private attr but needed for tk reference


def _stop_capture() -> None:
    """Stop the audio capture pipeline."""
    global _stream, _running, _buffer

    if _buffer:
        _buffer.flush()
        _buffer.reset()
        _buffer = None

    if _stream:
        try:
            _stream.stop()
        except Exception:
            pass
        try:
            _stream.close()
        except Exception:
            pass
        _stream = None

    _running = False
    logger.info("Audio capture stopped")


def _toggle_capture() -> None:
    """Toggle audio capture on/off."""
    if _running:
        _stop_capture()
    else:
        _start_capture()


def _export_session() -> None:
    """Export current session memory to a text file."""
    if not _memory:
        return
    try:
        path = _memory.export_txt()
        logger.info("Session exported to %s", path)
    except Exception as exc:
        logger.error("Export failed: %s", exc)


def _on_settings_close(new_settings: dict) -> None:
    """Callback when Settings dialog is closed with new values."""
    global _settings, _overlay
    if "bilingual" in new_settings and _overlay:
        _overlay.bilingual = new_settings["bilingual"]
    if "opacity" in new_settings:
        _overlay.attributes("-alpha", new_settings["opacity"])
    if "timestamps" in new_settings:
        _overlay.show_timestamps = new_settings["timestamps"]
    # Save settings to disk
    _settings = _settings or type("Settings", (), {})()
    for key, value in new_settings.items():
        setattr(_settings, key, value)
    try:
        _settings.save()
    except AttributeError:
        pass  # _settings is a plain dict-like object


def main() -> None:
    """Application entry point — wires up all modules and starts the UI."""
    import customtkinter as ctk

    ctk.set_appearance_mode("dark")
    ctk.set_dpi_scaling(True)

    global _overlay, _memory, _translator, _settings

    # 1. Load settings
    from voice_assist.config.settings import AppSettings
    _settings = AppSettings.load()

    # 2. Initialize translator
    from voice_assist.translator.engine import TranslatorEngine
    _translator = TranslatorEngine()

    # 3. Initialize session memory
    from voice_assist.memory.session import SessionMemory
    _memory = SessionMemory()

    # 4. Create overlay window
    from voice_assist.overlay.window import OverlayWindow
    _overlay = OverlayWindow(
        hide_delay_ms=15000,
        bg_alpha=_settings.overlay_opacity,
        bilingual=_settings.bilingual,
        show_timestamps=_settings.timestamps_enabled,
    )
    _overlay.geometry("+50+50")  # default position

    # 5. Create floating controls
    from voice_assist.ui.tray import FloatingControls, SettingsDialog

    controls = FloatingControls(
        on_start=lambda: _toggle_capture(),
        on_stop=lambda: _toggle_capture(),
        on_settings=_open_settings,
        on_minimize=lambda: None,  # overlay manages its own visibility
    )
    controls.set_position(0, 0)

    # 6. Set up hotkey toggle (Tkinter's after() based approach for portability)
    def _hotkey_toggle():
        _overlay.toggle_visibility()

    # Note: True global hotkey requires platform-specific setup. For now,
    # the toggle button in the controls panel serves the same purpose.
    # A real implementation would register:
    #   - macOS: CGEventTap / Quartz hotkey registration
    #   - Windows: pynput.keyboard.GlobalHotKeys
    #   - Linux: xlib global hotkey

    # 7. Mainloop
    logger.info("Starting main loop...")
    try:
        ctk.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        _cleanup()


def _open_settings() -> None:
    """Open the settings dialog."""
    from voice_assist.ui.tray import SettingsDialog

    dialog = SettingsDialog(
        parent_settings=_settings,
        on_bilingual_change=lambda v: (_overlay.__setattr__("bilingual", v) if _overlay else None),
        on_opacity_change=lambda v: (_overlay.configure(attributes=("-alpha", v)) if _overlay else None),
        on_timestamps_change=lambda v: (_overlay.__setattr__("show_timestamps", v) if _overlay else None),
        on_hotkey_change=lambda h: None,  # stub — global hotkey registration pending
    )
    dialog.grab_set()
    dialog.wait_window()


def _cleanup() -> None:
    """Clean up all resources on exit."""
    global _stream, _overlay, _memory, _buffer

    logger.info("Cleaning up...")

    # Stop capture
    _stop_capture()

    # Clear session memory
    if _memory:
        _memory.clear()

    # Destroy overlay
    if _overlay and hasattr(_overlay, "_root"):
        try:
            _overlay.after_cancel(_overlay._hide_timer)  # noqa: SLF001
        except (AttributeError, TclError):
            pass
        try:
            _overlay.destroy()
        except Exception:
            pass

    logger.info("Cleanup complete")


from tkinter import TclError
