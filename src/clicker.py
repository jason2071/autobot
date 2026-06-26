"""Mouse clicking with Retina-aware coordinate scaling.

Two backends:
- foreground (default): pyautogui — moves the real cursor, then clicks.
- background: Quartz CGEventPostToPid — posts the click directly to the window
  under the target point WITHOUT moving your physical cursor. macOS only.
  Apps that read raw HID input or have anti-cheat may ignore synthetic events.

Captured frames are in *physical* pixels (Retina = 2x). pyautogui / Quartz click
in *logical* points. We compute scale once and convert before every click.
"""

from __future__ import annotations

import random
import time

import pyautogui

# Drag the mouse to a screen corner to abort (foreground backend only).
pyautogui.FAILSAFE = True

try:
    import Quartz  # type: ignore

    _HAS_QUARTZ = True
except ImportError:  # non-macOS or pyobjc missing
    _HAS_QUARTZ = False


def _window_pid_at(x: float, y: float) -> int | None:
    """PID of the topmost normal window containing logical point (x, y)."""
    if not _HAS_QUARTZ:
        return None
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


def _post_background_click(x: float, y: float) -> None:
    """Post a left click at logical (x, y) to the window under it, no cursor move."""
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
    else:
        # fallback: global tap (this DOES move the cursor)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


class Clicker:
    def __init__(
        self,
        capture_width: int,
        min_interval: float = 0.3,
        jitter: int = 0,
        background: bool = False,
    ) -> None:
        """capture_width: width in physical pixels of the captured monitor.

        scale = logical_width / physical_width  (e.g. 0.5 on Retina).
        background: if True, click without moving the real cursor (macOS/Quartz).
        """
        logical_width = pyautogui.size().width
        self.scale = logical_width / capture_width if capture_width else 1.0
        self.min_interval = min_interval
        self.jitter = jitter
        self.background = background and _HAS_QUARTZ
        if background and not _HAS_QUARTZ:
            raise RuntimeError(
                "background click needs pyobjc-framework-Quartz (macOS). "
                "pip install pyobjc-framework-Quartz"
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
