"""
Google AI Mode Scraper — Optimized v2
Goes directly to Google AI Mode URL (?udm=50), waits for the AI response
to finish streaming, scrapes the AI content, returns it.
Uses Selenium.  Keeps browser alive between queries for speed.

Optimizations over v1:
  - implicit_wait(0) eliminates 2s penalty per missed selector
  - Fixed 2s sleep replaced with adaptive wait (0.5s initial)
  - Polling interval reduced to 0.5s, stable checks reduced to 2
  - Single JS call replaces sequential selector fallback chain
  - Cached primary selector avoids redundant lookups
  - Random micro-delays for anti-detection
  - Stealth: navigator.webdriver patched, chrome.runtime injected
"""
import os
import time
import json
import random
import threading
import urllib.parse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException,
    StaleElementReferenceException
)
import config


# ── Real selectors discovered from Google AI Mode DOM ──
# Priority order – first match wins.
AI_CONTENT_SELECTORS = [
    "#aim-chrome-initial-inline-async-container",   # async-loaded AI response (ID — fastest)
    "div[data-xid='aim-mars-turn-root']",           # turn root wrapper
    "div.tonYlb.Uphzyf",                            # turn content area
    "div.qJYHHd.mp0vvc",                            # turn container
    "div.WzWwpc.vve6Ce",                            # chat area
    "div.SLPe5b",                                   # inner wrapper
    "div.bzXtMb",                                   # outer wrapper
]

# ── Single JS script that tries all selectors in one round-trip ──
# json.dumps handles quotes safely (no mangled attribute selectors).
_JS_SCRAPE_ALL = """
var sels = %s;
for (var i = 0; i < sels.length; i++) {
    var els = document.querySelectorAll(sels[i]);
    for (var j = 0; j < els.length; j++) {
        var t = (els[j].innerText || '').trim();
        if (t.length > 50) return t;
    }
}
var areas = document.querySelectorAll('#center_col, #rso, #search, main');
var best = '';
for (var k = 0; k < areas.length; k++) {
    var t = (areas[k].innerText || '').trim();
    if (t.length > best.length && t.length < 20000) best = t;
}
if (best.length > 50) return best;
return (document.body.innerText || '').substring(0, 10000);
""" % json.dumps(AI_CONTENT_SELECTORS)

# ── Noise filters (pre-compiled for speed) ──
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


