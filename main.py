"""
AI Command Center — Main Entry Point
Launches Web UI, MCP Server, and/or Desktop window.

Usage:
    python main.py              → Start Web UI + MCP Server
    python main.py --desktop    → Start Desktop app (PyWebView)
    python main.py --web        → Start Web UI only
    python main.py --mcp        → Start MCP Server (HTTP) only
    python main.py --mcp-stdio  → Start MCP Server (stdio) only
"""
import sys
import threading
import argparse


def banner():
    print(r"""
    ╔══════════════════════════════════════════════════╗
    ║          ⚡ AI COMMAND CENTER ⚡                 ║
    ║                                                  ║
    ║   Multi-Provider AI Scraper                      ║
    ║   Google AI Mode • Gemini Pro • ChatGPT          ║
    ║   Web UI + MCP Server + Desktop                  ║
    ╚══════════════════════════════════════════════════╝
    """)


def start_web():
    """Start the Flask Web UI server."""
    from web_app import run_web_app
    run_web_app()


def start_mcp_http():
    """Start the MCP server over HTTP."""
    from mcp_server import run_mcp_server
    run_mcp_server()


def start_mcp_stdio():
    """Start the MCP server in stdio mode."""
    from mcp_server import run_stdio_mode
    run_stdio_mode()


def main():
    parser = argparse.ArgumentParser(description="AI Command Center")
    parser.add_argument("--web", action="store_true", help="Start Web UI only")
    parser.add_argument("--mcp", action="store_true", help="Start MCP Server (HTTP) only")
    parser.add_argument("--mcp-stdio", action="store_true", help="Start MCP Server (stdio) only")
    parser.add_argument("--desktop", action="store_true", help="Start Desktop app (PyWebView)")
    args = parser.parse_args()

    banner()

    # Desktop mode — delegate to desktop.py
    if args.desktop:
        print("[*] Launching Desktop app...")
        from desktop import main as desktop_main
        desktop_main()
        return

    # If --mcp-stdio, run in stdio mode (blocking, no other servers)
    if args.mcp_stdio:
        print("[*] Starting MCP Server (stdio mode)...")
        start_mcp_stdio()
        return

    # If specific mode requested
    if args.web and not args.mcp:
        print("[*] Starting Web UI only...")
        start_web()
        return

    if args.mcp and not args.web:
        print("[*] Starting MCP Server (HTTP) only...")
        start_mcp_http()
        return

    # Default: Start both Web UI and MCP Server in parallel
    import config
    print(f"[*] Starting Web UI at http://{config.WEB_HOST}:{config.WEB_PORT}")
    print(f"[*] Starting MCP Server at http://{config.MCP_HOST}:{config.MCP_PORT}")
    print(f"[*] Conversations stored in: {config.CONVERSATIONS_DIR}")
    print()

    # MCP in background thread
    mcp_thread = threading.Thread(target=start_mcp_http, daemon=True)
    mcp_thread.start()

    # Web UI in main thread (blocking)
    start_web()


if __name__ == "__main__":
    main()
