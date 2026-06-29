"""Capture a specific window's pixels via Win32 PrintWindow.

Unlike screen-region capture (mss), this grabs the *window's own* content even
when another app overlaps it — PrintWindow renders the window into an off-screen
DC. PW_RENDERFULLCONTENT (flag 2) also works for GPU/DirectX surfaces such as
the LDPlayer emulator.

Coordinates here are *window-local* (0,0 = window top-left). Use origin() to map
to absolute screen coords for clicking. Windows only.
"""

from __future__ import annotations

import ctypes
import re
from ctypes import windll, wintypes
from typing import Any

import numpy as np
import win32gui  # type: ignore
import win32ui  # type: ignore
import win32con  # type: ignore

_PW_RENDERFULLCONTENT = 2
_MONITOR_DEFAULTTONEAREST = 2
_MONITORINFOF_PRIMARY = 1


class _RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", wintypes.DWORD)]


def _window_monitor(hwnd: int) -> tuple[int, int, int, int, bool]:
    """(left, top, width, height, is_primary) of the monitor the window sits on,
    in physical screen pixels. Lets a dxcam capture pick the right OUTPUT and
    convert to output-local coords — without this, dxcam only sees the PRIMARY
    monitor and a window on a second display fails ('Invalid Region')."""
    u = windll.user32
    hmon = u.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    u.GetMonitorInfoW(hmon, ctypes.byref(mi))
    r = mi.rcMonitor
    return (r.left, r.top, r.right - r.left, r.bottom - r.top,
            bool(mi.dwFlags & _MONITORINFOF_PRIMARY))


def _parse_dxcam_outputs(info: str) -> list[dict]:
    """Parse `dxcam.output_info()` into [{device, output, width, height,
    primary}], so an output can be matched to a monitor by resolution."""
    out = []
    for m in re.finditer(
        r"Device\[(\d+)\]\s*Output\[(\d+)\]:\s*Res:\((\d+),\s*(\d+)\)"
        r".*?Primary:(\w+)", info):
        out.append({
            "device": int(m.group(1)), "output": int(m.group(2)),
            "width": int(m.group(3)), "height": int(m.group(4)),
            "primary": m.group(5).lower() == "true",
        })
    return out


class WindowCapture:
    """PrintWindow-based grabber for one HWND. Mirrors ScreenCapture.grab()."""

    def __init__(self, hwnd: int, method: str = "dxcam") -> None:
        """method:
          - "dxcam": DXGI desktop duplication of the window's SCREEN region —
            ~0.1ms/grab and pixel-correct (the composited frame), vs ~20ms for
            PrintWindow. The window must stay visible/uncovered (we already
            require that for touch). This is the default — low latency is what
            lets the bot keep up as a song speeds up.
          - "printwindow": ~20ms/grab but overlap-proof (renders even when
            covered). Correct fallback if dxcam is unavailable.
          - "bitblt": fast GDI blit, but reads the WRONG layer for LDPlayer
            (GPU surface) — kept only for non-emulator windows.
        """
        self.hwnd = hwnd
        self.method = method
        # cached GDI resources, (re)built only when the window size changes —
        # recreating a DC + bitmap every frame is the bulk of the per-grab cost
        self._dc: Any = None
        self._mfc: Any = None
        self._save: Any = None
        self._bmp: Any = None
        self._size = (0, 0)
        self._cam: Any = None      # dxcam camera (created lazily, per output)
        self._last: Any = None     # last good dxcam frame (grab() returns None if no
                              # new display frame yet — reuse the previous one)
        self._dxcam: Any = None    # the dxcam module
        self._outputs: list[dict] = []   # parsed output_info()
        self._out_key: tuple | None = None   # (device, output) of the live camera
        self._out_origin = (0, 0)  # that output's top-left in screen pixels
        if method == "dxcam":
            try:
                import dxcam
                self._dxcam = dxcam
                self._outputs = _parse_dxcam_outputs(dxcam.output_info())
            except Exception:  # fall back to PrintWindow if dxcam missing
                self.method = "printwindow"
                self._dxcam = None

    def origin(self) -> tuple[int, int]:
        """Current (left, top) of the window in absolute screen pixels."""
        l, t = win32gui.GetWindowRect(self.hwnd)[:2]
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

        if self.method == "dxcam":
            return self._grab_dxcam(l, t, w, h, region)

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

    def _ensure_cam(self) -> tuple[int, int]:
        """(Re)create the dxcam camera bound to the OUTPUT showing this window,
        and return that output's screen-pixel origin. dxcam grabs in coords local
        to its output, so a window on a second monitor needs the matching output
        plus an origin offset — `dxcam.create()` alone only ever sees the primary
        display."""
        ml, mt, mw, mh, primary = _window_monitor(self.hwnd)
        # match the dxcam output to this monitor by resolution (+ primary flag to
        # disambiguate identical resolutions); fall back to output 0.
        match = None
        for o in self._outputs:
            if o["width"] == mw and o["height"] == mh:
                if match is None or o["primary"] == primary:
                    match = o
        if match is None:
            match = self._outputs[0] if self._outputs else {"device": 0, "output": 0}
        key = (match["device"], match["output"])
        if key != self._out_key:
            if self._cam is not None:
                try:
                    self._cam.release()
                except Exception:
                    pass
            self._cam = self._dxcam.create(
                device_idx=match["device"], output_idx=match["output"],
                output_color="BGR")
            self._out_key = key
            self._last = None
        self._out_origin = (ml, mt)
        return ml, mt

    def _grab_dxcam(self, l, t, w, h, region) -> np.ndarray:
        """DXGI grab of the window's screen rect (in its OUTPUT's local coords),
        then crop the requested window-local region locally. Always captures the
        FULL window (so the cached `_last` has a stable shape across strip/full
        calls) and reuses it when the duplication API has no newer frame."""
        ox, oy = self._ensure_cam()
        ow = self._outputs and next(
            (o["width"] for o in self._outputs
             if (o["device"], o["output"]) == self._out_key), None)
        oh = next((o["height"] for o in self._outputs
                   if (o["device"], o["output"]) == self._out_key), None)
        sx, sy = max(l - ox, 0), max(t - oy, 0)
        ex = (min(l - ox + w, ow) if ow else l - ox + w)
        ey = (min(t - oy + h, oh) if oh else t - oy + h)
        reg = (sx, sy, ex, ey)
        frame = self._cam.grab(region=reg)
        if frame is None:           # no new display frame since last grab
            frame = self._last
            if frame is None:       # cold start: block briefly for first frame
                import time
                for _ in range(50):
                    frame = self._cam.grab(region=reg)
                    if frame is not None:
                        break
                    time.sleep(0.005)
                if frame is None:
                    raise RuntimeError("dxcam returned no frame (window off-screen?)")
        self._last = frame          # full-window frame, stable shape
        if region:
            y0 = max(int(region["top"]), 0)
            x0 = max(int(region["left"]), 0)
            y1 = min(y0 + int(region["height"]), frame.shape[0])
            x1 = min(x0 + int(region["width"]), frame.shape[1])
            frame = frame[y0:y1, x0:x1]
        return np.ascontiguousarray(frame)

    def close(self) -> None:
        self._free()
        if self._cam is not None:
            try:
                self._cam.release()
            except Exception:
                pass
            self._cam = None

    def __enter__(self) -> "WindowCapture":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
