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
