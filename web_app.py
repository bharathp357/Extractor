"""
Flask Web Application — AI Command Center.
Multi-provider Web UI: routes queries to Google AI Mode, Gemini Pro, or ChatGPT.
Serves React frontend from static/react/ build output.
"""
import os
import threading
from flask import Flask, render_template, request, jsonify, send_from_directory
from providers import get_automator, get_all_statuses, get_available_providers, preload_all, get_preload_status
from storage import get_storage
import config

# React build directory
REACT_BUILD = os.path.join(os.path.dirname(__file__), "static", "react")

app = Flask(__name__, static_folder=REACT_BUILD, static_url_path="")

# Session state (in-memory, per-server-run)
session_conversations = []
session_lock = threading.Lock()


# ─────────────────────────── Pages ───────────────────────────

@app.route("/")
def index():
    """Serve React SPA; fallback to old template if build missing."""
    react_index = os.path.join(REACT_BUILD, "index.html")
    if os.path.exists(react_index):
        return send_from_directory(REACT_BUILD, "index.html")
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
    """Debug endpoint: dump UIA tree info for a provider's tab."""
    data = request.get_json() or {}
    provider = data.get("provider", "gemini")

    try:
        automator = get_automator(provider)
        wm = automator.window_manager

        with wm.lock:
            wm.switch_to(provider)
            import time as _t
            _t.sleep(0.5)

            result = {"provider": provider, "title": wm.get_title()}

            # Get UIA window
            window = wm.get_uia_window()
            if not window:
                result["error"] = "No UIA window"
                return jsonify(result)

            # Find Document
            docs = window.descendants(control_type="Document")
            result["document_count"] = len(docs)

            if docs:
                doc = docs[0]
                result["doc_name"] = doc.element_info.name or ""

                # Get all Edit controls in the document
                edits = doc.descendants(control_type="Edit")
                result["edits"] = []
                for e in edits:
                    try:
                        name = e.element_info.name or ""
                        rect = e.rectangle()
                        result["edits"].append({
                            "name": name[:80],
                            "rect": f"({rect.left},{rect.top},{rect.right},{rect.bottom})",
                        })
                    except Exception:
                        pass

                # Get all Text fragments (first 30)
                texts = doc.descendants(control_type="Text")
                result["text_count"] = len(texts)
                result["texts"] = []
                for t in texts[:30]:
                    try:
                        name = t.element_info.name
                        if name and name.strip():
                            result["texts"].append(name.strip()[:100])
                    except Exception:
                        pass

                # Get all Buttons in the document
                buttons = doc.descendants(control_type="Button")
                result["buttons"] = []
                for b in buttons[:15]:
                    try:
                        name = b.element_info.name or ""
                        result["buttons"].append(name[:50])
                    except Exception:
                        pass

            return jsonify(result)
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
