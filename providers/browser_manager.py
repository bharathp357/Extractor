"""
Browser Manager — Shared Chrome instance with per-provider tab management.

Design:
  - ONE Chrome process with persistent user-data-dir (logins survive restarts)
  - Each provider gets its own tab (window handle)
  - switch_to(provider) activates the correct tab before any interaction
  - Single threading.Lock serialises all driver access across providers
  - Stealth CDP patches applied once at launch, inherited by all tabs
"""
import os
import time
import threading
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.common.exceptions import WebDriverException
import config


class BrowserManager:
    """
    Singleton-ish shared browser controller.
    Created once; providers reference it via self.browser_manager.
    """

    def __init__(self):
        self.driver = None
        self.lock = threading.Lock()
        # provider_name -> window handle string
        self._tabs: dict[str, str] = {}
        self._active_provider: str | None = None
        self._launch_browser()

    # ──────────────── Browser Lifecycle ────────────────

    def _build_options(self):
        """Construct Chrome options with stealth + persistent profile."""
        browser = config.BROWSER.lower()
        opts = ChromeOptions() if browser != "edge" else EdgeOptions()

        if config.HEADLESS:
            opts.add_argument("--headless=new")

        # ── Persistent profile (logins survive restarts) ──
        profile_dir = config.CHROME_PROFILE_DIR
        if profile_dir:
            os.makedirs(profile_dir, exist_ok=True)
            opts.add_argument(f"--user-data-dir={profile_dir}")

        # ── Anti-detection ──
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--lang=en-US")
        opts.add_argument("--window-size=1400,900")
        opts.add_argument("--disable-infobars")
        opts.add_argument("--disable-popup-blocking")
        opts.add_argument("--enable-features=NetworkService,NetworkServiceInProcess")
        opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        opts.add_experimental_option("useAutomationExtension", False)

        if config.USER_AGENT:
            opts.add_argument(f"--user-agent={config.USER_AGENT}")

        return opts

    def _launch_browser(self):
        """Launch Chrome/Edge with stealth patches."""
        try:
            opts = self._build_options()

            if config.BROWSER.lower() == "edge":
                self.driver = webdriver.Edge(options=opts)
            else:
                self.driver = webdriver.Chrome(options=opts)

            self.driver.implicitly_wait(config.IMPLICIT_WAIT)

            # ── Stealth CDP patches ──
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    window.chrome = { runtime: {} };
                """
            })

            # Minimize browser window — user should only see the web UI
            try:
                self.driver.minimize_window()
            except Exception:
                pass

            # The first tab is the default blank tab
            self._tabs = {}
            self._active_provider = None
            print(f"[+] Browser launched ({config.BROWSER}) — stealth mode, minimized, profile: {config.CHROME_PROFILE_DIR or 'temp'}")

        except WebDriverException as e:
            error_msg = str(e)
            # Profile locked — retry without persistent profile
            if "Chrome failed to start: crashed" in error_msg or "DevToolsActivePort" in error_msg:
                print(f"[!] Profile locked, retrying without persistent profile...")
                try:
                    opts = self._build_options()
                    # Remove user-data-dir argument
                    opts._arguments = [a for a in opts._arguments if not a.startswith("--user-data-dir=")]
                    if config.BROWSER.lower() == "edge":
                        self.driver = webdriver.Edge(options=opts)
                    else:
                        self.driver = webdriver.Chrome(options=opts)
                    self.driver.implicitly_wait(config.IMPLICIT_WAIT)
                    self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                        "source": """
                            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                            window.chrome = { runtime: {} };
                        """
                    })
                    try:
                        self.driver.minimize_window()
                    except Exception:
                        pass
                    self._tabs = {}
                    self._active_provider = None
                    print(f"[+] Browser launched ({config.BROWSER}) — stealth mode, minimized, NO persistent profile (fallback)")
                except WebDriverException as e2:
                    print(f"[!] Failed to launch browser (fallback): {e2}")
                    self.driver = None
            else:
                print(f"[!] Failed to launch browser: {e}")
                self.driver = None

    def restart(self):
        """Kill browser and relaunch."""
        self.close_all()
        self._launch_browser()

    def close_all(self):
        """Quit the browser entirely."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
        self._tabs.clear()
        self._active_provider = None

    # ──────────────── Preloading ────────────────

    def preload_tabs(self, providers_urls: list[tuple[str, str]]) -> dict:
        """
        Open all provider tabs with short page-load timeouts.
        Chrome loads pages in parallel across tabs.
        Returns: {provider_name: load_ms}
        """
        timings = {}
        if not self.driver:
            return timings

        with self.lock:
            for name, url in providers_urls:
                if name in self._tabs:
                    timings[name] = 0
                    continue

                t = time.perf_counter()
                try:
                    # First tab: reuse the blank initial tab
                    if len(self._tabs) == 0:
                        current = self.driver.current_url
                        if current in ("about:blank", "data:,", "chrome://newtab/"):
                            handle = self.driver.current_window_handle
                            self._tabs[name] = handle
                            self._active_provider = name
                            self.driver.set_page_load_timeout(config.PRELOAD_TAB_TIMEOUT)
                            try:
                                self.driver.get(url)
                            except Exception:
                                pass  # Timeout OK — page keeps loading in background
                            timings[name] = round((time.perf_counter() - t) * 1000)
                            continue

                    # Subsequent tabs
                    self.driver.execute_script("window.open('');")
                    handles = self.driver.window_handles
                    new_handle = handles[-1]
                    self.driver.switch_to.window(new_handle)
                    self._tabs[name] = new_handle
                    self._active_provider = name

                    self.driver.set_page_load_timeout(config.PRELOAD_TAB_TIMEOUT)
                    try:
                        self.driver.get(url)
                    except Exception:
                        pass  # Timeout OK — parallel background load

                except Exception as e:
                    print(f"[!] Preload tab {name}: {e}")

                timings[name] = round((time.perf_counter() - t) * 1000)

            # Restore normal timeout
            try:
                self.driver.set_page_load_timeout(30)
            except Exception:
                pass

        return timings

    # ──────────────── Tab Management ────────────────

    def open_tab(self, provider_name: str, url: str) -> bool:
        """
        Open a new tab for a provider and navigate to url.
        Must be called inside self.lock.
        """
        if not self.driver:
            return False

        if provider_name in self._tabs:
            # Tab already exists — just switch to it
            self.switch_to(provider_name)
            return True

        try:
            # If this is the very first tab and we're on about:blank, reuse it
            if len(self._tabs) == 0:
                current = self.driver.current_url
                if current in ("about:blank", "data:,", "chrome://newtab/"):
                    handle = self.driver.current_window_handle
                    self._tabs[provider_name] = handle
                    self._active_provider = provider_name
                    self.driver.get(url)
                    return True

            # Open new tab via JavaScript
            self.driver.execute_script("window.open('');")
            # Switch to the newly opened tab (last handle)
            all_handles = self.driver.window_handles
            new_handle = all_handles[-1]
            self.driver.switch_to.window(new_handle)
            self._tabs[provider_name] = new_handle
            self._active_provider = provider_name
            self.driver.get(url)
            return True

        except Exception as e:
            print(f"[!] Failed to open tab for {provider_name}: {e}")
            return False

    def switch_to(self, provider_name: str) -> bool:
        """
        Activate the tab for a given provider.
        Must be called inside self.lock.
        Returns False if the tab doesn't exist.
        """
        if not self.driver:
            return False

        if self._active_provider == provider_name:
            return True  # Already on this tab

        handle = self._tabs.get(provider_name)
        if not handle:
            return False

        try:
            self.driver.switch_to.window(handle)
            self._active_provider = provider_name
            return True
        except Exception as e:
            print(f"[!] Failed to switch to {provider_name}: {e}")
            # Handle might be stale — remove it
            self._tabs.pop(provider_name, None)
            return False

    def close_tab(self, provider_name: str):
        """Close a single provider's tab."""
        if not self.driver:
            return

        handle = self._tabs.pop(provider_name, None)
        if not handle:
            return

        try:
            self.driver.switch_to.window(handle)
            self.driver.close()
            # Switch to remaining tab if any
            remaining = self.driver.window_handles
            if remaining:
                self.driver.switch_to.window(remaining[0])
                # Find which provider owns this handle
                for name, h in self._tabs.items():
                    if h == remaining[0]:
                        self._active_provider = name
                        break
                else:
                    self._active_provider = None
            else:
                self._active_provider = None
        except Exception as e:
            print(f"[!] Error closing tab for {provider_name}: {e}")

        if self._active_provider == provider_name:
            self._active_provider = None

    def has_tab(self, provider_name: str) -> bool:
        """Check if a provider's tab exists."""
        return provider_name in self._tabs

    def get_tab_url(self, provider_name: str) -> str:
        """Get current URL of a provider's tab."""
        if not self.driver or provider_name not in self._tabs:
            return ""
        try:
            self.switch_to(provider_name)
            return self.driver.current_url
        except Exception:
            return ""

    def is_alive(self) -> bool:
        """Check if the browser process is still running."""
        if not self.driver:
            return False
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False

    @property
    def active_tabs(self) -> list[str]:
        """List of provider names with open tabs."""
        return list(self._tabs.keys())


# ──────────────── Singleton ────────────────

_manager: BrowserManager | None = None
_manager_lock = threading.Lock()


def get_browser_manager() -> BrowserManager:
    """Thread-safe singleton accessor."""
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = BrowserManager()
    return _manager
