"""Launch the Where Winds Meet autoplayer.

The instrument minigame must be on screen (topmost / uncovered) and FOCUSED —
capture is dxcam (fast, low-latency) and the keyboard presses go to the
foreground window, so keep the game in front while it plays.

    python run_wwm.py                 # auto-find the "Where Winds Meet" window
    python run_wwm.py --title XANTHUS  # match a different window-title substring
    python run_wwm.py --list           # just list windows and exit

Press Esc (or Ctrl-C) to stop.
"""

from __future__ import annotations

import argparse
import time

from src.capture.window_picker import list_windows, focus_window
from src.games.wwm import WWMConfig, WWMEngine

DEFAULT_MATCH = "where winds meet"


def _find(match: str):
    match = match.lower()
    for w in list_windows():
        if w.hwnd and match in w.title.lower():
            return w
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Where Winds Meet autoplayer")
    ap.add_argument("--title", default=DEFAULT_MATCH,
                    help="window-title substring to target (default: %(default)r)")
    ap.add_argument("--list", action="store_true", help="list windows and exit")
    ap.add_argument("--countdown", type=float, default=3.0)
    ap.add_argument("--lead-ms", type=float, default=None,
                    help="override input-latency lead (ms); tune for Perfect timing")
    ap.add_argument("--method", default="dxcam", choices=["dxcam", "printwindow"])
    args = ap.parse_args()

    if args.list:
        for w in list_windows():
            if w.hwnd:
                b = w.bounds
                print(f"  hwnd={w.hwnd:<10} {b['width']}x{b['height']}  {w.title}")
        return 0

    win = _find(args.title)
    if win is None:
        print(f"no window matching {args.title!r}. Try --list.")
        return 1
    print(f"target: {win.title}  ({win.bounds['width']}x{win.bounds['height']}, "
          f"hwnd={win.hwnd})")
    focus_window(win.title)

    cfg = WWMConfig(target_hwnd=win.hwnd, window_method=args.method)
    if args.lead_ms is not None:
        cfg.lead_ms = args.lead_ms

    for s in range(int(args.countdown), 0, -1):
        print(f"starting in {s}…", end="\r", flush=True)
        time.sleep(1)
    print("go — Esc to stop          ")

    eng = WWMEngine(cfg, on_status=lambda m: print(f"[wwm] {m}"))
    eng.start()
    try:
        while eng.running:
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    finally:
        eng.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
