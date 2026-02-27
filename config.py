"""
Configuration for AI Command Center — Multi-Provider
"""
import os

# === Paths ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONVERSATIONS_DIR = os.path.join(BASE_DIR, "conversations")

# === Browser Settings ===
BROWSER = "chrome"               # "chrome" or "edge"
HEADLESS = False                  # True = run browser in background (no visible window)
CHROME_PROFILE_DIR = os.path.join(BASE_DIR, "ai_cmd_profile")  # Persistent profile (logins survive)

# === Timing (seconds) — shared defaults ===
PAGE_LOAD_WAIT = 3
AI_MODE_CLICK_WAIT = 1
AI_RESPONSE_TIMEOUT = 30         # Max wait for AI response to finish generating
AI_RESPONSE_POLL = 0.1           # How often to check if response is complete (ultra-fast)
STABLE_CHECKS = 2                # Consecutive same-content checks = done (2 x 0.15s = 0.3s)
IMPLICIT_WAIT = 0                # Selenium implicit wait (0 = fast)
STREAMING_INITIAL_WAIT = 0.05    # Minimal pause after container found before first poll

# === Anti-Detection ===
RANDOM_DELAY_MIN = 0.01
RANDOM_DELAY_MAX = 0.03
USER_AGENT = ""                  # Custom user-agent (empty = browser default)

# === Provider URLs ===
GOOGLE_URL = "https://www.google.com"
GEMINI_URL = "https://gemini.google.com/app"
CHATGPT_URL = "https://chatgpt.com"

# === Web Server ===
WEB_HOST = "127.0.0.1"
WEB_PORT = 5050

# === MCP Server ===
MCP_HOST = "127.0.0.1"
MCP_PORT = 5051

# === Persistent Chat State ===
CHAT_URLS_FILE = os.path.join(BASE_DIR, ".chat_urls.json")  # Saves active chat URLs per provider

# === Startup Preloading ===
PRELOAD_ON_STARTUP = True         # Pre-launch browser + all tabs at startup
PRELOAD_TAB_TIMEOUT = 4           # Max seconds per tab during preload (parallel loading)

# Ensure directories exist
os.makedirs(CONVERSATIONS_DIR, exist_ok=True)
