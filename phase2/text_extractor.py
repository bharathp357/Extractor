"""
Text Extractor — reads AI response text from Chrome without DOM injection.

BACKGROUND-SAFE: Uses only UIA accessibility tree methods.
No physical mouse or keyboard input needed.

Primary method: Windows UI Automation (UIA) accessibility tree.
Chrome exposes its DOM as UIA elements when launched with --force-renderer-accessibility.
Key discovery: Use descendants(control_type='Document') to find the page root,
then descendants(control_type='Text') to harvest all visible text fragments (~200ms).

Fallback method: Clipboard extraction via PostMessage Ctrl+A/Ctrl+C (background-safe).
"""
import time
import ctypes

from phase2 import config as p2config
from phase2.utils.clipboard import (
    get_clipboard, set_clipboard, save_and_restore_clipboard,
)

# Win32 message constants for background clipboard fallback
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_CONTROL = 0x11
PostMessage = ctypes.windll.user32.PostMessageW


class TextExtractor:
    """
    Extract text from Chrome using UIA accessibility tree.
    BACKGROUND-SAFE: Does NOT move the mouse or take over the keyboard.
    """

    def __init__(self, window_manager):
        self._wm = window_manager
        self._doc_cache = None  # Cache the Document element

    # ─────────────────── Public API ───────────────────

    def get_response_text(self, provider: str) -> str:
        """
        Extract AI response text from the current page via UIA tree.
        Returns the cleaned response string, or "" if extraction fails.
        """
        text = self._extract_via_uia(provider)
        if text and len(text.strip()) > 10:
            return text.strip()

        # Fallback to clipboard (background-safe via PostMessage)
        text = self._extract_via_clipboard()
        if text and len(text.strip()) > 10:
            return text.strip()

        return ""

    def detect_streaming(self, provider: str) -> bool:
        """
        Check if the AI is still generating a response.
        Searches the UIA tree for "Stop" / "Thinking" buttons.
        """
        doc = self._find_document()
        if not doc:
            return False

        try:
            streaming_keywords = self._get_streaming_keywords(provider)
            buttons = doc.descendants(control_type="Button")
            for btn in buttons:
                try:
                    name = (btn.element_info.name or "").lower()
                    for keyword in streaming_keywords:
                        if keyword in name:
                            return True
                except Exception:
                    continue
        except Exception:
            pass

        return False

    def poll_response(self, provider: str) -> dict:
        """
        Combined poll: check streaming status + extract text in one call.
        Returns {streaming: bool, text: str}.
        """
        streaming = self.detect_streaming(provider)
        text = self.get_response_text(provider)
        return {"streaming": streaming, "text": text}

    def invalidate_cache(self):
        """Clear cached Document element (call after tab switch or navigation)."""
        self._doc_cache = None

    # ─────────────────── UIA Extraction ───────────────────

    def _find_document(self):
        """
        Find the Chrome Document element in the UIA tree.
        Uses descendants(control_type='Document') which is fast (~60ms).
        Caches the result since the Document element persists across page loads.
        """
        if self._doc_cache is not None:
            # Verify cache is still valid
            try:
                _ = self._doc_cache.element_info.name
                return self._doc_cache
            except Exception:
                self._doc_cache = None

        window = self._wm.get_uia_window()
        if not window:
            return None

        try:
            docs = window.descendants(control_type="Document")
            if docs:
                self._doc_cache = docs[0]
                return self._doc_cache
        except Exception:
            pass

        return None

    def _extract_via_uia(self, provider: str) -> str:
        """
        Extract text from Chrome's UIA tree using descendants(control_type='Text').
        This returns individual text fragments from the page (~200ms total).
        """
        doc = self._find_document()
        if not doc:
            return ""

        try:
            # Harvest ALL Text elements from the Document
            text_elements = doc.descendants(control_type="Text")
            fragments = []
            for el in text_elements:
                try:
                    name = el.element_info.name
                    if name and name.strip():
                        fragments.append(name.strip())
                except Exception:
                    continue

            if not fragments:
                return ""

            # Provider-specific filtering and assembly
            if provider == "google":
                return self._isolate_google_response(fragments)
            elif provider == "gemini":
                return self._isolate_gemini_response(fragments)
            elif provider == "chatgpt":
                return self._isolate_chatgpt_response(fragments)

            return "\n".join(fragments)
        except Exception as e:
            print(f"[phase2/extractor] UIA extraction error: {e}")
            return ""

    # ─────────────────── Fragment Assembly ───────────────────

    @staticmethod
    def _join_fragments(fragments: list) -> str:
        """
        Intelligently join UIA text fragments into readable text.

        Rules:
          - Fragments ending with ':' get a newline after (they're headers/labels)
          - Short fragments (<80 chars) without ending punctuation get space-joined
          - Fragments that end a sentence get their own line
        """
        if not fragments:
            return ""

        lines = []
        buffer = ""

        for frag in fragments:
            frag = frag.strip()
            if not frag:
                continue

            is_header = frag.endswith(":")

            buffer_is_partial = (
                buffer
                and len(buffer) < 80
                and not buffer.endswith((".", "!", "?", ":", ";"))
                and not is_header
            )

            if buffer_is_partial:
                buffer = buffer + " " + frag
            else:
                if buffer:
                    lines.append(buffer)
                buffer = frag

            if frag.endswith((".", "!", "?")) or is_header:
                lines.append(buffer)
                buffer = ""

        if buffer:
            lines.append(buffer)

        return "\n".join(lines)

    # ─────────────────── Provider-Specific Isolation ───────────────────

    def _isolate_google_response(self, fragments: list) -> str:
        """
        Isolate the AI response from Google AI Mode UIA text fragments.
        Strategy: Skip header noise, collect from first real content
        until source citations or footer noise.
        """
        noise_exact = frozenset({
            "accessibility links", "skip to main content", "accessibility help",
            "accessibility feedback", "ai mode", "filters and topics",
            "sign in", "search results", "ai overview", "main menu",
            "search", "images", "news", "videos", "maps", "more",
            "tools", "safesearch", "all", "about", "feedback",
            "search labs", "ai mode response is ready", "new tab",
        })

        noise_substr = [
            "ai can make mistakes", "double-check responses",
            "you can now share this thread", "quick results from the web",
            "google.com", "google account:", "google apps",
            "set google chrome", "set as default",
        ]

        # Find the query text fragment (first non-noise fragment > 5 chars)
        query_idx = -1
        for i, frag in enumerate(fragments):
            fl = frag.lower()
            if fl in noise_exact:
                continue
            if any(ns in fl for ns in noise_substr):
                continue
            if len(frag) > 5:
                query_idx = i
                break

        if query_idx < 0:
            return ""

        # Skip the query itself
        start_idx = query_idx + 1

        # Source citation markers
        source_markers = [
            " - wikipedia", " - w3schools", " - aws", "search results",
            "ai mode response is ready", "geeksforgeeks", "stackoverflow",
            "medium.com", "reddit.com",
        ]

        import re
        _DATE_PATTERN = re.compile(r'\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}', re.I)
        _URL_PATTERN = re.compile(r'[a-z0-9]+\.(com|org|net|io|dev|in)\b', re.I)

        cleaned = []
        for frag in fragments[start_idx:]:
            fl = frag.lower()
            if fl in noise_exact:
                continue
            if any(ns in fl for ns in noise_substr):
                continue
            if any(sm in fl for sm in source_markers):
                break
            if "..." in frag and len(frag) > 60:
                break
            if _DATE_PATTERN.search(frag) and _URL_PATTERN.search(frag):
                break
            if len(frag.strip()) < 1:
                continue
            cleaned.append(frag)

        return self._join_fragments(cleaned)

    def _isolate_gemini_response(self, fragments: list) -> str:
        """
        Isolate the LAST AI response from Gemini UIA text fragments.

        The full UIA tree contains ALL conversation history:
          ["You said <query1>", "Gemini said", ...response...,
           "You said <query2>", "Gemini said", ...response..., etc.]

        Strategy: Find the LAST "Gemini said" marker and return
        only the content after it (the most recent response).
        """
        noise_exact = frozenset({
            "gemini", "new chat", "recent", "thinking", "thinking...",
            "show thinking", "gem manager", "settings", "help",
            "activity", "gemini apps", "new tab", "main menu",
            "home", "explore", "conversation with gemini",
        })
        noise_substr = [
            "gemini may display inaccurate info",
            "gemini is ai and can make mistakes",
            "google privacy", "check your responses",
            "gemini is thinking", "google account:",
            "ask gemini", "you stopped this response",
        ]

        # Find the LAST "Gemini said" marker
        last_gemini_idx = -1
        for i, frag in enumerate(fragments):
            fl = frag.lower().strip()
            if fl == "gemini said" or fl.startswith("gemini said"):
                last_gemini_idx = i

        # If no marker found, fall back to returning all cleaned text
        if last_gemini_idx < 0:
            cleaned = []
            for frag in fragments:
                fl = frag.lower().strip()
                if fl in noise_exact:
                    continue
                if any(ns in fl for ns in noise_substr):
                    continue
                if fl.startswith("you said"):
                    continue
                if fl == "gemini said" or fl.startswith("gemini said"):
                    continue
                if len(frag.strip()) < 2:
                    continue
                cleaned.append(frag)
            return self._join_fragments(cleaned)

        # Take everything AFTER the last "Gemini said" marker
        cleaned = []
        for frag in fragments[last_gemini_idx + 1:]:
            fl = frag.lower().strip()
            if fl in noise_exact:
                continue
            if any(ns in fl for ns in noise_substr):
                continue
            # Stop at the next "You said" (user's follow-up query)
            if fl.startswith("you said"):
                break
            if fl == "gemini said" or fl.startswith("gemini said"):
                break
            if len(frag.strip()) < 2:
                continue
            cleaned.append(frag)

        return self._join_fragments(cleaned)

    def _isolate_chatgpt_response(self, fragments: list) -> str:
        """
        Isolate the LAST AI response from ChatGPT UIA text fragments.

        ChatGPT conversation structure:
          ["You", "user query", "ChatGPT said:", ...response...,
           "You", "user query2", "ChatGPT said:", ...response2...]

        Strategy: Find the LAST "ChatGPT said:" and return content after it.
        """
        noise_exact = frozenset({
            "chatgpt", "new chat", "upgrade", "gpt-4o", "gpt-4",
            "temporary chat", "today", "yesterday", "previous 7 days",
            "explore gpts", "my gpts", "you", "chatgpt said:",
            "send a message", "message chatgpt", "new tab",
        })
        noise_substr = [
            "chatgpt can make mistakes", "memory updated",
            "openai", "terms of use", "privacy policy",
            "check important info", "free research preview",
            "consider checking important info",
        ]

        # Find the LAST "ChatGPT said:" marker
        last_marker_idx = -1
        for i, frag in enumerate(fragments):
            fl = frag.lower().strip()
            if fl == "chatgpt said:" or fl.startswith("chatgpt said"):
                last_marker_idx = i

        if last_marker_idx < 0:
            # No marker — return all cleaned text
            cleaned = []
            for frag in fragments:
                fl = frag.lower()
                if fl in noise_exact:
                    continue
                if any(ns in fl for ns in noise_substr):
                    continue
                if len(frag.strip()) < 2:
                    continue
                cleaned.append(frag)
            return self._join_fragments(cleaned)

        # Take everything AFTER the last "ChatGPT said:" marker
        cleaned = []
        for frag in fragments[last_marker_idx + 1:]:
            fl = frag.lower().strip()
            if fl in noise_exact:
                continue
            if any(ns in fl for ns in noise_substr):
                continue
            # Stop at the next user turn
            if fl == "you":
                break
            if fl == "chatgpt said:" or fl.startswith("chatgpt said"):
                break
            if len(frag.strip()) < 2:
                continue
            cleaned.append(frag)

        return self._join_fragments(cleaned)

    # ─────────────────── Clipboard Fallback (Background-Safe) ───────────────────

    @save_and_restore_clipboard
    def _extract_via_clipboard(self) -> str:
        """
        Fallback text extraction via clipboard.
        Uses PostMessage Ctrl+A/Ctrl+C — does NOT use physical keyboard.
        """
        hwnd = self._get_hwnd()
        if not hwnd:
            return ""

        # Clear clipboard first
        set_clipboard("")
        time.sleep(0.05)

        # Select all via PostMessage Ctrl+A
        vk_a = ord('A')
        PostMessage(hwnd, WM_KEYDOWN, VK_CONTROL, 0)
        time.sleep(0.01)
        PostMessage(hwnd, WM_KEYDOWN, vk_a, 0)
        time.sleep(0.01)
        PostMessage(hwnd, WM_KEYUP, vk_a, 0)
        time.sleep(0.01)
        PostMessage(hwnd, WM_KEYUP, VK_CONTROL, 0)
        time.sleep(0.3)

        # Copy via PostMessage Ctrl+C
        vk_c = ord('C')
        PostMessage(hwnd, WM_KEYDOWN, VK_CONTROL, 0)
        time.sleep(0.01)
        PostMessage(hwnd, WM_KEYDOWN, vk_c, 0)
        time.sleep(0.01)
        PostMessage(hwnd, WM_KEYUP, vk_c, 0)
        time.sleep(0.01)
        PostMessage(hwnd, WM_KEYUP, VK_CONTROL, 0)
        time.sleep(0.3)

        # Deselect via Escape
        vk_esc = 0x1B
        PostMessage(hwnd, WM_KEYDOWN, vk_esc, 0)
        time.sleep(0.01)
        PostMessage(hwnd, WM_KEYUP, vk_esc, 0)

        text = get_clipboard()
        return text if text else ""

    def _get_hwnd(self):
        """Get the native window handle for PostMessage."""
        window = self._wm.get_uia_window()
        if window:
            try:
                return window.handle
            except Exception:
                pass
        return None

    # ─────────────────── Streaming Detection Helpers ───────────────────

    @staticmethod
    def _get_streaming_keywords(provider: str) -> list:
        """Return keywords that indicate active response generation."""
        base = ["stop", "cancel"]
        if provider == "google":
            return base
        elif provider == "gemini":
            return base + ["thinking"]
        elif provider == "chatgpt":
            return base + ["stop generating", "stop streaming"]
        return base
