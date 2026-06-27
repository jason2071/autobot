"""Predictive tile timing for Magic Tiles.

The reactive path only saw a tile once it reached a thin strip near the hit
line — a race the bot loses as the song speeds up. This module instead senses a
tile's leading (bottom) edge crossing a TRIGGER line placed well above the hit
line, measures the board-wide fall velocity, and lets the caller SCHEDULE the
press for the exact moment the edge will reach the hit line:

    t_press = now + (hit_y - y_trig) / v - lead_s

Timing then comes from position + velocity, not reaction speed, so it holds up
at any tempo. A single horizontal trigger line is the dedup mechanism — each
tile produces exactly one rising edge (bottom crosses → press) and one falling
edge (top crosses → release) per lane, so no fragile per-tile tracking /
association is needed (full multi-object tracking shattered on guide-lines and
flicker; this does not).

Everything here is pure (no capture/touch I/O) so it is unit/replay testable —
same convention as the pure functions in `src/bot.py`. Geometry (board edges,
lane bands, hit line) is reused from `src/bot.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# --- segmentation -------------------------------------------------------------
def _raw_runs(occ: "np.ndarray") -> list[tuple[int, int]]:
    """All maximal runs of True rows as (y_top, y_bottom) — no length filter."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    n = len(occ)
    for y in range(n):
        if occ[y] and start is None:
            start = y
        elif not occ[y] and start is not None:
            runs.append((start, y - 1))
            start = None
    if start is not None:
        runs.append((start, n - 1))
    return runs


def _merge(runs: list[tuple[int, int]], gap: int) -> list[tuple[int, int]]:
    """Join runs separated by <= `gap` rows (bridges a tile's centre guide-line
    / gradient so one note isn't split into several segments)."""
    if not runs:
        return runs
    out = [runs[0]]
    for yt, yb in runs[1:]:
        py_t, py_b = out[-1]
        if yt - py_b - 1 <= gap:
            out[-1] = (py_t, yb)
        else:
            out.append((yt, yb))
    return out


def lane_segments(
    board, bands, margin: float, min_run: int = 12, dark_frac: float = 0.5,
    y_lo: int = 0, y_hi: int | None = None, merge_gap: int = 24,
) -> list[list[tuple[int, int]]]:
    """Per lane, the vertical spans of tiles as (y_top, y_bottom) in board-y.

    A board row is "occupied" in a lane when the fraction of pixels darker than
    `bg - margin` exceeds `dark_frac`, where `bg` is the board's median
    brightness (relative → skin-independent, same idea as `tiles_dark_lanes` /
    `tiles_dark_frac`). Rows outside `[y_lo, y_hi)` are ignored — this clips the
    persistent dark UI (score header at the top, keyboard/hit-zone below the
    line) that would otherwise look like stuck tiles. Raw runs are then merged
    across small gaps (`merge_gap`) and the survivors >= `min_run` are returned.

    `board` is the full board image (BGR or gray); `bands` is the list of
    (x0, x1) lane columns from `tiles_lane_geometry`.
    """
    import cv2

    gray = board if board.ndim == 2 else cv2.cvtColor(board, cv2.COLOR_BGR2GRAY)
    gray = gray.astype(np.int16)
    h = gray.shape[0]
    lo = max(0, y_lo)
    hi = h if y_hi is None else min(y_hi, h)
    bg = float(np.median(gray))
    thr = bg - margin
    out: list[list[tuple[int, int]]] = []
    # scan only rows in [lo, hi): everything outside is cropped UI, and limiting
    # the per-row run scan to the play area keeps the hot loop cheap. Runs are
    # offset back to board-y by `lo`.
    for x0, x1 in bands:
        col = gray[lo:hi, x0:x1]
        occ = (col < thr).mean(axis=1) > dark_frac  # bool per row in [lo, hi)
        runs = _merge(_raw_runs(occ), merge_gap)
        out.append([(a + lo, b + lo) for a, b in runs if b - a + 1 >= min_run])
    return out


# --- velocity (board-wide fall speed, px/s) -----------------------------------
def leading_bottoms(
    segments: list[list[tuple[int, int]]], hit_y: float
) -> list[float | None]:
    """Per lane, the bottom-y of the lowest tile still ABOVE the hit line — the
    leading edge whose downward motion gives the fall velocity."""
    out: list[float | None] = []
    for s in segments:
        below = [yb for _yt, yb in s if yb < hit_y]
        out.append(float(max(below)) if below else None)
    return out


def update_velocity(
    v: float, prev_bottoms: list[float | None] | None,
    bottoms: list[float | None], dt: float,
    alpha: float = 0.3, max_speed: float = 6000.0,
) -> float:
    """Smoothly track the board-wide fall velocity (px/s).

    All tiles scroll at one speed, so the median of the plausible per-lane
    leading-edge displacements this frame is a robust instantaneous estimate;
    an EMA (`alpha`) smooths it. A displacement is kept only when it is downward
    and its implied SPEED is below `max_speed` px/s (a tile vanishing / a new
    one appearing gives an implausible jump). Gating on speed, not raw pixels,
    means a fast tile on a slow frame isn't wrongly discarded (which would
    freeze `v`).
    """
    if not prev_bottoms or dt <= 0:
        return v
    deltas = [b - a for a, b in zip(prev_bottoms, bottoms)
              if a is not None and b is not None and 0 < b - a < max_speed * dt]
    if not deltas:
        return v
    inst = (sorted(deltas)[len(deltas) // 2]) / dt
    return inst if v <= 0 else alpha * inst + (1 - alpha) * v


# --- trigger-line occupancy + scheduling --------------------------------------
def occupancy_at(
    segments: list[list[tuple[int, int]]], y_top: float, y_bot: float
) -> list[bool]:
    """Per lane: is any tile overlapping the trigger band [y_top, y_bot]?"""
    return [any(not (yb < y_top or yt > y_bot) for yt, yb in s)
            for s in segments]


@dataclass
class Event:
    t: float          # monotonic time to actuate
    kind: str         # 'press' | 'release'
    lane: int


def schedule_edges(
    prev_occ: list[bool], occ: list[bool], v: float | None,
    y_trig: float, hit_y: float, now: float, lead_s: float,
) -> list[Event]:
    """Edge-triggered scheduling at the trigger line.

    A tile's BOTTOM edge crossing the trigger (rising occupancy) → schedule a
    press for when it reaches the hit line; its TOP edge crossing (falling
    occupancy) → schedule the release. Both use the same lead time
    `(hit_y - y_trig)/v`, so the press→release gap equals the tile's real dwell
    at the line (short tile → tap, long note → hold). `lead_s` is a fixed
    input+emulator latency offset. The caller keeps `prev_occ` between frames.
    """
    if not v or v <= 0:
        return []
    eta = (hit_y - y_trig) / v - lead_s
    events: list[Event] = []
    for ln in range(len(occ)):
        if occ[ln] and not prev_occ[ln]:
            events.append(Event(now + eta, "press", ln))
        elif not occ[ln] and prev_occ[ln]:
            events.append(Event(now + eta, "release", ln))
    return events
