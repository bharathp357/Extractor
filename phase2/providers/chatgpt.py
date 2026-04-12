"""
ChatGPT — Phase 2 provider using OS-level automation.

BACKGROUND-SAFE: All input uses UIA SetValue/Invoke and PostMessage.
The user's mouse and keyboard are NEVER taken over.

Input: Fill prompt textarea via UIA SetValue, click Send via Invoke or press Enter via PostMessage.
Response: UIA tree extraction of last assistant response.
Streaming: Detect "Stop generating" button via UIA tree.
Chat persistence: Saves conversation URL to .chat_urls.json.
"""
import json
import time

from phase2.base import Phase2BaseAutomator
from phase2 import config as p2config


# Noise filters (reused from Phase 1 chatgpt.py)
_NOISE_EXACT = frozenset({
    "chatgpt", "new chat", "upgrade", "gpt-4o", "gpt-4",
    "temporary chat", "today", "yesterday", "previous 7 days",
    "explore gpts", "my gpts", "you", "chatgpt said:",
    "send a message", "message chatgpt",
})

_NOISE_SUBSTR = [
    "chatgpt can make mistakes", "memory updated",
    "openai", "terms of use", "privacy policy",
    "check important info", "free research preview",
    "consider checking important info",
]


class ChatGPTAutomator(Phase2BaseAutomator):
    """ChatGPT automator — fully background-safe."""

    provider_name = "chatgpt"
    display_name = "ChatGPT"

    def __init__(self, window_manager):
        super().__init__(window_manager)
        self._chat_url = ""
        self._load_chat_url()

    def _load_chat_url(self):
        """Load saved chat URL from disk."""
        try:
            with open(p2config.CHAT_URLS_FILE, "r") as f:
                saved = json.load(f)
            self._chat_url = saved.get("chatgpt", "")
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
            saved["chatgpt"] = self._chat_url
            with open(p2config.CHAT_URLS_FILE, "w") as f:
                json.dump(saved, f, indent=2)
        except Exception:
            pass

    def send_and_get_response(self, prompt: str) -> dict:
        """Send a new prompt to ChatGPT."""
        result = self._make_result(prompt)
        t_start = time.perf_counter()

        with self.window_manager.lock:
            try:
                # Switch to ChatGPT tab
                self._switch_to_tab()
                time.sleep(0.5)

                # Navigate to ChatGPT if not in conversation
                if not self._in_conversation:
                    t_nav = time.perf_counter()
                    self._navigate(p2config.CHATGPT_URL)
                    time.sleep(2.5)
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

                # Click send button via UIA Invoke, or Enter via PostMessage
                self._click_send_button()
                input_ms = round((time.perf_counter() - t_input) * 1000)

                # Wait for response to start
                time.sleep(1.5)

                # Poll for response (diff-based)
                poll_result = self._poll_response_loop(pre_text=pre_text)

                # Clean response
                response = self._clean_response(
                    poll_result["text"], _NOISE_EXACT, _NOISE_SUBSTR
                )

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
                if url and "chatgpt.com" in url and "/c/" in url:
                    self._chat_url = url
                    self._save_chat_url()

            except Exception as e:
                result["response"] = f"[Error: {e}]"
                result["success"] = False

        return result

    def send_followup(self, prompt: str) -> dict:
        """Send a follow-up message in the current ChatGPT conversation."""
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
                self._click_send_button()
                input_ms = round((time.perf_counter() - t_input) * 1000)

                time.sleep(1.5)
                poll_result = self._poll_response_loop(pre_text=pre_text)

                response = self._clean_response(
                    poll_result["text"], _NOISE_EXACT, _NOISE_SUBSTR
                )

                result["response"] = response or "[No response detected]"
                result["success"] = bool(response)
                result["timing"] = {
                    "input_ms": input_ms,
                    "polling_ms": poll_result["polling_ms"],
                    "poll_count": poll_result["poll_count"],
                    "total_ms": round((time.perf_counter() - t_start) * 1000),
                }
                self._conversation_count += 1

                # Update chat URL
                url = self.window_manager.get_address_bar_url()
                if url and "chatgpt.com" in url and "/c/" in url:
                    self._chat_url = url
                    self._save_chat_url()

            except Exception as e:
                result["response"] = f"[Error: {e}]"
                result["success"] = False

        return result

    def new_conversation(self) -> None:
        """Start a new ChatGPT conversation."""
        with self.window_manager.lock:
            self._switch_to_tab()
            time.sleep(0.3)
            self._navigate(p2config.CHATGPT_URL)
            time.sleep(2.5)
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
        """Check if logged in by examining the window title."""
        title = self.window_manager.get_title()
        if not title:
            return False
        title_lower = title.lower()
        return "log in" not in title_lower and "sign up" not in title_lower
