"""
Provider Registry — creates and manages all AI provider automators.

Usage:
    from providers import get_automator, get_all_statuses
    google = get_automator("google")
    result = google.send_and_get_response("What is Docker?")
"""
import threading
from providers.base import BaseAutomator
from providers.browser_manager import get_browser_manager, BrowserManager


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
    get_browser_manager().close_all()


def _get_display_name(provider: str) -> str:
    """Friendly display name for a provider."""
    names = {
        "google": "Google AI Mode",
        "gemini": "Gemini Pro",
        "chatgpt": "ChatGPT",
    }
    return names.get(provider, provider.title())
