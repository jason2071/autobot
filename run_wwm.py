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


def _visualise(eng, last_press, hold=0.18):
    """Main-thread cv2 loop: six big lane tiles that flash when the bot detects a
    note approaching that lane's target — watch this and press the lit key."""
    import cv2

    W, H, n = 960, 300, len(KEYS)
    pad, top, bot = 24, 70, 250
    tw = (W - pad * 2) // n
    while eng.running:
        img = np.full((H, W, 3), 24, np.uint8)
        now = time.monotonic()
        for i, k in enumerate(KEYS):
            x = pad + i * tw
            lit = now - last_press[i] < hold
            col = (70, 220, 90) if lit else (55, 55, 60)
            cv2.rectangle(img, (x + 6, top), (x + tw - 6, bot), col,
                          -1 if lit else 3)
            tcol = (15, 30, 15) if lit else (170, 170, 175)
            (sz, _), _ = cv2.getTextSize(k, cv2.FONT_HERSHEY_SIMPLEX, 3.0, 6)
            cv2.putText(img, k, (x + (tw - sz) // 2, 195),
                        cv2.FONT_HERSHEY_SIMPLEX, 3.0, tcol, 6)
        cv2.putText(img, "VISION-ONLY (no keys sent) - press the lit key - q to stop",
                    (pad, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180, 180, 185), 1)
        cv2.imshow("autobot - WWM cue", img)
        if cv2.waitKey(16) & 0xFF in (ord("q"), 27):
            break
    cv2.destroyAllWindows()


def main() -> int:
    ap = argparse.ArgumentParser(description="Where Winds Meet vision watcher")
    ap.add_argument("--title", default=DEFAULT_MATCH)
    ap.add_argument("--list", action="store_true", help="list windows and exit")
    ap.add_argument("--method", default="dxcam", choices=["dxcam", "printwindow"])
    ap.add_argument("--offset", type=int, default=None,
                    help="cue lead in px (higher = lights earlier; default 90)")
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
    if args.offset is not None:
        cfg.press_offset_px = args.offset
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
