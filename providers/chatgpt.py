"""
ChatGPT Provider — scrapes chatgpt.com

Flow:
  1. First launch: navigate to chatgpt.com, user logs in manually once
     (persistent Chrome profile keeps session alive).
     Cloudflare challenge typically auto-passes with stealth patches.
  2. Find the chat textarea (#prompt-textarea)
  3. Type prompt, submit
  4. Poll for response stability (streaming detection via "Stop generating" button)
  5. Scrape + clean the response

Supports follow-up conversations natively (ChatGPT maintains context per chat).
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


# ── ChatGPT DOM selectors ──
# Input selectors
_INPUT_SELECTORS = [
    "#prompt-textarea",
    "textarea[data-id='root']",
    "div#prompt-textarea[contenteditable='true']",
    "div[contenteditable='true'][data-placeholder*='Message']",
    "textarea[placeholder*='Message']",
    "div[id='prompt-textarea']",
]

# Send button selectors
_SEND_SELECTORS = [
    "button[data-testid='send-button']",
    "button[aria-label='Send prompt']",
    "button[aria-label='Send']",
    "form button[type='submit']",
]

# Response container selectors — last match = most recent response
_RESPONSE_SELECTORS = [
    "div[data-message-author-role='assistant']",
    "div.agent-turn",
    ".markdown.prose",
    "div[data-testid*='conversation-turn']",
]

# JS: count assistant response elements
_JS_COUNT_RESPONSES = """
var sels = [
    'div[data-message-author-role="assistant"] .markdown',
    'div[data-message-author-role="assistant"]',
    'div.agent-turn .markdown',
    '.markdown.prose'
];
for (var i = 0; i < sels.length; i++) {
    var els = document.querySelectorAll(sels[i]);
    if (els.length > 0) return els.length;
}
return 0;
"""

# JS scrape: get the LAST assistant response
_JS_SCRAPE = """
var sels = [
    'div[data-message-author-role="assistant"] .markdown',
    'div[data-message-author-role="assistant"]',
    'div.agent-turn .markdown',
    '.markdown.prose'
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

# Streaming detection: "Stop generating" button present = still streaming
_STOP_SELECTORS = [
    "button[aria-label='Stop generating']",
    "button[data-testid='stop-button']",
    "button[aria-label='Stop streaming']",
]

# New chat button selectors
_NEW_CHAT_SELECTORS = [
    "a[href='/']",
    "button[aria-label*='New chat']",
    "nav a[href='/']",
    "a[data-testid='create-new-chat-button']",
]

# Noise filters
_NOISE_EXACT = frozenset({
    "chatgpt", "new chat", "upgrade", "upgrade plan",
    "get plus", "gpt-4o", "gpt-4", "today",
    "yesterday", "previous 7 days",
})
_NOISE_CONTAINS = (
    "chatgpt can make mistakes",
    "check important info",
    "free research preview",
    "our terms",
    "openai",
    "memory updated",
)


class ChatGPTAutomator(BaseAutomator):
    """
    ChatGPT scraper — follows the BaseAutomator interface.
    Uses the shared BrowserManager's Chrome instance (dedicated tab).
    """

    provider_name = "chatgpt"
    display_name = "ChatGPT"

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
                    start_url = self._chat_url or config.CHATGPT_URL
                    self.browser_manager.open_tab(self.provider_name, start_url)
                    self._wait_page_ready(driver, timeout=5)
                    if self._chat_url:
                        self._in_conversation = True
                        print(f"[chatgpt] Resuming saved chat: {self._chat_url}")
                self.browser_manager.switch_to(self.provider_name)

                # Check login
                if not self._check_login(driver):
                    result["response"] = ("NOT_LOGGED_IN: Please log in to ChatGPT. "
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
                    result["response"] = "ERROR: Could not find ChatGPT input."
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
                    print(f"[chatgpt] {len(text)} chars in {total_ms}ms | "
                          f"nav={result['timing']['navigation_ms']}ms "
                          f"ph1={details.get('phase1_ms', '?')}ms "
                          f"polls={details.get('poll_count', '?')}")
                else:
                    result["response"] = "ERROR: Could not scrape ChatGPT response."
                    print(f"[chatgpt] Failed after {total_ms}ms")

            except Exception as e:
                result["response"] = f"ERROR: {str(e)}"
                print(f"[chatgpt] Error: {e}")

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
                    print(f"[chatgpt] new_conversation click failed: {e}")
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
        """Check if we're on the ChatGPT app (logged in) vs auth page."""
        url = driver.current_url.lower()

        # Auth pages
        if "auth0.openai.com" in url or "auth.openai.com" in url:
            return False
        if "login" in url or "signup" in url:
            return False

        # Cloudflare challenge page
        if "challenges" in url or "cdn-cgi" in url:
            return False

        # On chatgpt.com — verify input exists
        if "chatgpt.com" in url or "chat.openai.com" in url:
            for sel in _INPUT_SELECTORS[:3]:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    if els:
                        self._logged_in = True
                        return True
                except Exception:
                    continue
            # URL is right, might still be loading
            self._logged_in = True
            return True

        return False

    # ──────────────── Input / Submit ────────────────

    def _type_and_submit(self, driver, prompt: str) -> bool:
        """Find the chat input, type the prompt, and submit — all via JS for speed."""
        try:
            # Step 1: Find input and set content in ONE JS call (saves ~500ms of find_elements)
            typed = driver.execute_script("""
                var inputSels = %s;
                var el = null;
                for (var i = 0; i < inputSels.length; i++) {
                    var found = document.querySelector(inputSels[i]);
                    if (found && found.offsetParent !== null) { el = found; break; }
                }
                if (!el) return 'no-input';
                el.focus();
                if (el.tagName === 'TEXTAREA') {
                    // Use native setter to trigger React state updates
                    var setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
                    setter.call(el, arguments[0]);
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                } else {
                    // contenteditable div (ProseMirror)
                    el.textContent = arguments[0];
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                }
                return 'typed';
            """ % json.dumps(_INPUT_SELECTORS), prompt)

            if typed != 'typed':
                print("[chatgpt] Could not find chat input element")
                return False

            time.sleep(0.04)  # Let React update state

            # Step 2: Find and click send button via JS (saves ~400ms of find_elements)
            sent = driver.execute_script("""
                var sendSels = %s;
                for (var i = 0; i < sendSels.length; i++) {
                    var btn = document.querySelector(sendSels[i]);
                    if (btn && btn.offsetParent !== null) { btn.click(); return true; }
                }
                return false;
            """ % json.dumps(_SEND_SELECTORS))

            if not sent:
                # Fallback: find input and press Enter via Selenium
                for sel in _INPUT_SELECTORS[:3]:
                    try:
                        els = driver.find_elements(By.CSS_SELECTOR, sel)
                        for el in els:
                            if el.is_displayed():
                                el.send_keys(Keys.RETURN)
                                return True
                    except Exception:
                        continue
                return False

            return True
        except Exception as e:
            print(f"[chatgpt] Failed to type/submit: {e}")
            return False

    def _click_new_chat(self, driver):
        """Click New Chat to start a fresh conversation."""
        for sel in _NEW_CHAT_SELECTORS:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed():
                        el.click()
                        self._in_conversation = False
                        self._conversation_count = 0
                        time.sleep(1)
                        return True
            except Exception:
                continue

        # Fallback: navigate directly
        try:
            driver.get(config.CHATGPT_URL)
            time.sleep(2)
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
                    print(f"[chatgpt] Loaded saved chat URL: {url}")
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
            print(f"[chatgpt] Could not save chat URL: {e}")

    def _save_current_chat_url(self, driver) -> None:
        """Capture and save the current ChatGPT chat URL (has unique conversation ID like /c/abc123)."""
        try:
            url = driver.current_url
            if url and "chatgpt.com" in url and "/c/" in url:
                self._chat_url = url
                self._save_chat_url(url)
                print(f"[chatgpt] Saved chat URL: {url}")
        except Exception:
            pass

    def _count_responses(self, driver) -> int:
        """Count assistant response elements in the DOM."""
        try:
            return driver.execute_script(_JS_COUNT_RESPONSES) or 0
        except Exception:
            return 0

    # ──────────────── Wait + Scrape ────────────────

    def _poll_once(self, driver) -> dict:
        """Combined streaming check + scrape in a single JS call (saves ~100-200ms/poll)."""
        try:
            return driver.execute_script("""
                // 1. Check if "Stop generating" button is visible (still streaming)
                var stopSels = [
                    'button[aria-label="Stop generating"]',
                    'button[data-testid="stop-button"]',
                    'button[aria-label="Stop streaming"]'
                ];
                for (var s = 0; s < stopSels.length; s++) {
                    var stops = document.querySelectorAll(stopSels[s]);
                    for (var i = 0; i < stops.length; i++) {
                        if (stops[i].offsetParent !== null) {
                            // Still streaming — also grab current text for tracking
                            var partialSels = [
                                'div[data-message-author-role="assistant"] .markdown',
                                'div[data-message-author-role="assistant"]',
                                'div.agent-turn .markdown',
                                '.markdown.prose'
                            ];
                            for (var p = 0; p < partialSels.length; p++) {
                                var pels = document.querySelectorAll(partialSels[p]);
                                if (pels.length > 0) {
                                    var txt = (pels[pels.length-1].innerText || '').trim();
                                    if (txt.length > 0) return {streaming: true, text: txt};
                                }
                            }
                            return {streaming: true, text: ''};
                        }
                    }
                }
                // 2. Not streaming — scrape last response
                var sels = [
                    'div[data-message-author-role="assistant"] .markdown',
                    'div[data-message-author-role="assistant"]',
                    'div.agent-turn .markdown',
                    '.markdown.prose'
                ];
                for (var i = 0; i < sels.length; i++) {
                    var els = document.querySelectorAll(sels[i]);
                    if (els.length > 0) {
                        var last = els[els.length - 1];
                        var t = (last.innerText || '').trim();
                        if (t.length > 0) return {streaming: false, text: t};
                    }
                }
                return {streaming: false, text: ''};
            """) or {"streaming": False, "text": ""}
        except Exception:
            return {"streaming": False, "text": ""}

    def _wait_and_scrape(self, driver, pre_count: int = 0) -> tuple:
        details = {"poll_count": 0, "polling_ms": 0, "phase1_ms": 0}
        last_text = ""
        stable_count = 0
        new_response_detected = False

        t_poll = time.perf_counter()
        deadline = time.perf_counter() + config.AI_RESPONSE_TIMEOUT

        # Phase 1: Wait for a NEW assistant response element to appear
        while time.perf_counter() < deadline:
            cur_count = self._count_responses(driver)
            if cur_count > pre_count:
                new_response_detected = True
                break
            time.sleep(0.08)
        details["phase1_ms"] = round((time.perf_counter() - t_poll) * 1000)

        # Phase 2: Stability polling (combined streaming check + scrape)
        while time.perf_counter() < deadline:
            details["poll_count"] += 1

            poll = self._poll_once(driver)
            is_streaming = poll.get("streaming", False)
            current_text = (poll.get("text") or "").strip()

            if current_text and len(current_text) > 0:
                if not is_streaming and current_text == last_text:
                    stable_count += 1
                    if stable_count >= config.STABLE_CHECKS:
                        details["polling_ms"] = round((time.perf_counter() - t_poll) * 1000)
                        return self._clean_response(current_text), details
                elif current_text != last_text:
                    stable_count = 0
                    last_text = current_text

            time.sleep(config.AI_RESPONSE_POLL)

        details["polling_ms"] = round((time.perf_counter() - t_poll) * 1000)
        final = last_text if last_text else self._scrape_via_js(driver)
        return (self._clean_response(final) if final else ""), details

    def _is_streaming(self, driver) -> bool:
        """Check if ChatGPT is still generating (Stop button visible)."""
        try:
            return driver.execute_script("""
                var sels = [
                    'button[aria-label="Stop generating"]',
                    'button[data-testid="stop-button"]',
                    'button[aria-label="Stop streaming"]'
                ];
                for (var s = 0; s < sels.length; s++) {
                    var els = document.querySelectorAll(sels[s]);
                    for (var i = 0; i < els.length; i++) {
                        if (els[i].offsetParent !== null) return true;
                    }
                }
                return false;
            """) is True
        except Exception:
            return False

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
