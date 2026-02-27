# Setup Guide — AI Command Center

One-time setup. Copy-paste each block into your terminal.

---

## Prerequisites

- **Python 3.11+** → [python.org/downloads](https://www.python.org/downloads/)
- **Node.js 18+** → [nodejs.org](https://nodejs.org/) (needed to build the React frontend)
- **Google Chrome** (latest stable)
- **Git** → [git-scm.com](https://git-scm.com/)
- **Windows 10/11**

---

## Step 1: Clone

```powershell
git clone https://github.com/bharathp357/Extractor.git
cd Extractor
```

---

## Step 2: Python venv + dependencies

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## Step 3: Build the React frontend

```powershell
cd frontend
npm install
npm run build
cd ..
```

This compiles the React app into `static/react/` which Flask serves automatically.

---

## Step 4: Run the tool

```powershell
.venv\Scripts\activate
python main.py --web
```

Open **http://127.0.0.1:5050** in your browser.

---

## Step 5: First-run login (one time only)

On first launch, Chrome opens minimized in the background.

1. Open Chrome from the taskbar (it will be minimized)
2. You will see 3 tabs — Google, Gemini, ChatGPT
3. Log in to each one:
   - **Google tab** — Sign into your Google account (for AI Mode)
   - **Gemini tab** — Accept terms if prompted (uses same Google login)
   - **ChatGPT tab** — Sign into your OpenAI account
4. Minimize Chrome again
5. Go back to `http://127.0.0.1:5050` — status dots will turn green

That's it. Logins are saved in `ai_cmd_profile/`. You won't need to log in again on this machine.

---

## All run modes

| Mode | Command | Description |
|---|---|---|
| **Web UI** (default) | `python main.py --web` | React frontend at http://127.0.0.1:5050 |
| **MCP server** | `python main.py --mcp` | MCP protocol on port 5051 |
| **Both** | `python main.py` | Web UI + MCP server together |
| **Desktop** | `python main.py --desktop` | Standalone desktop window |

> Always activate the venv first: `.venv\Scripts\activate`

---

## Development (React hot-reload)

If you want to edit the React frontend with live reload:

**Terminal 1 — Flask backend:**
```powershell
cd Extractor
.venv\Scripts\activate
python main.py --web
```

**Terminal 2 — Vite dev server:**
```powershell
cd Extractor\frontend
npm run dev
```

Then open **http://localhost:5173** (Vite dev server). It proxies `/api/*` requests to Flask on port 5050 automatically.

When done, build for production:
```powershell
cd frontend
npm run build
```

---

## One-liner (after first setup)

```powershell
cd Extractor; .venv\Scripts\activate; python main.py --web
```

---

## Common commands

```powershell
# Kill stale Chrome/Python (if app won't start)
Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process chromedriver -ErrorAction SilentlyContinue | Stop-Process -Force
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force

# Rebuild React frontend after code changes
cd frontend; npm run build; cd ..

# Check what's using port 5050
Get-NetTCPConnection -LocalPort 5050 | Select-Object OwningProcess, State

# Update from GitHub
git pull origin main
cd frontend; npm install; npm run build; cd ..
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Chrome won't start | Close all Chrome windows first, then retry |
| `session not created` / connection refused | Kill all `chrome.exe` + `chromedriver.exe` processes, restart |
| Profile locked error | Kill all `chrome.exe`: `Get-Process chrome \| Stop-Process -Force` |
| Provider shows orange dot | Login expired — open Chrome from taskbar, re-login |
| Provider shows gray dot | Click "Reconnect" in the UI |
| Port 5050 in use | Kill old process: `Get-Process python \| Stop-Process -Force` |
| React UI not loading / old UI shows | Rebuild: `cd frontend; npm run build; cd ..` then restart |
| `npm run build` fails | Run `cd frontend; npm install` first |

---

## Project structure

```
Extractor/
├── main.py              # Entry point (--web, --mcp, --desktop)
├── web_app.py           # Flask server, serves React build
├── config.py            # Ports, timeouts, feature flags
├── storage.py           # Conversation file storage
├── providers/           # Selenium automators (Google, Gemini, ChatGPT)
├── frontend/            # React source (Vite + React 19 + Framer Motion)
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/  # ChatPanel, Message, Sidebar, Header, etc.
│   │   ├── utils/       # API client, constants
│   │   └── index.css    # Design system
│   ├── package.json
│   └── vite.config.js
├── static/react/        # Built React output (served by Flask)
├── ai_cmd_profile/      # Chrome user profile (login sessions)
└── conversations/       # Saved conversation files
```

---

## Benchmark Report — Google AI Mode Scraping Limits

**Test date:** Feb 27, 2026 · **35 queries sent, 0 blocked, 0 failures**

### How the test works

We sent queries back-to-back at 3 different speeds to find the sweet spot:

| Test | Queries | Delay between | Result |
|---|---|---|---|
| **Burst** (full speed) | 15 | 0s | ✅ All passed, 0 blocks |
| **Paced** | 10 | 2s | ✅ All passed, 0 blocks |
| **Safe** | 10 | 4s | ✅ All passed, 0 blocks |

### Latency (per query)

| Metric | Burst | Paced (2s) | Safe (4s) |
|---|---|---|---|
| **Average** | 4,455ms | 2,602ms | 2,582ms |
| **Minimum** | 1,763ms | 2,274ms | 2,072ms |
| **Maximum** | 30,830ms | 3,118ms | 4,170ms |
| **Avg response** | 1,591 chars | 1,723 chars | 1,766 chars |

> Burst mode had one outlier at 30.8s (likely Google throttling briefly), but never blocked.

### Throughput — How many queries can you scrape?

| Time Period | Burst (max) | Paced (recommended) | Safe (conservative) |
|---|---|---|---|
| **1 minute** | ~13 | ~14 | ~11 |
| **1 hour** | ~792 | ~828 | ~668 |
| **24 hours** | ~19,000 | ~19,800 | ~16,000 |
| **24h with cooldowns** | — | — | ~7,500 |

### Recommended usage patterns

| Use Case | Strategy | Queries/hr |
|---|---|---|
| **Light use** (interactive) | Type when you need, no limits | Unlimited |
| **Moderate scraping** | 2s delay between queries | ~600-800/hr |
| **Heavy scraping** | 4s delay + 5min break every 50 queries | ~400-500/hr |
| **24hr marathon** | 4s delay + 5min break every 50q | ~7,500/day |

### Will Google block you?

Based on our testing:

- **0 blocks** in 35 back-to-back queries (including 15 with zero delay)
- Google AI Mode is **very tolerant** of automated queries through a real browser
- The tool uses a **persistent Chrome profile** with real cookies/sessions — it looks like a real user
- Selenium stealth patches (CDP masking, navigator flags) help avoid detection
- **No CAPTCHAs** encountered during any test

### Why it doesn't get blocked

1. **Real browser** — not HTTP requests, actual Chrome with full JS rendering
2. **Persistent profile** — same cookies, history, fingerprint as a real user
3. **Stealth mode** — CDP detection patched, `navigator.webdriver` flag removed
4. **Human-like timing** — random micro-delays between actions
5. **Single session** — reuses the same tab, doesn't spam new connections

### Cooldown recommendations

| Duration | Suggested cooldown |
|---|---|
| Every 50 queries | 5 minute break |
| Every 200 queries | 15 minute break |
| Every 500 queries | 30 minute break |
| After 1000 queries | 1-2 hour break |

### Run the benchmark yourself

```powershell
.venv\Scripts\activate
python benchmark.py
```

Results are saved to `benchmark_report.json` with per-query timing data.