class GoogleAIModeAutomator:
    """
    Fast Google AI Mode scraper:
      1. Navigates directly to google.com/search?q=QUERY&udm=50
      2. Waits for AI streaming to complete
      3. Scrapes only the AI-generated content
    Browser stays alive between queries — no restart overhead.
    """

    def __init__(self):
        self.driver = None
        self.lock = threading.Lock()
        self._launch_browser()

    # ──────────────── Browser Management ────────────────

    def _build_options(self, browser_type: str):
        """Build browser options with stealth flags."""
        if browser_type == "edge":
            opts = EdgeOptions()
        else:
            opts = ChromeOptions()

        if config.HEADLESS:
            opts.add_argument("--headless=new")

        # ── Anti-detection flags ──
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--lang=en-US")
        opts.add_argument("--window-size=1400,900")
        opts.add_argument("--disable-infobars")
        opts.add_argument("--disable-popup-blocking")

        # Realistic rendering
        opts.add_argument("--enable-features=NetworkService,NetworkServiceInProcess")

        # Remove automation indicators
        opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        opts.add_experimental_option("useAutomationExtension", False)

        if config.USER_AGENT:
            opts.add_argument(f"--user-agent={config.USER_AGENT}")

        return opts

    def _launch_browser(self):
        """Launch Chrome or Edge browser with stealth patches."""
        try:
            opts = self._build_options(config.BROWSER.lower())

            if config.BROWSER.lower() == "edge":
                self.driver = webdriver.Edge(options=opts)
            else:
                self.driver = webdriver.Chrome(options=opts)

            # CRITICAL: implicit_wait(0) — eliminates 2000ms penalty
            # per missed find_elements call.  We use explicit waits instead.
            self.driver.implicitly_wait(config.IMPLICIT_WAIT)

            # ── Stealth patches via CDP ──
            # Patch navigator.webdriver to undefined
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    window.chrome = { runtime: {} };
                """
            })

            print(f"[+] Browser launched ({config.BROWSER}) — stealth mode")
        except WebDriverException as e:
            print(f"[!] Failed to launch browser: {e}")
            self.driver = None

    def reconnect(self):
        """Close and relaunch the browser."""
        self.close()
        self._launch_browser()

    def close(self):
        """Close the browser."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    # ──────────────── Core Flow ────────────────

    def send_and_get_response(self, prompt: str) -> dict:
        """
        Optimised pipeline:
          1. Build direct AI Mode URL with udm=50
          2. Single navigation (no multi-step clicks)
          3. Wait for AI container, then adaptive poll until stable
          4. Single JS call scrapes + returns text
          5. Fast cleaning pass

        Returns dict with prompt, response, timestamp, success, timing
        """
        result = {
            "prompt": prompt,
            "response": "",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "success": False,
            "timing": {}
        }

        with self.lock:
            if not self.driver:
                result["response"] = "ERROR: Browser not connected. Click Reconnect."
                return result

            try:
                t_total = time.perf_counter()

                # ── Step 1: Navigate ──
                t_nav = time.perf_counter()
                encoded_q = urllib.parse.quote_plus(prompt)
                ai_url = f"https://www.google.com/search?q={encoded_q}&udm=50"
                self.driver.get(ai_url)
                result["timing"]["navigation_ms"] = round((time.perf_counter() - t_nav) * 1000)

                # ── Step 2: Wait + Scrape (combined) ──
                t_scrape = time.perf_counter()
                response_text, scrape_details = self._wait_and_scrape()
                result["timing"]["scrape_ms"] = round((time.perf_counter() - t_scrape) * 1000)
                result["timing"].update(scrape_details)

                # ── Step 3: Finalise ──
                total_ms = round((time.perf_counter() - t_total) * 1000)
                result["timing"]["total_ms"] = total_ms

                if response_text:
                    result["response"] = response_text
                    result["success"] = True
                    print(f"[<] {len(response_text)} chars in {total_ms}ms | "
                          f"nav={result['timing']['navigation_ms']}ms "
                          f"scrape={result['timing']['scrape_ms']}ms "
                          f"polls={scrape_details.get('poll_count', '?')}")
                else:
                    self._dump_page_source()
                    result["response"] = "ERROR: Could not scrape AI Mode response. Debug files saved."
                    print(f"[!] Failed after {total_ms}ms")

            except TimeoutException:
                result["response"] = "ERROR: Timed out waiting for AI Mode response"
                print("[!] Timeout")
            except Exception as e:
                result["response"] = f"ERROR: {str(e)}"
                print(f"[!] Error: {e}")

        return result

    # ──────────────── Wait + Scrape (Optimised) ────────────────

    def _wait_and_scrape(self) -> tuple:
        """
        Optimised wait strategy:
          1. WebDriverWait for #aim-chrome-... (event-driven, no CPU burn)
          2. Tiny adaptive pause (0.5s, not 2s)
          3. Fast poll loop: 0.5s interval, 2 stable checks to confirm done
          4. Single JS call per poll (not 7 separate Selenium calls)

        Returns (cleaned_text, timing_details)
        """
        details = {"poll_count": 0, "container_wait_ms": 0, "polling_ms": 0}
        last_text = ""
        stable_count = 0

        # ── Phase 1: Wait for container to appear (event-driven) ──
        t_cw = time.perf_counter()
        container_sel = "#aim-chrome-initial-inline-async-container"
        try:
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, container_sel))
            )
        except TimeoutException:
            print("[!] AI container not found within 20s")
        details["container_wait_ms"] = round((time.perf_counter() - t_cw) * 1000)

        # ── Phase 2: Adaptive initial pause ──
        # Just 0.5s — enough for streaming to start, not a full 2s waste
        time.sleep(config.STREAMING_INITIAL_WAIT)

        # ── Phase 3: Fast stability polling ──
        t_poll = time.perf_counter()
        deadline = time.perf_counter() + config.AI_RESPONSE_TIMEOUT

        while time.perf_counter() < deadline:
            details["poll_count"] += 1

            # Single JS call does all selector work in-browser (no WebDriver round-trips)
            current_text = self._scrape_via_js()

            if current_text and len(current_text) > 30:
                if current_text == last_text:
                    stable_count += 1
                    if stable_count >= config.STABLE_CHECKS:
                        details["polling_ms"] = round((time.perf_counter() - t_poll) * 1000)
                        return self._clean_response(current_text), details
                else:
                    stable_count = 0
                    last_text = current_text

            # Anti-detection: add tiny random jitter to poll interval
            jitter = random.uniform(config.RANDOM_DELAY_MIN, config.RANDOM_DELAY_MAX)
            time.sleep(config.AI_RESPONSE_POLL + jitter)

        details["polling_ms"] = round((time.perf_counter() - t_poll) * 1000)
        # Timeout — return best we have
        final = last_text if last_text else self._scrape_via_js()
        return (self._clean_response(final) if final else ""), details

    # ──────────────── Scraping (Single JS Call) ────────────────

    def _scrape_via_js(self) -> str:
        """
        Execute a single JavaScript call that tries all selectors in-browser.
        This replaces 7 sequential Selenium find_elements calls, saving
        ~7 WebDriver round-trips per poll iteration.
        """
        try:
            text = self.driver.execute_script(_JS_SCRAPE_ALL)
            if text and len(text.strip()) > 30:
                return text.strip()
        except Exception:
            pass
        return ""

    def _scrape_ai_content(self) -> str:
        """Legacy fallback — sequential Selenium selectors."""
        for selector in AI_CONTENT_SELECTORS:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                for el in elements:
                    try:
                        text = el.text.strip()
                        if text and len(text) > 50:
                            return self._clean_response(text)
                    except StaleElementReferenceException:
                        continue
            except Exception:
                continue
        return ""

    # ──────────────── Text Cleaning ────────────────

    def _clean_response(self, text: str) -> str:
        """
        Remove Google navigation / UI chrome from scraped text.
        Uses pre-compiled module-level _NOISE_EXACT (frozenset) and
        _NOISE_CONTAINS (tuple) for O(1) exact and fast substring checks.
        """
        lines = text.split("\n")
        cleaned = []
        content_started = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            low = stripped.lower()

            # O(1) frozenset lookup
            if low in _NOISE_EXACT:
                continue

            # Substring scan (tuple, not list — marginally faster iteration)
            if any(n in low for n in _NOISE_CONTAINS):
                continue

            if not content_started and len(stripped) > 40:
                content_started = True

            if not content_started and len(stripped) < 30:
                continue

            cleaned.append(stripped)

        return "\n".join(cleaned).strip()

    # ──────────────── Debug ────────────────

    def _dump_page_source(self):
        """Save current page HTML + visible text for debugging."""
        try:
            html_path = os.path.join(config.BASE_DIR, "debug_page.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            print(f"[DEBUG] Page source -> {html_path}")

            txt_path = os.path.join(config.BASE_DIR, "debug_text.txt")
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(body_text)
            print(f"[DEBUG] Page text  -> {txt_path}")
        except Exception as e:
            print(f"[!] Could not dump page source: {e}")

    # ──────────────── Status ────────────────

    def get_status(self) -> dict:
        """Check browser connection status."""
        connected = False
        current_url = ""

        if self.driver:
            try:
                current_url = self.driver.current_url
                connected = True
            except:
                connected = False
                self.driver = None

        return {
            "connected": connected,
            "browser": config.BROWSER,
            "current_url": current_url,
            "headless": config.HEADLESS,
            "settings": {
                "ai_response_timeout": config.AI_RESPONSE_TIMEOUT,
                "stable_checks": config.STABLE_CHECKS,
                "poll_interval": config.AI_RESPONSE_POLL
            }
        }


# ──────────────── Singleton ────────────────

_automator = None

def get_automator() -> GoogleAIModeAutomator:
    """Get or create the singleton automator instance."""
    global _automator
    if _automator is None:
        _automator = GoogleAIModeAutomator()
    return _automator
