"""
Google AI Mode Provider — scrapes google.com/search?q=QUERY&udm=50

Optimized v2:
  - implicit_wait(0) eliminates 2s penalty per missed selector
  - Fixed 2s sleep → adaptive wait (0.5s initial)
  - Polling 0.5s × 2 stable checks
  - Single JS call replaces sequential selector fallback
  - Random micro-delays for anti-detection
"""
import json
import time
import random
import urllib.parse

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, StaleElementReferenceException
)

from providers.base import BaseAutomator
import config


# ── Selectors (Google AI Mode DOM) ──
AI_CONTENT_SELECTORS = [
    "#aim-chrome-initial-inline-async-container",
    "div[data-xid='aim-mars-turn-root']",
    "div.tonYlb.Uphzyf",
    "div.qJYHHd.mp0vvc",
    "div.WzWwpc.vve6Ce",
    "div.SLPe5b",
    "div.bzXtMb",
]

# JS scrape — PRIMARY: Only AI Mode specific selectors
_JS_SCRAPE_AI = """
var sels = %s;
for (var i = 0; i < sels.length; i++) {
    var els = document.querySelectorAll(sels[i]);
    for (var j = 0; j < els.length; j++) {
        var t = (els[j].innerText || '').trim();
        if (t.length > 20) return t;
    }
}
return '';
""" % json.dumps(AI_CONTENT_SELECTORS)

# JS scrape — FALLBACK: Broader page areas (used only at timeout)
_JS_SCRAPE_FALLBACK = """
var areas = document.querySelectorAll('#center_col, #rso, #search, main');
var best = '';
for (var k = 0; k < areas.length; k++) {
    var t = (areas[k].innerText || '').trim();
    if (t.length > best.length && t.length < 20000) best = t;
}
if (best.length > 50) return best;
return '';
"""

# JS combined poll: streaming check + AI content scrape in ONE call
_JS_POLL_COMBINED = """
var btns = document.querySelectorAll('button[aria-label*="Stop"], button[aria-label*="stop"]');
for (var i = 0; i < btns.length; i++) {
    if (btns[i].offsetParent !== null) return {streaming: true, text: ''};
}
var sels = %s;
for (var i = 0; i < sels.length; i++) {
    var els = document.querySelectorAll(sels[i]);
    for (var j = 0; j < els.length; j++) {
        var t = (els[j].innerText || '').trim();
        if (t.length > 20) return {streaming: false, text: t};
    }
}
return {streaming: false, text: ''};
""" % json.dumps(AI_CONTENT_SELECTORS)

# ── Noise filters (pre-compiled) ──
_NOISE_EXACT = frozenset({
    "accessibility links", "skip to main content", "accessibility help",
    "accessibility feedback", "filters and topics", "ai mode", "all",
    "images", "videos", "shopping", "news", "more", "sign in",
    "search results", "show all",
})
_NOISE_CONTAINS = (
    "ai can make mistakes", "double-check responses",
    "you can now share this thread", "quick results from the web:",
)


