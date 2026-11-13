"""In-memory session storage for English→Russian translation pairs."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TranslationEntry:
    """A single English→Russian translation captured during a session."""

    timestamp: str
    english: str
    russian: str


class SessionMemory:
    """Holds all transcription/translation pairs for the current run.

    Memory is **ephemeral** — it is cleared when the application exits unless
    explicitly exported.  Thread-safe via a simple lock.
    """

    def __init__(self):
        self._entries: List[TranslationEntry] = []
        self._lock = __import__("threading").Lock()

    # ---- public API -------------------------------------------------------

    def add(self, english: str, russian: str) -> TranslationEntry:
        """Append a new (en, ru) pair and return it.

        Parameters
        ----------
        english : str
            Original English text from Whisper transcription.
        russian : str
            Translated Russian text from argos-translate.

        Returns
        -------
        TranslationEntry
            The newly added entry with a generated timestamp.
        """
        entry = TranslationEntry(
            timestamp=datetime.now().isoformat(),
            english=english.strip(),
            russian=russian.strip(),
        )
        with self._lock:
            self._entries.append(entry)
        logger.debug("Added session entry #%d", len(self._entries))
        return entry

    @property
    def entries(self) -> List[TranslationEntry]:
        """Return a snapshot of all entries in chronological order."""
        with self._lock:
            return list(self._entries)

    @property
    def count(self) -> int:
        """Return the number of stored entries."""
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        """Discard all session data. Called on application exit."""
        with self._lock:
            self._entries.clear()
        logger.info("Session memory cleared (%d entries discarded)", self.count)

    # ---- export -----------------------------------------------------------

    def export_txt(self, path: Optional[str] = None) -> Path:
        """Export session memory to a plain-text file (*English → Russian*).

        Parameters
        ----------
        path : str | None
            Target file path. Defaults to ``session_transcript.txt`` in the
            current working directory.

        Returns
        -------
        Path
            The path where the file was written.
        """
        if path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"session_transcript_{ts}.txt"
        p = Path(path)

        lines = []
        with self._lock:
            for entry in self._entries:
                lines.append(f"[{entry.timestamp}] {entry.english}")
                lines.append(f"  → {entry.russian}")
                lines.append("")

        p.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Session exported to %s (%d pairs)", p, self.count)
        return p

    def export_json(self, path: Optional[str] = None) -> Path:
        """Export session memory to a JSON file.

        Each entry is ``{"timestamp": ..., "english": ..., "russian": ...}``.
        """
        if path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"session_transcript_{ts}.json"
        p = Path(path)

        data = {
            "exported_at": datetime.now().isoformat(),
            "pairs": [asdict(e) for e in self.entries],
        }
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Session JSON exported to %s (%d pairs)", p, self.count)
        return p
