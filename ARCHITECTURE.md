# Architecture — AI Command Center

Deep technical reference for the multi-provider AI response extractor.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Component Architecture](#component-architecture)
3. [Request Flow — End to End](#request-flow--end-to-end)
4. [Provider Layer](#provider-layer)
5. [Browser Manager](#browser-manager)
6. [DOM Scraping Strategy](#dom-scraping-strategy)
7. [Low-Latency Pipeline](#low-latency-pipeline)
8. [Anti-Detection](#anti-detection)
9. [Text Cleaning Pipeline](#text-cleaning-pipeline)
10. [Storage Layer](#storage-layer)
11. [MCP Protocol](#mcp-protocol)
12. [Frontend Architecture](#frontend-architecture)
13. [Threading Model](#threading-model)
14. [Configuration Reference](#configuration-reference)
15. [File Map](#file-map)

---

## 1. System Overview

The system operates as a **browser automation pipeline** that:

1. Maintains a single Chrome process with persistent login sessions
2. Manages one tab per AI provider (Google AI Mode, Gemini Pro, ChatGPT)
3. Exposes three interfaces: Web UI (Flask), MCP Server (JSON-RPC), Desktop (PyWebView)
4. Routes user queries to the specified provider via DOM injection
5. Polls for streaming completion using combined JavaScript execution
6. Scrapes, cleans, and returns the AI-generated response

No API keys. No LLM SDKs. Purely browser-based extraction.

---

## 2. Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              INTERFACES                                 │
│                                                                         │
│  ┌──────────────┐    ┌──────────────────┐    ┌────────────────────┐    │
│  │   Flask App   │    │   MCP Server     │    │  Desktop (PyWebView│)   │
│  │  web_app.py   │    │  mcp_server.py   │    │  desktop.py        │    │
│  │  port 5050    │    │  port 5051/stdio │    │  native window     │    │
│  └───────┬───────┘    └────────┬─────────┘    └─────────┬──────────┘   │
│          │                     │                        │               │
└──────────┼─────────────────────┼────────────────────────┼───────────────┘
           │                     │                        │
           └─────────────────────┼────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│                         PROVIDER LAYER                                  │
│                        providers/__init__.py                            │
│                                                                         │
│   Registry: lazy import → thread-safe singleton per provider            │
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────┐   │
│  │  GoogleAIMode   │  │   GeminiPro     │  │     ChatGPT          │   │
│  │  google_ai.py   │  │   gemini.py     │  │     chatgpt.py       │   │
│  │  434 lines      │  │   603 lines     │  │     577 lines        │   │
│  └────────┬────────┘  └────────┬────────┘  └──────────┬───────────┘   │
│           │                    │                       │                │
│           └────────────────────┼───────────────────────┘               │
│                                │                                        │
│                    ┌───────────▼───────────┐                           │
│                    │   BaseAutomator       │                           │
│                    │   base.py (95 lines)  │                           │
│                    └───────────┬───────────┘                           │
└────────────────────────────────┼────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│                        BROWSER LAYER                                    │
│                     browser_manager.py (297 lines)                      │
│                                                                         │
│   - ONE Chrome process, persistent user-data-dir                        │
│   - Per-provider tab management (open / switch / close)                 │
│   - threading.Lock serializes all WebDriver calls                       │
│   - Stealth CDP patches (navigator.webdriver, plugins, languages)       │
│   - Minimized window (user only sees Web UI)                            │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │   Chrome + CDP            │
                    │   Selenium 4.x WebDriver  │
                    │   Persistent profile       │
                    │   ai_cmd_profile/          │
                    └──────────────────────────┘
```

---

## 3. Request Flow — End to End

### Web UI Flow (user sends "What is Docker?" to Google AI Mode)

```
[Browser] POST /api/send {prompt: "What is Docker?", provider: "google"}
    │
    ▼
[web_app.py] api_send()
    ├── Validate input
    ├── get_automator("google")  →  lazy init if first call
    ├── t_start = perf_counter()
    │
    ▼
[google_ai.py] send_and_get_response("What is Docker?")
    ├── browser_manager.lock.acquire()
    ├── browser_manager.switch_to("google")
    ├── Navigate: google.com/search?q=What+is+Docker%3F&udm=50
    ├── Wait for AI container (WebDriverWait, 12s timeout)
    │
    ├── ── POLLING LOOP (100ms intervals) ──
    │   ├── execute_script(_JS_POLL_COMBINED)
    │   │   Returns: {streaming: bool, text: string}
    │   │
    │   ├── If streaming=true → reset stable counter, continue
    │   ├── If text changed → reset stable counter, continue
    │   ├── If text same → increment stable counter
    │   ├── If stable_count >= 2 → DONE
    │   └── If elapsed > 30s → TIMEOUT (try fallback JS)
    │
    ├── _clean_response(raw_text)
    │   ├── Strip noise lines (accessibility, controls)
    │   ├── Collapse whitespace
    │   └── Return cleaned text
    │
    ├── browser_manager.lock.release()
    └── Return result dict {success, prompt, response, timing}
    │
    ▼
[web_app.py] api_send() continued
    ├── Calculate overhead (route_ms - scrape_ms)
    ├── If provider == "google" → storage.save_conversation()
    │   └── _prune(max_keep=10)  →  delete oldest beyond 10
    └── Return JSON response

Total: ~1.5s (warm, Google) | ~2.7s (ChatGPT) | ~3.9s (Gemini)
```

### Follow-up Flow

Same as above, but:
- No page navigation — stays in the current chat tab
- Uses the existing conversation context
- Gemini/ChatGPT: types into the same input, scrapes the LAST response element
- Google AI Mode: navigates to a new URL (stateless search, no real follow-up)

---

## 4. Provider Layer

### BaseAutomator (Abstract)

```python
class BaseAutomator(ABC):
    provider_name: str     # "google", "gemini", "chatgpt"
    display_name: str      # "Google AI Mode", etc.
    browser_manager        # Shared BrowserManager instance

    # Abstract — each provider implements:
    send_and_get_response(prompt) -> dict    # New query
    send_followup(prompt) -> dict            # Continue conversation
    new_conversation() -> None               # Reset state
    get_status() -> dict                     # Connection info
    is_logged_in() -> bool                   # Auth check

    # Shared helpers:
    _make_result(prompt) -> dict             # Standard result skeleton
    reconnect() -> None                      # Close + reopen tab
    close() -> None                          # Close tab
```

### Provider Comparison

| Feature | Google AI Mode | Gemini Pro | ChatGPT |
|---|---|---|---|
| URL | google.com/search?udm=50 | gemini.google.com | chatgpt.com |
| Login required | No (Google account optional) | Yes (Google account) | Yes (OpenAI account) |
| Input method | URL navigation (query in URL) | JS injection into contenteditable | JS injection into textarea |
| Follow-up | New URL per query (stateless) | Same chat (stateful) | Same chat (stateful) |
| Streaming detection | Stop button visibility | Stop button + element count | Stop button + element count |
| Response scraping | AI Mode containers (8 selectors) | Last `.markdown` element | Last `assistant` message |
| Typical latency | 1.5s | 3.9s | 2.7s |
| Chat persistence | URL-based (no persistence) | Saves chat URL to .chat_urls.json | Saves chat URL to .chat_urls.json |

### DOM Selector Strategy

Each provider maintains multiple fallback selectors because AI service DOMs change frequently:

- **Google AI Mode**: 7 content selectors (`#aim-chrome-initial-inline-async-container`, `div[data-xid='aim-mars-turn-root']`, etc.)
- **Gemini**: 7 input selectors, 8 response selectors
- **ChatGPT**: 6 input selectors, 4 response selectors, 3 stop-button selectors

Selectors are tried in order of specificity. The first successful match is used.

---

## 5. Browser Manager

### Design Decisions

1. **Single Chrome process** — All providers share one browser instance. Launching 3 separate browsers would consume 3x memory and make anti-detection harder.

2. **Tab-per-provider** — Each provider gets its own tab (`window.open()`). The `BrowserManager` maps `provider_name → window_handle`.

3. **Serialized access** — One `threading.Lock` protects all WebDriver operations. Selenium's WebDriver is not thread-safe; concurrent `switch_to.window()` calls would corrupt state.

4. **Persistent profile** — `--user-data-dir=ai_cmd_profile/` keeps cookies, localStorage, and service workers across restarts. Users log in once.

5. **Fallback without profile** — If the profile is locked (another Chrome instance using it), the manager retries without `--user-data-dir`.

### Tab Lifecycle

```
open_tab("google", "https://google.com")
  → If first tab and on about:blank → reuse it
  → Otherwise → window.open('') → switch to new handle → navigate

switch_to("gemini")
  → If already active → no-op
  → driver.switch_to.window(handle)

close_tab("chatgpt")
  → switch to handle → driver.close() → switch to remaining tab
```

---

## 6. DOM Scraping Strategy

### Combined JS Polling (key optimization)

Instead of making 5+ separate Selenium calls per poll cycle:

```
OLD (slow):
  find_elements("stop button")     → 1 Selenium call
  find_elements("response div")    → 1 Selenium call
  get text from element            → 1 Selenium call
  Total: 3-5 roundtrips × 100ms each = 300-500ms per poll

NEW (fast):
  execute_script(_JS_POLL_COMBINED)  → 1 Selenium call
  Returns: {streaming: bool, text: string}
  Total: 1 roundtrip × ~15ms = 15ms per poll
```

The combined JS checks for streaming indicators AND scrapes content in a single DOM traversal.

### Google AI Mode — Two-Phase Scrape

1. **Primary JS** (`_JS_SCRAPE_AI`): Only AI Mode specific selectors. Fast, targeted.
2. **Fallback JS** (`_JS_SCRAPE_FALLBACK`): Broader `#center_col`, `#rso`, `main` areas. Used only at timeout as last resort.

### Content Validation

`_is_content_real(text)` filters false positives:
- Rejects text shorter than 20 characters
- Rejects exact matches against noise set (accessibility links, navigation)
- Rejects text containing disclaimer phrases

---

## 7. Low-Latency Pipeline

### Timing Breakdown (Google AI Mode, warm query)

| Phase | Duration | Technique |
|---|---|---|
| Route overhead (Flask) | ~17ms | Minimal JSON parsing |
| Tab switch | ~0ms | Already on Google tab (no-op) |
| URL navigation | ~400ms | Direct `driver.get()` |
| Container wait | ~200ms | WebDriverWait with CSS selector |
| Initial streaming wait | 50ms | `STREAMING_INITIAL_WAIT` |
| Polling (N cycles) | ~700ms | 100ms intervals, combined JS |
| Text cleaning | ~1ms | String operations |
| **Total** | **~1,493ms** | |

### Optimization Techniques Applied

1. `implicit_wait(0)` — Eliminates 2s penalty when a `find_element` fails
2. Combined JS polling — 1 roundtrip instead of 5 per cycle
3. JS-based input (Gemini/ChatGPT) — 2 calls instead of 10+ Selenium calls
4. 100ms poll interval (down from 500ms) — Detects completion faster
5. 2 stable checks (down from 4) — 200ms stability window
6. No settle phase — Removed unnecessary 2s sleep before polling
7. Persistent browser — No cold-start between queries

---

## 8. Anti-Detection

Applied once at Chrome launch, inherited by all tabs:

```javascript
// CDP: Page.addScriptToEvaluateOnNewDocument
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
window.chrome = { runtime: {} };
```

Chrome flags:
- `--disable-blink-features=AutomationControlled`
- `excludeSwitches: ["enable-automation"]`
- `useAutomationExtension: false`
- Random micro-delays (10-30ms) between actions

---

## 9. Text Cleaning Pipeline

Each provider has its own cleaner, but the pattern is shared:

```
Raw DOM text
    │
    ▼
Strip exact noise lines     (accessibility, nav, controls)
    │
    ▼
Strip contains-noise lines  (disclaimers, "AI can make mistakes")
    │
    ▼
Remove duplicate lines      (DOM sometimes renders content twice)
    │
    ▼
Collapse excessive whitespace
    │
    ▼
Trim leading/trailing
    │
    ▼
Clean text (returned to user)
```

Google AI Mode uses pre-compiled `frozenset` for O(1) noise lookup.

---

## 10. Storage Layer

### Design

```
storage.py → ConversationStorage (singleton)
    │
    ├── save_conversation(prompt, response, metadata)
    │   └── _prune(max_keep=10)  ←  auto-delete oldest
    │
    ├── list_conversations()  →  sorted desc by timestamp
    ├── read_conversation(filename)
    └── delete_conversation(filename)
```

### Rules

- **Only Google AI Mode** conversations are saved (filtered in `web_app.py`)
- Maximum **10 files** kept (auto-pruned after each save)
- Format: human-readable `.txt` with headers, dividers, metadata
- Filename: `YYYYMMDD_HHMMSS_prompt_snippet.txt`
- Directory: `conversations/`

### File Format

```
======================================================================
  AI COMMAND CENTER — CONVERSATION LOG
  Provider: google
  Date: 2026-02-26 16:05:16
======================================================================

----------------------------------------------------------------------
  PROMPT:
----------------------------------------------------------------------
What is Docker?

----------------------------------------------------------------------
  RESPONSE:
----------------------------------------------------------------------
Docker is a platform for developing, shipping, ...

----------------------------------------------------------------------
  METADATA:
----------------------------------------------------------------------
  timestamp: 2026-02-26 16:05:16
  provider: google

======================================================================
```

---

## 11. MCP Protocol

### JSON-RPC 2.0 over HTTP

```
POST http://127.0.0.1:5051/
Content-Type: application/json

{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "send_prompt", "arguments": {"prompt": "What is Docker?", "provider": "google"}}, "id": 1}
```

### Supported Methods

| Method | Description |
|---|---|
| `initialize` | Handshake, returns server info + capabilities |
| `tools/list` | List all available MCP tools |
| `tools/call` | Execute a tool (send_prompt, get_status, etc.) |

### stdio Mode

For IDE integration (e.g., Claude Desktop, Cursor):
```bash
python main.py --mcp-stdio
```
Reads JSON-RPC from stdin, writes responses to stdout. One request per line.

---

## 12. Frontend Architecture

### Layout

```
┌─────────────────────────────────────────────────────┐
│ Sidebar (240px)        │  Tab Bar                   │
│                        │  [AI Mode] [Gemini] [GPT]  │
│ ┌─ Providers ────────┐ ├───────────────────────────│
│ │ ● Google AI Mode    │ │                           │
│ │ ○ Gemini Pro        │ │    Active Chat Panel      │
│ │ ○ ChatGPT           │ │                           │
│ ├─ AI Mode History ──┤ │    (3 separate panels,     │
│ │ query_1.txt         │ │     only active visible)   │
│ │ query_2.txt         │ │                           │
│ │ ...                 │ │                           │
│ └────────────────────┘ │  ┌──────────────────────┐  │
│                        │  │ [textarea] [send btn] │  │
│                        │  └──────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### Key Design Decisions

- **3 separate chat panels** — Each provider has its own message list, input, and scroll position. Switching providers doesn't clear messages.
- **No frameworks** — Vanilla HTML/CSS/JS. Single file, ~500 lines.
- **Dark theme** — CSS custom properties, matches professional AI tool aesthetics.
- **No emojis** — Clean typography, SVG icons only.
- **History sidebar** — Shows only AI Mode saved conversations (max 10).
- **Status dots** — Green (connected), orange (needs login), gray (disconnected). Polled every 15s.

---

## 13. Threading Model

```
Main Thread
    │
    ├── Flask (blocking) or PyWebView (blocking)
    │
    ├── MCP Server Thread (daemon, if --mcp or default mode)
    │
    └── Browser Manager
        └── threading.Lock
            ├── Provider A acquire → switch_to → scrape → release
            ├── Provider B acquire → switch_to → scrape → release
            └── Provider C acquire → switch_to → scrape → release
```

- Flask handles concurrent HTTP requests via Werkzeug's thread pool
- All WebDriver calls are serialized through `BrowserManager.lock`
- Provider automators are thread-safe singletons (created once, reused)
- No async/await — synchronous Selenium calls within lock

---

## 14. Configuration Reference

All in `config.py`:

| Constant | Value | Purpose |
|---|---|---|
| `BROWSER` | `"chrome"` | Browser engine (chrome/edge) |
| `HEADLESS` | `False` | Headless mode |
| `CHROME_PROFILE_DIR` | `./ai_cmd_profile` | Persistent profile path |
| `PAGE_LOAD_WAIT` | `3` | Seconds to wait after navigation |
| `AI_RESPONSE_TIMEOUT` | `30` | Max seconds to wait for AI response |
| `AI_RESPONSE_POLL` | `0.1` | Poll interval (seconds) |
| `STABLE_CHECKS` | `2` | Consecutive same-content polls = done |
| `STREAMING_INITIAL_WAIT` | `0.05` | Pause before first poll |
| `IMPLICIT_WAIT` | `0` | Selenium implicit wait |
| `RANDOM_DELAY_MIN` | `0.01` | Anti-detection delay range |
| `RANDOM_DELAY_MAX` | `0.03` | Anti-detection delay range |
| `WEB_HOST` | `127.0.0.1` | Flask bind address |
| `WEB_PORT` | `5050` | Flask port |
| `MCP_HOST` | `127.0.0.1` | MCP bind address |
| `MCP_PORT` | `5051` | MCP port |
| `CHAT_URLS_FILE` | `.chat_urls.json` | Persisted chat URLs |
| `CONVERSATIONS_DIR` | `./conversations` | Saved conversation files |

---

## 15. File Map

| File | Lines | Purpose |
|---|---|---|
| `main.py` | 98 | Entry point, argument parsing, thread orchestration |
| `config.py` | 47 | All configuration constants |
| `web_app.py` | 212 | Flask routes, REST API |
| `mcp_server.py` | 367 | MCP JSON-RPC server (HTTP + stdio) |
| `desktop.py` | 119 | PyWebView desktop wrapper |
| `storage.py` | 173 | Conversation storage, auto-prune |
| `providers/__init__.py` | 103 | Provider registry, lazy singletons |
| `providers/base.py` | 95 | Abstract base class |
| `providers/browser_manager.py` | 297 | Chrome lifecycle, tab management |
| `providers/google_ai.py` | 434 | Google AI Mode scraper |
| `providers/gemini.py` | 603 | Gemini Pro scraper |
| `providers/chatgpt.py` | 577 | ChatGPT scraper |
| `templates/index.html` | ~500 | Web UI (dark theme, 3 panels) |
| **Total** | **~3,625** | |
