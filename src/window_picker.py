"""List on-screen windows cross-platform, so the bot can target one of them.

Bounds are returned in *logical* screen points (what the OS reports). The GUI
scales them to physical pixels (what mss needs) using the capture/logical ratio.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

try:
    import Quartz  # type: ignore

    _HAS_QUARTZ = True
except ImportError:
    _HAS_QUARTZ = False

try:
    import win32gui  # type: ignore

    _HAS_WIN32 = True
except ImportError:
    _HAS_WIN32 = False

_MIN_SIDE = 40  # ignore tiny utility windows


@dataclass
class Window:
    title: str
    bounds: dict  # {"top","left","width","height"} in logical points


def _mac_windows() -> list[Window]:
    opts = (
        Quartz.kCGWindowListOptionOnScreenOnly
        | Quartz.kCGWindowListExcludeDesktopElements
    )
    wins = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID)
    out: list[Window] = []
    for w in wins:  # front-to-back
        if w.get("kCGWindowLayer", 0) != 0:
            continue
        b = w.get("kCGWindowBounds")
        if not b or b["Width"] < _MIN_SIDE or b["Height"] < _MIN_SIDE:
            continue
        owner = w.get("kCGWindowOwnerName", "") or ""
        name = w.get("kCGWindowName", "") or ""
        title = f"{owner} — {name}" if name else owner
        out.append(
            Window(
                title=title or f"window {w.get('kCGWindowNumber')}",
                bounds={
                    "top": int(b["Y"]),
                    "left": int(b["X"]),
                    "width": int(b["Width"]),
                    "height": int(b["Height"]),
                },
            )
        )
    return out


def _win_windows() -> list[Window]:
    out: list[Window] = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        w, h = right - left, bottom - top
        if w < _MIN_SIDE or h < _MIN_SIDE:
            return
        out.append(
            Window(title=title, bounds={"top": top, "left": left, "width": w, "height": h})
        )

    win32gui.EnumWindows(cb, None)
    return out


def list_windows() -> list[Window]:
    """Return visible windows, topmost first. Empty if unsupported."""
    if sys.platform == "darwin" and _HAS_QUARTZ:
        return _mac_windows()
    if sys.platform.startswith("win") and _HAS_WIN32:
        return _win_windows()
    return []
