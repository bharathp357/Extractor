"""
Human-Like Input Simulation — the core anti-detection module.

Inspired by Botasaurus's humancursor: uses 4th-order Bezier curves for
mouse movement, Gaussian-distributed keystroke timing, micro-jitter,
overshoot-and-correct, and variable dwell times.

All input goes through Win32 SendInput (via PyAutoGUI), which enters the
OS kernel input queue — indistinguishable from physical hardware events.
Websites see isTrusted=true on every event.
"""
import time
import random
import math

import numpy as np
import pyautogui

from phase2 import config as p2config
from phase2.utils.clipboard import set_clipboard

# Disable PyAutoGUI's built-in pause — we add our own human-like delays
pyautogui.PAUSE = 0
# Safety: prevent pyautogui from throwing on edge-of-screen moves
pyautogui.FAILSAFE = True


class HumanInput:
    """OS-level human-like mouse and keyboard simulation."""

    def __init__(self):
        self._last_pos = pyautogui.position()

    # ─────────────────── Mouse ───────────────────

    def move_to(self, x: int, y: int):
        """Move mouse along a Bezier curve with micro-jitter."""
        start = pyautogui.position()
        end = (int(x), int(y))
        distance = math.hypot(end[0] - start[0], end[1] - start[1])

        if distance < 3:
            # Already at target
            pyautogui.moveTo(end[0], end[1], _pause=False)
            self._last_pos = end
            return

        # Duration proportional to distance (Fitts's law inspired)
        duration = self._movement_duration(distance)
        # ~5px per step, minimum 15 steps for smoothness
        steps = max(int(distance / 5), 15)

        # Generate Bezier path with random control points
        points = self._bezier_path(start, end, steps)

        # Add perpendicular micro-jitter (simulates hand tremor)
        points = self._add_jitter(points, p2config.MOUSE_JITTER_PX)

        # Execute the movement
        step_delay = duration / len(points)
        for px, py in points:
            cx, cy = int(round(px)), int(round(py))
            # Clamp to screen bounds
            cx = max(0, min(cx, pyautogui.size()[0] - 1))
            cy = max(0, min(cy, pyautogui.size()[1] - 1))
            pyautogui.moveTo(cx, cy, _pause=False)
            time.sleep(step_delay)

        # Final snap to exact target
        pyautogui.moveTo(end[0], end[1], _pause=False)
        self._last_pos = end

    def click(self, x: int, y: int, button: str = "left"):
        """Move to target with possible overshoot, dwell, then click."""
        # Overshoot pattern (15% of the time, like a real hand)
        if random.random() < p2config.MOUSE_OVERSHOOT_PROB:
            overshoot = random.randint(5, p2config.MOUSE_OVERSHOOT_PX)
            angle = random.uniform(0, 2 * math.pi)
            ox = int(x + overshoot * math.cos(angle))
            oy = int(y + overshoot * math.sin(angle))
            self.move_to(ox, oy)
            time.sleep(random.uniform(0.05, 0.15))
            self.move_to(x, y)
        else:
            self.move_to(x, y)

        # Dwell before click (log-normal distribution)
        dwell = random.lognormvariate(
            math.log(p2config.MOUSE_DWELL_MEAN),
            p2config.MOUSE_DWELL_SIGMA,
        )
        time.sleep(max(0.03, min(dwell, 0.5)))

        pyautogui.click(x, y, button=button, _pause=False)

    def double_click(self, x: int, y: int):
        """Double-click with human-like timing between clicks."""
        self.move_to(x, y)
        dwell = random.lognormvariate(
            math.log(p2config.MOUSE_DWELL_MEAN),
            p2config.MOUSE_DWELL_SIGMA,
        )
        time.sleep(max(0.03, min(dwell, 0.3)))
        pyautogui.doubleClick(x, y, _pause=False)

    def triple_click(self, x: int, y: int):
        """Triple-click to select a paragraph/line."""
        self.move_to(x, y)
        time.sleep(random.uniform(0.04, 0.12))
        pyautogui.click(x, y, clicks=3, _pause=False)

    # ─────────────────── Keyboard ───────────────────

    def type_text(self, text: str):
        """
        Type text with Gaussian-distributed inter-key delays.
        Auto-switches to paste mode for long text (>PASTE_THRESHOLD chars).
        """
        if len(text) > p2config.PASTE_THRESHOLD:
            self.paste_text(text)
            return

        for i, char in enumerate(text):
            # Use pyautogui.write for printable chars, press for special
            if char == "\n":
                pyautogui.press("enter", _pause=False)
            elif char == "\t":
                pyautogui.press("tab", _pause=False)
            else:
                pyautogui.write(char, _pause=False)

            # Gaussian inter-key delay
            delay_ms = random.gauss(
                p2config.KEYSTROKE_MEAN_MS, p2config.KEYSTROKE_SIGMA_MS
            )
            delay_ms = max(30, min(delay_ms, 300))  # clamp to realistic range

            # Occasional "thinking" pause (3% chance)
            if random.random() < p2config.KEYSTROKE_PAUSE_PROB:
                delay_ms += p2config.KEYSTROKE_PAUSE_MS

            # Extra pause after punctuation (like a real typist)
            if char in ".!?,;:":
                delay_ms += random.uniform(50, 150)

            time.sleep(delay_ms / 1000.0)

    def paste_text(self, text: str):
        """Paste text via clipboard (Ctrl+V). For long text or special chars."""
        set_clipboard(text)
        time.sleep(random.uniform(0.03, 0.08))
        pyautogui.hotkey("ctrl", "v", _pause=False)
        time.sleep(random.uniform(0.08, 0.15))

    def press_key(self, key: str):
        """Press and release a single key with realistic timing."""
        time.sleep(random.uniform(0.02, 0.06))
        pyautogui.press(key, _pause=False)
        time.sleep(random.uniform(0.03, 0.08))

    def hotkey(self, *keys):
        """Press a key combination (e.g., 'ctrl', 'l')."""
        time.sleep(random.uniform(0.02, 0.05))
        pyautogui.hotkey(*keys, _pause=False)
        time.sleep(random.uniform(0.03, 0.08))

    def scroll(self, clicks: int = 3, direction: str = "down"):
        """Scroll with variable speed. clicks = number of scroll ticks."""
        actual = -clicks if direction == "down" else clicks
        # Break into individual scroll ticks with variable timing
        for _ in range(abs(clicks)):
            pyautogui.scroll(1 if actual > 0 else -1, _pause=False)
            time.sleep(random.uniform(0.03, 0.12))

    # ─────────────────── Bezier Math ───────────────────

    def _bezier_path(self, start: tuple, end: tuple, steps: int) -> list:
        """
        Generate a 4th-order Bezier curve with 3 random control points.
        The control points are offset perpendicular to the straight line,
        creating natural-looking curved paths.
        """
        sx, sy = float(start[0]), float(start[1])
        ex, ey = float(end[0]), float(end[1])
        dx, dy = ex - sx, ey - sy
        line_len = math.hypot(dx, dy)

        if line_len < 1:
            return [start, end]

        # Unit vectors along and perpendicular to the line
        ux, uy = dx / line_len, dy / line_len
        px, py = -uy, ux  # perpendicular

        # 3 control points at t=0.25, 0.5, 0.75 with random perpendicular offset
        controls = []
        for t_frac in (0.25, 0.5, 0.75):
            # Position along the line
            base_x = sx + dx * t_frac
            base_y = sy + dy * t_frac
            # Random perpendicular offset (larger for longer moves)
            offset = random.gauss(0, line_len * 0.12)
            cx = base_x + px * offset
            cy = base_y + py * offset
            controls.append((cx, cy))

        # All Bezier points: start + 3 controls + end
        all_points = [(sx, sy)] + controls + [(ex, ey)]
        n = len(all_points) - 1  # degree = 4

        # Evaluate Bezier at each step
        path = []
        for step in range(steps + 1):
            t = step / steps
            bx, by = 0.0, 0.0
            for i, (cpx, cpy) in enumerate(all_points):
                coeff = self._bernstein(n, i, t)
                bx += coeff * cpx
                by += coeff * cpy
            path.append((bx, by))

        return path

    @staticmethod
    def _bernstein(n: int, i: int, t: float) -> float:
        """Bernstein polynomial basis function."""
        return math.comb(n, i) * (t ** i) * ((1 - t) ** (n - i))

    @staticmethod
    def _add_jitter(points: list, magnitude: float) -> list:
        """
        Add perpendicular micro-jitter to simulate hand tremor.
        Start and end points are kept exact.
        """
        if magnitude <= 0 or len(points) < 3:
            return points

        result = [points[0]]  # Keep start exact
        for i in range(1, len(points) - 1):
            px, py = points[i]
            jx = random.gauss(0, magnitude * 0.5)
            jy = random.gauss(0, magnitude * 0.5)
            result.append((px + jx, py + jy))
        result.append(points[-1])  # Keep end exact
        return result

    @staticmethod
    def _movement_duration(distance: float) -> float:
        """
        Calculate mouse movement duration based on distance.
        Inspired by Fitts's law: longer distance = more time, but logarithmic.
        Adds ±10% randomness.
        """
        min_d = p2config.MOUSE_SPEED_MIN
        max_d = p2config.MOUSE_SPEED_MAX
        # Logarithmic scaling (Fitts's law)
        if distance <= 1:
            duration = min_d
        else:
            # Scale: 50px -> ~0.15s, 500px -> ~0.35s, 1500px -> ~0.6s
            ratio = math.log(distance) / math.log(1500)
            duration = min_d + (max_d - min_d) * min(ratio, 1.0)

        # Add 10% randomness
        duration *= random.uniform(0.9, 1.1)
        return max(min_d, min(duration, max_d))
