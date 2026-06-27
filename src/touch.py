"""Background multi-touch via Win32 InjectTouchInput (Windows only).

Injects system-level touch contacts at *physical screen* coordinates. Unlike
pyautogui (moves the real cursor) or pynput (goes to the focused window), this
lands on whatever window is topmost at the point **without needing focus** — so
the bot can play while you work in another window, as long as the target stays
visible/uncovered.

One contact per lane ("slot") gives true multi-finger: several lanes can be held
at once (chords / simultaneous long notes). InjectTouchInput requires that EVERY
call carry the full set of currently-down contacts (held ones flagged UPDATE),
so the injector tracks active slots and re-sends them on every operation.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

try:
    _u = ctypes.windll.user32
    _OK = True
except Exception:  # pragma: no cover - non-Windows
    _OK = False

PT_TOUCH = 0x02
PF_DOWN, PF_UPDATE, PF_UP = 0x00010000, 0x00020000, 0x00040000
PF_INRANGE, PF_INCONTACT = 0x00000002, 0x00000004
_TOUCH_MASK = 0x1 | 0x2 | 0x4  # CONTACTAREA | ORIENTATION | PRESSURE


class _POINTER_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerType", wintypes.DWORD), ("pointerId", wintypes.DWORD),
        ("frameId", wintypes.DWORD), ("pointerFlags", wintypes.DWORD),
        ("sourceDevice", wintypes.HANDLE), ("hwndTarget", wintypes.HWND),
        ("ptPixelLocation", wintypes.POINT), ("ptHimetricLocation", wintypes.POINT),
        ("ptPixelLocationRaw", wintypes.POINT), ("ptHimetricLocationRaw", wintypes.POINT),
        ("dwTime", wintypes.DWORD), ("historyCount", wintypes.UINT),
        ("InputData", ctypes.c_int32), ("dwKeyStates", wintypes.DWORD),
        ("PerformanceCount", ctypes.c_uint64), ("ButtonChangeType", ctypes.c_int),
    ]


class _POINTER_TOUCH_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerInfo", _POINTER_INFO), ("touchFlags", wintypes.DWORD),
        ("touchMask", wintypes.DWORD), ("rcContact", wintypes.RECT),
        ("rcContactRaw", wintypes.RECT), ("orientation", wintypes.UINT),
        ("pressure", wintypes.UINT),
    ]


class TouchInjector:
    """Multi-finger touch injector. `slot` is the lane index (one finger each)."""

    # Reserved slot for the permanent anchor contact (see set_anchor).
    ANCHOR_SLOT = 100

    def __init__(self, max_contacts: int = 10) -> None:
        if not _OK:
            raise RuntimeError("touch injection needs Windows (user32)")
        # MODE_DEFAULT = 1
        if not _u.InitializeTouchInjection(max_contacts, 1):
            raise RuntimeError("InitializeTouchInjection failed")
        self._pos: dict[int, tuple[int, int]] = {}  # slot -> (x, y) currently down

    @staticmethod
    def _contact(slot: int, x: int, y: int, flags: int) -> _POINTER_TOUCH_INFO:
        t = _POINTER_TOUCH_INFO()
        t.pointerInfo.pointerType = PT_TOUCH
        t.pointerInfo.pointerId = slot + 1  # ids start at 1
        t.pointerInfo.pointerFlags = flags
        t.pointerInfo.ptPixelLocation = wintypes.POINT(int(x), int(y))
        t.touchMask = _TOUCH_MASK
        t.rcContact = wintypes.RECT(int(x) - 4, int(y) - 4, int(x) + 4, int(y) + 4)
        t.orientation = 90
        t.pressure = 32000
        return t

    def _inject(self, *, down=None, up=None) -> None:
        contacts = []
        for s, (x, y) in self._pos.items():
            if s == up:
                continue
            flag = (PF_DOWN if s == down else PF_UPDATE) | PF_INRANGE | PF_INCONTACT
            contacts.append(self._contact(s, x, y, flag))
        if up is not None and up in self._pos:
            x, y = self._pos[up]
            contacts.append(self._contact(up, x, y, PF_UP))
        if not contacts:
            return
        arr = (_POINTER_TOUCH_INFO * len(contacts))(*contacts)
        _u.InjectTouchInput(len(contacts), ctypes.byref(arr))

    def down(self, slot: int, x: int, y: int) -> None:
        """Press (and hold) a finger at the screen point for `slot`."""
        self._pos[slot] = (int(x), int(y))
        self._inject(down=slot)

    def move(self, slot: int, x: int, y: int) -> None:
        if slot in self._pos:
            self._pos[slot] = (int(x), int(y))
            self._inject()

    def up(self, slot: int) -> None:
        """Lift the finger for `slot`."""
        if slot in self._pos:
            self._inject(up=slot)
            self._pos.pop(slot, None)

    def tap(self, slot: int, x: int, y: int, hold: float = 0.0) -> None:
        """Quick down+up at a point (for one-off taps like START / menu)."""
        import time
        self.down(slot, x, y)
        if hold:
            time.sleep(hold)
        self.up(slot)

    def set_anchor(self, x: int, y: int) -> None:
        """Hold one PRIMARY contact down permanently at a harmless point.

        Windows promotes the *primary* touch pointer to a mouse move on UP, which
        jerks the real cursor to the touch point. By parking a permanent anchor
        as the primary pointer, every lane tap that follows is a *secondary*
        contact — so taps never move the cursor (the cursor only ever parks once,
        at the anchor). Call this BEFORE any lane down so the anchor owns primary.
        Anchor it on a non-interactive spot (e.g. the window's letterbox margin)
        so the held contact triggers no game action and no desktop press-and-hold.
        """
        self.down(self.ANCHOR_SLOT, x, y)

    def up_all(self) -> None:
        for slot in list(self._pos):
            self.up(slot)

    def close(self) -> None:
        self.up_all()
