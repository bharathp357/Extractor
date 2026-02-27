"""
Gemini Pro Provider — scrapes gemini.google.com

Flow:
  1. First launch: navigate to gemini.google.com, user logs in manually once
     (persistent Chrome profile keeps the session alive across restarts)
  2. Find the chat input (contenteditable div or textarea)
  3. Type prompt, submit
  4. Poll for response stability (streaming detection)
  5. Scrape + clean the response

Supports follow-up conversations natively (Gemini maintains context per chat).
"""
import time
import json
import random
import os

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from providers.base import BaseAutomator
import config


# ── Gemini DOM selectors (discovered via inspection, may need updating) ──
# Input selectors — ordered by specificity
_INPUT_SELECTORS = [
    "div.ql-editor[contenteditable='true']",        # Quill rich-text editor
    "rich-textarea div[contenteditable='true']",     # rich-textarea component
    "div[contenteditable='true'][aria-label*='prompt']",
    "div[contenteditable='true'][role='textbox']",
    "div.input-area-container textarea",
    "textarea[aria-label*='prompt']",
    "div[contenteditable='true']",
]

# Response container selectors
_RESPONSE_SELECTORS = [
    "message-content.model-response-text",           # Gemini's custom element
    ".model-response-text .markdown",                # Markdown rendered response
    "div.response-container-content",
    "div.conversation-container model-response",
    ".response-content",
    "model-response .markdown",
    "message-content .markdown",
    ".markdown-main-panel",
]

# JS: count response elements in DOM
_JS_COUNT_RESPONSES = """
var sels = [
    'message-content.model-response-text .markdown',
    'model-response .markdown',
    '.response-container-content',
    'message-content .markdown',
    '.markdown-main-panel',
    'div[data-test-id="response-content"]'
];
for (var i = 0; i < sels.length; i++) {
    var els = document.querySelectorAll(sels[i]);
    if (els.length > 0) return els.length;
}
return 0;
"""

# JS scrape — get the LAST response element's text
_JS_SCRAPE = """
var sels = [
    'message-content.model-response-text .markdown',
    'model-response .markdown',
    '.response-container-content',
    'message-content .markdown',
    '.markdown-main-panel',
    'div[data-test-id="response-content"]'
];
for (var i = 0; i < sels.length; i++) {
    var els = document.querySelectorAll(sels[i]);
    if (els.length > 0) {
        var last = els[els.length - 1];
        var t = (last.innerText || '').trim();
        if (t.length > 0) return t;
    }
}
return '';
"""

# New chat button selectors
_NEW_CHAT_SELECTORS = [
    "button[aria-label*='New chat']",
    "a[aria-label*='New chat']",
    "button[data-test-id='new-chat']",
    ".new-chat-button",
    "a[href='/app']",
]

# Noise filters
_NOISE_EXACT = frozenset({
    "gemini", "new chat", "recent", "gem manager",
    "help", "activity", "settings", "show more",
    "answer now", "show thinking", "thinking",
    "gemini said", "gemini said...",
})
_NOISE_CONTAINS = (
    "gemini may display inaccurate info",
    "double-check its responses",
    "your chats aren't used",
    "gemini apps activity",
    "report legal issue",
)
# Thinking-phase artifact phrases (appear in response during thinking, before actual answer)
_THINKING_ARTIFACTS = (
    "answer now",
    "gemini said",
    "show thinking",
    "analysis",
    "approach",
    "reasoning",
    "solution",
    "step",
)


