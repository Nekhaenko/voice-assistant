"""Application configuration management."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class AppSettings:
    """Persistent application settings.

    All values have sensible defaults; only non-default values need to be
    persisted on disk.
    """

    audio_source_index: int = -1              # -1 = default device
    bilingual: bool = True
    overlay_opacity: float = 0.85
    timestamps_enabled: bool = False
    hotkey: str = ""                           # platform-specific default
    overlay_x: int = 50
    overlay_y: int = 50
    _config_path: str = field(default="", repr=False)   # internal

    # ---- serialization ----------------------------------------------------

    @classmethod
    def load(cls, path: Optional[str] = None) -> "AppSettings":
        """Load settings from disk or return defaults.

        Parameters
        ----------
        path : str | None
            Custom config file path. Defaults to ``~/.voice-assist/config.json``.
        """
        config_path = Path(path) if path else cls._default_path()
        settings = cls()
        if config_path.exists():
            try:
                raw = json.loads(config_path.read_text(encoding="utf-8"))
                known_keys = {f.name for f in cls.__dataclass_fields__.values() if not f.name.startswith("_")}
                filtered = {k: v for k, v in raw.items() if k in known_keys}
                settings = cls(**filtered)  # type: ignore[arg-type]
                settings._config_path = str(config_path)
                logger.debug("Loaded settings from %s", config_path)
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("Failed to parse config %s: %s — using defaults", config_path, exc)
        return settings

    def save(self, path: Optional[str] = None) -> None:
        """Persist current settings to disk.

        Parameters
        ----------
        path : str | None
            Custom config file path. Uses the previously loaded path if ``None``.
        """
        config_path = Path(path or self._config_path) if path else self._default_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        data.pop("_config_path", None)
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._config_path = str(config_path)
        logger.debug("Saved settings to %s", config_path)

    @staticmethod
    def _default_path() -> Path:
        home = Path.home() / ".voice-assist"
        home.mkdir(parents=True, exist_ok=True)
        return home / "config.json"

    # ---- platform defaults ------------------------------------------------

    @property
    def hotkey_default(self) -> str:
        if sys.platform == "darwin":
            return "Command+Shift+Space"
        if sys.platform == "win32":
            return "Ctrl+Shift+Space"
        return "Super+Shift+Space"
