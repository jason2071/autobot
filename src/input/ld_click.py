"""Background message-click into LDPlayer's render child window (Windows only).

This is an ALTERNATIVE input channel to `src/touch.py` (`InjectTouchInput`).
It posts Win32 `WM_LBUTTONDOWN/UP` messages straight to LDPlayer's internal
"RenderWindow"/"TheRender" child HWND — the technique used by the old C#
`EzCBot.LDClickBG`. Ported here as a *fallback* for surfaces the touch injector
can't reach (e.g. some video-ad SDK overlays where 200+ injected taps cleared
nothing): a posted window message may land where a system touch contact does not.

Caveats (read before relying on this):
- Newer LDPlayer builds render on a DX surface; message-based clicks are often
  IGNORED there. That is exactly why the bot's primary input is InjectTouchInput,
  not this. Treat this as "try it, measure it", not a drop-in replacement.
- Coordinates are CLIENT-relative to the *child render window*, not the main LD
  window. Use `child_origin()` to convert main-window-local coords (what the rest
  of the bot uses) into child-client coords.
- No cursor guard needed: posted messages never move the real cursor.

Standalone by design — import nothing from the bot. Delete this one file to drop
the experiment.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

_u = ctypes.windll.user32  # Windows-only: LDPlayer Win32 messaging

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001

# LDPlayer's render child. (class name, window text) candidates across versions.
_RENDER_CANDIDATES = [
    ("RenderWindow", "TheRender"),   # classic LDPlayer (matches EzCBot.LDClickBG)
    ("RenderWindow", None),
    ("subWin", None),                # some LD9 builds nest the render under subWin
]

_u.FindWindowExW.restype = wintypes.HWND
_u.FindWindowExW.argtypes = [
    wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
_u.SendMessageW.restype = ctypes.c_ssize_t
_u.SendMessageW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_u.PostMessageW.restype = wintypes.BOOL
_u.PostMessageW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_u.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]


def _lparam(x: int, y: int) -> int:
    """MAKELPARAM(x, y) — low word x, high word y."""
    return (int(y) & 0xFFFF) << 16 | (int(x) & 0xFFFF)


def _class_of(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    _u.GetClassNameW(hwnd, buf, 256)
    return buf.value


def find_render_child(hwnd):
    """Return the render-child HWND under `hwnd`, or None.

    Tries the known (class, text) pairs first; falls back to scanning every
    descendant for a class containing "Render".
    """
    if not hwnd:
        return None
    for cls, txt in _RENDER_CANDIDATES:
        child = _u.FindWindowExW(hwnd, None, cls, txt)
        if child:
            return child
    # Fallback: walk children, pick the first whose class mentions Render.
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(child, _):
        if "render" in _class_of(child).lower():
            found.append(child)
            return False  # stop
        return True

    _u.EnumChildWindows(hwnd, _enum, 0)
    return found[0] if found else None


def child_origin(parent, child) -> tuple[int, int]:
    """(dx, dy) offset of `child`'s top-left within `parent`'s window rect.

    Add this to a child-client coord to get a parent-window coord; subtract it to
    go the other way. Lets callers pass main-window-local coords and convert.
    """
    pr, cr = wintypes.RECT(), wintypes.RECT()
    _u.GetWindowRect(parent, ctypes.byref(pr))
    _u.GetWindowRect(child, ctypes.byref(cr))
    return (cr.left - pr.left, cr.top - pr.top)


class LDMessageClicker:
    """Message-based clicker bound to one LDPlayer window.

    `x, y` passed to click/drag are CLIENT coords of the render child. To use the
    bot's main-window-local coords, subtract `self.origin` first (or pass
    `main_local=True`).
    """

    def __init__(self, hwnd, post: bool = False) -> None:
        self.parent = hwnd
        self.child = find_render_child(hwnd)
        if not self.child:
            raise RuntimeError("LDPlayer render child not found (RenderWindow/TheRender)")
        self.origin = child_origin(hwnd, self.child)
        # SendMessage blocks until handled (sync); PostMessage queues (async).
        self._send = _u.PostMessageW if post else _u.SendMessageW

    def _xy(self, x: int, y: int, main_local: bool) -> tuple[int, int]:
        if main_local:
            return (int(x) - self.origin[0], int(y) - self.origin[1])
        return (int(x), int(y))

    def click(self, x: int, y: int, main_local: bool = False) -> None:
        cx, cy = self._xy(x, y, main_local)
        lp = _lparam(cx, cy)
        self._send(self.child, WM_LBUTTONDOWN, MK_LBUTTON, lp)
        self._send(self.child, WM_LBUTTONUP, 0, lp)

    def drag(self, x0: int, y0: int, x1: int, y1: int,
             main_local: bool = False) -> None:
        ax, ay = self._xy(x0, y0, main_local)
        bx, by = self._xy(x1, y1, main_local)
        self._send(self.child, WM_LBUTTONDOWN, MK_LBUTTON, _lparam(ax, ay))
        self._send(self.child, WM_MOUSEMOVE, MK_LBUTTON, _lparam(bx, by))
        self._send(self.child, WM_LBUTTONUP, 0, _lparam(bx, by))


class WMInjector:
    """Tap injector via WM-message clicks — a drop-in for `touch.TouchInjector`
    that works even when the target window is COVERED or unfocused, because the
    clicks are POSTED straight to the render-child HWND, not delivered to
    whatever is topmost at the screen point (which is what InjectTouchInput does,
    so that one needs the window visible/uncovered). This is the input half of
    "background mode" (paired with PrintWindow capture, which is likewise
    cover-proof).

    Same interface + same SCREEN coordinates as TouchInjector: per call the
    screen point is converted to render-child-client coords using the window's
    CURRENT rect, so a moved window still lands right. LIMITATION: one mouse
    button, so true simultaneous multi-touch (chords) is not possible —
    overlapping lane holds serialize to the latest point. Fine for
    one-tap-at-a-time play, weaker than InjectTouchInput on chord-heavy charts.
    """

    def __init__(self, hwnd, max_contacts: int = 10,
                 restore_cursor: bool = True) -> None:
        self._clk = LDMessageClicker(hwnd, post=True)  # PostMessage (async)
        self._cdx, self._cdy = self._clk.origin        # child offset in parent
        self._hwnd = hwnd
        self._down: dict[int, tuple[int, int]] = {}

    def _child(self, x: int, y: int) -> tuple[int, int]:
        r = wintypes.RECT()
        _u.GetWindowRect(self._hwnd, ctypes.byref(r))
        return (int(x) - r.left - self._cdx, int(y) - r.top - self._cdy)

    def down(self, slot: int, x: int, y: int) -> None:
        cx, cy = self._child(x, y)
        self._clk._send(self._clk.child, WM_LBUTTONDOWN, MK_LBUTTON, _lparam(cx, cy))
        self._down[slot] = (cx, cy)

    def move(self, slot: int, x: int, y: int) -> None:
        if slot in self._down:
            cx, cy = self._child(x, y)
            self._clk._send(self._clk.child, WM_MOUSEMOVE, MK_LBUTTON, _lparam(cx, cy))
            self._down[slot] = (cx, cy)

    def up(self, slot: int) -> None:
        if slot in self._down:
            cx, cy = self._down.pop(slot)
            self._clk._send(self._clk.child, WM_LBUTTONUP, 0, _lparam(cx, cy))

    def tap(self, slot: int, x: int, y: int, hold: float = 0.0) -> None:
        import time
        self.down(slot, x, y)
        if hold:
            time.sleep(hold)
        self.up(slot)

    def up_all(self) -> None:
        for s in list(self._down):
            self.up(s)

    def close(self) -> None:
        self.up_all()


if __name__ == "__main__":  # quick self-test: find LD render child + its offset
    import sys
    _u.FindWindowW.restype = wintypes.HWND
    _u.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    title = sys.argv[1] if len(sys.argv) > 1 else "LDPlayer"
    top = _u.FindWindowW(None, title)
    print(f"main hwnd ({title!r}): {top}")
    if top:
        ch = find_render_child(top)
        print(f"render child: {ch}  class={_class_of(ch) if ch else None}")
        if ch:
            print(f"child origin in parent: {child_origin(top, ch)}")
