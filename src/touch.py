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
import threading
import time
from ctypes import wintypes

try:
    _u = ctypes.windll.user32
    _k = ctypes.windll.kernel32
    _OK = True
except Exception:  # pragma: no cover - non-Windows
    _OK = False

PT_TOUCH = 0x02
PF_DOWN, PF_UPDATE, PF_UP = 0x00010000, 0x00020000, 0x00040000
PF_INRANGE, PF_INCONTACT = 0x00000002, 0x00000004
_TOUCH_MASK = 0x1 | 0x2 | 0x4  # CONTACTAREA | ORIENTATION | PRESSURE

# --- cursor guard: block the synthetic mouse that touch injection promotes ----
_WH_MOUSE_LL = 14
_WM_QUIT = 0x0012
_LLMHF_INJECTED = 0x00000001
_ULONG_PTR = ctypes.c_size_t

if _OK:
    _HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    _u.CallNextHookEx.restype = ctypes.c_ssize_t
    _u.CallNextHookEx.argtypes = [
        wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    _u.SetWindowsHookExW.restype = wintypes.HHOOK


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _CursorGuard:
    """Stops background touch from moving/clicking the real cursor.

    Windows promotes the primary touch pointer to synthetic mouse input, which
    jerks the cursor to the touch point (and could click another window). We
    can't demote our touches — LDPlayer only accepts the *primary* contact — so
    instead we install a low-level mouse hook (WH_MOUSE_LL) on a dedicated pumped
    thread that **swallows injected mouse events** (LLMHF_INJECTED) and passes
    genuine user input through. Net: taps land in the game, the cursor never
    follows, and the user's own mouse keeps working.
    """

    def __init__(self) -> None:
        self._tid: int | None = None
        self._hook = None
        self._proc = None  # keep the CFUNCTYPE alive
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        for _ in range(100):  # wait until the hook is installed (or fails)
            if self._hook is not None:
                break
            time.sleep(0.005)

    def _run(self) -> None:
        self._tid = _k.GetCurrentThreadId()
        self._proc = _HOOKPROC(self._cb)
        self._hook = _u.SetWindowsHookExW(_WH_MOUSE_LL, self._proc, None, 0) or 0
        msg = wintypes.MSG()
        while _u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _u.TranslateMessage(ctypes.byref(msg))
            _u.DispatchMessageW(ctypes.byref(msg))
        if self._hook:
            _u.UnhookWindowsHookEx(self._hook)

    def _cb(self, nCode, wParam, lParam):
        if nCode >= 0:
            ms = ctypes.cast(lParam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
            if ms.flags & _LLMHF_INJECTED:
                return 1  # swallow synthetic mouse from our touch injection
        return _u.CallNextHookEx(None, nCode, wParam, lParam)

    def close(self) -> None:
        if self._tid:
            _u.PostThreadMessageW(self._tid, _WM_QUIT, 0, 0)
            self._tid = None


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

    def __init__(self, max_contacts: int = 10, restore_cursor: bool = True) -> None:
        if not _OK:
            raise RuntimeError("touch injection needs Windows (user32)")
        # MODE_DEFAULT = 1
        if not _u.InitializeTouchInjection(max_contacts, 1):
            raise RuntimeError("InitializeTouchInjection failed")
        self._pos: dict[int, tuple[int, int]] = {}  # slot -> (x, y) currently down
        # Keep the real cursor still: a hook swallows the synthetic mouse input
        # Windows promotes from our injected touch (see _CursorGuard).
        self._guard = _CursorGuard() if restore_cursor else None

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
        if slot not in self._pos:
            return
        self._inject(up=slot)
        self._pos.pop(slot, None)

    def tap(self, slot: int, x: int, y: int, hold: float = 0.0) -> None:
        """Quick down+up at a point (for one-off taps like START / menu)."""
        import time
        self.down(slot, x, y)
        if hold:
            time.sleep(hold)
        self.up(slot)

    def up_all(self) -> None:
        for slot in list(self._pos):
            self.up(slot)

    def close(self) -> None:
        self.up_all()
        if self._guard is not None:
            time.sleep(0.03)  # let the hook swallow the last up's promotion
            self._guard.close()
            self._guard = None
