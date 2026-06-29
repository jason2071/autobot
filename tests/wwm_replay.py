"""Offline sanity gate for the Where Winds Meet reactive tracker.

Replays the live engine's exact detection + reactive press logic
(`src/games/wwm.py` geometry + mask + hit-band rising-edge press) over a recorded
clip and checks the result is healthy: a sane number of presses spread across all
six lanes, with a low duplicate-press rate (the mask-flicker double-tap this
guards against).

Per-note timing accuracy is verified visually instead (the annotated-frame /
per-lane timeline tools in scratchpad, and live on the machine) — a reliable
automatic ground truth is infeasible here because the long "hold" notes and the
flower-icon hole in each circle defeat naive blob tracking, so this gate asserts
only what can be measured without labels: detection works, every lane maps, and
the presser fires about once per note.

Skips itself on a clean checkout (clip gitignored) — same convention as
`tests/predict_replay.py`. Run: `python -m tests.wwm_replay`.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core import predict  # noqa: E402
from src.games import wwm  # noqa: E402

CLIP = os.path.join("videos", "Where-Winds-Meet.mp4")


def _plan(clip):
    """Replay the engine's reactive press logic. Returns (presses, nframes);
    `presses` is a list of (time_s, lane)."""
    import cv2

    v = cv2.VideoCapture(clip)
    fps = v.get(cv2.CAP_PROP_FPS) or 60.0
    dt = 1.0 / fps
    cfg = wwm.WWMConfig()
    band = cfg.hit_band
    min_tap_s = cfg.min_tap_ms / 1000.0

    bands = None
    hit_y = 0.0
    y_lo = y_hi = 0
    lanes = len(cfg.keys)
    hit_streak = [cfg.release_frames] * lanes
    down = [False] * lanes
    held = [0.0] * lanes
    armed = [True] * lanes
    presses: list[tuple[float, int]] = []

    fi = -1
    while True:
        ok, frame = v.read()
        if not ok:
            break
        fi += 1
        now = fi * dt
        if bands is None:
            h, w = frame.shape[:2]
            bands, hit_y = (wwm.calibrate(frame, cfg.hw_frac)
                            or wwm.model_geometry(w, h, cfg.hw_frac))
            y_lo = int(cfg.header_frac * h)
            y_hi = int(hit_y + 6 * band)

        mask = wwm.note_mask(frame, cfg.note_v_min, cfg.note_s_max)
        mask[:y_lo] = False
        segs = predict.lane_segments(
            frame, bands, margin=40, min_run=cfg.min_run, dark_frac=cfg.dark_frac,
            y_lo=y_lo, y_hi=y_hi, merge_gap=cfg.merge_gap, mask=mask)
        c = hit_y - cfg.press_offset_px
        hit_occ = wwm._hysteresis(
            predict.occupancy_at(segs, c - band, c + band), hit_streak,
            cfg.release_frames)

        for i in range(lanes):
            if not hit_occ[i]:
                armed[i] = True
            elif armed[i] and not down[i]:
                presses.append((now, i))
                down[i] = True
                held[i] = now
                armed[i] = False
        for i in range(lanes):
            if down[i]:
                hd = now - held[i]
                if hd > cfg.max_hold_s or (not hit_occ[i] and hd >= min_tap_s):
                    down[i] = False
    v.release()
    return presses, fi + 1


def test_wwm_sanity():
    if not os.path.isfile(CLIP):
        print(f"SKIP: {CLIP} not present (clean checkout)")
        return
    try:
        import cv2  # noqa: F401
    except Exception:
        print("SKIP: opencv not available")
        return

    presses, n = _plan(CLIP)
    lanes = len(wwm.WWMConfig().keys)
    per = [sum(1 for _, ln in presses if ln == i) for i in range(lanes)]

    # duplicate-tap rate: a second press in the same lane within 150ms is almost
    # certainly one note flickering, not two real notes (notes arrive slower).
    last = [-9.0] * lanes
    dups = 0
    for t, ln in sorted(presses):
        if t - last[ln] < 0.150:
            dups += 1
        last[ln] = t
    dup_rate = dups / max(len(presses), 1)

    keys = wwm.WWMConfig().keys
    print(f"frames {n}  presses {len(presses)}  "
          f"per-lane {dict(zip((k.upper() for k in keys), per))}")
    print(f"duplicate-tap rate {dup_rate*100:.1f}%  ({dups}/{len(presses)})")

    # detection produced a healthy chart's worth of presses...
    assert 150 <= len(presses) <= 700, f"press count off: {len(presses)}"
    # ...spread across every lane (all six key-lanes map + detect)...
    assert all(p >= 5 for p in per), f"some lane never pressed: {per}"
    # ...and the flicker double-tap is rare.
    assert dup_rate <= 0.12, f"duplicate-tap rate too high: {dup_rate*100:.1f}%"
    print("PASS")


if __name__ == "__main__":
    test_wwm_sanity()
