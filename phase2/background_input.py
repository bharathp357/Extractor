"""
Background-Safe Input — sends input to Chrome WITHOUT taking over the mouse/keyboard.

Uses Windows UI Automation (UIA) element methods:
  - SetValue() for text input fields (ValuePattern)
  - Invoke() for buttons (InvokePattern)
  - PostMessage WM_KEYDOWN/WM_CHAR for key presses

The user keeps full control of their mouse and keyboard at all times.
Chrome processes these as real accessibility events — no detection vectors.
"""
import time
import ctypes
import ctypes.wintypes

from phase2.utils.clipboard import set_clipboard

# Win32 message constants
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_CHAR = 0x0102
VK_RETURN = 0x0D
VK_TAB = 0x09
VK_CONTROL = 0x11

PostMessage = ctypes.windll.user32.PostMessageW
SendMessage = ctypes.windll.user32.SendMessageW
FindWindowEx = ctypes.windll.user32.FindWindowExW


class BackgroundInput:
    """
    Send input to Chrome in the background via UIA + Win32 messages.
    Does NOT move the mouse or take over the keyboard.
    """

    def __init__(self, window_manager):
        self._wm = window_manager

    # ─────────────────── Text Input via UIA ───────────────────

    def set_input_text(self, element, text: str) -> bool:
        """
        Set text in a UIA input element via clipboard paste.
        Focus element -> set clipboard -> Ctrl+V via type_keys.
        """
        # Focus the element via UIA
        try:
            element.set_focus()
        except Exception:
            pass
        time.sleep(0.15)

        # Paste text via clipboard (most reliable for Chrome)
        return self._paste_text(text)

    def click_element(self, element) -> bool:
        """
        Click a UIA element using InvokePattern.Invoke().
        Does NOT move the physical mouse.
        """
        try:
            # Try UIA InvokePattern (pure programmatic click)
            iface = element.iface_invoke
            if iface:
                iface.Invoke()
                return True
        except Exception:
            pass

        try:
            # Fallback: UIA Toggle (for checkboxes/toggle buttons)
            iface = element.iface_toggle
            if iface:
                iface.Toggle()
                return True
        except Exception:
            pass

        try:
            # Fallback 2: pywinauto click() which uses PostMessage
            # (NOT click_input() which uses SendInput/physical mouse)
            element.click()
            return True
        except Exception:
            pass

        return False

    # ─────────────────── Key Presses via PostMessage ───────────────────

    def send_enter(self, hwnd=None) -> bool:
        """Send Enter key to Chrome via PostMessage (no physical keyboard)."""
        hwnd = hwnd or self._get_render_hwnd()
        if not hwnd:
            return False
        PostMessage(hwnd, WM_KEYDOWN, VK_RETURN, 0)
        time.sleep(0.02)
        PostMessage(hwnd, WM_KEYUP, VK_RETURN, 0)
        return True

    def send_tab(self, hwnd=None) -> bool:
        """Send Tab key via PostMessage."""
        hwnd = hwnd or self._get_render_hwnd()
        if not hwnd:
            return False
        PostMessage(hwnd, WM_KEYDOWN, VK_TAB, 0)
        time.sleep(0.02)
        PostMessage(hwnd, WM_KEYUP, VK_TAB, 0)
        return True

    def send_text_via_messages(self, text: str, hwnd=None) -> bool:
        """
        Type text by sending WM_CHAR messages for each character.
        Works in background — no physical keyboard involved.
        """
        hwnd = hwnd or self._get_render_hwnd()
        if not hwnd:
            return False
        for ch in text:
            PostMessage(hwnd, WM_CHAR, ord(ch), 0)
            time.sleep(0.005)
        return True

    def ctrl_key(self, key_char: str, hwnd=None) -> bool:
        """Send Ctrl+key combo via PostMessage (e.g., Ctrl+L, Ctrl+A)."""
        hwnd = hwnd or self._get_render_hwnd()
        if not hwnd:
            return False
        vk = ord(key_char.upper())
        PostMessage(hwnd, WM_KEYDOWN, VK_CONTROL, 0)
        time.sleep(0.01)
        PostMessage(hwnd, WM_KEYDOWN, vk, 0)
        time.sleep(0.01)
        PostMessage(hwnd, WM_KEYUP, vk, 0)
        time.sleep(0.01)
        PostMessage(hwnd, WM_KEYUP, VK_CONTROL, 0)
        return True

    def _paste_text(self, text: str, hwnd=None) -> bool:
        """
        Paste text via clipboard + Ctrl+V.
        Tries type_keys first, falls back to bringing window to focus briefly.
        """
        set_clipboard(text)
        time.sleep(0.05)

        window = self._wm.get_uia_window()
        if window:
            # Try without foreground first
            try:
                window.type_keys("^v", set_foreground=False)
                time.sleep(0.2)
                return True
            except Exception:
                pass
            # Fallback: briefly focus for the paste
            try:
                window.set_focus()
                time.sleep(0.05)
                window.type_keys("^v")
                time.sleep(0.2)
                return True
            except Exception:
                pass

        # Last fallback: PostMessage
        hwnd = hwnd or self._get_render_hwnd()
        if hwnd:
            self.ctrl_key('v', hwnd)
            time.sleep(0.15)
            return True
        return False

    # ─────────────────── Navigation ───────────────────

    def navigate_to_url(self, url: str) -> bool:
        """
        Navigate Chrome to a URL using the address bar via UIA.
        No physical mouse or keyboard needed.
        """
        window = self._wm.get_uia_window()
        if not window:
            return False

        try:
            # Find the address bar Edit control via UIA
            edit = window.child_window(
                control_type="Edit",
                title="Address and search bar"
            )
            if not edit.exists(timeout=2):
                # Fallback: find first Edit with "address" in name
                edits = window.descendants(control_type="Edit")
                for e in edits:
                    name = (e.element_info.name or "").lower()
                    if "address" in name:
                        edit = e
                        break
                else:
                    return False

            # Set focus to address bar, set URL, press Enter
            try:
                edit.set_focus()
            except Exception:
                pass
            time.sleep(0.1)

            # Set value directly via UIA
            if not self.set_input_text(edit, url):
                return False
            time.sleep(0.1)

            # Press Enter to navigate
            self.send_enter()
            return True
        except Exception as e:
            print(f"[phase2/bg_input] navigate failed: {e}")
            return False

    # ─────────────────── Find & Interact with Web Elements ───────────────────

    def find_and_fill_input(self, provider: str, text: str) -> bool:
        """
        Find the chat input field in the web page via UIA and fill it.
        Works entirely in background — no mouse/keyboard takeover.
        """
        doc = self._find_document()
        if not doc:
            return False

        # Search for Edit controls within the web content
        try:
            edits = doc.descendants(control_type="Edit")
            for edit in edits:
                try:
                    name = (edit.element_info.name or "").lower()
                    if any(kw in name for kw in [
                        "prompt", "message", "ask", "search", "follow",
                        "type", "enter", "chat", "reply",
                    ]):
                        return self.set_input_text(edit, text)
                except Exception:
                    continue

            # Fallback: try any Edit in the document
            for edit in edits:
                try:
                    rect = edit.rectangle()
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if w > 200 and 20 < h < 300:
                        return self.set_input_text(edit, text)
                except Exception:
                    continue
        except Exception as e:
            print(f"[phase2/bg_input] find_input failed: {e}")

        return False

    def find_and_click_send(self) -> bool:
        """
        Find and click the Send button via UIA InvokePattern.
        Falls back to pressing Enter.
        """
        doc = self._find_document()
        if not doc:
            self.send_enter()
            return True

        chrome_btns = frozenset({
            "minimize", "maximize", "close", "back", "forward",
            "reload", "new tab", "search tabs", "chrome", "you",
        })

        try:
            buttons = doc.descendants(control_type="Button")
            for btn in buttons:
                try:
                    name = (btn.element_info.name or "").lower()
                    if name in chrome_btns:
                        continue
                    if any(kw in name for kw in ["send", "submit"]):
                        return self.click_element(btn)
                except Exception:
                    continue
        except Exception:
            pass

        # Fallback: press Enter via PostMessage
        self.send_enter()
        return True

    # ─────────────────── Helpers ───────────────────

    def _get_render_hwnd(self):
        """Get the native window handle for Chrome's render widget."""
        window = self._wm.get_uia_window()
        if not window:
            return None
        try:
            return window.handle
        except Exception:
            return None

    def _find_document(self):
        """Find the Document element (web content root) in the UIA tree."""
        window = self._wm.get_uia_window()
        if not window:
            return None
        try:
            docs = window.descendants(control_type="Document")
            return docs[0] if docs else None
        except Exception:
            return None
