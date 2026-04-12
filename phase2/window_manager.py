"""
Window Manager — Phase 2 equivalent of BrowserManager.

BACKGROUND-SAFE: All operations use UIA element methods.
The user's mouse and keyboard are NEVER taken over.

Architecture: Single Chrome window, single active tab. Provider switching
is done by navigating the address bar to the provider URL — not Ctrl+N
tab switching, which requires foreground focus and fails in background.
"""
import time
import ctypes
import threading
import json

from pywinauto import Application

from phase2.chrome_launcher import ChromeLauncher
from phase2 import config as p2config

# Win32
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_RETURN = 0x0D
VK_CONTROL = 0x11
PostMessage = ctypes.windll.user32.PostMessageW


class WindowManager:
    """
    Phase 2 Chrome window manager — single-tab, address-bar navigation.
    Fully background-safe: no Ctrl+N tab switching needed.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self._chrome = ChromeLauncher()
        self._app = None
        self._main_window = None
        self._active_provider = None
        self._provider_urls = {
            "google": p2config.GOOGLE_URL,
            "gemini": p2config.GEMINI_URL,
            "chatgpt": p2config.CHATGPT_URL,
        }
        self._load_saved_urls()

    def _load_saved_urls(self):
        try:
            with open(p2config.CHAT_URLS_FILE, "r") as f:
                saved = json.load(f)
            if saved.get("gemini"):
                self._provider_urls["gemini"] = saved["gemini"]
            if saved.get("chatgpt"):
                self._provider_urls["chatgpt"] = saved["chatgpt"]
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

    # ─────────────────── Launch & Connect ───────────────────

    def launch_and_connect(self, urls: list = None) -> bool:
        """Launch Chrome with a single URL and connect PyWinAuto."""
        launch_url = p2config.GOOGLE_URL
        if urls:
            item = urls[0]
            launch_url = item[1] if isinstance(item, (list, tuple)) else item

        if not self._chrome.launch([launch_url]):
            return False

        time.sleep(p2config.CHROME_LAUNCH_TIMEOUT - 2)
        return self._connect_to_chrome()

    def _connect_to_chrome(self) -> bool:
        pid = self._chrome.pid
        strategies = []
        if pid:
            strategies.append(("PID", {"process": pid}))
        strategies.append(("title", {"title_re": ".*Chrome.*"}))
        strategies.append(("class", {"class_name": "Chrome_WidgetWin_1"}))

        for strategy, kwargs in strategies:
            try:
                self._app = Application(backend="uia").connect(**kwargs)
                self._main_window = self._app.top_window()
                title = self._main_window.window_text()
                print(f"[phase2/wm] Connected by {strategy}: {title[:60]}")
                return True
            except Exception:
                continue

        print("[phase2/wm] FATAL: Could not connect to Chrome")
        self._app = None
        self._main_window = None
        return False

    # ─────────────────── Provider Switching (Address Bar) ───────────────────

    def switch_to(self, provider_name: str) -> bool:
        """Switch provider by navigating the address bar — no tab switching."""
        if self._active_provider == provider_name:
            return True

        url = self._provider_urls.get(provider_name)
        if not url:
            return False

        # Already on the right page?
        current = self.get_address_bar_url()
        if current and self._url_matches(current, provider_name):
            self._active_provider = provider_name
            return True

        self.navigate(url)
        time.sleep(2.0)
        self._active_provider = provider_name
        return True

    def navigate(self, url: str):
        """Navigate to a URL via the address bar (background-safe)."""
        if not self._main_window:
            return
        try:
            edit = self._find_address_bar()
            if not edit:
                print("[phase2/wm] navigate: address bar not found")
                return

            try:
                edit.set_focus()
            except Exception:
                pass
            time.sleep(0.15)

            # Set URL via UIA ValuePattern
            try:
                iface = edit.iface_value
                if iface:
                    iface.SetValue(url)
                else:
                    edit.set_edit_text(url)
            except Exception:
                edit.set_edit_text(url)
            time.sleep(0.15)

            # Press Enter
            try:
                edit.type_keys("{ENTER}", set_foreground=False)
            except Exception:
                hwnd = self._get_hwnd()
                if hwnd:
                    PostMessage(hwnd, WM_KEYDOWN, VK_RETURN, 0)
                    time.sleep(0.02)
                    PostMessage(hwnd, WM_KEYUP, VK_RETURN, 0)
        except Exception as e:
            print(f"[phase2/wm] navigate failed: {e}")

    def update_provider_url(self, provider_name: str, url: str):
        if url and provider_name in self._provider_urls:
            self._provider_urls[provider_name] = url

    def close_tab(self, provider_name: str):
        self.navigate("about:blank")
        time.sleep(0.3)
        if self._active_provider == provider_name:
            self._active_provider = None

    def has_tab(self, provider_name: str) -> bool:
        return provider_name in self._provider_urls

    # ─────────────────── Window Operations ───────────────────

    def bring_to_front(self):
        if self._main_window:
            try:
                if self._main_window.is_minimized():
                    self._main_window.restore()
                self._main_window.set_focus()
            except Exception:
                self._connect_to_chrome()

    def get_window_rect(self) -> tuple:
        if self._main_window:
            try:
                r = self._main_window.rectangle()
                return (r.left, r.top, r.right, r.bottom)
            except Exception:
                pass
        return (0, 0, 1400, 900)

    def get_title(self) -> str:
        if self._main_window:
            try:
                return self._main_window.window_text()
            except Exception:
                pass
        return ""

    def get_uia_window(self):
        return self._main_window

    def get_app(self):
        return self._app

    def is_alive(self) -> bool:
        if self._chrome.is_alive():
            return True
        if self._main_window:
            try:
                if self._main_window.window_text():
                    return True
            except Exception:
                self._main_window = None
        return False

    def restart(self):
        self.close_all()
        time.sleep(1)
        self.launch_and_connect()

    def close_all(self):
        self._chrome.kill()
        self._app = None
        self._main_window = None
        self._active_provider = None

    # ─────────────────── Preloading ───────────────────

    def preload_tabs(self, providers_urls: list) -> dict:
        timings = {}
        for name, url in providers_urls:
            t = time.perf_counter()
            if url:
                self._provider_urls[name] = url
            timings[name] = round((time.perf_counter() - t) * 1000)
        return timings

    def get_address_bar_url(self) -> str:
        edit = self._find_address_bar()
        if not edit:
            return ""
        try:
            return edit.get_value() or ""
        except Exception:
            return ""

    @property
    def active_tabs(self) -> list:
        return list(self._provider_urls.keys())

    # ─────────────────── Helpers ───────────────────

    def _get_hwnd(self):
        if self._main_window:
            try:
                return self._main_window.handle
            except Exception:
                pass
        return None

    def _find_address_bar(self):
        if not self._main_window:
            return None
        try:
            edit = self._main_window.child_window(
                control_type="Edit", title="Address and search bar"
            )
            if edit.exists(timeout=1):
                return edit
        except Exception:
            pass
        try:
            edits = self._main_window.descendants(control_type="Edit")
            for e in edits:
                name = (e.element_info.name or "").lower()
                if "address" in name:
                    return e
        except Exception:
            pass
        return None

    @staticmethod
    def _url_matches(url: str, provider: str) -> bool:
        u = url.lower()
        if provider == "google":
            return "google.com/search" in u
        elif provider == "gemini":
            return "gemini.google.com" in u
        elif provider == "chatgpt":
            return "chatgpt.com" in u
        return False


# ─────────────────── Singleton ───────────────────

_manager = None
_manager_lock = threading.Lock()


def get_window_manager() -> WindowManager:
    global _manager
    if _manager is not None and not _manager.is_alive():
        with _manager_lock:
            if _manager is not None and not _manager.is_alive():
                try:
                    _manager.close_all()
                except Exception:
                    pass
                _manager = None
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = WindowManager()
    return _manager


def reset_window_manager():
    global _manager
    with _manager_lock:
        if _manager:
            try:
                _manager.close_all()
            except Exception:
                pass
        _manager = None
