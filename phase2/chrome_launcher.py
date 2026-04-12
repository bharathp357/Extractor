"""
Chrome Launcher — starts Chrome as a normal OS process (no WebDriver).

Zero automation fingerprint: no chromedriver, no CDP, no remote-debugging-port.
The only special flag is --force-renderer-accessibility for UIA tree access.
"""
import os
import time
import subprocess
import threading

from phase2 import config as p2config


def _kill_stale_chrome():
    """
    Kill leftover chrome.exe from previous runs that use OUR profile directory.
    Reuses Phase 1 WMIC-based approach but skips chromedriver (not used in Phase 2).
    """
    profile_dir = (
        os.path.normpath(p2config.CHROME_PROFILE_DIR).lower()
        if p2config.CHROME_PROFILE_DIR
        else None
    )
    killed = 0

    if not profile_dir:
        return 0

    try:
        result = subprocess.run(
            [
                "wmic", "process", "where", "name='chrome.exe'", "get",
                "ProcessId,CommandLine", "/FORMAT:CSV",
            ],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.strip().splitlines():
            if profile_dir in line.lower():
                parts = line.strip().split(",")
                if parts:
                    try:
                        pid = int(parts[-1].strip())
                        subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True, timeout=3,
                        )
                        killed += 1
                    except (ValueError, subprocess.TimeoutExpired):
                        pass
    except Exception:
        pass

    if killed:
        print(f"[phase2/launcher] Killed {killed} stale Chrome processes")
        time.sleep(1.5)
    return killed


class ChromeLauncher:
    """Launch and manage Chrome as a normal OS process (no WebDriver)."""

    def __init__(self):
        self._process = None
        self._lock = threading.Lock()

    def launch(self, urls: list = None) -> bool:
        """
        Launch Chrome with persistent profile and accessibility enabled.
        Returns True on success.
        """
        with self._lock:
            if self._process and self._process.poll() is None:
                print("[phase2/launcher] Chrome already running")
                return True

            chrome_exe = self._find_chrome()
            if not chrome_exe:
                print("[phase2/launcher] FATAL: Chrome executable not found")
                return False

            # Kill stale Chrome on our profile to release lock files
            _kill_stale_chrome()

            # Build launch arguments — NO automation flags
            args = [chrome_exe]

            # Persistent profile (reuses Phase 1's login sessions)
            profile_dir = p2config.CHROME_PROFILE_DIR
            if profile_dir:
                os.makedirs(profile_dir, exist_ok=True)
                args.append(f"--user-data-dir={os.path.abspath(profile_dir)}")

            # Phase 2 specific flags
            args.extend(p2config.CHROME_LAUNCH_FLAGS)

            # Initial URLs to open as tabs
            if urls:
                args.extend(urls)

            print(f"[phase2/launcher] Launching Chrome: {chrome_exe}")
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait for Chrome to initialize
            time.sleep(2.5)
            if self._process.poll() is not None:
                print("[phase2/launcher] Chrome exited immediately")
                self._process = None
                return False

            print(
                f"[phase2/launcher] Chrome launched successfully (PID {self._process.pid})"
            )
            return True

    def kill(self):
        """Terminate the Chrome process."""
        with self._lock:
            if self._process:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    try:
                        self._process.kill()
                    except Exception:
                        pass
                except Exception:
                    pass
                self._process = None
                print("[phase2/launcher] Chrome killed")

    def is_alive(self) -> bool:
        """Check if Chrome process is still running."""
        return self._process is not None and self._process.poll() is None

    @property
    def pid(self) -> int:
        """Return Chrome's process ID, or 0 if not running."""
        return self._process.pid if self._process else 0

    def _find_chrome(self) -> str:
        """Locate the Chrome executable on disk."""
        candidates = [
            p2config.CHROME_EXE,
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(
                r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
            ),
        ]
        for path in candidates:
            if path and os.path.isfile(path):
                return path
        return ""