class GeminiProAutomator(BaseAutomator):
    """
    Gemini Pro scraper — follows the BaseAutomator interface.
    Uses the shared BrowserManager's Chrome instance (dedicated tab).
    """

    provider_name = "gemini"
    display_name = "Gemini Pro"

    def __init__(self, browser_manager):
        super().__init__(browser_manager)
        self._logged_in = False
        self._chat_url = self._load_chat_url()  # Restore last chat URL
        self._cached_input_sel = None  # Cache the working input selector

    # ──────────────── Core: New Query ────────────────

    def send_and_get_response(self, prompt: str) -> dict:
        result = self._make_result(prompt)

        with self.browser_manager.lock:
            driver = self.browser_manager.driver
            if not driver:
                result["response"] = "ERROR: Browser not connected."
                return result

            try:
                # Ensure tab exists and is active
                if not self.browser_manager.has_tab(self.provider_name):
                    # Use saved chat URL to resume previous conversation
                    start_url = self._chat_url or config.GEMINI_URL
                    self.browser_manager.open_tab(self.provider_name, start_url)
                    self._wait_page_ready(driver, timeout=5)
                    if self._chat_url:
                        self._in_conversation = True
                        print(f"[gemini] Resuming saved chat: {self._chat_url}")
                self.browser_manager.switch_to(self.provider_name)

                # Check login status
                if not self._check_login(driver):
                    result["response"] = ("NOT_LOGGED_IN: Please log in to Gemini. "
                                          "The browser window should be showing the login page. "
                                          "Log in manually, then retry.")
                    return result

                t_total = time.perf_counter()

                # NOTE: No new chat here — all queries go into the SAME chat
                # User must explicitly call new_conversation() for a fresh chat

                # Count existing responses BEFORE sending (to detect new one)
                pre_count = self._count_responses(driver)

                # Type and submit
                t_nav = time.perf_counter()
                if not self._type_and_submit(driver, prompt):
                    result["response"] = "ERROR: Could not find Gemini chat input."
                    return result
                result["timing"]["navigation_ms"] = round((time.perf_counter() - t_nav) * 1000)

                # Wait for NEW response to appear + scrape it
                t_scrape = time.perf_counter()
                text, details = self._wait_and_scrape(driver, pre_count)
                result["timing"]["scrape_ms"] = round((time.perf_counter() - t_scrape) * 1000)
                result["timing"].update(details)

                total_ms = round((time.perf_counter() - t_total) * 1000)
                result["timing"]["total_ms"] = total_ms

                if text:
                    result["response"] = text
                    result["success"] = True
                    self._in_conversation = True
                    self._conversation_count += 1
                    # Save the chat URL so we can resume after restart
                    self._save_current_chat_url(driver)
                    print(f"[gemini] {len(text)} chars in {total_ms}ms | "
                          f"nav={result['timing']['navigation_ms']}ms "
                          f"ph1={details.get('phase1_ms', '?')}ms "
                          f"polls={details.get('poll_count', '?')}")
                else:
                    result["response"] = "ERROR: Could not scrape Gemini response."
                    print(f"[gemini] Failed after {total_ms}ms")

            except Exception as e:
                result["response"] = f"ERROR: {str(e)}"
                print(f"[gemini] Error: {e}")

        return result

    # ──────────────── Follow-Up ────────────────

    def send_followup(self, prompt: str) -> dict:
        # All queries go to same chat — follow-up is the same as send
        return self.send_and_get_response(prompt)

    # ──────────────── Conversation Control ────────────────

    def new_conversation(self) -> None:
        """Start a new chat — only when user explicitly requests it."""
        with self.browser_manager.lock:
            driver = self.browser_manager.driver
            if driver and self.browser_manager.has_tab(self.provider_name):
                try:
                    self.browser_manager.switch_to(self.provider_name)
                    self._click_new_chat(driver)
                except Exception as e:
                    print(f"[gemini] new_conversation click failed: {e}")
        self._in_conversation = False
        self._conversation_count = 0
        self._chat_url = None
        self._save_chat_url(None)  # Clear saved URL

    # ──────────────── Status ────────────────

    def get_status(self) -> dict:
        connected = False
        current_url = ""

        if self.browser_manager.driver and self.browser_manager.has_tab(self.provider_name):
            try:
                with self.browser_manager.lock:
                    self.browser_manager.switch_to(self.provider_name)
                    current_url = self.browser_manager.driver.current_url
                    connected = True
                    self._logged_in = self._check_login(self.browser_manager.driver)
            except Exception:
                connected = False

        return {
            "provider": self.provider_name,
            "display_name": self.display_name,
            "connected": connected,
            "current_url": current_url,
            "in_conversation": self._in_conversation,
            "conversation_count": self._conversation_count,
            "requires_login": True,
            "logged_in": self._logged_in,
        }

    def is_logged_in(self) -> bool:
        return self._logged_in

    # ──────────────── Login Detection ────────────────

    def _check_login(self, driver) -> bool:
        """Check if we're on the Gemini app (logged in) vs login/landing page."""
        url = driver.current_url.lower()
        # If on accounts.google.com or marketing page, not logged in
        if "accounts.google.com" in url:
            return False
        if "gemini.google.com/app" in url or "gemini.google.com/chat" in url:
            # Verify an input is present (actual app, not error page)
            for sel in _INPUT_SELECTORS[:3]:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    if els:
                        self._logged_in = True
                        return True
                except Exception:
                    continue
        # Try broader check
        if "gemini.google.com" in url:
            # Could still be loading — give benefit of doubt if URL is right
            self._logged_in = True
            return True
        return False

    # ──────────────── Input / Submit ────────────────

    def _type_and_submit(self, driver, prompt: str) -> bool:
        """Find the chat input, type the prompt, and submit — JS-optimized."""
        try:
            # Step 1: Find input and set content via JS (saves ~300ms of find_elements)
            typed = driver.execute_script("""
                var inputSels = %s;
                var el = null;
                for (var i = 0; i < inputSels.length; i++) {
                    var found = document.querySelector(inputSels[i]);
                    if (found && found.offsetParent !== null) { el = found; break; }
                }
                if (!el) return 'no-input';
                el.focus();
                el.textContent = arguments[0];
                el.dispatchEvent(new Event('input', {bubbles: true}));
                return 'typed';
            """ % json.dumps(_INPUT_SELECTORS), prompt)

            if typed != 'typed':
                print("[gemini] Could not find chat input element")
                return False

            time.sleep(0.04)  # Let state update

            # Step 2: Submit via JS keyboard event or Selenium Enter key
            # Try Selenium send_keys for reliability (Gemini uses contenteditable)
            for sel in _INPUT_SELECTORS[:3]:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els:
                        if el.is_displayed():
                            el.send_keys(Keys.RETURN)
                            return True
                except Exception:
                    continue

            # Fallback: JS Enter event
            driver.execute_script("""
                var inputSels = %s;
                for (var i = 0; i < inputSels.length; i++) {
                    var el = document.querySelector(inputSels[i]);
                    if (el && el.offsetParent !== null) {
                        el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true}));
                        return;
                    }
                }
            """ % json.dumps(_INPUT_SELECTORS[:3]))
            return True
        except Exception as e:
            print(f"[gemini] Failed to type/submit: {e}")
            return False

    def _click_new_chat(self, driver):
        """Click the New Chat button to start a fresh conversation."""
        for sel in _NEW_CHAT_SELECTORS:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        el.click()
                        self._in_conversation = False
                        self._conversation_count = 0
                        return True
            except Exception:
                continue

        # Fallback: navigate to /app directly
        try:
            driver.get(config.GEMINI_URL)
            time.sleep(1.5)
            self._in_conversation = False
            self._conversation_count = 0
            return True
        except Exception:
            return False

    # ──────────────── Chat URL Persistence ────────────────

    def _load_chat_url(self) -> str:
        """Load saved chat URL from disk (survives restarts)."""
        try:
            if os.path.exists(config.CHAT_URLS_FILE):
                with open(config.CHAT_URLS_FILE, 'r') as f:
                    data = json.load(f)
                url = data.get(self.provider_name, "")
                if url:
                    print(f"[gemini] Loaded saved chat URL: {url}")
                return url
        except Exception:
            pass
        return ""

    def _save_chat_url(self, url: str) -> None:
        """Save chat URL to disk."""
        try:
            data = {}
            if os.path.exists(config.CHAT_URLS_FILE):
                with open(config.CHAT_URLS_FILE, 'r') as f:
                    data = json.load(f)
            if url:
                data[self.provider_name] = url
            else:
                data.pop(self.provider_name, None)
            with open(config.CHAT_URLS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[gemini] Could not save chat URL: {e}")

    def _save_current_chat_url(self, driver) -> None:
        """Capture and save the current Gemini chat URL (has unique conversation ID)."""
        try:
            url = driver.current_url
            if url and "gemini.google.com" in url and url != config.GEMINI_URL:
                self._chat_url = url
                self._save_chat_url(url)
                print(f"[gemini] Saved chat URL: {url}")
        except Exception:
            pass

    def _count_responses(self, driver) -> int:
        """Count response elements in the DOM."""
        try:
            return driver.execute_script(_JS_COUNT_RESPONSES) or 0
        except Exception:
            return 0

    def _is_thinking(self, driver) -> bool:
        """Check if Gemini is still in thinking/generating phase."""
        try:
            result = driver.execute_script("""
                var btns = document.querySelectorAll('button');
                for (var i = 0; i < btns.length; i++) {
                    var t = (btns[i].textContent || '').trim().toLowerCase();
                    var label = (btns[i].getAttribute('aria-label') || '').toLowerCase();
                    if (t === 'thinking' || t === 'thinking...') return true;
                    if (label.indexOf('stop') >= 0 || label.indexOf('cancel') >= 0) {
                        if (btns[i].offsetParent !== null) return true;
                    }
                }
                var spinners = document.querySelectorAll(
                    '.loading-content-spinner-container, [class*="response-loading"], [class*="generating"]'
                );
                for (var i = 0; i < spinners.length; i++) {
                    if (spinners[i].offsetParent !== null) return true;
                }
                return false;
            """)
            return result is True
        except Exception:
            return False

    def _poll_once(self, driver) -> dict:
        """Combined thinking check + scrape in a single JS call (saves ~30-50ms/poll)."""
        try:
            return driver.execute_script("""
                // 1. Check if still thinking/generating
                var btns = document.querySelectorAll('button');
                for (var i = 0; i < btns.length; i++) {
                    var t = (btns[i].textContent || '').trim().toLowerCase();
                    var label = (btns[i].getAttribute('aria-label') || '').toLowerCase();
                    if (t === 'thinking' || t === 'thinking...') return {thinking: true, text: ''};
                    if ((label.indexOf('stop') >= 0 || label.indexOf('cancel') >= 0) && btns[i].offsetParent !== null)
                        return {thinking: true, text: ''};
                }
                var spinners = document.querySelectorAll(
                    '.loading-content-spinner-container, [class*="response-loading"], [class*="generating"]'
                );
                for (var i = 0; i < spinners.length; i++) {
                    if (spinners[i].offsetParent !== null) return {thinking: true, text: ''};
                }
                // 2. Scrape last response
                var sels = [
                    'message-content.model-response-text .markdown',
                    'model-response .markdown',
                    '.response-container-content',
                    'message-content .markdown',
                    '.markdown-main-panel',
                    'div[data-test-id="response-content"]'
                ];
                for (var i = 0; i < sels.length; i++) {
                    var els = document.querySelectorAll(sels[i]);
                    if (els.length > 0) {
                        var last = els[els.length - 1];
                        var txt = (last.innerText || '').trim();
                        if (txt.length > 0) return {thinking: false, text: txt};
                    }
                }
                return {thinking: false, text: ''};
            """) or {"thinking": False, "text": ""}
        except Exception:
            return {"thinking": False, "text": ""}

    def _looks_like_artifact(self, text: str) -> bool:
        """Check if scraped text looks like thinking-phase artifacts rather than real response."""
        if not text:
            return True
        low = text.lower().strip()
        # Only reject if it's PURELY artifact phrases (not mixed with real content)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        # Check if ALL lines are artifact/noise phrases
        artifact_lines = 0
        for line in lines:
            low_line = line.lower()
            if low_line in _NOISE_EXACT:
                artifact_lines += 1
            elif any(a in low_line for a in _THINKING_ARTIFACTS):
                artifact_lines += 1
        # Only reject if EVERY line is an artifact
        if len(lines) > 0 and artifact_lines == len(lines):
            return True
        return False

    # ──────────────── Wait + Scrape ────────────────

    def _wait_and_scrape(self, driver, pre_count: int = 0) -> tuple:
        details = {"poll_count": 0, "polling_ms": 0, "phase1_ms": 0}
        last_text = ""
        stable_count = 0
        new_response_detected = False
        text_change_count = 0  # Track how many times text changed (streaming evidence)

        t_poll = time.perf_counter()
        deadline = time.perf_counter() + config.AI_RESPONSE_TIMEOUT

        # Phase 1: Wait for a NEW response element to appear in the DOM
        while time.perf_counter() < deadline:
            cur_count = self._count_responses(driver)
            if cur_count > pre_count:
                new_response_detected = True
                break
            time.sleep(0.08)
        details["phase1_ms"] = round((time.perf_counter() - t_poll) * 1000)

        # Phase 2: Wait for thinking to finish + stability polling
        while time.perf_counter() < deadline:
            details["poll_count"] += 1

            # Combined thinking check + scrape in ONE JS call
            poll = self._poll_once(driver)

            # If Gemini is still thinking/generating, don't check stability
            if poll.get("thinking"):
                stable_count = 0
                time.sleep(config.AI_RESPONSE_POLL)
                continue

            current_text = (poll.get("text") or "").strip()

            # Skip thinking artifacts (not the real response yet)
            if self._looks_like_artifact(current_text):
                stable_count = 0
                time.sleep(config.AI_RESPONSE_POLL)
                continue

            if current_text and len(current_text) > 0:
                if current_text == last_text:
                    stable_count += 1
                    # Accept stability if:
                    # (a) we saw streaming (text changed at least once after initial appear), OR
                    # (b) text is substantial (>50 chars = likely real response), OR
                    # (c) enough stability checks passed (longer wait = more confident)
                    min_checks = config.STABLE_CHECKS
                    if text_change_count == 0 and len(current_text) < 50:
                        # No streaming evidence + short text: require extra stability
                        min_checks = config.STABLE_CHECKS + 2
                    if stable_count >= min_checks:
                        details["polling_ms"] = round((time.perf_counter() - t_poll) * 1000)
                        return self._clean_response(current_text), details
                else:
                    text_change_count += 1
                    stable_count = 0
                    last_text = current_text

            time.sleep(config.AI_RESPONSE_POLL)

        details["polling_ms"] = round((time.perf_counter() - t_poll) * 1000)
        final = last_text if last_text else self._scrape_via_js(driver)
        return (self._clean_response(final) if final else ""), details

    def _scrape_via_js(self, driver) -> str:
        try:
            text = driver.execute_script(_JS_SCRAPE)
            if text and len(text.strip()) > 0:
                return text.strip()
        except Exception:
            pass
        return ""

    # ──────────────── Text Cleaning ────────────────

    def _clean_response(self, text: str) -> str:
        lines = text.split("\n")
        cleaned = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            low = stripped.lower()
            if low in _NOISE_EXACT:
                continue
            if any(n in low for n in _NOISE_CONTAINS):
                continue
            cleaned.append(stripped)

        return "\n".join(cleaned).strip()
