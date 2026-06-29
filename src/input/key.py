"""Keyboard injector for keymapped rhythm games (Windows only).

Where Winds Meet (and similar piano/instrument minigames) map each lane to a
physical key (S D F J K L). Unlike Magic Tiles — which needs touch contacts at
screen points — here the cleanest, lowest-latency input is the keyboard itself:
each key is independent, so true simultaneous chords (multiple lanes pressed the
same frame) come for free, with none of the single-mouse-button serialization
that capped background mode.

Implementation: Win32 `SendInput` with SCANCODE flags (`KEYEVENTF_SCANCODE`).
Games that read DirectInput / raw scancodes (most do) honour scancode injection
where a virtual-key `keybd_event` is ignored, so we send Set-1 scancodes, not VK
codes. One key-state per lane ("slot"); `down`/`up` are idempotent so a repeated
schedule never double-fires.

Interface mirrors `touch.TouchInjector` (`down`/`up`/`tap`/`up_all`/`close`) so an
engine can swap input backends, except coordinates are irrelevant — a slot maps
to a key, not a point.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

_u = ctypes.windll.user32  # Windows-only: SendInput keyboard

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

# Set-1 (XT) make-codes for the keys a chart can use. Letter row + home row are
# all non-extended, so no EXTENDEDKEY flag is needed for the default S D F J K L.
_SCAN: dict[str, int] = {
    "a": 0x1E, "b": 0x30, "c": 0x2E, "d": 0x20, "e": 0x12, "f": 0x21,
    "g": 0x22, "h": 0x23, "i": 0x17, "j": 0x24, "k": 0x25, "l": 0x26,
    "m": 0x32, "n": 0x31, "o": 0x18, "p": 0x19, "q": 0x10, "r": 0x13,
    "s": 0x1F, "t": 0x14, "u": 0x16, "v": 0x2F, "w": 0x11, "x": 0x2D,
    "y": 0x15, "z": 0x2C,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
    "space": 0x39, ";": 0x27, "'": 0x28, ",": 0x33, ".": 0x34, "/": 0x35,
}


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _MOUSEINPUT(ctypes.Structure):
    # never used, but its size makes the union large enough for SendInput to read
    # the whole record (KEYBDINPUT is smaller than MOUSEINPUT on 64-bit).
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


_u.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
_u.SendInput.restype = wintypes.UINT


def _send(scan: int, up: bool) -> None:
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    inp = _INPUT(type=INPUT_KEYBOARD,
                 u=_INPUTUNION(ki=_KEYBDINPUT(0, scan, flags, 0, None)))
    _u.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


class KeyInjector:
    """Per-lane key-press injector. `keys[slot]` is the key for that lane.

    `x, y` arguments are accepted (so the engine can call it like a touch
    injector) but ignored — a keyboard press has no screen point.
    """

    def __init__(self, keys=("s", "d", "f", "j", "k", "l")) -> None:
        self._scans: list[int] = []
        for k in keys:
            kk = k.lower()
            if kk not in _SCAN:
                raise ValueError(f"no scancode for key {k!r}")
            self._scans.append(_SCAN[kk])
        self._down = [False] * len(self._scans)
        self.keys = tuple(k.lower() for k in keys)

    def down(self, slot: int, x: int = 0, y: int = 0) -> None:
        if 0 <= slot < len(self._scans) and not self._down[slot]:
            _send(self._scans[slot], up=False)
            self._down[slot] = True

    def up(self, slot: int) -> None:
        if 0 <= slot < len(self._scans) and self._down[slot]:
            _send(self._scans[slot], up=True)
            self._down[slot] = False

    def tap(self, slot: int, x: int = 0, y: int = 0, hold: float = 0.0) -> None:
        self.down(slot)
        if hold:
            time.sleep(hold)
        self.up(slot)

    def up_all(self) -> None:
        for s in range(len(self._scans)):
            self.up(s)

    def close(self) -> None:
        self.up_all()

    def __enter__(self) -> "KeyInjector":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


if __name__ == "__main__":  # quick self-test: tap S D F J K L with 0.3s gaps
    inj = KeyInjector()
    print("tapping", inj.keys, "in 2s — focus a text field to see output")
    time.sleep(2)
    for i in range(len(inj.keys)):
        inj.tap(i, hold=0.05)
        time.sleep(0.3)
    print("done")
