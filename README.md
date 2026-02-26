# AI Command Center

Multi-provider AI response extractor. Routes queries to **Google AI Mode**, **Gemini Pro**, and **ChatGPT** through a single unified interface — no API keys required.

Uses Selenium browser automation with stealth patches to interact with live AI services through a real Chrome session. Responses are scraped, cleaned, and returned via a Web UI, MCP server, or desktop app.

---

## Key Numbers

| Metric | Value |
|---|---|
| Google AI Mode latency | ~1.5s (warm) |
| ChatGPT latency | ~2.7s (warm) |
| Gemini Pro latency | ~3.9s (warm) |
| API cost | $0 |
| Providers | 3 (Google, Gemini, ChatGPT) |
| Interfaces | 3 (Web UI, MCP Server, Desktop) |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Browser Automation | Selenium 4.x + Chrome DevTools Protocol |
| Web Server | Flask 3.x |
| Desktop Wrapper | pywebview 6.1 |
| MCP Protocol | JSON-RPC 2.0 (HTTP + stdio) |
| Browser | Chrome (persistent profile, stealth mode) |
| Frontend | Vanilla HTML/CSS/JS (dark theme, no frameworks) |
| Storage | Flat text files (auto-pruned, max 10) |

---

## Project Structure

```
P2/
├── main.py                  # Entry point (--web, --mcp, --desktop, --mcp-stdio)
├── config.py                # All configuration constants
├── web_app.py               # Flask routes and REST API
├── mcp_server.py            # MCP server (JSON-RPC 2.0)
├── desktop.py               # PyWebView desktop wrapper
├── storage.py               # Conversation storage (text files, max 10, auto-prune)
├── requirements.txt         # Python dependencies
│
├── providers/               # Provider abstraction layer
│   ├── __init__.py          # Provider registry (lazy import, thread-safe singletons)
│   ├── base.py              # Abstract base class for all providers
│   ├── browser_manager.py   # Shared Chrome instance + tab management
│   ├── google_ai.py         # Google AI Mode scraper (~434 lines)
│   ├── gemini.py            # Gemini Pro scraper (~603 lines)
│   └── chatgpt.py           # ChatGPT scraper (~577 lines)
│
├── templates/
│   └── index.html           # Web UI (dark theme, 3 separate chat panels)
│
├── conversations/           # Saved AI Mode conversations (auto-pruned to 10)
├── ai_cmd_profile/          # Persistent Chrome profile (logins survive restarts)
└── .gitignore
```

---

## How It Works

1. **Launch** — `main.py` starts Flask (port 5050) and optionally the MCP server (port 5051). On first run, Chrome opens with a persistent profile.

2. **Browser Manager** — A singleton `BrowserManager` owns one Chrome process. Each provider gets its own tab. A `threading.Lock` serializes all driver access. Stealth CDP patches (`navigator.webdriver = undefined`, fake plugins/languages) are applied at launch.

3. **Provider Model** — Each provider (Google, Gemini, ChatGPT) extends `BaseAutomator`. They implement `send_and_get_response()`, `send_followup()`, `new_conversation()`, and handle their own DOM selectors, input methods, and response scraping.

4. **Query Flow** — User sends a prompt via the Web UI or MCP. Flask routes it to the correct provider's automator. The automator switches to its Chrome tab, types the prompt (via JS injection), waits for streaming to finish (combined JS polling), scrapes the response, cleans it, and returns it.

5. **Storage** — Only Google AI Mode conversations are saved to disk. Files are timestamped `.txt` logs. Auto-pruned to keep the most recent 10.

---

## Setup

### Prerequisites

- Python 3.11+
- Google Chrome installed
- Chrome user logged into Google, Gemini, and ChatGPT (first run only)

### Install

```bash
git clone https://github.com/bharathp08/Extractor.git
cd Extractor
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

### Run

```bash
# Web UI + MCP Server (default)
python main.py

# Web UI only
python main.py --web

# MCP Server only (HTTP)
python main.py --mcp

# MCP Server (stdio mode, for IDE integration)
python main.py --mcp-stdio

# Desktop app (PyWebView native window)
python main.py --desktop
```

On first launch, Chrome will open. Log into Google, Gemini, and ChatGPT manually. The persistent profile saves sessions — you only log in once.

Web UI: `http://127.0.0.1:5050`
MCP Server: `http://127.0.0.1:5051`

---

## API Reference

### Send Prompt

```
POST /api/send
Content-Type: application/json

{
  "prompt": "What is Docker?",
  "provider": "google",     // "google" | "gemini" | "chatgpt"
  "followup": false          // true = continue existing conversation
}
```

