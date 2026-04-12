"""
Phase 2 Base Automator — extends the original BaseAutomator with OS-level
automation primitives instead of Selenium WebDriver.

BACKGROUND-SAFE: All input uses UIA element methods (SetValue, Invoke)
and PostMessage. The user's mouse and keyboard are NEVER taken over.
"""
import time
import os
import importlib.util

# Load providers/base.py directly without triggering providers/__init__.py
# This prevents the circular import: phase2.base -> providers -> phase2.providers -> phase2.base
_base_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "providers", "base.py")
_spec = importlib.util.spec_from_file_location("providers.base", _base_path)
_base_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base_mod)
BaseAutomator = _base_mod.BaseAutomator

from phase2.text_extractor import TextExtractor
from phase2.background_input import BackgroundInput
from phase2 import config as p2config


class Phase2BaseAutomator(BaseAutomator):
    """
    Phase 2 base class for all AI provider automators.

    BACKGROUND-SAFE: Uses UIA ValuePattern, InvokePattern, and PostMessage.
    Does NOT move the physical mouse or take over the keyboard.
    """

    def __init__(self, window_manager):
        # Store as browser_manager for BaseAutomator compatibility
        super().__init__(window_manager)
        self.window_manager = window_manager
        self.bg_input = BackgroundInput(window_manager)
        self.extractor = TextExtractor(window_manager)

    # ─────────────────── Overrides ───────────────────

    def _wait_page_ready(self, driver=None, timeout: float = 10) -> bool:
        """
        Wait until the page appears loaded.
        Phase 2: checks the window title changes (indicates page load).
        """
        initial_title = self.window_manager.get_title()
        deadline = time.time() + timeout
        while time.time() < deadline:
            title = self.window_manager.get_title()
            # Title changes once page loads (e.g., "New Tab" -> "Google")
            if title and title != initial_title:
                return True
            # Also accept if title is already meaningful
            if title and "new tab" not in title.lower():
                return True
            time.sleep(0.3)
        return True  # Proceed anyway after timeout

    def reconnect(self) -> None:
        """Re-establish connection to Chrome."""
        if not self.window_manager.is_alive():
            print(f"[{self.provider_name}] Chrome dead — restarting...")
            self.window_manager.restart()
        else:
            self.window_manager.close_tab(self.provider_name)
        self._in_conversation = False
        self._conversation_count = 0

    def close(self) -> None:
        """Close this provider's tab."""
        self.window_manager.close_tab(self.provider_name)
        self._in_conversation = False
        self._conversation_count = 0

    # ─────────────────── Shared Helpers (Background-Safe) ───────────────────

    def _switch_to_tab(self) -> bool:
        """Switch Chrome to this provider's tab."""
        self.extractor.invalidate_cache()
        return self.window_manager.switch_to(self.provider_name)

    def _navigate(self, url: str):
        """Navigate the current tab to a URL."""
        self.extractor.invalidate_cache()
        self.window_manager.navigate(url)

    def _find_and_fill_input(self, prompt: str) -> bool:
        """
        Find the chat input field and fill it with the prompt text.
        Uses UIA ValuePattern.SetValue() — no physical keyboard needed.
        """
        return self.bg_input.find_and_fill_input(self.provider_name, prompt)

    def _click_send_button(self) -> bool:
        """
        Find and click the Send button via UIA InvokePattern.
        Falls back to pressing Enter via PostMessage.
        No physical mouse movement.
        """
        return self.bg_input.find_and_click_send()

    def _send_enter(self) -> bool:
        """Send Enter key via PostMessage (no physical keyboard)."""
        return self.bg_input.send_enter()

    def _poll_response_loop(self, pre_text: str = "",
                             min_response_len: int = 50) -> dict:
        """
        Poll for AI response completion using UIA text extraction.
        Uses diff-based approach: only returns text that is NEW since pre_text.

        Returns: {"text": str, "poll_count": int, "polling_ms": int}
        """
        t_start = time.perf_counter()
        last_text = ""
        stable_count = 0
        poll_count = 0
        content_appeared = False
        pre_len = len(pre_text) if pre_text else 0
        deadline = time.time() + p2config.RESPONSE_TIMEOUT

        while time.time() < deadline:
            poll_count += 1

            result = self.extractor.poll_response(self.provider_name)
            streaming = result["streaming"]
            current_text = result["text"]
            current_len = len(current_text) if current_text else 0

            # Streaming detected — reset stability
            if streaming:
                stable_count = 0
                if current_text and current_len > pre_len + 20:
                    last_text = current_text
                    content_appeared = True
                time.sleep(p2config.RESPONSE_POLL_INTERVAL)
                continue

            # Check if real content appeared (not just noise)
            if current_text and current_len > max(pre_len + 20, min_response_len):
                if not content_appeared:
                    content_appeared = True
                    last_text = current_text
                    stable_count = 0
                    time.sleep(p2config.RESPONSE_POLL_INTERVAL)
                    continue

            # Stability check — only after content has appeared
            if content_appeared and current_text:
                if current_text == last_text:
                    stable_count += 1
                    if stable_count >= p2config.STABLE_CHECKS:
                        break
                else:
                    stable_count = 0
                    last_text = current_text

            time.sleep(p2config.RESPONSE_POLL_INTERVAL)

        polling_ms = round((time.perf_counter() - t_start) * 1000)

        # Diff-based: extract only the NEW text (after pre_text)
        final_text = self._extract_new_text(last_text, pre_text)

        return {
            "text": final_text,
            "poll_count": poll_count,
            "polling_ms": polling_ms,
        }

    @staticmethod
    def _extract_new_text(full_text: str, pre_text: str) -> str:
        """
        Extract only the new text that appeared after pre_text.
        This ensures we only return the LATEST AI response, not the full
        conversation history.
        """
        if not pre_text or not full_text:
            return full_text or ""

        # If the full text starts with the pre_text, return only the new part
        if full_text.startswith(pre_text):
            new_part = full_text[len(pre_text):].strip()
            if new_part:
                return new_part

        # Fuzzy diff: find the longest common prefix and return the rest
        # This handles cases where UIA fragments shift slightly between polls
        pre_lines = pre_text.strip().split("\n")
        full_lines = full_text.strip().split("\n")

        if not pre_lines or not full_lines:
            return full_text

        # Find where the new content starts by matching from the end of pre_text
        # Look for the last line of pre_text in the full text
        last_pre_line = pre_lines[-1].strip()
        if last_pre_line and len(last_pre_line) > 10:
            for i, line in enumerate(full_lines):
                if line.strip() == last_pre_line:
                    # Everything after this line is new
                    new_lines = full_lines[i + 1:]
                    if new_lines:
                        return "\n".join(new_lines).strip()

        # If pre_text is a subset of full_text (common with conversation history),
        # try to find where they diverge
        match_idx = 0
        min_len = min(len(pre_lines), len(full_lines))
        for i in range(min_len):
            if pre_lines[i].strip() == full_lines[i].strip():
                match_idx = i + 1
            else:
                break

        if match_idx > 0 and match_idx < len(full_lines):
            new_lines = full_lines[match_idx:]
            result = "\n".join(new_lines).strip()
            if result:
                return result

        # Fallback: return full text if we can't isolate the diff
        return full_text

    @staticmethod
    def _clean_response(text: str, noise_exact: frozenset,
                        noise_substr: list) -> str:
        """
        Clean response text by removing noise lines.
        Reusable by all providers — same logic as Phase 1.
        """
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned.append("")
                continue
            if stripped.lower() in noise_exact:
                continue
            if any(ns in stripped.lower() for ns in noise_substr):
                continue
            cleaned.append(stripped)

        # Remove leading/trailing blank lines
        result = "\n".join(cleaned).strip()
        # Collapse 3+ consecutive blank lines into 2
        while "\n\n\n" in result:
            result = result.replace("\n\n\n", "\n\n")
        return result
