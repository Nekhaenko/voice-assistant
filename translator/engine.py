"""Translation engine wrapping deep-translator (Google Translate).

Note: This environment's package mirror blocks torch (required by argos-translate's
stanza dependency), so we use deep-translator which wraps Google Translate.
It requires internet access but needs no API key and is free for reasonable usage.
"""

from __future__ import annotations

import logging
import threading
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Network check
# ---------------------------------------------------------------------------

_HOSTS_TO_CHECK = ("translate.google.com", "www.google.com")


def is_online(timeout: float = 3.0) -> bool:
    """Quick connectivity check against known Google hosts.

    Returns ``True`` if at least one host responds within *timeout* seconds.
    """
    for host in _HOSTS_TO_CHECK:
        try:
            urllib.request.urlopen(f"https://{host}", timeout=timeout)
            return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# Thread-safe engine singleton
# ---------------------------------------------------------------------------

_engine = None
_lock = threading.Lock()


def _get_engine():
    """Lazily create and cache the translation engine."""
    global _engine
    if _engine is not None:
        return _engine
    with _lock:
        if _engine is not None:
            return _engine
        try:
            from deep_translator import GoogleTranslator
            _engine = GoogleTranslator(source="en", target="ru")
            logger.info("deep-translator (Google) engine initialized successfully")
        except ImportError:
            logger.error(
                "deep-translator not installed. Install with: pip install deep-translator"
            )
            raise
    return _engine


class TranslatorEngine:
    """Thread-safe wrapper around a deep-translator translation instance."""

    def __init__(self):
        self._translator = _get_engine()

    def translate_en_ru(self, text: str) -> str:
        """Translate *text* from English to Russian via Google Translate.

        If no internet connection is available, returns the original English text.

        Parameters
        ----------
        text : str
            Source English text.

        Returns
        -------
        str
            Translated Russian text.  If translation fails or returns empty,
            the original English *text* is returned unchanged.
        """
        if not text or not text.strip():
            return text

        # Quick online check before attempting translation
        if not is_online():
            logger.debug("No internet connection — returning original text")
            return text

        try:
            result = self._translator.translate(text.strip())
            return result if result else text  # fallback to original
        except Exception as exc:
            logger.warning("deep-translator failed for '%s': %s", text[:40], exc)
            return text  # fallback: return original


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def translate_en_ru(text: str) -> str:
    """One-shot translation convenience function.

    Not ideal for repeated calls in a running application — use
    :class:`TranslatorEngine` instead.
    """
    engine = TranslatorEngine()
    return engine.translate_en_ru(text)
