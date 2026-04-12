"""
Gemini Pro — Phase 2 provider using OS-level automation.

BACKGROUND-SAFE: All input uses UIA SetValue/Invoke and PostMessage.
The user's mouse and keyboard are NEVER taken over.

Input: Fill chat input via UIA SetValue, press Enter via PostMessage.
Response: UIA tree extraction of last model response.
Streaming: Detect "thinking"/"stop" buttons via UIA tree.
Chat persistence: Saves conversation URL to .chat_urls.json.
"""
import json
import time

from phase2.base import Phase2BaseAutomator
from phase2 import config as p2config


# Noise filters (reused from Phase 1 gemini.py)
_NOISE_EXACT = frozenset({
    "gemini", "new chat", "recent", "thinking", "thinking...",
    "show thinking", "gem manager", "settings", "help",
    "activity", "gemini apps", "home", "explore",
    "answer now", "analysis", "approach", "reasoning",
})

_NOISE_SUBSTR = [
    "gemini may display inaccurate info",
    "google privacy", "check your responses",
    "gemini is thinking", "report a legal issue",
    "your conversations", "double-check responses",
]

# Thinking artifact phrases (Phase 1 logic)
_ARTIFACT_PHRASES = frozenset({
    "answer now", "show thinking", "analysis", "approach",
    "reasoning", "let me think", "thinking...", "observation",
    "plan", "step 1", "step 2",
})


class GeminiProAutomator(Phase2BaseAutomator):
    """Gemini Pro automator — fully background-safe."""

    provider_name = "gemini"
    display_name = "Gemini Pro"

    def __init__(self, window_manager):
        super().__init__(window_manager)
        self._chat_url = ""
        self._load_chat_url()

    def _load_chat_url(self):
        """Load saved chat URL from disk."""
        try:
            with open(p2config.CHAT_URLS_FILE, "r") as f:
                saved = json.load(f)
            self._chat_url = saved.get("gemini", "")
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._chat_url = ""

    def _save_chat_url(self):
        """Save current chat URL to disk."""
        try:
            try:
                with open(p2config.CHAT_URLS_FILE, "r") as f:
                    saved = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                saved = {}
            saved["gemini"] = self._chat_url
            with open(p2config.CHAT_URLS_FILE, "w") as f:
                json.dump(saved, f, indent=2)
        except Exception:
            pass

    def send_and_get_response(self, prompt: str) -> dict:
        """Send a new prompt to Gemini."""
        result = self._make_result(prompt)
        t_start = time.perf_counter()

        with self.window_manager.lock:
            try:
                # Switch to Gemini tab
                self._switch_to_tab()
                time.sleep(0.5)

                # If not in conversation, navigate to Gemini
                if not self._in_conversation:
                    t_nav = time.perf_counter()
                    self._navigate(p2config.GEMINI_URL)
                    time.sleep(2.0)
                    self._wait_page_ready(timeout=10)
                    nav_ms = round((time.perf_counter() - t_nav) * 1000)
                else:
                    nav_ms = 0

                # Get pre-text for diff-based extraction
                pre_text = self.extractor.get_response_text(self.provider_name)

                # Find input and fill via UIA (no mouse/keyboard)
                t_input = time.perf_counter()
                if not self._find_and_fill_input(prompt):
                    # Fallback: type via WM_CHAR messages
                    self.bg_input.send_text_via_messages(prompt)

                time.sleep(0.2)

                # Submit via PostMessage Enter
                self._send_enter()
                input_ms = round((time.perf_counter() - t_input) * 1000)

                # Wait for response to start
                time.sleep(1.5)

                # Poll for response (diff-based)
                poll_result = self._poll_response_loop(pre_text=pre_text)

                # Clean response
                response = self._clean_response(
                    poll_result["text"], _NOISE_EXACT, _NOISE_SUBSTR
                )

                # Filter thinking artifacts
                if self._looks_like_artifact(response):
                    response = ""

                result["response"] = response or "[No response detected]"
                result["success"] = bool(response)
                result["timing"] = {
                    "navigation_ms": nav_ms,
                    "input_ms": input_ms,
                    "polling_ms": poll_result["polling_ms"],
                    "poll_count": poll_result["poll_count"],
                    "total_ms": round((time.perf_counter() - t_start) * 1000),
                }

                self._in_conversation = True
                self._conversation_count += 1

                # Save chat URL
                url = self.window_manager.get_address_bar_url()
                if url and "gemini.google.com" in url:
                    self._chat_url = url
                    self._save_chat_url()

            except Exception as e:
                result["response"] = f"[Error: {e}]"
                result["success"] = False

        return result

    def send_followup(self, prompt: str) -> dict:
        """Send a follow-up message in the current Gemini conversation."""
        result = self._make_result(prompt)
        t_start = time.perf_counter()

        with self.window_manager.lock:
            try:
                self._switch_to_tab()
                time.sleep(0.3)

                # Get pre-text for diff-based extraction
                pre_text = self.extractor.get_response_text(self.provider_name)

                # Find input and fill via UIA (no mouse/keyboard)
                t_input = time.perf_counter()
                if not self._find_and_fill_input(prompt):
                    self.bg_input.send_text_via_messages(prompt)

                time.sleep(0.2)
                self._send_enter()
                input_ms = round((time.perf_counter() - t_input) * 1000)

                time.sleep(1.5)
                poll_result = self._poll_response_loop(pre_text=pre_text)

                response = self._clean_response(
                    poll_result["text"], _NOISE_EXACT, _NOISE_SUBSTR
                )

                if self._looks_like_artifact(response):
                    response = ""

                result["response"] = response or "[No response detected]"
                result["success"] = bool(response)
                result["timing"] = {
                    "input_ms": input_ms,
                    "polling_ms": poll_result["polling_ms"],
                    "poll_count": poll_result["poll_count"],
                    "total_ms": round((time.perf_counter() - t_start) * 1000),
                }
                self._conversation_count += 1

            except Exception as e:
                result["response"] = f"[Error: {e}]"
                result["success"] = False

        return result

    def new_conversation(self) -> None:
        """Start a new Gemini conversation."""
        with self.window_manager.lock:
            self._switch_to_tab()
            time.sleep(0.3)
            self._navigate(p2config.GEMINI_URL)
            time.sleep(2.0)
        self._in_conversation = False
        self._conversation_count = 0
        self._chat_url = ""
        self._save_chat_url()

    def get_status(self) -> dict:
        return {
            "provider": self.provider_name,
            "display_name": self.display_name,
            "connected": self.window_manager.is_alive(),
            "in_conversation": self._in_conversation,
            "conversation_count": self._conversation_count,
            "chat_url": self._chat_url,
            "mode": "phase2",
        }

    def is_logged_in(self) -> bool:
        """Check if logged in by looking at the window title."""
        title = self.window_manager.get_title()
        if not title:
            return False
        title_lower = title.lower()
        return "sign in" not in title_lower and "login" not in title_lower

    @staticmethod
    def _looks_like_artifact(text: str) -> bool:
        """Check if text is just thinking-phase artifacts."""
        if not text:
            return True
        lines = [l.strip().lower() for l in text.split("\n") if l.strip()]
        if not lines:
            return True
        return all(l in _ARTIFACT_PHRASES for l in lines)
