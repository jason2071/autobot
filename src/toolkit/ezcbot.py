"""EzCBot toolkit — reusable emulator-bot primitives (Windows only).

A Python port of the *reusable* parts of the old C# `cs/EzCBot.cs` general bot
toolkit, collected into one standalone module so they can be reused outside the
tiles bot (any LDPlayer / Nox / BlueStacks automation).

The bot ALREADY has better versions of the heavy pieces, so this module REUSES
them rather than re-porting:
  - window capture  -> `window_capture.WindowCapture` (dxcam / PrintWindow)
  - template match  -> `detector.match_template` / `find_color` / `check_pixel`
  - LDPlayer click  -> `ld_click.LDMessageClicker`  (EzCBot `LDClickBG`)
…and re-exports them below. What this file ADDS is the EzCBot functionality the
repo lacked: window management, live-pixel read, region pixel-search returning a
coordinate, message-based clicks, and small utilities.

EzCBot.cs method -> here:
  FindWindow / FindWindowEx ........ find_window / find_window_ex
  GetWindowText / GetClassName ..... window_text / class_name
  GetControlSize / GetWindowRect ... window_size / window_rect
  ActiveWindow / HideApp / ShowAPP . activate / hide / show
  MoveWindow / WindowMove .......... move_window
  CheckProcess / loadProcessList ... process_running / list_windows
  GetColorAt / GETCOLOR ............ get_pixel / pixel_match
  PixelSearch / McPixelSearch ...... pixel_search / mc_pixel_search
  Search (EmguCV match) ............ find_image
  Clicktobg / BSClickBG ............ msg_click / bs_click
  LDClickBG ........................ ld_click.LDMessageClicker (re-exported)
  RandomNumber / RandomString ...... rand / rand_string
  saveLogFile ...................... save_log
  SendLine* ........................ DROPPED (LINE Notify API shut down 2025)
"""

from __future__ import annotations

import ctypes
import datetime
import random
import string
from ctypes import wintypes

import numpy as np

import win32api  # type: ignore
import win32con  # type: ignore
import win32gui  # type: ignore

# Re-export the repo's superior implementations so callers get one entry point.
from ..detect.detector import check_pixel, find_color, match_template, load_template  # noqa: E402
from ..capture.window_capture import WindowCapture  # noqa: E402

try:
    from ..input.ld_click import LDMessageClicker, find_render_child  # noqa: E402
except Exception:  # ld_click is Windows-only too
    LDMessageClicker = None  # type: ignore
    find_render_child = None  # type: ignore

__all__ = [
    "WindowCapture", "match_template", "find_color", "check_pixel", "load_template",
    "LDMessageClicker", "find_render_child",
    "find_window", "find_window_ex", "window_text", "class_name",
    "window_rect", "window_size", "activate", "hide", "show", "move_window",
    "process_running", "list_windows",
    "capture", "get_pixel", "pixel_match", "pixel_search", "mc_pixel_search",
    "find_image", "msg_click", "bs_click", "mouse_click",
    "rand", "rand_string", "save_log",
]


def _lparam(x: int, y: int) -> int:
    return (int(y) & 0xFFFF) << 16 | (int(x) & 0xFFFF)


# --- Window management (EzCBot: FindWindow / ActiveWindow / MoveWindow ...) ----

def find_window(class_name: str | None = None, title: str | None = None) -> int:
    """HWND of a top-level window by class and/or title (0 if none)."""
    return win32gui.FindWindow(class_name, title)


def find_window_ex(parent: int, child_after: int,
                   class_name: str | None, title: str | None) -> int:
    return win32gui.FindWindowEx(parent, child_after, class_name, title)


def window_text(hwnd: int) -> str:
    return win32gui.GetWindowText(hwnd)


