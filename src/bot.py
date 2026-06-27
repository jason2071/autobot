"""BotEngine: capture -> detect -> click loop running on a background thread."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .capture import ScreenCapture
from . import detector


@dataclass
class BotConfig:
    # tiles mode (Magic Tiles 3 style: N lanes, dark tile reaches hit line)
    region: dict | None = None  # {"top","left","width","height"}; window-local
    tiles_lanes: int = 4
    tiles_hit: float = 0.80      # hit line as a fraction of region height
    # a lane has a tile when its brightness is this far BELOW the lane median
    # (relative, so it works for any skin: black, blue, etc.)
    tiles_margin: int = 40       # a row is "dark" when this far below board median
    tiles_dark_frac: float = 0.5  # fraction of a lane row that must be dark
    tiles_poll: float = 0.001    # seconds between scans (fast; tiles speed up)
    tiles_max_hold: float = 4.0  # force-release a hold after this many seconds
    tiles_release_frames: int = 3  # frames of light before releasing (debounce)
    # --- predictive tracking knobs (see src/predict.py) ---
    # Detect tiles across the whole board, track the board-wide fall velocity,
    # and SCHEDULE each press for when the tile reaches the hit line, instead of
    # reacting once it is already there. Timing then comes from position +
    # velocity, so it keeps up as the song speeds up.
    tiles_play_top: float = 0.18   # ignore the score-header UI above this (frac H)
    tiles_trig_lead: float = 0.25  # trigger line this frac of H ABOVE the hit line
    tiles_trig_band: int = 12      # trigger sense band half-thickness (px)
    tiles_min_run: int = 12        # min vertical run (px) to count as a tile
    tiles_merge_gap: int = 30      # bridge a tile's centre guide-line / gradient
    tiles_lead_ms: float = 0.0     # fixed input+emulator latency offset (tune live)
    tiles_min_tap_ms: float = 30.0  # floor a tap's hold so the touch registers
    tiles_confirm_ms: float = 200.0  # after a press, wait up to this for the tile
                                     # to appear at the hit line; if it never does
                                     # (a phantom press) release instead of holding
    # opt-in: also flag a lane active when it carries this note colour (BGR) —
    # detects bright/coloured notes and slides (the lit lane shifts across the
    # board, and the per-lane state machine follows it). A lane is active when it
    # is dark OR matches ANY of these colours — so a skin with several note
    # colours (e.g. cyan notes + pink slides) is fully covered. Empty = darkness
    # only (no change for classic black-tile skins).
    tiles_note_colors: list[tuple[int, int, int]] = field(default_factory=list)
    tiles_note_tol: int = 18       # hue tolerance (degrees) for the note colours
    mode: str = "tiles"  # only mode supported
    # input is always background multi-touch (Win32 InjectTouchInput): one finger
    # per lane, no focus needed, real cursor never moves. (see src/touch.py)
    # when set, capture this window directly instead of a screen region.
    # region is window-local. window_method: "bitblt" (fast) keeps the window
    # visible; "printwindow" (slower) is immune to other apps overlapping it.
    target_hwnd: int | None = None
    window_method: str = "dxcam"  # DXGI duplication: ~0.1ms/grab & pixel-correct
                                  # (low latency = keeps up as the song speeds up).
                                  # "printwindow" (~20ms) is the fallback; bitblt
                                  # grabs the wrong GPU layer for LDPlayer.
    # helper templates clicked on sight (e.g. retry / start buttons between songs)
    tiles_helpers: list[str] = field(default_factory=list)
    tiles_helper_threshold: float = 0.8
    tiles_helper_interval: float = 0.3  # how often to scan for helper buttons


StatusCallback = Callable[[str], None]


# --- tiles-mode pure logic (unit-testable, no I/O) ----------------------------
def tiles_dark_lanes(means: list[float], margin: float) -> list[bool]:
    """A lane has a tile when it is `margin` darker than the median lane.

    Relative, so it works on any skin (black tiles, blue tiles, etc.).
    """
    bg = sorted(means)[len(means) // 2]
    return [m < bg - margin for m in means]


def tiles_color_lanes(frame, lane_bands_x, bgr, hue_tol, min_frac=0.30):
    """Flag lanes whose hit band is mostly the note colour `bgr` (within
    `hue_tol` hue degrees). Used for bright/coloured notes and slides — the lit
    lane shifts across the board as the diagonal descends.

    `frame` is the BGR strip; `lane_bands_x` is the list of (x0, x1) columns.
    Returns one bool per lane.
    """
    import cv2
    import numpy as np

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    th, ts, tv = cv2.cvtColor(np.uint8([[list(bgr)]]), cv2.COLOR_BGR2HSV)[0][0]
    lo = np.array([max(int(th) - hue_tol, 0), 80, 80])
    hi = np.array([min(int(th) + hue_tol, 179), 255, 255])
    mask = cv2.inRange(hsv, lo, hi)
    return [float(mask[:, x0:x1].mean()) / 255.0 > min_frac
            for x0, x1 in lane_bands_x]


def tiles_board_edges(frame: "np.ndarray") -> tuple[int, int] | None:
    """Find the left/right edges of the play board via vertical-edge detection.

    The lane dividers and board borders are persistent vertical lines; tiles
    only add partial-height edges, so averaging |dx| over most of the height
    makes the board borders the outermost strong peaks. Returns (left, right)
    in frame-x, or None if detection is unreliable (caller falls back).
    """
    import cv2
    import numpy as np

    h, w = frame.shape[:2]
    if w < 20 or h < 20:
        return None
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(float)
    band = gray[int(h * 0.12):int(h * 0.95)]
    sx = np.abs(cv2.Sobel(band, cv2.CV_64F, 1, 0, ksize=3))
    prof = sx.mean(axis=0)
    th = prof.mean() + prof.std()
    peaks = [
        x for x in range(1, w - 1)
        if prof[x] > th and prof[x] >= prof[x - 1] and prof[x] >= prof[x + 1]
    ]
    if len(peaks) < 2:
        return None
    left, right = peaks[0], peaks[-1]
    # only trust detection when the outermost edges sit near the region borders
    # (a real board fills the region). Otherwise (menus, start screen, decor)
    # fall back to an even split so we don't lock onto a wrong inner box.
    if left > w * 0.15 or right < w * 0.85:
        return None
    return left, right


def tiles_lane_geometry(frame: "np.ndarray", lanes: int) -> tuple[list[float], list[tuple[int, int]]]:
    """Lane center x's and per-lane sample bands (x0, x1), in frame-x.

    Auto-detects the board edges so side margins don't shift the lanes; falls
    back to an even split over the full width if detection is unreliable.
    """
    w = frame.shape[1]
    edges = tiles_board_edges(frame)
    left, right = edges if edges else (0, w)
    span = (right - left) / lanes
    centers = [left + (i + 0.5) * span for i in range(lanes)]
    bands = [(int(left + (i + 0.25) * span), int(left + (i + 0.75) * span))
             for i in range(lanes)]
    return centers, bands


def tiles_hysteresis(
    raw_dark: list[bool], light_streak: list[int], release_frames: int
) -> list[bool]:
    """Debounce releases: a lane stays 'dark' until it has read light for
    `release_frames` consecutive frames. Bridges brief bright streaks inside a
    long tile (hold guide line, gradient) so the hold isn't dropped early.
    Mutates `light_streak` in place; returns the debounced dark flags.
    """
    eff = []
    for i, d in enumerate(raw_dark):
        if d:
            light_streak[i] = 0
        else:
            light_streak[i] += 1
        eff.append(d or light_streak[i] < release_frames)
    return eff


class BotEngine:
    def __init__(self, config: BotConfig, on_status: StatusCallback | None = None) -> None:
        self.config = config
        self.on_status = on_status or (lambda _msg: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # --- core loop ---------------------------------------------------------
    def _validate(self) -> str | None:
        """Return an error message if the config can't run, else None."""
        if self.config.region is None:
            return "set the game region first (TARGET)"
        return None

    def _run(self) -> None:
        err = self._validate()
        if err:
            self.on_status(f"error: {err}")
            return
        # mss must be created inside this thread.
        cap = ScreenCapture()
        try:
            self._run_tiles(cap)
        except Exception as e:  # surface failsafe / runtime errors to GUI
            self.on_status(f"stopped: {e}")
        finally:
            cap.close()
            self.on_status("stopped")

    def _run_tiles(self, cap) -> None:
        """Magic Tiles 3 loop, PREDICTIVE (see src/predict.py).

        Each frame: grab the whole board, segment the tiles per lane, track the
        board-wide fall velocity from the leading edges, sense occupancy at a
        TRIGGER line above the hit line, and SCHEDULE a press for the moment the
        tile will reach the hit line (`t = now + (hit - trig)/v - lead`). A
        single trigger line is the dedup (one rising edge = press, one falling =
        release per tile → multi-hold / chords fall out for free, one finger per
        lane). Timing comes from position + velocity, so it keeps up as the song
        speeds up instead of racing to react at the line.

        Safety: a press only ever follows a trigger rising edge, holds
        force-release after `tiles_max_hold`, Esc stops the bot even while held,
        and everything is released in `finally`.
        """
        from . import predict

        cfg = self.config
        mon = cfg.region  # validated non-None for tiles mode
        lanes = max(1, cfg.tiles_lanes)
        H = mon["height"]

        # capture source: a specific window (dxcam, low-latency) when a target
        # hwnd is set, else the screen region (mss). For window capture `mon` is
        # window-local and (ox, oy) maps it back to screen for touch.
        win = None
        if cfg.target_hwnd:
            from .window_capture import WindowCapture
            win = WindowCapture(cfg.target_hwnd, cfg.window_method)
        src_grab = win.grab if win else cap.grab
        ox, oy = win.origin() if win else (0, 0)

        # all detection is in board-image coords (row 0 = mon["top"]); only touch
        # converts to screen. Trigger line sits `tiles_trig_lead` of the height
        # above the hit line — the head-start the velocity projection needs.
        hit_row = int(H * cfg.tiles_hit)
        y_lo = int(H * cfg.tiles_play_top)
        y_hi = min(H, hit_row + 40)
        y_trig = hit_row - int(H * cfg.tiles_trig_lead)
        band = max(2, cfg.tiles_trig_band)
        lead_s = cfg.tiles_lead_ms / 1000.0
        min_tap_s = cfg.tiles_min_tap_ms / 1000.0
        confirm_s = cfg.tiles_confirm_ms / 1000.0

        # lane geometry in WINDOW-LOCAL coords; (ox, oy) is the window origin and
        # is refreshed every loop, so moving LDPlayer mid-play keeps the touches
        # on the board. Even split until the real board is confidently detected.
        centers, bands = tiles_lane_geometry(src_grab(mon), lanes)
        tx = [int(mon["left"] + cx) for cx in centers]       # lane x (local)
        ty = mon["top"] + hit_row                            # hit-line y (local)
        locked = tiles_board_edges(src_grab(mon)) is not None

        def _recalibrate(board) -> None:
            nonlocal centers, bands, tx, locked
            if tiles_board_edges(board) is None:
                return
            centers, bands = tiles_lane_geometry(board, lanes)
            tx = [int(mon["left"] + cx) for cx in centers]
            locked = True

        # --- per-lane actuator: background multi-touch (one finger per lane) ---
        from .touch import TouchInjector
        touch = TouchInjector(max_contacts=max(lanes + 2, 10))

        down = [False] * lanes          # which lanes are currently held
        held_since = [0.0] * lanes
        arrival = [0.0] * lanes          # predicted time the tile reaches the line
        seen_hit = [False] * lanes       # tile confirmed at the hit line this hold

        def press(i, now):
            if not down[i]:
                touch.down(i, ox + tx[i], oy + ty)
                down[i] = True
                held_since[i] = now
                seen_hit[i] = False

        def release(i):
            if down[i]:
                touch.up(i)
                down[i] = False

        def release_all():
            for i in range(lanes):
                if down[i]:
                    try:
                        touch.up(i)
                    except Exception:
                        pass
                    down[i] = False

        # Esc = emergency stop (works while inputs are held).
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

        def _segments(board):
            return predict.lane_segments(
                board, bands, cfg.tiles_margin, cfg.tiles_min_run,
                cfg.tiles_dark_frac, y_lo=y_lo, y_hi=y_hi,
                merge_gap=cfg.tiles_merge_gap)

        def _trigger_occ(board, segs):
            occ = predict.occupancy_at(segs, y_trig - band, y_trig + band)
            if cfg.tiles_note_colors:  # OR in coloured notes / slides
                tb = board[max(0, y_trig - band): y_trig + band]
                for bgr in cfg.tiles_note_colors:
                    col = tiles_color_lanes(tb, bands, bgr, cfg.tiles_note_tol)
                    occ = [a or c for a, c in zip(occ, col)]
            return occ

        # helper buttons (start, etc.) clicked on sight between songs
        helpers = []
        for path in cfg.tiles_helpers:
            try:
                helpers.append((path, detector.load_template(path)))
            except ValueError:
                pass
        last_helper = 0.0

        def _scan_helpers(full) -> bool:
            """Match helper templates against the WHOLE window (so full-screen
            templates like the unlock popup fit) and click. The unlock popup is
            escaped by tapping the first (unlocked) bottom thumbnail instead of
            the match center."""
            fh, fw = full.shape[:2]
            for path, tpl in helpers:
                if tpl.shape[0] > fh or tpl.shape[1] > fw:
                    continue
                hits = detector.match_template(full, tpl, cfg.tiles_helper_threshold)
                if not hits:
                    continue
                hx, hy, _ = hits[0]
                release_all()  # drop any holds before tapping
                if "unlock" in path.lower():
                    # leave the locked-song popup -> first bottom thumbnail
                    cx_, cy_ = fw * 0.066, fh * 0.95
                else:
                    cx_, cy_ = hx, hy
                touch.tap(lanes, int(ox + cx_), int(oy + cy_))  # background tap
                return True
            return False

        # predictive state
        v = 0.0
        prev_bottoms = None
        prev_occ = [False] * lanes
        trig_streak = [cfg.tiles_release_frames] * lanes  # trigger-occ debounce
        hit_streak = [cfg.tiles_release_frames] * lanes   # hit-occ debounce
        queue: list[predict.Event] = []  # scheduled presses, absolute monotonic
        last_t = time.monotonic()
        last_active = 0.0  # last time any lane was active (a tile near the line)

        def _reset_play() -> None:
            """Fresh board (after a helper tap): forget motion + pending events."""
            nonlocal v, prev_bottoms, prev_occ
            release_all()
            queue.clear()
            v = 0.0
            prev_bottoms = None
            prev_occ = [False] * lanes
            for i in range(lanes):
                trig_streak[i] = cfg.tiles_release_frames
                hit_streak[i] = cfg.tiles_release_frames
                seen_hit[i] = False

        self.on_status("running (tiles/predictive) — Esc to stop")
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                if win is not None:       # follow the window if it's moved
                    ox, oy = win.origin()

                # Helper scan (full-window grab + template match) is expensive and
                # halves the capture rate. Only run it when the board has been
                # QUIET for a while — between songs (waiting on START / unlock).
                quiet = now - last_active > 1.0
                if quiet and now - last_helper >= cfg.tiles_helper_interval:
                    last_helper = now
                    if not locked:           # auto-lock onto the real board
                        _recalibrate(src_grab(mon))
                    if helpers and _scan_helpers(src_grab(None)):
                        _reset_play()
                        self._stop.wait(0.1)
                        last_t = time.monotonic()
                        continue

                board = src_grab(mon)
                segs = _segments(board)

                # board-wide fall velocity from the leading edges
                dt = now - last_t
                last_t = now
                bottoms = predict.leading_bottoms(segs, hit_row)
                v = predict.update_velocity(v, prev_bottoms, bottoms, dt)
                prev_bottoms = bottoms

                # PRESS is predictive: a tile crossing the trigger schedules a
                # press for when it will reach the hit line (must be on time).
                # RELEASE is reactive: hold until the tile actually clears the
                # hit line. A late release is harmless; an early one drops a long
                # note (the fatal "ตายตอนกดยาว" bug — a velocity overshoot made
                # the predicted release fire before the note's tail left the
                # line). So releases are NOT scheduled — only the press edges are.
                occ = tiles_hysteresis(_trigger_occ(board, segs), trig_streak,
                                       cfg.tiles_release_frames)
                hit_occ = tiles_hysteresis(
                    predict.occupancy_at(segs, hit_row - band, hit_row + band),
                    hit_streak, cfg.tiles_release_frames)
                if any(occ) or any(hit_occ) or any(down):
                    last_active = now
                queue.extend(e for e in predict.schedule_edges(
                    prev_occ, occ, v, y_trig, hit_row, now, lead_s)
                    if e.kind == "press")
                prev_occ = occ

                # fire due presses (record the predicted arrival time)
                due = [e for e in queue if e.t <= now]
                if due:
                    queue = [e for e in queue if e.t > now]
                    for ev in sorted(due, key=lambda e: e.t):
                        press(ev.lane, now)
                        arrival[ev.lane] = now + lead_s

                # reactive release. A tile occupies the hit line from arrival
                # until its tail clears; hold for exactly that span:
                #  - keep holding until the tile is first SEEN at the hit band
                #    (so a press fired a few frames early — the prediction's
                #    jitter — is not released in the gap before the tile lands;
                #    that gap-release was the long-note death),
                #  - then release once it clears (hit band empty + min-tap floor),
                #  - if it never appears within `confirm_s`, it was a phantom
                #    press → release so the lane isn't blocked,
                #  - max-hold is the final backstop.
                for i in range(lanes):
                    if not down[i]:
                        continue
                    if hit_occ[i]:
                        seen_hit[i] = True
                    held = now - held_since[i]
                    if held > cfg.tiles_max_hold:
                        release(i)
                    elif seen_hit[i] and not hit_occ[i] and held >= min_tap_s:
                        release(i)
                    elif (not seen_hit[i] and held > confirm_s and not segs[i]):
                        # confirm window elapsed and the lane is now EMPTY — the
                        # press had no tile behind it (phantom). If a tile is
                        # still descending in this lane we keep holding (the press
                        # just fired early — don't release into the gap).
                        release(i)

                self._stop.wait(cfg.tiles_poll)
        finally:
            release_all()
            if touch is not None:
                touch.close()
            if listener is not None:
                listener.stop()
            if win is not None:
                win.close()
