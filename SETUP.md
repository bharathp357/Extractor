# Setup Guide — AI Command Center

One-time setup. Copy-paste each block into your terminal.

---

## Step 1: Clone

```powershell
git clone https://github.com/bharathp357/Extractor.git
cd Extractor
```

---

## Step 2: Create venv + Install dependencies

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## Step 3: Run the tool

```powershell
.venv\Scripts\activate
python main.py --web
```

Open `http://127.0.0.1:5050` in your browser.

---

## Step 4: First-run login (one time only)

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

## Quick reference

| Action | Command |
|---|---|
| Run the tool | `.venv\Scripts\activate` then `python main.py --web` |
| Run with MCP server | `.venv\Scripts\activate` then `python main.py` |
| Run desktop app | `.venv\Scripts\activate` then `python main.py --desktop` |
| Run MCP only | `.venv\Scripts\activate` then `python main.py --mcp` |

---

## One-liner (after first setup)

```powershell
cd Extractor; .venv\Scripts\activate; python main.py --web
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Chrome won't start | Close all Chrome windows first, then retry |
| Profile locked error | Kill all `chrome.exe` processes: `Get-Process chrome \| Stop-Process -Force` |
| Provider shows orange dot | Login expired — open Chrome from taskbar, re-login |
| Provider shows gray dot | Click "Reconnect" in the UI |
| Port 5050 in use | Kill old process: `Get-Process python \| Stop-Process -Force` |

---

## Requirements

- Python 3.11+
- Google Chrome
- Windows 10/11
