"""
Phase 2 Configuration — all constants for undetectable automation.

Extends the base config with Phase 2-specific settings for human-like
mouse/keyboard behavior, UIA text extraction, and image matching.
"""
import os
import sys

# Add parent to path so we can import base config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as base_config

# === Paths ===
PHASE2_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_ASSETS_DIR = os.path.join(PHASE2_DIR, "image_assets")

# === Chrome Launch ===
CHROME_EXE = ""  # Auto-detect if empty
CHROME_PROFILE_DIR = base_config.CHROME_PROFILE_DIR  # Reuse Phase 1 profile
CHROME_LAUNCH_FLAGS = [
    "--force-renderer-accessibility",
    "--window-size=1400,900",
    "--window-position=100,50",
    "--lang=en-US",
]
CHROME_LAUNCH_TIMEOUT = 15  # seconds to wait for Chrome window to appear

# === Human Input: Mouse (Botasaurus-inspired) ===
MOUSE_SPEED_MIN = 0.15         # seconds for short moves (~50px)
MOUSE_SPEED_MAX = 0.6          # seconds for long moves (~1500px)
MOUSE_BEZIER_ORDER = 4         # 4th order Bezier (3 random control points)
MOUSE_JITTER_PX = 2            # perpendicular micro-jitter magnitude (pixels)
MOUSE_OVERSHOOT_PROB = 0.15    # 15% chance of overshoot-and-correct
MOUSE_OVERSHOOT_PX = 15        # max overshoot distance in pixels
MOUSE_DWELL_MEAN = 0.12        # mean dwell time before click (seconds, log-normal)
MOUSE_DWELL_SIGMA = 0.04       # sigma for dwell time

# === Human Input: Keyboard ===
KEYSTROKE_MEAN_MS = 95          # mean inter-key delay (milliseconds)
KEYSTROKE_SIGMA_MS = 30         # standard deviation
KEYSTROKE_PAUSE_PROB = 0.03     # 3% chance of longer "thinking" pause
KEYSTROKE_PAUSE_MS = 400        # thinking pause duration (ms)
PASTE_THRESHOLD = 100           # chars above which we paste instead of typing

# === UIA Text Extraction ===
UIA_SEARCH_TIMEOUT = 10         # seconds to wait for UIA elements
UIA_POLL_INTERVAL = 0.15        # seconds between UIA tree reads

# === Response Polling ===
RESPONSE_TIMEOUT = 45           # max wait for AI response (seconds)
RESPONSE_POLL_INTERVAL = 0.2    # seconds between response polls
STABLE_CHECKS = 3               # consecutive identical readings = done

# === Image Matching ===
IMAGE_CONFIDENCE = 0.85         # pyautogui locateOnScreen confidence threshold

# === Tab Indices (Chrome Ctrl+N shortcuts, 1-based) ===
TAB_INDICES = {
    "google": 1,
    "gemini": 2,
    "chatgpt": 3,
}

# === Provider URLs (reuse from base config) ===
GOOGLE_URL = base_config.GOOGLE_URL
GEMINI_URL = base_config.GEMINI_URL
CHATGPT_URL = base_config.CHATGPT_URL

# === Persistent Chat State (reuse from base) ===
CHAT_URLS_FILE = base_config.CHAT_URLS_FILE

# === Web / MCP Server (reuse from base) ===
WEB_HOST = base_config.WEB_HOST
WEB_PORT = base_config.WEB_PORT
MCP_HOST = base_config.MCP_HOST
MCP_PORT = base_config.MCP_PORT
