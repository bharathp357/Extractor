"""
Screen utilities — screenshot capture and image matching.

Wraps PyAutoGUI's image recognition for finding UI elements on screen.
"""
import time

import pyautogui
from PIL import Image

from phase2 import config as p2config


def find_on_screen(image_path: str, confidence: float = None,
                   region: tuple = None):
    """
    Find an image on screen.

    Returns (center_x, center_y) or None if not found.
    """
    conf = confidence or p2config.IMAGE_CONFIDENCE
    try:
        location = pyautogui.locateOnScreen(
            image_path, confidence=conf, region=region
        )
        if location:
            return pyautogui.center(location)
    except pyautogui.ImageNotFoundException:
        pass
    except Exception:
        pass
    return None


def wait_for_image(image_path: str, timeout: float = 10,
                   confidence: float = None, poll: float = 0.3):
    """
    Poll until image appears on screen.

    Returns (center_x, center_y) or None on timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        pos = find_on_screen(image_path, confidence)
        if pos:
            return pos
        time.sleep(poll)
    return None


def wait_until_image_gone(image_path: str, timeout: float = 30,
                          confidence: float = None, poll: float = 0.3) -> bool:
    """
    Wait until an image disappears from screen (e.g. Stop button gone = done).

    Returns True if image disappeared, False on timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        pos = find_on_screen(image_path, confidence)
        if pos is None:
            return True
        time.sleep(poll)
    return False


def take_screenshot(region: tuple = None) -> Image.Image:
    """Capture screen or a specific region. Returns PIL Image."""
    return pyautogui.screenshot(region=region)
