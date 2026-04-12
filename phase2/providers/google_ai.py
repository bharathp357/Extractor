"""
Google AI Mode — Phase 2 provider using OS-level automation.

BACKGROUND-SAFE: All input uses UIA SetValue/Invoke and PostMessage.
The user's mouse and keyboard are NEVER taken over.

Input: Navigate to google.com/search?q=QUERY&udm=50 via address bar.
Follow-up: Fill follow-up textarea via UIA SetValue, press Enter via PostMessage.
Response: UIA tree extraction + clipboard fallback.
Streaming: Detect "Stop" button via UIA tree.
"""
import time
import urllib.parse

from phase2.base import Phase2BaseAutomator
from phase2 import config as p2config


# Noise filters (reused from Phase 1 google_ai.py)
_NOISE_EXACT = frozenset({
    "accessibility links", "skip to main content", "ai mode",
    "sign in", "search results", "ai overview", "main menu",
    "search", "images", "news", "videos", "maps", "more",
    "tools", "safesearch", "all", "about", "feedback",
    "all filters", "search modes", "web", "shopping",
})

_NOISE_SUBSTR = [
    "ai can make mistakes", "double-check responses",
    "you can now share this thread", "quick results from the web:",
    "google search", "privacy policy", "terms of service",
    "how search works", "learn more",
]


class GoogleAIModeAutomator(Phase2BaseAutomator):
    """Google AI Mode automator — fully background-safe."""

    provider_name = "google"
    display_name = "Google AI Mode"

    def send_and_get_response(self, prompt: str) -> dict:
        """Send a new query to Google AI Mode."""
        result = self._make_result(prompt)
        t_start = time.perf_counter()

        with self.window_manager.lock:
            try:
                # Switch to Google tab
                self._switch_to_tab()
                time.sleep(0.3)

                # Navigate to AI Mode URL
                t_nav = time.perf_counter()
                encoded = urllib.parse.quote_plus(prompt)
                url = f"https://www.google.com/search?q={encoded}&udm=50"
                self._navigate(url)

                # Wait for page to load + AI response to start generating
                time.sleep(3.0)
                self._wait_page_ready(timeout=10)
                nav_ms = round((time.perf_counter() - t_nav) * 1000)

                # Poll for response
                poll_result = self._poll_response_loop()

                # Clean the response
                response = self._clean_response(
                    poll_result["text"], _NOISE_EXACT, _NOISE_SUBSTR
                )

                # Verify it's real content (not just the query echoed back)
                if self._is_content_real(response, prompt):
                    result["response"] = response
                    result["success"] = True
                else:
                    result["response"] = response or "[No AI response detected]"
                    result["success"] = bool(response)

                result["timing"] = {
                    "navigation_ms": nav_ms,
                    "polling_ms": poll_result["polling_ms"],
                    "poll_count": poll_result["poll_count"],
                    "total_ms": round((time.perf_counter() - t_start) * 1000),
                }

                self._in_conversation = True
                self._conversation_count += 1

            except Exception as e:
                result["response"] = f"[Error: {e}]"
                result["success"] = False

        return result

    def send_followup(self, prompt: str) -> dict:
        """Send a follow-up in the current Google AI conversation."""
        result = self._make_result(prompt)
        t_start = time.perf_counter()

        with self.window_manager.lock:
            try:
                self._switch_to_tab()
                time.sleep(0.3)

                # Get pre-text for diff-based extraction
                pre_text = self.extractor.get_response_text(self.provider_name)

                t_input = time.perf_counter()

                # Find and fill the follow-up input via UIA (no mouse/keyboard)
                if not self._find_and_fill_input(prompt):
                    # Fallback: try sending via PostMessage
                    self.bg_input.send_tab()
                    time.sleep(0.3)
                    self.bg_input.send_text_via_messages(prompt)

                time.sleep(0.15)

                # Submit via PostMessage Enter
                self._send_enter()
                input_ms = round((time.perf_counter() - t_input) * 1000)

                # Wait for new response
                time.sleep(1.0)

                # Poll for response
                poll_result = self._poll_response_loop(pre_text=pre_text)

                response = self._clean_response(
                    poll_result["text"], _NOISE_EXACT, _NOISE_SUBSTR
                )

                result["response"] = response
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
        """Reset — Google AI Mode is stateless (URL-based)."""
        self._in_conversation = False
        self._conversation_count = 0

    def get_status(self) -> dict:
        return {
            "provider": self.provider_name,
            "display_name": self.display_name,
            "connected": self.window_manager.is_alive(),
            "in_conversation": self._in_conversation,
            "conversation_count": self._conversation_count,
            "mode": "phase2",
        }

    def is_logged_in(self) -> bool:
        # Google AI Mode doesn't require login
        return True

    @staticmethod
    def _is_content_real(text: str, prompt: str) -> bool:
        """Check that scraped text isn't just the query echoed back."""
        if not text:
            return False
        clean = text.strip().lower()
        prompt_lower = prompt.strip().lower()
        # If the response is basically just the prompt, it's not real
        if clean == prompt_lower or clean.startswith(prompt_lower) and len(clean) < len(prompt_lower) + 20:
            return False
        return len(clean) > 20
