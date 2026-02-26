"""
AI Command Center — Desktop App (PyWebView)

Launches the Flask backend in a background thread, then opens a native
desktop window pointing at the local UI. No browser tab needed.

Usage:
    python desktop.py                → Default 1200x800 window
    python desktop.py --fullscreen   → Fullscreen
    python desktop.py --debug        → Enable webview dev tools
"""
import sys
import threading
import argparse
import time

import config


def _start_flask():
    """Run the Flask app in a daemon thread (no stdout noise)."""
    import logging
    # Silence Flask/Werkzeug request logs in the console
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    from web_app import app
    app.run(
        host=config.WEB_HOST,
        port=config.WEB_PORT,
        debug=False,
        use_reloader=False,   # reloader spawns a child process — breaks pywebview
    )


def _start_mcp():
    """Run MCP server in a daemon thread."""
    from mcp_server import run_mcp_server
    run_mcp_server()


def _wait_for_flask(timeout: float = 10.0):
    """Block until Flask is accepting connections."""
    import urllib.request
    import urllib.error

    url = f"http://{config.WEB_HOST}:{config.WEB_PORT}/api/providers"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.3)
    return False


def main():
    parser = argparse.ArgumentParser(description="AI Command Center — Desktop")
    parser.add_argument("--fullscreen", action="store_true", help="Launch fullscreen")
    parser.add_argument("--debug", action="store_true", help="Enable webview dev tools")
    parser.add_argument("--width", type=int, default=1200, help="Window width (default 1200)")
    parser.add_argument("--height", type=int, default=800, help="Window height (default 800)")
    parser.add_argument("--no-mcp", action="store_true", help="Skip MCP server")
    args = parser.parse_args()

    print(r"""
    ╔══════════════════════════════════════════════════╗
    ║          ⚡ AI COMMAND CENTER — Desktop ⚡        ║
    ║                                                  ║
    ║   Google AI Mode • Gemini Pro • ChatGPT          ║
    ╚══════════════════════════════════════════════════╝
    """)

    # ── Start Flask backend ──
    flask_thread = threading.Thread(target=_start_flask, daemon=True)
    flask_thread.start()
    print(f"[*] Flask server starting on http://{config.WEB_HOST}:{config.WEB_PORT}")

    # ── Start MCP server (optional) ──
    if not args.no_mcp:
        mcp_thread = threading.Thread(target=_start_mcp, daemon=True)
        mcp_thread.start()
        print(f"[*] MCP server starting on http://{config.MCP_HOST}:{config.MCP_PORT}")

    # ── Wait for Flask to be ready ──
    print("[*] Waiting for backend...")
    if not _wait_for_flask():
        print("[!] Flask failed to start within 10s — launching window anyway")

    # ── Open native window ──
    import webview

    url = f"http://{config.WEB_HOST}:{config.WEB_PORT}"
    print(f"[*] Opening desktop window → {url}")

    window = webview.create_window(
        title="AI Command Center",
        url=url,
        width=args.width,
        height=args.height,
        resizable=True,
        min_size=(800, 500),
        text_select=True,
        fullscreen=args.fullscreen,
    )

    # webview.start() blocks until the window is closed
    webview.start(debug=args.debug)

    # Window closed — clean up
    print("[*] Window closed. Shutting down...")
    from providers import close_all
    close_all()


if __name__ == "__main__":
    main()
