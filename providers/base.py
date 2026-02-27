"""
Base Automator — Abstract interface for all AI provider scrapers.

Every provider (Google AI Mode, Gemini Pro, ChatGPT) must extend this class.
The BrowserManager owns the shared Chrome instance; providers get the driver
via self.browser_manager and switch to their own tab before every operation.
"""
from abc import ABC, abstractmethod
from typing import Optional
import time


class BaseAutomator(ABC):
    """
    Shared contract for all AI scrapers.

    Subclasses MUST implement the abstract methods.
    The base class provides:
      - Standard result dict construction
      - Provider name / display label
      - Follow-up conversation state tracking
    """

    provider_name: str = "base"          # override in subclass
    display_name: str = "Base Provider"  # shown in UI

    def __init__(self, browser_manager):
        self.browser_manager = browser_manager
        self._in_conversation: bool = False   # True after first prompt in a session
        self._conversation_count: int = 0     # Number of exchanges in current conversation

    # ──────────────── Abstract Methods ────────────────

    @abstractmethod
    def send_and_get_response(self, prompt: str) -> dict:
        """
        Send a NEW prompt (starts a new conversation or navigates to a fresh page).
        Returns standard result dict.
        """
        ...

    @abstractmethod
    def send_followup(self, prompt: str) -> dict:
        """
        Send a follow-up message within an existing conversation.
        Returns standard result dict.
        """
        ...

    @abstractmethod
    def new_conversation(self) -> None:
        """Reset conversation state so the next prompt starts fresh."""
        ...

    @abstractmethod
    def get_status(self) -> dict:
        """Return provider-specific status info."""
        ...

    @abstractmethod
    def is_logged_in(self) -> bool:
        """Check if the provider's tab is authenticated (for login-required providers)."""
        ...

    # ──────────────── Shared Helpers ────────────────

    def _make_result(self, prompt: str) -> dict:
        """Build the standard result dict skeleton."""
        return {
            "prompt": prompt,
            "response": "",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "success": False,
            "provider": self.provider_name,
            "timing": {},
        }

    def _wait_page_ready(self, driver, timeout: float = 5) -> bool:
        """Wait until page reaches interactive or complete state."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                state = driver.execute_script("return document.readyState")
                if state in ("interactive", "complete"):
                    return True
            except Exception:
                pass
            time.sleep(0.1)
        return False

    def reconnect(self) -> None:
        """
        Re-open the tab for this provider.
        BrowserManager handles the actual tab lifecycle.
        """
        self.browser_manager.close_tab(self.provider_name)
        self._in_conversation = False
        self._conversation_count = 0

    def close(self) -> None:
        """Close this provider's tab."""
        self.browser_manager.close_tab(self.provider_name)
        self._in_conversation = False
        self._conversation_count = 0