def class_name(hwnd: int) -> str:
    return win32gui.GetClassName(hwnd) or ""


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) in absolute screen pixels."""
    return win32gui.GetWindowRect(hwnd)


def window_size(hwnd: int) -> tuple[int, int]:
    l, t, r, b = window_rect(hwnd)
    return r - l, b - t


def activate(hwnd: int) -> None:
    """Show + bring to foreground + focus (EzCBot ActiveWindow)."""
    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
    win32gui.SetForegroundWindow(hwnd)


def hide(hwnd: int) -> None:
    win32gui.ShowWindow(hwnd, win32con.SW_HIDE)


def show(hwnd: int) -> None:
    win32gui.ShowWindow(hwnd, win32con.SW_SHOW)


def move_window(hwnd: int, x: int, y: int,
                w: int | None = None, h: int | None = None) -> None:
    """Move (and optionally resize) a window. Keeps current size if w/h None."""
    if w is None or h is None:
        cw, ch = window_size(hwnd)
        w, h = w or cw, h or ch
    win32gui.MoveWindow(hwnd, x, y, w, h, True)


def process_running(exe_name: str) -> bool:
    """True if a process whose image name contains `exe_name` is running.

    EzCBot CheckProcess (Process.GetProcessesByName). Uses Toolhelp32 so it has
    no third-party dependency. `exe_name` is matched case-insensitively as a
    substring, e.g. "dnplayer", "LDPlayer", "Nox".
    """
    TH32CS_SNAPPROCESS = 0x00000002

    class _PE32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    k = ctypes.windll.kernel32
    snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return False
    needle = exe_name.lower()
    try:
        entry = _PE32()
        entry.dwSize = ctypes.sizeof(_PE32)
        ok = k.Process32First(snap, ctypes.byref(entry))
        while ok:
            if needle in entry.szExeFile.decode(errors="ignore").lower():
                return True
            ok = k.Process32Next(snap, ctypes.byref(entry))
        return False
    finally:
        k.CloseHandle(snap)


def list_windows(keyword: str | None = None) -> list[tuple[int, str, str]]:
    """Visible top-level windows as (hwnd, title, class).

    `keyword` (case-insensitive) filters title+class — e.g. "ld", "nox",
    "player". Replaces EzCBot loadProcessList for finding an emulator window.
    """
    out: list[tuple[int, str, str]] = []

    def _cb(h, _):
        if not win32gui.IsWindowVisible(h):
            return
        t = win32gui.GetWindowText(h) or ""
        c = win32gui.GetClassName(h) or ""
        if not t.strip():
            return
        if keyword and keyword.lower() not in (t + c).lower():
            return
        out.append((h, t, c))

    win32gui.EnumWindows(_cb, None)
    return out


# --- Capture + color (EzCBot: CaptureWindow / GetColorAt) ----------------------

def capture(hwnd: int, method: str = "printwindow") -> np.ndarray:
    """One-shot grab of a window as a BGR ndarray (EzCBot CaptureWindow).

    Creates and tears down a WindowCapture each call — fine for occasional menu
    checks, but for a hot loop hold a `WindowCapture` and call `.grab()` instead.
    Defaults to PrintWindow (overlap-proof, correct GPU layer for LDPlayer).
    """
    cap = WindowCapture(hwnd, method=method)
    try:
        return cap.grab()
    finally:
        cap.close()


def get_pixel(frame: np.ndarray, x: int, y: int) -> tuple[int, int, int]:
    """(B, G, R) of a pixel in an already-grabbed frame (EzCBot GetColorAt).

    Reading from a captured frame (not GDI GetPixel) gets the correct layer for
    GPU-rendered emulators, where raw GetPixel can read the wrong surface.
    """
    if y < 0 or x < 0 or y >= frame.shape[0] or x >= frame.shape[1]:
        raise IndexError(f"({x},{y}) out of frame {frame.shape[1]}x{frame.shape[0]}")
    b, g, r = frame[y, x][:3]
    return int(b), int(g), int(r)


def pixel_match(frame: np.ndarray, x: int, y: int,
                bgr: tuple[int, int, int], tol: int = 20) -> bool:
    """True if pixel (x,y) matches `bgr` within per-channel `tol` (EzCBot GETCOLOR)."""
    return check_pixel(frame, x, y, bgr, tol)


# --- Pixel search (EzCBot: PixelSearch / McPixelSearch) ------------------------

def pixel_search(frame: np.ndarray, bgr: tuple[int, int, int], tol: int = 0,
                 rect: tuple[int, int, int, int] | None = None
                 ) -> tuple[int, int] | None:
    """First pixel matching `bgr` within `tol`, scanning top-left → bottom-right.

    Returns (x, y) in frame coords, or None. `rect` = (left, top, right, bottom)
    restricts the search region. EzCBot PixelSearch, vectorised with numpy.
    """
    sub = frame
    ox, oy = 0, 0
    if rect:
        l, t, r, b = rect
        ox, oy = max(l, 0), max(t, 0)
        sub = frame[oy:max(b, 0), ox:max(r, 0)]
    if sub.size == 0:
        return None
    bb, gg, rr = (sub[..., 0].astype(int), sub[..., 1].astype(int),
                  sub[..., 2].astype(int))
    B, G, R = bgr
    mask = ((np.abs(bb - B) <= tol) & (np.abs(gg - G) <= tol)
            & (np.abs(rr - R) <= tol))
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return None
    return int(xs[0] + ox), int(ys[0] + oy)


def mc_pixel_search(frame: np.ndarray, cx: int, cy: int, radius: int,
                    bgr: tuple[int, int, int], tol: int = 0
                    ) -> tuple[int, int] | None:
    """Pixel search in a box of `radius` around (cx, cy) (EzCBot McPixelSearch)."""
    return pixel_search(frame, bgr, tol,
                        (cx - radius, cy - radius, cx + radius, cy + radius))


# --- Image search (EzCBot: Search via EmguCV MatchTemplate) --------------------

def find_image(frame: np.ndarray, template: np.ndarray | str,
               accuracy: float = 0.9) -> tuple[int, int] | None:
    """Best template match center in `frame`, or None below `accuracy`.

    `template` may be a path or a loaded BGR array. EzCBot Search, on top of the
    repo's tint-robust grayscale `match_template`.
    """
    tpl = load_template(template) if isinstance(template, str) else template
    hits = match_template(frame, tpl, threshold=accuracy)
    if not hits:
        return None
    x, y, _ = max(hits, key=lambda h: h[2])
    return x, y


# --- Message clicks (EzCBot: Clicktobg / BSClickBG) ----------------------------

def msg_click(hwnd: int, x: int, y: int) -> None:
    """Background left-click via SendMessage to `hwnd` (EzCBot Clicktobg).

    Window-local coords. NOTE: like all message clicks, often IGNORED by DX-
    rendered emulators (LDPlayer) — the bot's reliable path is InjectTouchInput
    (`touch.py`). For LDPlayer specifically use `LDMessageClicker` (posts to the
    render child) instead of this.
    """
    lp = _lparam(x, y)
    win32gui.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
    win32gui.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, lp)


def bs_click(hwnd: int, x: int, y: int) -> None:
    """BlueStacks-style click: Send + Post both messages (EzCBot BSClickBG)."""
    lp = _lparam(x, y)
    win32gui.SendMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp)
    win32gui.SendMessage(hwnd, win32con.WM_LBUTTONUP, 0, lp)
    win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lp)


def mouse_click(hwnd: int, x: int, y: int, button: str = "left") -> None:
    """Real-cursor click at a window-local point (EzCBot MouseClick).

    WARNING: moves the actual mouse cursor (unlike msg_click / touch). Provided
    for parity; prefer the background methods so the user's cursor is left alone.
    """
    sx, sy = win32gui.ClientToScreen(hwnd, (int(x), int(y)))
    win32api.SetCursorPos((sx, sy))
    if button == "right":
        down, up = win32con.MOUSEEVENTF_RIGHTDOWN, win32con.MOUSEEVENTF_RIGHTUP
    else:
        down, up = win32con.MOUSEEVENTF_LEFTDOWN, win32con.MOUSEEVENTF_LEFTUP
    win32api.mouse_event(down, sx, sy, 0, 0)
    win32api.mouse_event(up, sx, sy, 0, 0)


# --- Utility (EzCBot: RandomNumber / RandomString / saveLogFile) ---------------

def rand(lo: int, hi: int) -> int:
    """Random int in [lo, hi] (EzCBot RandomNumber, inclusive)."""
    return random.randint(lo, hi)


def rand_string(size: int, lower_case: bool = False) -> str:
    """Random A–Z (or a–z) string (EzCBot RandomString)."""
    alphabet = string.ascii_lowercase if lower_case else string.ascii_uppercase
    return "".join(random.choice(alphabet) for _ in range(size))


def save_log(path: str, detail: str) -> None:
    """Append a timestamped line to a log file (EzCBot saveLogFile)."""
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{datetime.datetime.now()} {detail}\n")


if __name__ == "__main__":  # quick demo: list emulator-like windows
    import sys
    kw = sys.argv[1] if len(sys.argv) > 1 else None
    for h, t, c in list_windows(kw):
        print(f"{h:>10}  {t!r}  [{c}]")
