"""Capture a specific window's pixels via Win32 PrintWindow.

Unlike screen-region capture (mss), this grabs the *window's own* content even
when another app overlaps it — PrintWindow renders the window into an off-screen
DC. PW_RENDERFULLCONTENT (flag 2) also works for GPU/DirectX surfaces such as
the LDPlayer emulator.

Coordinates here are *window-local* (0,0 = window top-left). Use origin() to map
to absolute screen coords for clicking. Windows only.
"""

from __future__ import annotations

import numpy as np

try:
    import win32gui  # type: ignore
    import win32ui  # type: ignore
    import win32con  # type: ignore
    from ctypes import windll

    _OK = True
except Exception:  # pragma: no cover - non-Windows
    _OK = False

_PW_RENDERFULLCONTENT = 2


class WindowCapture:
    """PrintWindow-based grabber for one HWND. Mirrors ScreenCapture.grab()."""

    def __init__(self, hwnd: int, method: str = "printwindow") -> None:
        """method: "bitblt" (fast, ~400fps, but reads on-screen pixels so it
        fails if another window overlaps) or "printwindow" (slower ~65fps but
        overlap-proof — renders the window even when covered)."""
        if not _OK:
            raise RuntimeError("window capture needs pywin32 (Windows only)")
        self.hwnd = hwnd
        self.method = method
        # cached GDI resources, (re)built only when the window size changes —
        # recreating a DC + bitmap every frame is the bulk of the per-grab cost
        self._dc = None
        self._mfc = None
        self._save = None
        self._bmp = None
        self._size = (0, 0)

    def origin(self) -> tuple[int, int]:
        """Current (left, top) of the window in absolute screen pixels."""
        l, t, _r, _b = win32gui.GetWindowRect(self.hwnd)
        return l, t

    def size(self) -> tuple[int, int]:
        l, t, r, b = win32gui.GetWindowRect(self.hwnd)
        return r - l, b - t

    def _free(self) -> None:
        if self._bmp is not None:
            win32gui.DeleteObject(self._bmp.GetHandle())
        if self._save is not None:
            self._save.DeleteDC()
        if self._mfc is not None:
            self._mfc.DeleteDC()
        if self._dc is not None:
            win32gui.ReleaseDC(self.hwnd, self._dc)
        self._dc = self._mfc = self._save = self._bmp = None

    def _ensure(self, w: int, h: int) -> None:
        if self._bmp is not None and self._size == (w, h):
            return
        self._free()
        self._dc = win32gui.GetWindowDC(self.hwnd)
        self._mfc = win32ui.CreateDCFromHandle(self._dc)
        self._save = self._mfc.CreateCompatibleDC()
        self._bmp = win32ui.CreateBitmap()
        self._bmp.CreateCompatibleBitmap(self._mfc, w, h)
        self._save.SelectObject(self._bmp)
        self._size = (w, h)

    def grab(self, region: dict | None = None) -> np.ndarray:
        """Return the window content as BGR. `region` (window-local
        {top,left,width,height}) crops the result; None returns the whole
        window."""
        l, t, r, b = win32gui.GetWindowRect(self.hwnd)
        w, h = r - l, b - t
        if w <= 0 or h <= 0:
            raise RuntimeError("window has no area (minimized?)")

        self._ensure(w, h)

        def _read() -> np.ndarray:
            buf = self._bmp.GetBitmapBits(True)  # BGRA, row-major
            return np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 4)[:, :, :3]

        if self.method == "printwindow":
            windll.user32.PrintWindow(self.hwnd, self._save.GetSafeHdc(),
                                      _PW_RENDERFULLCONTENT)
            arr = _read()
        else:  # bitblt — fast, but reads on-screen pixels (fails if covered)
            self._save.BitBlt((0, 0), (w, h), self._mfc, (0, 0), win32con.SRCCOPY)
            arr = _read()
            # if the window is covered / minimized, BitBlt yields (near) black —
            # fall back to PrintWindow so we still "see" the game this frame
            if arr[::8, ::8].mean() < 8:
                windll.user32.PrintWindow(self.hwnd, self._save.GetSafeHdc(),
                                          _PW_RENDERFULLCONTENT)
                arr = _read()

        if region:
            y0 = max(int(region["top"]), 0)
            x0 = max(int(region["left"]), 0)
            y1 = min(y0 + int(region["height"]), h)
            x1 = min(x0 + int(region["width"]), w)
            arr = arr[y0:y1, x0:x1]
        return np.ascontiguousarray(arr)

    def close(self) -> None:
        self._free()

    def __enter__(self) -> "WindowCapture":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
