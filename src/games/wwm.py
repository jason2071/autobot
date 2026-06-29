"""Where Winds Meet — 6-lane keyboard rhythm autoplayer.

The instrument minigame drops bright translucent note-circles down six fixed
lanes (keys **S D F J K L**) toward a target-circle row near the bottom; you
press the lane's key as the note reaches the target. Notes come in two kinds:
a single circle = a TAP, a tall capsule (head + body + tail) = a HOLD (press and
keep the key down while the body crosses the target).

Detection reuses the lane segmentation from `src/core/predict.py`, but play is
purely REACTIVE: a note is pressed the moment a segment reaches the target band,
and held until the band clears (a tap releases at once, a long note holds head→
tail). Unlike Magic Tiles — whose tiles accelerate from ~1400→3100 px/s with a
sub-frame hit window, so presses must be SCHEDULED from velocity — these notes
fall slow and steady (~520 px/s) onto a target circle with generous tolerance, so
reacting on the band lands "Perfect" (a measured sweep showed the predictive
schedule added nothing). Output is the keyboard (`src/input/key.py`) — each key
independent, so chords (several lanes the same frame) are free, unlike Magic
Tiles' single-button background mode.

Geometry is **resolution- and aspect-independent**. Measured on real captures at
both 1920x1080 and 3440x1440 the rhythm UI scales with screen HEIGHT and is
horizontally CENTERED: each lane sits at `x = W/2 + k*H` (k constant per lane),
the target row at `y = 0.865*H`. So the same constants drive 16:9 and 21:9. A
light auto-calibration refines the lane x-centers + target y from the actual
frame (the S D F J K L letter glyphs + the target-circle row) and falls back to
the model when it can't get a clean read.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np

from ..core import predict


# --- geometry (height-scaled, horizontally centered) --------------------------
# lane x-offset from screen centre, in units of frame HEIGHT. Averaged from
# measurements at 1920x1080 (centres 335/540/748/1170/1383/1585) and 3440x1440
# (884/1156/1439/2000/2282/2554) — both yielded the same constants to <0.5%.
LANE_K: tuple[float, ...] = (-0.580, -0.390, -0.196, 0.194, 0.391, 0.579)
HIT_FRAC = 0.865          # target-circle row centre, as fraction of H
HW_FRAC = 0.051           # lane half-width, as fraction of H (55/1080)
DEFAULT_KEYS = ("s", "d", "f", "j", "k", "l")


def model_geometry(w: int, h: int, hw_frac: float = HW_FRAC):
    """(bands, hit_y) from the height-scaled centred model. `bands` is the list
    of (x0, x1) lane columns; `hit_y` is the target-row y. Pure."""
    cx = [w / 2 + k * h for k in LANE_K]
    hw = hw_frac * h
    bands = [(max(int(c - hw), 0), min(int(c + hw), w)) for c in cx]
    return bands, HIT_FRAC * h


def calibrate(frame, hw_frac: float = HW_FRAC):
    """Refine (bands, hit_y) from a real frame; return None if no clean read.

    Detects the six key-letter glyph columns in the bottom strip (crisp light
    text on dark) and the target-circle row centre. Validated against the model
    shape: six columns, split 3 + 3 with a wide centre gap. On any mismatch the
    caller falls back to `model_geometry`.
    """
    import cv2

    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    # letters live in the bottom ~2-8% of the frame
    y0, y1 = int(h * 0.92), int(h * 0.99)
    strip = gray[y0:y1, :]
    colsum = (strip > 150).sum(0)
    cols = np.where(colsum > 2)[0]
    if len(cols) == 0:
        return None
    groups: list[int] = []
    s = p = int(cols[0])
    gap = int(0.02 * w)  # split letters at least 2% of width apart
    for c in cols[1:]:
        c = int(c)
        if c - p > gap:
            groups.append((s + p) // 2)
            s = c
        p = c
    groups.append((s + p) // 2)
    if len(groups) != 6:
        return None
    sp = [groups[i + 1] - groups[i] for i in range(5)]
    # within-group spacings ~equal, centre gap ~2x — reject otherwise
    side = (sp[0] + sp[1] + sp[3] + sp[4]) / 4
    if side <= 0 or sp[2] < 1.6 * side or sp[2] > 2.6 * side:
        return None
    if max(sp[0], sp[1], sp[3], sp[4]) > 1.4 * side:
        return None
    hw = hw_frac * h
    bands = [(max(int(c - hw), 0), min(int(c + hw), w)) for c in groups]
    return bands, HIT_FRAC * h


def note_mask(frame, v_min: int = 165, s_max: int = 80) -> "np.ndarray":
    """Boolean note mask: a note pixel is BRIGHT and LOW-saturation — the white
    translucent note-circle. Measured across lanes: notes read V>170 & S<70 while
    the busy night background (clouds, foliage, the player model) stays out of
    that corner. The narrow per-lane columns plus the row `dark_frac` in
    `lane_segments` reject the few stray bright-grey background pixels.
    """
    import cv2

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    return (V > v_min) & (S < s_max)


def _hysteresis(raw: list[bool], streak: list[int], release_frames: int) -> list[bool]:
    """Debounce: a lane stays True until it reads False for `release_frames`
    consecutive frames (bridges the darker note centre / icon). Mutates
    `streak`."""
    out = []
    for i, d in enumerate(raw):
        if d:
            streak[i] = 0
        else:
            streak[i] += 1
        out.append(d or streak[i] < release_frames)
    return out


# --- config + engine ----------------------------------------------------------
@dataclass
class WWMConfig:
    target_hwnd: int = 0
    window_method: str = "dxcam"        # PC game on screen → low-latency capture
    keys: tuple = DEFAULT_KEYS
    region: dict | None = None          # window-local crop; None = whole window

    note_v_min: int = 165
    note_s_max: int = 80
    hw_frac: float = HW_FRAC
    auto_calibrate: bool = True

    header_frac: float = 0.06           # crop the score header
    hit_band: int = 28                  # half-height of the press/hit band (px@H
                                        # this is ~half a note circle: a note is
                                        # "on the target" within ±hit_band of it)
    press_offset_px: int = 40           # shift the band UP to fire EARLIER — the
                                        # one live timing knob. Raise it if the
                                        # hit lands late (note already on the
                                        # target before it fires); lower if early.
                                        # ~px; at ~520 px/s, 40px ≈ 77ms earlier.
    min_run: int = 18
    dark_frac: float = 0.42
    merge_gap: int = 18                 # bridge a note's centre-icon hole

    min_tap_ms: float = 40.0            # hold every tap at least this long
    max_hold_s: float = 2.5             # stuck-key backstop
    release_frames: int = 3             # debounce the band going empty (bridges a
                                        # ≤2-frame mask flicker so one note isn't
                                        # released+re-pressed as a double-tap)
    poll: float = 0.0

    # SAFETY: dry_run is the DEFAULT. The detector runs (capture + decide) but NO
    # keys are sent to the game — it only reports which lane it WOULD press via
    # the on_event callback, for a passive on-screen visualiser. Injected input
    # (SendInput) carries an OS "injected" flag a kernel anti-cheat can read, so
    # actuating an online game that ships such protection (Where Winds Meet runs
    # elevated → it has one) risks an account ban. Leave dry_run on for any
    # anti-cheat title; only set it False for an offline / non-protected target.
    dry_run: bool = True


class WWMEngine:
    """Threaded autoplayer. `start()` runs the capture→detect→schedule→key loop
    on a daemon thread; `stop()` (or Esc) ends it and releases all keys."""

    def __init__(self, config: WWMConfig, on_status=None, on_event=None) -> None:
        self.config = config
        self.on_status = on_status or (lambda _m: None)
        # on_event(lane:int, kind:str) — 'press'/'release' the bot decided on.
        # In dry_run this is the ONLY output (no keys are sent); a visualiser
        # lights the lane. Always fired, so it also tracks a real actuation run.
        self.on_event = on_event or (lambda _lane, _kind: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        cfg = self.config
        from ..capture.window_capture import WindowCapture
        from ..input.key import KeyInjector

        win = WindowCapture(cfg.target_hwnd, cfg.window_method)
        # dry_run (default): never construct the key injector, so no keys can
        # reach the game — purely passive detection. on_event reports decisions.
        keys = None if cfg.dry_run else KeyInjector(cfg.keys)
        lanes = len(cfg.keys)

        down = [False] * lanes
        held_since = [0.0] * lanes
        armed = [True] * lanes           # may press again only after the band clears

        def press(i, now):
            if not down[i]:
                if keys is not None:
                    keys.down(i)
                down[i] = True
                held_since[i] = now
                self.on_event(i, "press")

        def release(i):
            if down[i]:
                if keys is not None:
                    keys.up(i)
                down[i] = False
                self.on_event(i, "release")

        def release_all():
            for i in range(lanes):
                release(i)

        # Esc = emergency stop (works while keys are held).
        listener = None
        try:
            from pynput import keyboard

            def _on_press(key):
                if key == keyboard.Key.esc:
                    self._stop.set()
                    return False

            listener = keyboard.Listener(on_press=_on_press)
            listener.start()
        except Exception:
            listener = None

        # geometry, resolved once and re-resolved if the window resizes
        geom_size = (0, 0)
        bands: list[tuple[int, int]] = []
        hit_y = 0.0
        band = cfg.hit_band
        # detection STRIP: only the rows around the target are needed for reactive
        # play, so the per-frame HSV conversion + segmentation run on a thin band
        # instead of the whole 3440x1440 frame — ~6x faster (measured 19ms→3ms),
        # which keeps the loop fast enough that a falling note can't skip the band
        # between frames (the cause of scattered live misses). The strip reaches
        # 110px ABOVE the band so a note is seen approaching even on a slow frame.
        strip_lo = 0
        strip_hi = 0
        c_local = 0.0

        def _resolve(frame):
            nonlocal bands, hit_y, geom_size, strip_lo, strip_hi, c_local
            h, w = frame.shape[:2]
            g = calibrate(frame, cfg.hw_frac) if cfg.auto_calibrate else None
            how = "calibrated"
            if g is None:
                g = model_geometry(w, h, cfg.hw_frac)
                how = "model"
            bands, hit_y = g
            c = hit_y - cfg.press_offset_px
            strip_lo = max(int(c - band - 110), 0)
            strip_hi = min(int(c + band + 20), h)
            c_local = c - strip_lo
            geom_size = (w, h)
            self.on_status(f"geometry {how}: {w}x{h} hit_y={hit_y:.0f} "
                           f"lanes={[ (a + b) // 2 for a, b in bands]}")

        min_tap_s = cfg.min_tap_ms / 1000.0
        hit_streak = [cfg.release_frames] * lanes

        # WWM is played purely REACTIVELY: detect each note as it reaches the
        # target row and press the lane's key. Validated frame-by-frame on real
        # captures — the press fires exactly as the note circle lands on the
        # target ("Perfect"). Prediction/velocity (used for Magic Tiles, whose
        # tiles accelerate from ~1400→3100 px/s with a sub-frame hit window) buys
        # nothing here: these notes fall slow + steady (~520 px/s) with a target
        # circle ~±half-a-note tolerance, and a measured sweep showed adding the
        # predictive schedule changed coverage by zero. Keyboard latency is a few
        # ms, so reacting on the band is on time; `press_offset_px` shifts the
        # band up for any residual lag.
        self.on_status("running (WWM/vision-only — no keys sent) — Esc to stop"
                       if cfg.dry_run else "running (WWM/reactive) — Esc to stop")
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                frame = win.grab(cfg.region)
                h, w = frame.shape[:2]
                if (w, h) != geom_size:
                    _resolve(frame)

                # crop to the detection strip, then segment only that (cheap).
                strip = frame[strip_lo:strip_hi]
                mask = note_mask(strip, cfg.note_v_min, cfg.note_s_max)
                segs = predict.lane_segments(
                    strip, bands, margin=40, min_run=cfg.min_run,
                    dark_frac=cfg.dark_frac, y_lo=0, y_hi=strip.shape[0],
                    merge_gap=cfg.merge_gap, mask=mask)

                # a note is "on the target" when a segment overlaps the band
                # centred at the target (shifted up by press_offset_px to fire
                # early). Coordinates are strip-local.
                hit_occ = _hysteresis(
                    predict.occupancy_at(segs, c_local - band, c_local + band),
                    hit_streak, cfg.release_frames)

                for i in range(lanes):
                    if not hit_occ[i]:
                        armed[i] = True          # band clear → ready for next note
                    elif armed[i] and not down[i]:
                        press(i, now)            # rising edge → one press per note
                        armed[i] = False

                # release: a tap holds briefly then the band clears; a long note
                # keeps the band occupied (head→tail) so it stays held until the
                # tail leaves. `min_tap_s` guarantees the key registers; max_hold
                # is the stuck-key backstop.
                for i in range(lanes):
                    if not down[i]:
                        continue
                    held = now - held_since[i]
                    if held > cfg.max_hold_s:
                        release(i)
                    elif not hit_occ[i] and held >= min_tap_s:
                        release(i)

                self._stop.wait(cfg.poll)
        finally:
            release_all()
            if keys is not None:
                keys.close()
            win.close()
            if listener is not None:
                listener.stop()
            self.on_status("stopped")