class GoogleAIModeAutomator(BaseAutomator):
    """
    Fast Google AI Mode scraper.
    Navigates directly to google.com/search?q=QUERY&udm=50
    Waits for streaming, scrapes via JS, returns cleaned text.
    """

    provider_name = "google"
    display_name = "Google AI Mode"

    def __init__(self, browser_manager):
        super().__init__(browser_manager)

    # ──────────────── Core: New Query ────────────────

    def send_and_get_response(self, prompt: str) -> dict:
        result = self._make_result(prompt)

        with self.browser_manager.lock:
            driver = self.browser_manager.driver
            if not driver:
                result["response"] = "ERROR: Browser not connected. Click Reconnect."
                return result

            try:
                # Ensure our tab is active
                if not self.browser_manager.has_tab(self.provider_name):
                    self.browser_manager.open_tab(self.provider_name, "about:blank")
                self.browser_manager.switch_to(self.provider_name)

                t_total = time.perf_counter()

                # Navigate
                t_nav = time.perf_counter()
                encoded_q = urllib.parse.quote_plus(prompt)
                url = f"https://www.google.com/search?q={encoded_q}&udm=50"
                driver.get(url)
                result["timing"]["navigation_ms"] = round((time.perf_counter() - t_nav) * 1000)

                # Wait + Scrape
                t_scrape = time.perf_counter()
                text, details = self._wait_and_scrape(driver, prompt)
                result["timing"]["scrape_ms"] = round((time.perf_counter() - t_scrape) * 1000)
                result["timing"].update(details)

                total_ms = round((time.perf_counter() - t_total) * 1000)
                result["timing"]["total_ms"] = total_ms

                if text:
                    result["response"] = text
                    result["success"] = True
                    self._in_conversation = True
                    self._conversation_count += 1
                    print(f"[google] {len(text)} chars in {total_ms}ms | "
                          f"nav={result['timing']['navigation_ms']}ms "
                          f"polls={details.get('poll_count', '?')}")
                else:
                    self._dump_page_source(driver)
                    result["response"] = "ERROR: Could not scrape AI Mode response."
                    print(f"[google] Failed after {total_ms}ms")

            except TimeoutException:
                result["response"] = "ERROR: Timed out waiting for AI Mode response"
            except Exception as e:
                result["response"] = f"ERROR: {str(e)}"
                print(f"[google] Error: {e}")

        return result

    # ──────────────── Follow-Up ────────────────

    def send_followup(self, prompt: str) -> dict:
        """
        Send a follow-up within the same AI Mode conversation.
        If no active conversation, falls back to send_and_get_response.
        """
        if not self._in_conversation:
            return self.send_and_get_response(prompt)

        result = self._make_result(prompt)

        with self.browser_manager.lock:
            driver = self.browser_manager.driver
            if not driver:
                result["response"] = "ERROR: Browser not connected."
                return result

            try:
                self.browser_manager.switch_to(self.provider_name)
                t_total = time.perf_counter()

                # Find the follow-up input on the AI Mode page
                followup_selectors = [
                    "textarea[aria-label*='follow']",
                    "textarea[aria-label*='Ask']",
                    "div[contenteditable='true']",
                    "textarea.gLFyf",
                    "textarea",
                ]

                input_el = None
                for sel in followup_selectors:
                    try:
                        els = driver.find_elements(By.CSS_SELECTOR, sel)
                        for el in els:
                            if el.is_displayed():
                                input_el = el
                                break
                    except Exception:
                        continue
                    if input_el:
                        break

                if not input_el:
                    # No follow-up input found — start a fresh query
                    print("[google] No follow-up input — starting new query")
                    self._in_conversation = False
                    return self.send_and_get_response(prompt)

                # Type and submit follow-up
                input_el.clear()
                input_el.send_keys(prompt)
                time.sleep(0.08)

                # Try pressing Enter or clicking submit
                from selenium.webdriver.common.keys import Keys
                input_el.send_keys(Keys.RETURN)

                result["timing"]["navigation_ms"] = round((time.perf_counter() - t_total) * 1000)

                # Wait for new response
                t_scrape = time.perf_counter()
                text, details = self._wait_and_scrape(driver, prompt)
                result["timing"]["scrape_ms"] = round((time.perf_counter() - t_scrape) * 1000)
                result["timing"].update(details)

                total_ms = round((time.perf_counter() - t_total) * 1000)
                result["timing"]["total_ms"] = total_ms

                if text:
                    result["response"] = text
                    result["success"] = True
                    self._conversation_count += 1
                    print(f"[google] follow-up: {len(text)} chars in {total_ms}ms")
                else:
                    result["response"] = "ERROR: Could not scrape follow-up response."

            except Exception as e:
                result["response"] = f"ERROR: {str(e)}"
                print(f"[google] Follow-up error: {e}")

        return result

    # ──────────────── Conversation Control ────────────────

    def new_conversation(self) -> None:
        self._in_conversation = False
        self._conversation_count = 0

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
            except Exception:
                connected = False

        return {
            "provider": self.provider_name,
            "display_name": self.display_name,
            "connected": connected,
            "current_url": current_url,
            "in_conversation": self._in_conversation,
            "conversation_count": self._conversation_count,
            "requires_login": False,
            "logged_in": True,  # Google AI Mode is public
        }

    def is_logged_in(self) -> bool:
        return True  # No login needed for Google search

    # ──────────────── Wait + Scrape ────────────────

    def _is_content_real(self, text: str, prompt: str) -> bool:
        """Check if scraped text is real AI content, not just the echoed query heading."""
        if not text:
            return False
        # If text is substantially longer than prompt, it's real content
        if len(text) > len(prompt) + 80:
            return True
        # If text doesn't closely match the prompt, it's real content
        if prompt.lower().strip() not in text.lower():
            return True
        # Text is mostly just the query echo
        return False

    def _is_streaming(self, driver) -> bool:
        """Check if Google AI Mode is still streaming/generating."""
        try:
            return driver.execute_script("""
                var btns = document.querySelectorAll('button[aria-label*="Stop"], button[aria-label*="stop"]');
                for (var i = 0; i < btns.length; i++) {
                    if (btns[i].offsetParent !== null) return true;
                }
                return false;
            """) is True
        except Exception:
            return False

    def _poll_once(self, driver) -> dict:
        """Combined streaming check + AI content scrape in ONE JS call."""
        try:
            return driver.execute_script(_JS_POLL_COMBINED) or {"streaming": False, "text": ""}
        except Exception:
            return {"streaming": False, "text": ""}

    def _wait_and_scrape(self, driver, prompt: str = "") -> tuple:
        details = {"poll_count": 0, "container_wait_ms": 0, "polling_ms": 0, "phase1_ms": 0}
        last_text = ""
        stable_count = 0

        # Phase 1: Wait for AI container to appear in DOM
        t_cw = time.perf_counter()
        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "#aim-chrome-initial-inline-async-container")
                )
            )
        except TimeoutException:
            print("[google] AI container not found within 20s")
        details["container_wait_ms"] = round((time.perf_counter() - t_cw) * 1000)
        details["phase1_ms"] = details["container_wait_ms"]

        # Phase 2: Wait for REAL AI content (not just query echo)
        t_poll = time.perf_counter()
        deadline = time.perf_counter() + config.AI_RESPONSE_TIMEOUT
        content_appeared = False

        while time.perf_counter() < deadline:
            details["poll_count"] += 1

            # Combined streaming check + scrape in ONE JS call
            poll = self._poll_once(driver)

            # If still streaming, reset stability
            if poll.get("streaming"):
                stable_count = 0
                time.sleep(config.AI_RESPONSE_POLL)
                continue

            current_text = (poll.get("text") or "").strip()

            # Skip if no content or just query echo
            if not current_text or not self._is_content_real(current_text, prompt):
                time.sleep(0.1)
                continue

            # Real AI content appeared
            if not content_appeared:
                content_appeared = True
                last_text = current_text
                time.sleep(config.AI_RESPONSE_POLL)
                continue

            # Phase 3: Stability polling
            if current_text == last_text:
                stable_count += 1
                if stable_count >= config.STABLE_CHECKS:
                    details["polling_ms"] = round((time.perf_counter() - t_poll) * 1000)
                    return self._clean_response(current_text), details
            else:
                stable_count = 0
                last_text = current_text

            time.sleep(config.AI_RESPONSE_POLL)

        details["polling_ms"] = round((time.perf_counter() - t_poll) * 1000)
        final = last_text if last_text else self._scrape_via_js(driver, fallback=True)
        return (self._clean_response(final) if final else ""), details

    # ──────────────── JS Scraping ────────────────

    def _scrape_via_js(self, driver, fallback: bool = False) -> str:
        """Scrape AI Mode response text. If fallback=True, also try broader selectors."""
        try:
            text = driver.execute_script(_JS_SCRAPE_AI)
            if text and len(text.strip()) > 0:
                return text.strip()
        except Exception:
            pass
        if fallback:
            try:
                text = driver.execute_script(_JS_SCRAPE_FALLBACK)
                if text and len(text.strip()) > 50:
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

    # ──────────────── Debug ────────────────

    def _dump_page_source(self, driver):
        import os
        try:
            html_path = os.path.join(config.BASE_DIR, "debug_page.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            txt_path = os.path.join(config.BASE_DIR, "debug_text.txt")
            body_text = driver.find_element(By.TAG_NAME, "body").text
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(body_text)
            print(f"[google] Debug files saved")
        except Exception as e:
            print(f"[google] Could not dump page: {e}")
