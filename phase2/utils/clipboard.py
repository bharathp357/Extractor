"""
Thread-safe clipboard operations for Phase 2.

Used by HumanInput.paste_text() and TextExtractor clipboard fallback.
"""
import threading
import functools

import pyperclip

_clip_lock = threading.Lock()


def get_clipboard() -> str:
    """Read current clipboard content (thread-safe)."""
    with _clip_lock:
        try:
            return pyperclip.paste() or ""
        except Exception:
            return ""


def set_clipboard(text: str) -> None:
    """Write text to clipboard (thread-safe)."""
    with _clip_lock:
        try:
            pyperclip.copy(text)
        except Exception:
            pass


def save_and_restore_clipboard(func):
    """Decorator: saves clipboard before the call, restores it after."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        saved = get_clipboard()
        try:
            return func(*args, **kwargs)
        finally:
            set_clipboard(saved)
    return wrapper
