"""CustomTkinter-based translucent topmost overlay window."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Optional

import customtkinter as ctk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default visual constants
# ---------------------------------------------------------------------------
_DEFAULT_BG_ALPHA: float = 0.85       # opacity of the background (1 = solid)
_TEXT_COLOR: str = "#ffffff"
_ENGLISH_COLOR: str = "#aaaaaa"      # lighter color for original English line
_FONT_SIZE_RU: int = 18
_FONT_SIZE_EN: int = 14
_MARGINS: int = 16
_MAX_WIDTH: int = 600
_LINE_SPACING: int = 6


class OverlayWindow(ctk.CTkToplevel):
    """A draggable, semi-transparent, always-on-top window for displaying translations.

    The overlay shows each entry as:

        ENGLISH ORIGINAL          (lighter, smaller)
          Русский перевод         (bold, larger)

    It auto-hides when no new content arrives for *hide_delay_ms* milliseconds,
    and reappears immediately when new content is added.
    """

    def __init__(
        self,
        hide_delay_ms: int = 15_000,
        bg_alpha: float = _DEFAULT_BG_ALPHA,
        bilingual: bool = True,
        show_timestamps: bool = False,
    ):
        super().__init__()
        self.title("Voice Assist")
        self.attributes("-topmost", True)
        self.attributes("-alpha", bg_alpha)

        # Make the window translucent (macOS compatibility)
        try:
            self.attributes("-transparent", True)
        except tk.TclError:
            pass  # not supported on this platform

        self._bilingual = bilingual
        self._show_timestamps = show_timestamps
        self._hide_after_ms = hide_delay_ms
        self._last_activity_ms: Optional[int] = None

        # Geometry
        self.geometry(f"{_MAX_WIDTH}x120")
        self.resizable(True, True)

        # Drag tracking
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._is_dragging = False

        # Text area widget
        self._text_area = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._text_area.pack(fill="both", expand=True, padx=_MARGINS, pady=_MARGINS)

        # Bind drag events on the outer frame
        self.bind("<Button-1>", self._on_drag_start)
        self.bind("<B1-Motion>", self._on_drag_move)

        # Hide timer
        self.withdraw()  # start hidden; show() activates it
        self._schedule_hide()

    # ---- public API -------------------------------------------------------

    @property
    def is_visible(self) -> bool:
        return self.winfo_viewable()

    @property
    def bilingual(self) -> bool:
        return self._bilingual

    @bilingual.setter
    def bilingual(self, value: bool) -> None:
        self._bilingual = value

    @property
    def show_timestamps(self) -> bool:
        return self._show_timestamps

    @show_timestamps.setter
    def show_timestamps(self, value: bool) -> None:
        self._show_timestamps = value

    def show(self) -> None:
        """Show the window and cancel any scheduled auto-hide."""
        self.deiconify()
        self.lift()
        self.focus_force()
        self._last_activity_ms = self._current_ms()
        self.after_cancel(self._hide_timer) if hasattr(self, "_hide_timer") else None
        self._schedule_hide()

    def hide(self) -> None:
        """Hide the window (keeps it alive for future use)."""
        self.withdraw()

    def toggle_visibility(self) -> None:
        if self.is_visible:
            self.hide()
        else:
            self.show()

    def add_entry(self, english: str, russian: str) -> None:
        """Append a new translation entry to the overlay scrollable area."""
        self.show()
        self._last_activity_ms = self._current_ms()
        self._reset_hide_timer()

        frame = ctk.CTkFrame(self._text_area, corner_radius=6)
        frame.pack(fill="x", pady=(0, _LINE_SPACING))

        if self._show_timestamps:
            from datetime import datetime
            time_str = datetime.now().strftime("%H:%M:%S")
            time_label = ctk.CTkLabel(
                frame, text=f"[{time_str}]", font=("monospace", 9),
                text_color="#666666", anchor="w",
            )
            time_label.pack(side="left", padx=(0, 8), pady=2)

        # English line
        if self._bilingual:
            en_label = ctk.CTkLabel(
                frame,
                text=english.strip(),
                font=ctk.CTkFont(size=_FONT_SIZE_EN),
                text_color=_ENGLISH_COLOR,
                wraplength=_MAX_WIDTH - 40,
                anchor="w",
            )
            en_label.pack(fill="x", padx=4, pady=2)

        # Russian line (always shown)
        ru_label = ctk.CTkLabel(
            frame,
            text=russian.strip(),
            font=ctk.CTkFont(size=_FONT_SIZE_RU, weight="bold"),
            text_color=_TEXT_COLOR,
            wraplength=_MAX_WIDTH - 40,
            anchor="w",
        )
        ru_label.pack(fill="x", padx=4, pady=2)

        # Auto-scroll to the bottom
        self._text_area.canvas.yview_moveto(1.0)

    def clear(self) -> None:
        """Remove all entries from the overlay."""
        for child in self._text_area.winfo_children():
            child.destroy()

    # ---- dragging ---------------------------------------------------------

    def _on_drag_start(self, event: tk.Event) -> None:
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self._is_dragging = True

    def _on_drag_move(self, event: tk.Event) -> None:
        if not self._is_dragging:
            return
        dx = event.x - self._drag_start_x
        dy = event.y - self._drag_start_y
        geo = self.geometry().split("+")
        x = int(geo[0]) + dx if len(geo) > 1 else 0
        y = int(geo[1]) + dy if len(geo) > 1 else 0
        w, h = geo[0].split("x")
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ---- auto-hide --------------------------------------------------------

    def _schedule_hide(self) -> None:
        if hasattr(self, "_hide_timer"):
            self.after_cancel(self._hide_timer)
        self._hide_timer = self.after(self._hide_after_ms, self._auto_hide)

    def _reset_hide_timer(self) -> None:
        if hasattr(self, "_hide_timer"):
            self.after_cancel(self._hide_timer)
        self._schedule_hide()

    def _auto_hide(self) -> None:
        now = self._current_ms()
        if self._last_activity_ms and (now - self._last_activity_ms) >= self._hide_after_ms:
            self.hide()

    @staticmethod
    def _current_ms() -> int:
        return int(__import__("time").time() * 1000)
