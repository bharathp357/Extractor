"""
Provider Registry — creates and manages all AI provider automators.

Usage:
    from providers import get_automator, get_all_statuses
    google = get_automator("google")
    result = google.send_and_get_response("What is Docker?")
"""
import json
import threading
import time as _time
from providers.base import BaseAutomator
from providers.browser_manager import get_browser_manager, reset_browser_manager, BrowserManager
import config


# Provider name -> class mapping (lazy imports to avoid circular deps)
_PROVIDER_CLASSES = {
    "google": ("providers.google_ai", "GoogleAIModeAutomator"),
    "gemini": ("providers.gemini", "GeminiProAutomator"),
    "chatgpt": ("providers.chatgpt", "ChatGPTAutomator"),
}

# Active automator instances
_automators: dict[str, BaseAutomator] = {}
_registry_lock = threading.Lock()


def _import_class(module_path: str, class_name: str):
    """Dynamic import to avoid circular dependencies."""
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_automator(provider: str = "google") -> BaseAutomator:
    """
    Get or create an automator for the given provider.
    Thread-safe. Provider names: "google", "gemini", "chatgpt".
    """
    if provider not in _PROVIDER_CLASSES:
        raise ValueError(f"Unknown provider: '{provider}'. Available: {list(_PROVIDER_CLASSES.keys())}")

    if provider not in _automators:
        with _registry_lock:
            if provider not in _automators:
                module_path, class_name = _PROVIDER_CLASSES[provider]
                cls = _import_class(module_path, class_name)
                bm = get_browser_manager()
                _automators[provider] = cls(bm)

    return _automators[provider]


def get_all_statuses() -> dict:
    """
    Return status for all registered providers.
    Only queries providers that have been instantiated.
    Returns dict: provider_name -> status_dict
    """
    statuses = {}
    for name in _PROVIDER_CLASSES:
        if name in _automators:
            statuses[name] = _automators[name].get_status()
        else:
            statuses[name] = {
                "provider": name,
                "display_name": _get_display_name(name),
                "connected": False,
                "initialized": False,
            }
    return statuses


def get_available_providers() -> list[dict]:
    """Return list of all available provider info dicts."""
    result = []
    for name in _PROVIDER_CLASSES:
        result.append({
            "name": name,
            "display_name": _get_display_name(name),
            "initialized": name in _automators,
        })
    return result


def close_all():
    """Close all provider tabs and the browser."""
    for automator in _automators.values():
        try:
            automator.close()
        except Exception:
            pass
    _automators.clear()
    try:
        get_browser_manager().close_all()
    except Exception:
        pass
    reset_browser_manager()


def _get_display_name(provider: str) -> str:
    """Friendly display name for a provider."""
    names = {
        "google": "Google AI Mode",
        "gemini": "Gemini Pro",
        "chatgpt": "ChatGPT",
    }
    return names.get(provider, provider.title())


# ──────────────── Startup Preloading ────────────────

_preload_status = {"state": "pending", "timings": {}}
_preload_lock = threading.Lock()


def _get_preload_urls() -> list[tuple[str, str]]:
    """Get URLs for preloading, using saved chat URLs where available."""
    urls = [
        ("google", config.GOOGLE_URL),
        ("gemini", config.GEMINI_URL),
        ("chatgpt", config.CHATGPT_URL),
    ]
    try:
        with open(config.CHAT_URLS_FILE, "r") as f:
            saved = json.load(f)
        urls = [
            ("google", config.GOOGLE_URL),
            ("gemini", saved.get("gemini") or config.GEMINI_URL),
            ("chatgpt", saved.get("chatgpt") or config.CHATGPT_URL),
        ]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return urls


def preload_all():
    """Background preloader: launch browser + open all tabs + create automators."""
    global _preload_status

    with _preload_lock:
        _preload_status["state"] = "loading"

    t_start = _time.perf_counter()

    try:
        # Step 1: Launch browser (auto-kills stale processes if needed)
        t_browser = _time.perf_counter()
        bm = get_browser_manager()

        # Safety check: if browser is dead from a prior run, reset and retry
        if not bm.is_alive():
            print("[preload] Browser not alive — resetting...")
            reset_browser_manager()
            _automators.clear()
            bm = get_browser_manager()

        browser_ms = round((_time.perf_counter() - t_browser) * 1000)
        print(f"[preload] Browser launched in {browser_ms}ms")

        # Step 2: Open all tabs (pages load in parallel in Chrome)
        tab_urls = _get_preload_urls()
        tab_timings = bm.preload_tabs(tab_urls)
        print(f"[preload] Tabs opened: {tab_timings}")

        # Step 3: Create all automator instances
        t_auto = _time.perf_counter()
        for name in _PROVIDER_CLASSES:
            try:
                auto = get_automator(name)
                # If resuming a saved chat, mark as in-conversation
                if hasattr(auto, '_chat_url') and auto._chat_url:
                    auto._in_conversation = True
            except Exception as e:
                print(f"[preload] {name} automator failed: {e}")
        auto_ms = round((_time.perf_counter() - t_auto) * 1000)

        total_ms = round((_time.perf_counter() - t_start) * 1000)

        with _preload_lock:
            _preload_status = {
                "state": "ready",
                "timings": {
                    "browser_ms": browser_ms,
                    "tabs": tab_timings,
                    "automators_ms": auto_ms,
                    "total_ms": total_ms,
                },
            }

        print(f"[preload] All ready in {total_ms}ms "
              f"(browser={browser_ms}ms, tabs={tab_timings}, automators={auto_ms}ms)")

    except Exception as e:
        with _preload_lock:
            _preload_status = {"state": "error", "error": str(e)}
        print(f"[preload] Failed: {e}")


def get_preload_status() -> dict:
    """Get current preload state."""
    with _preload_lock:
        return dict(_preload_status)
