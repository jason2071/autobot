"""Where Winds Meet — vision watcher (safe, no input by default).

By DEFAULT this only WATCHES: it captures the game, detects each note reaching
the target, and lights a lane in a separate visualiser window — it sends NO keys
to the game. That matters because Where Winds Meet runs elevated (it ships
anti-cheat), and injected key input carries an OS flag a kernel anti-cheat can
read, so auto-playing it risks an account ban. Watching (screen capture only) is
passive.

    python run_wwm.py                 # watch: light lanes, send nothing (safe)
    python run_wwm.py --list          # list windows and exit
    python run_wwm.py --actuate       # ACTUALLY press keys — unsafe on anti-cheat
                                      #   games; only for offline/unprotected ones

Press Esc (or q in the visualiser) to stop.
"""

from __future__ import annotations

import argparse
import time

import numpy as np

from src.capture import window_picker
from src.games.wwm import WWMConfig, WWMEngine

DEFAULT_MATCH = "where winds meet"
KEYS = ("S", "D", "F", "J", "K", "L")


def _find(match: str):
    match = match.lower()
    for w in window_picker.list_windows():
        if w.hwnd and match in w.title.lower():
            return w
    return None


def _visualise(eng, last_press):
    """Main-thread cv2 loop: draw the six lanes, lit while recently pressed."""
    import cv2

    while eng.running:
        img = np.full((200, 720, 3), 28, np.uint8)
        now = time.monotonic()
        for i, k in enumerate(KEYS):
            x = 30 + i * 112
            lit = now - last_press[i] < 0.12
            col = (90, 200, 90) if lit else (70, 70, 70)
            cv2.rectangle(img, (x, 60), (x + 92, 150), col, -1 if lit else 2)
            cv2.putText(img, k, (x + 32, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.1,
                        (20, 20, 20) if lit else (200, 200, 200), 2)
        cv2.putText(img, "VISION-ONLY  (no keys sent)  -  q to stop", (30, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (180, 180, 180), 1)
        cv2.imshow("autobot - WWM watcher", img)
        if cv2.waitKey(16) & 0xFF in (ord("q"), 27):
            break
    cv2.destroyAllWindows()


def main() -> int:
    ap = argparse.ArgumentParser(description="Where Winds Meet vision watcher")
    ap.add_argument("--title", default=DEFAULT_MATCH)
    ap.add_argument("--list", action="store_true", help="list windows and exit")
    ap.add_argument("--method", default="dxcam", choices=["dxcam", "printwindow"])
    ap.add_argument("--actuate", action="store_true",
                    help="SEND keys to the game (unsafe on anti-cheat titles)")
    args = ap.parse_args()

    if args.list:
        for w in window_picker.list_windows():
            if w.hwnd:
                b = w.bounds
                print(f"  hwnd={w.hwnd:<10} {b['width']}x{b['height']}  {w.title}")
        return 0

    win = _find(args.title)
    if win is None:
        print(f"no window matching {args.title!r}. Try --list.")
        return 1
    print(f"target: {win.title}  ({win.bounds['width']}x{win.bounds['height']})")

    if args.actuate:
        if window_picker.input_blocked_by_uipi(win.hwnd):
            print("\n!! Game runs as ADMIN and this bot does not — Windows UIPI "
                  "drops injected keys.\n   It would also be VISIBLE to the game's "
                  "anti-cheat. Aborting --actuate.\n   (Run without --actuate to "
                  "watch safely.)")
            return 2
        print("\n!! --actuate sends INJECTED key input. On an anti-cheat game "
              "(this one) that risks\n   an account ban. Ctrl-C now if unsure. "
              "Continuing in 3s…")
        time.sleep(3)
        window_picker.focus_hwnd(win.hwnd)

    cfg = WWMConfig(target_hwnd=win.hwnd, window_method=args.method,
                    dry_run=not args.actuate)
    last_press = [0.0] * 6

    def on_event(lane, kind):
        if kind == "press":
            last_press[lane] = time.monotonic()

    eng = WWMEngine(cfg, on_status=lambda m: print(f"[wwm] {m}"), on_event=on_event)
    eng.start()
    try:
        _visualise(eng, last_press)
    except KeyboardInterrupt:
        pass
    finally:
        eng.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
