"""
Flask Web Application — AI Command Center.
Multi-provider Web UI: routes queries to Google AI Mode, Gemini Pro, or ChatGPT.
"""
import threading
from flask import Flask, render_template, request, jsonify
from providers import get_automator, get_all_statuses, get_available_providers, preload_all, get_preload_status
from storage import get_storage
import config

app = Flask(__name__)

# Session state (in-memory, per-server-run)
session_conversations = []
session_lock = threading.Lock()


# ─────────────────────────── Pages ───────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ─────────────────────────── Send Prompt ───────────────────────────

@app.route("/api/send", methods=["POST"])
def api_send():
    """
    Send a prompt to the specified provider.
    Body: { prompt: str, provider?: str, followup?: bool }
    """
    import time as _time
    t_route_start = _time.perf_counter()

    data = request.get_json()
    prompt = data.get("prompt", "").strip()
    provider = data.get("provider", "google").strip().lower()
    followup = data.get("followup", False)

    if not prompt:
        return jsonify({"error": "Empty prompt"}), 400

    try:
        automator = get_automator(provider)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    storage = get_storage()

    t_before_scrape = _time.perf_counter()

    # Route to follow-up or new query
    if followup:
        result = automator.send_followup(prompt)
    else:
        result = automator.send_and_get_response(prompt)

    t_after_scrape = _time.perf_counter()

    # Track route overhead
    route_total = round((_time.perf_counter() - t_route_start) * 1000)
    scrape_total = round((t_after_scrape - t_before_scrape) * 1000)
    overhead = route_total - scrape_total
    result.setdefault("timing", {})["route_ms"] = route_total
    result["timing"]["overhead_ms"] = overhead

    # Save to file (Google AI Mode only)
    if result["success"] and provider == "google":
        filepath = storage.save_conversation(
            prompt=result["prompt"],
            response=result["response"],
            metadata={
                "timestamp": result["timestamp"],
                "provider": result.get("provider", provider),
            }
        )
        result["saved_to"] = filepath

    return jsonify(result)


# ─────────────────────────── New Conversation ───────────────────────────

@app.route("/api/new-conversation", methods=["POST"])
def api_new_conversation():
    """Reset conversation state for a provider."""
    data = request.get_json() or {}
    provider = data.get("provider", "google")

    try:
        automator = get_automator(provider)
        automator.new_conversation()
        return jsonify({"success": True, "provider": provider})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


# ─────────────────────────── Status ───────────────────────────

@app.route("/api/status", methods=["GET"])
def api_status():
    """Return status for all providers."""
    return jsonify(get_all_statuses())


@app.route("/api/status/<provider>", methods=["GET"])
def api_provider_status(provider):
    """Return status for a single provider."""
    try:
        automator = get_automator(provider)
        return jsonify(automator.get_status())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/warmup", methods=["GET"])
def api_warmup():
    """Return preload/warmup status."""
    return jsonify(get_preload_status())


# ─────────────────────────── Providers ───────────────────────────

@app.route("/api/providers", methods=["GET"])
def api_providers():
    """List all available providers."""
    return jsonify(get_available_providers())


# ─────────────────────────── Reconnect ───────────────────────────

@app.route("/api/reconnect", methods=["POST"])
def api_reconnect():
    """Reconnect a provider (close + reopen its tab)."""
    data = request.get_json() or {}
    provider = data.get("provider", "google")

    try:
        automator = get_automator(provider)
        automator.reconnect()
        return jsonify(automator.get_status())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/debug/dom", methods=["POST"])
def api_debug_dom():
    """Debug endpoint: run JS in a provider's tab and return result."""
    data = request.get_json() or {}
    provider = data.get("provider", "gemini")
    js = data.get("js", "return document.title;")

    try:
        automator = get_automator(provider)
        with automator.browser_manager.lock:
            automator.browser_manager.switch_to(provider)
            result = automator.browser_manager.driver.execute_script(js)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────── History ───────────────────────────

@app.route("/api/history", methods=["GET"])
def api_history():
    storage = get_storage()
    return jsonify(storage.list_conversations())


@app.route("/api/history/<filename>", methods=["GET"])
def api_read_history(filename):
    storage = get_storage()
    content = storage.read_conversation(filename)
    if content:
        return jsonify({"filename": filename, "content": content})
    return jsonify({"error": "File not found"}), 404


@app.route("/api/history/<filename>", methods=["DELETE"])
def api_delete_history(filename):
    storage = get_storage()
    if storage.delete_conversation(filename):
        return jsonify({"success": True})
    return jsonify({"error": "File not found"}), 404


# ─────────────────────────── Session ───────────────────────────

@app.route("/api/session", methods=["GET"])
def api_session():
    with session_lock:
        return jsonify(session_conversations)


@app.route("/api/session/save", methods=["POST"])
def api_save_session():
    storage = get_storage()
    with session_lock:
        if not session_conversations:
            return jsonify({"error": "No conversations in session"}), 400
        filepath = storage.save_session(session_conversations)
    return jsonify({"success": True, "filepath": filepath})


@app.route("/api/session/clear", methods=["POST"])
def api_clear_session():
    with session_lock:
        session_conversations.clear()
    return jsonify({"success": True})


# ─────────────────────────── Run ───────────────────────────

def run_web_app():
    if config.PRELOAD_ON_STARTUP:
        _preload_thread = threading.Thread(target=preload_all, daemon=True, name="preloader")
        _preload_thread.start()
    app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=False)
