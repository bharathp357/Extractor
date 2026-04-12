"""
Phase 2 Provider Registry — manages all AI provider automators using
PyWinAuto + PyAutoGUI (no Selenium/WebDriver).

Mirrors the Phase 1 registry API so the Flask/MCP consumers work unchanged:
    from phase2.providers import get_automator, get_all_statuses, preload_all
"""
import json
import threading
import time as _time

from phase2.window_manager import get_window_manager, reset_window_manager
from phase2 import config as p2config


# Phase 2 provider classes (lazy imports)
_PROVIDER_CLASSES = {
    "google": ("phase2.providers.google_ai", "GoogleAIModeAutomator"),
    "gemini": ("phase2.providers.gemini", "GeminiProAutomator"),
    "chatgpt": ("phase2.providers.chatgpt", "ChatGPTAutomator"),
}

# Active automator instances
_automators: dict = {}
_registry_lock = threading.Lock()


def _import_class(module_path: str, class_name: str):
    """Dynamic import to avoid circular dependencies."""
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def get_automator(provider: str = "google"):
    """
    Get or create a Phase 2 automator for the given provider.
    Thread-safe. Provider names: "google", "gemini", "chatgpt".
    """
    if provider not in _PROVIDER_CLASSES:
        raise ValueError(
            f"Unknown provider: '{provider}'. "
            f"Available: {list(_PROVIDER_CLASSES.keys())}"
        )

    if provider not in _automators:
        with _registry_lock:
            if provider not in _automators:
                module_path, class_name = _PROVIDER_CLASSES[provider]
                cls = _import_class(module_path, class_name)
                wm = get_window_manager()
                _automators[provider] = cls(wm)

    return _automators[provider]


def get_all_statuses() -> dict:
    """Return status for all registered providers."""
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
                "mode": "phase2",
            }
    return statuses


def get_available_providers() -> list:
    """Return list of all available provider info dicts."""
    result = []
    for name in _PROVIDER_CLASSES:
        result.append({
            "name": name,
            "display_name": _get_display_name(name),
            "initialized": name in _automators,
            "mode": "phase2",
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
        get_window_manager().close_all()
    except Exception:
        pass
    reset_window_manager()


def _get_display_name(provider: str) -> str:
    """Friendly display name for a provider."""
    names = {
        "google": "Google AI Mode",
        "gemini": "Gemini Pro",
        "chatgpt": "ChatGPT",
    }
    return names.get(provider, provider.title())


# ─────────────────── Startup Preloading ───────────────────

_preload_status = {"state": "pending", "timings": {}}
_preload_lock = threading.Lock()


def _get_preload_urls() -> list:
    """Get URLs for preloading, using saved chat URLs where available."""
    urls = [
        ("google", p2config.GOOGLE_URL),
        ("gemini", p2config.GEMINI_URL),
        ("chatgpt", p2config.CHATGPT_URL),
    ]
    try:
        with open(p2config.CHAT_URLS_FILE, "r") as f:
            saved = json.load(f)
        urls = [
            ("google", p2config.GOOGLE_URL),
            ("gemini", saved.get("gemini") or p2config.GEMINI_URL),
            ("chatgpt", saved.get("chatgpt") or p2config.CHATGPT_URL),
        ]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return urls


def preload_all():
    """
    Background preloader: launch Chrome (as normal process) + open all tabs
    + create automators. Phase 2 version — no WebDriver involved.
    """
    global _preload_status

    with _preload_lock:
        _preload_status["state"] = "loading"

    t_start = _time.perf_counter()

    try:
        # Step 1: Launch Chrome and connect PyWinAuto
        t_browser = _time.perf_counter()
        wm = get_window_manager()

        # Launch if not already alive
        if not wm.is_alive():
            tab_urls = _get_preload_urls()
            urls = [url for _, url in tab_urls]
            wm.launch_and_connect(urls)

            # Safety check
            if not wm.is_alive():
                print("[phase2/preload] Chrome not alive — resetting...")
                reset_window_manager()
                _automators.clear()
                wm = get_window_manager()
                wm.launch_and_connect(urls)

        browser_ms = round((_time.perf_counter() - t_browser) * 1000)
        print(f"[phase2/preload] Chrome ready in {browser_ms}ms")

        # Step 2: Register tabs
        tab_urls = _get_preload_urls()
        tab_timings = wm.preload_tabs(tab_urls)
        print(f"[phase2/preload] Tabs registered: {tab_timings}")

        # Step 3: Create all automator instances
        t_auto = _time.perf_counter()
        for name in _PROVIDER_CLASSES:
            try:
                auto = get_automator(name)
                if hasattr(auto, "_chat_url") and auto._chat_url:
                    auto._in_conversation = True
            except Exception as e:
                print(f"[phase2/preload] {name} automator failed: {e}")
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

        print(
            f"[phase2/preload] All ready in {total_ms}ms "
            f"(chrome={browser_ms}ms, tabs={tab_timings}, auto={auto_ms}ms)"
        )

    except Exception as e:
        with _preload_lock:
            _preload_status = {"state": "error", "error": str(e)}
        print(f"[phase2/preload] Failed: {e}")


def get_preload_status() -> dict:
    """Get current preload state."""
    with _preload_lock:
        return dict(_preload_status)
