"""Mouse clicking with DPI/Retina-aware coordinate scaling. Cross-platform.

Two backends:
- foreground (default off): pyautogui — moves the real cursor, then clicks.
  Works on macOS, Windows, Linux.
- background: clicks the window under the target point WITHOUT moving your
  physical cursor.
    * macOS:   Quartz CGEventPostToPid
    * Windows: Win32 PostMessage (WM_LBUTTONDOWN/UP) to the window at point
  Apps that read raw HID input or have anti-cheat may ignore synthetic events.

Captured frames are in *physical* pixels (Retina / DPI scaling). pyautogui and
the OS event APIs use *logical* points. We compute scale once and convert
before every click.
"""

from __future__ import annotations

import random
import time

import pyautogui

# Drag the mouse to a screen corner to abort (foreground backend only).
pyautogui.FAILSAFE = True

# --- platform backends for background clicking --------------------------------
try:
    import Quartz  # type: ignore

    _HAS_QUARTZ = True
except ImportError:
    _HAS_QUARTZ = False

try:
    import win32api  # type: ignore
    import win32con  # type: ignore
    import win32gui  # type: ignore

    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False

BACKGROUND_SUPPORTED = _HAS_QUARTZ or _HAS_WIN32


# --- macOS (Quartz) -----------------------------------------------------------
def _window_pid_at(x: float, y: float) -> int | None:
    """PID of the topmost normal window containing logical point (x, y)."""
    opts = (
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements
    )
    wins = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID)
    for w in wins:  # front-to-back order; first hit is topmost
        if w.get("kCGWindowLayer", 0) != 0:  # skip menubar/dock/overlays
            continue
        b = w.get("kCGWindowBounds")
        if not b:
            continue
        wx, wy, ww, wh = b["X"], b["Y"], b["Width"], b["Height"]
        if wx <= x < wx + ww and wy <= y < wy + wh:
            return w.get("kCGWindowOwnerPID")
    return None


def _mac_post_click(x: float, y: float) -> None:
    pos = Quartz.CGPointMake(x, y)
    pid = _window_pid_at(x, y)
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, pos, Quartz.kCGMouseButtonLeft
    )
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, pos, Quartz.kCGMouseButtonLeft
    )
    if pid and hasattr(Quartz, "CGEventPostToPid"):
        Quartz.CGEventPostToPid(pid, down)
        Quartz.CGEventPostToPid(pid, up)
    else:  # fallback: global tap (this DOES move the cursor)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


# --- Windows (Win32) ----------------------------------------------------------
def _win_post_click(x: float, y: float) -> None:
    ix, iy = int(x), int(y)
    hwnd = win32gui.WindowFromPoint((ix, iy))
    if not hwnd:
        return
    cx, cy = win32gui.ScreenToClient(hwnd, (ix, iy))  # window-relative coords
    lparam = win32api.MAKELONG(cx, cy)
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
    win32api.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)


def _post_background_click(x: float, y: float) -> None:
    if _HAS_QUARTZ:
        _mac_post_click(x, y)
    elif _HAS_WIN32:
        _win_post_click(x, y)


class Clicker:
    def __init__(
        self,
        capture_width: int,
        min_interval: float = 0.3,
        jitter: int = 0,
        background: bool = False,
    ) -> None:
        """capture_width: width in physical pixels of the captured monitor.

        scale = logical_width / physical_width  (e.g. 0.5 on Retina, <1 on
        Windows with display scaling).
        background: if True, click without moving the real cursor.
        """
        logical_width = pyautogui.size().width
        self.scale = logical_width / capture_width if capture_width else 1.0
        self.min_interval = min_interval
        self.jitter = jitter
        self.background = background and BACKGROUND_SUPPORTED
        if background and not BACKGROUND_SUPPORTED:
            raise RuntimeError(
                "background click needs Quartz (macOS) or pywin32 (Windows). "
                "pip install -r requirements.txt"
            )
        self._last_click = 0.0

    def _to_logical(self, x: int, y: int, offset: tuple[int, int]) -> tuple[float, float]:
        ox, oy = offset
        lx = (x + ox) * self.scale
        ly = (y + oy) * self.scale
        if self.jitter:
            lx += random.randint(-self.jitter, self.jitter)
            ly += random.randint(-self.jitter, self.jitter)
        return lx, ly

    def click_at(self, x: int, y: int, region_offset: tuple[int, int] = (0, 0)) -> bool:
        """Click a frame coordinate. Returns False if rate-limited."""
        now = time.monotonic()
        if now - self._last_click < self.min_interval:
            return False

        lx, ly = self._to_logical(x, y, region_offset)
        if self.background:
            _post_background_click(lx, ly)
        else:
            pyautogui.click(lx, ly)
        self._last_click = now
        return True
