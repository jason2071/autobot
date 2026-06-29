"""List on-screen windows cross-platform, so the bot can target one of them.

Bounds are returned in *logical* screen points (what the OS reports). The GUI
scales them to physical pixels (what mss needs) using the capture/logical ratio.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # resolved for the type checker; real availability = the flags below
    import Quartz  # type: ignore
    import win32gui  # type: ignore

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
    hwnd: int | None = None  # Win32 window handle (None on macOS)


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
            Window(title=title, bounds={"top": top, "left": left, "width": w, "height": h},
                   hwnd=hwnd)
        )

    win32gui.EnumWindows(cb, None)
    return out


def _process_elevated(pid: int) -> bool | None:
    """Is the process `pid` running elevated (admin)? None if it can't be told."""
    try:
        import win32api  # type: ignore
        import win32con  # type: ignore
        import win32security  # type: ignore

        h = win32api.OpenProcess(
            win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        tok = win32security.OpenProcessToken(h, win32con.TOKEN_QUERY)
        return bool(win32security.GetTokenInformation(
            tok, win32security.TokenElevation))
    except Exception:
        return None


def we_are_elevated() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def input_blocked_by_uipi(hwnd: int) -> bool:
    """True when the target window runs elevated but we do NOT — Windows UIPI then
    silently drops our injected keyboard/mouse input even though focus + capture
    still work. The fix is to run this bot as Administrator."""
    if not (sys.platform.startswith("win") and _HAS_WIN32):
        return False
    try:
        import win32process  # type: ignore
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        return _process_elevated(pid) is True and not we_are_elevated()
    except Exception:
        return False


def list_windows() -> list[Window]:
    """Return visible windows, topmost first. Empty if unsupported."""
    if sys.platform == "darwin" and _HAS_QUARTZ:
        return _mac_windows()
    if sys.platform.startswith("win") and _HAS_WIN32:
        return _win_windows()
    return []


def focus_hwnd(hwnd: int) -> bool:
    """Force `hwnd` to the foreground, beating Windows' foreground lock.

    A plain SetForegroundWindow from a background process is usually refused
    (only the process that owns the current foreground / last input may set it),
    so we briefly AttachThreadInput to the current-foreground and target threads
    — which makes Windows treat the call as coming from the foreground — then
    detach. Without this the game never gets focus and injected keys land on
    whatever window does (e.g. the editor)."""
    if not (sys.platform.startswith("win") and _HAS_WIN32):
        return False
    import win32con  # type: ignore
    import win32process  # type: ignore
    import win32api  # type: ignore
    import ctypes

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    if win32gui.GetForegroundWindow() == hwnd:
        return True
    cur = win32api.GetCurrentThreadId()
    fg = win32gui.GetForegroundWindow()
    other = win32process.GetWindowThreadProcessId(fg)[0] if fg else 0
    tgt = win32process.GetWindowThreadProcessId(hwnd)[0]
    attached = [t for t in {other, tgt} if t and t != cur]
    for t in attached:
        ctypes.windll.user32.AttachThreadInput(cur, t, True)
    try:
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    finally:
        for t in attached:
            ctypes.windll.user32.AttachThreadInput(cur, t, False)
    return win32gui.GetForegroundWindow() == hwnd


def focus_window(title: str) -> bool:
    """Bring the window with this exact title to the foreground. Best effort;
    returns True if it found and raised the window."""
    if sys.platform.startswith("win") and _HAS_WIN32:
        target = []

        def cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == title:
                target.append(hwnd)

        win32gui.EnumWindows(cb, None)
        if not target:
            return False
        return focus_hwnd(target[0])

    if sys.platform == "darwin":
        # title is "Owner — Name"; activate the owning app via AppleScript.
        owner = title.split(" — ", 1)[0].strip()
        if not owner:
            return False
        import subprocess

        try:
            subprocess.run(
                ["osascript", "-e", f'tell application "{owner}" to activate'],
                check=False, capture_output=True, timeout=2,
            )
            return True
        except Exception:
            return False

    return False