**Response:**
```json
{
  "success": true,
  "prompt": "What is Docker?",
  "response": "Docker is a platform for ...",
  "provider": "google",
  "timestamp": "2026-02-26 16:05:00",
  "timing": {
    "total_ms": 1493,
    "route_ms": 1510,
    "overhead_ms": 17
  }
}
```

### Other Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/status` | All provider connection statuses |
| GET | `/api/status/<provider>` | Single provider status |
| GET | `/api/providers` | List available providers |
| POST | `/api/new-conversation` | Reset conversation for a provider |
| POST | `/api/reconnect` | Close and reopen a provider's tab |
| GET | `/api/history` | List saved conversations (AI Mode only) |
| GET | `/api/history/<filename>` | Read a saved conversation |
| DELETE | `/api/history/<filename>` | Delete a saved conversation |

---

## MCP Tools

The MCP server exposes these tools to AI agents via JSON-RPC 2.0:

| Tool | Description |
|---|---|
| `send_prompt` | Send a query to any provider, get scraped response |
| `get_status` | Check provider connection status |
| `new_conversation` | Start a fresh conversation |
| `reconnect` | Reconnect a provider (close + reopen tab) |
| `list_history` | List saved conversation files |
| `read_history` | Read a saved conversation |
| `delete_history` | Delete a saved conversation |

---

## Performance Optimizations

- **Combined JS polling** — Single `execute_script` call per poll cycle checks streaming state + scrapes content simultaneously (replaces 5+ separate Selenium calls)
- **JS-based input** — Prompt typing via injected JavaScript (2 calls) instead of sequential Selenium `find_element` chains (10+ calls)
- **Zero implicit wait** — `implicit_wait(0)` eliminates 2s penalty per missed selector
- **Adaptive streaming detection** — Polls at 100ms intervals, requires 2 consecutive stable checks (200ms stability window)
- **No unnecessary navigation** — Follow-up messages stay in the same chat tab, no page reload
- **Persistent browser** — Chrome stays running between queries, no cold-start overhead

---

## Architecture Diagram

```
                        ┌─────────────┐
                        │   User /    │
                        │  AI Agent   │
                        └──────┬──────┘
                               │
                 ┌─────────────┼─────────────┐
                 │             │             │
          ┌──────▼──────┐ ┌───▼────┐ ┌──────▼──────┐
          │  Web UI     │ │  MCP   │ │  Desktop    │
          │  Flask:5050 │ │  :5051 │ │  PyWebView  │
          └──────┬──────┘ └───┬────┘ └──────┬──────┘
                 │            │             │
                 └─────────┬──┘─────────────┘
                           │
                  ┌────────▼────────┐
                  │ Provider Registry│
                  │  (lazy + thread  │
                  │   safe singletons│)
                  └────────┬────────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
     ┌──────▼──────┐ ┌────▼─────┐ ┌──────▼──────┐
     │ Google AI   │ │ Gemini   │ │  ChatGPT    │
     │ Mode        │ │ Pro      │ │             │
     └──────┬──────┘ └────┬─────┘ └──────┬──────┘
            │              │              │
            └──────────────┼──────────────┘
                           │
                  ┌────────▼────────┐
                  │ Browser Manager │
                  │ (1 Chrome, N    │
                  │  tabs, 1 Lock)  │
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │  Chrome + CDP   │
                  │  Stealth Mode   │
                  │  Persistent     │
                  │  Profile        │
                  └─────────────────┘
```

---

## Storage

- Only **Google AI Mode** conversations are saved to disk
- Format: timestamped `.txt` files in `conversations/`
- Auto-pruned to keep the **10 most recent** files
- Gemini and ChatGPT responses are not stored (transient only)
- Filename pattern: `YYYYMMDD_HHMMSS_prompt_snippet.txt`

---

## Configuration

All settings in `config.py`:

| Setting | Default | Description |
|---|---|---|
| `WEB_PORT` | 5050 | Flask server port |
| `MCP_PORT` | 5051 | MCP server port |
| `AI_RESPONSE_TIMEOUT` | 30s | Max wait for AI response |
| `AI_RESPONSE_POLL` | 0.1s | Poll interval |
| `STABLE_CHECKS` | 2 | Consecutive stable polls = done |
| `STREAMING_INITIAL_WAIT` | 0.05s | Pause before first poll |
| `CHROME_PROFILE_DIR` | `./ai_cmd_profile` | Persistent Chrome profile path |
| `HEADLESS` | false | Run Chrome without visible window |

---

## License

MIT
