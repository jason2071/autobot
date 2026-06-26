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
    tiles_margin: int = 40
    tiles_sample_h: int = 18     # taller strip = catches faster tiles between polls
    tiles_lead: int = 12         # sample this many px ABOVE the hit line, so the
                                 # press fires earlier and beats capture/input lag
    tiles_poll: float = 0.001    # seconds between scans (fast; tiles speed up)
    tiles_max_hold: float = 4.0  # force-release a hold after this many seconds
    tiles_release_frames: int = 3  # frames of light before releasing (debounce)
    tiles_hold_extra: int = 0      # opt-in: extra light frames before releasing
                                   # a hold (helps long notes whose dark part is
                                   # shorter than the note; 0 = no change)
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
    window_method: str = "bitblt"  # fast/low-latency default (keeps up with the
                                   # game); "printwindow" = slower, capture covered
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


def tiles_dark_frac(
    lane_bands: list, margin: float, min_frac: float = 0.25
) -> list[bool]:
    """A lane has a tile when enough of its band is darker than the background.

    `lane_bands` is one 2D grayscale array per lane (the hit band sampled from
    the strip). Background brightness = the upper-middle lane mean (so a note
    covering up to half the lanes doesn't drag it down). A lane counts as a tile
    when the fraction of pixels darker than `bg - margin` exceeds `min_frac`.

    Using a *fraction over a tall band* (rather than the band mean) makes the
    hold robust to a note's light centre guide-line/dots, and — because the band
    spans from the lead point down to the hit line — keeps the hold until the
    note actually clears the line (fixes long notes releasing early).
    """
    means = sorted(float(b.mean()) for b in lane_bands)
    bg = means[len(means) // 2]
    thr = bg - margin
    return [float((b < thr).mean()) > min_frac for b in lane_bands]


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


def tiles_should_release(
    held: int | None, dark: list[bool], held_since: float, now: float, max_hold: float
) -> bool:
    """Release the pressed lane on a falling edge, or after the max hold time
    (the latter guards against a permanently-dark region locking the button)."""
    if held is None:
        return False
    return (not dark[held]) or (now - held_since > max_hold)


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


def tiles_kb_step(
    prev: list[bool], dark: list[bool], down: list[bool],
    since: list[float], now: float, max_hold: float,
) -> list[tuple[str, int]]:
    """Per-lane keyboard state machine (independent lanes -> true multi-hold).

    Mutates `down`/`since` in place and returns the ('press'|'release', lane)
    actions to actuate. Each lane: release on a falling edge or after max_hold,
    press on a light->dark rising edge. Lanes are independent, so two long
    tiles in different lanes are held at the same time.
    """
    actions: list[tuple[str, int]] = []
    for i in range(len(dark)):
        if down[i] and (not dark[i] or now - since[i] > max_hold):
            actions.append(("release", i))
            down[i] = False
        if dark[i] and not prev[i] and not down[i]:
            actions.append(("press", i))
            down[i] = True
            since[i] = now
    return actions


def tiles_rising(prev: list[bool], dark: list[bool]) -> list[int]:
    """Lanes with a light->dark RISING edge this frame (new tiles).

    Edge-triggered so a region dark from the start never fires. A list (not a
    single lane) so simultaneous tiles — chords — can all be handled.
    """
    return [i for i in range(len(dark)) if dark[i] and not prev[i]]


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
        """Magic Tiles 3 loop: watch N lanes at a hit line, press while a dark
        tile covers it. A short tile -> brief press (tap); a long tile -> a
        sustained hold until the tile clears.

        Two input backends:
          - "mouse":    one real cursor; a single tile/hold at a time, chords
                        are quick-tapped (no simultaneous holds).
          - "keyboard": one key per lane (LDPlayer key mapping). Each lane is
                        independent, so multiple long tiles / chords hold at
                        once. This is the way to support 2+ simultaneous holds.

        Safety: presses fire only on a light->dark EDGE (a permanently dark
        region never sticks), holds force-release after `tiles_max_hold`, Esc
        stops the bot even while inputs are held, and everything is released in
        `finally`.
        """
        cfg = self.config
        mon = cfg.region  # validated non-None for tiles mode
        lanes = max(1, cfg.tiles_lanes)
        H = mon["height"]

        # capture source: a specific window (PrintWindow, overlap-proof) when a
        # target hwnd is set, else the screen region (mss). For window capture
        # `mon` is window-local and (ox, oy) maps it back to screen for clicks.
        win = None
        if cfg.target_hwnd:
            from .window_capture import WindowCapture
            win = WindowCapture(cfg.target_hwnd, cfg.window_method)
        src_grab = win.grab if win else cap.grab
        ox, oy = win.origin() if win else (0, 0)

        # strip of pixels sampled `tiles_lead` px ABOVE the hit line, so a press
        # fires before the tile reaches the line — compensates capture/input lag.
        sh = max(2, cfg.tiles_sample_h)
        hit_y = mon["top"] + int(H * cfg.tiles_hit)
        strip = {"top": hit_y - cfg.tiles_lead - sh // 2, "left": mon["left"],
                 "width": mon["width"], "height": sh}

        # lane geometry in WINDOW-LOCAL coords; (ox, oy) is the window origin and
        # is refreshed every loop, so moving LDPlayer mid-play keeps the touches
        # on the board (capture follows the window too). Even split until the real
        # board is confidently detected, then lock onto it.
        typ = int(hit_y)                                     # hit-line y (local)
        centers, bands = tiles_lane_geometry(src_grab(mon), lanes)
        tx = [int(mon["left"] + cx) for cx in centers]       # lane x (local)
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

        def press(i):
            touch.down(i, ox + tx[i], oy + typ)

        def release(i):
            touch.up(i)

        def release_all():
            for i in range(lanes):
                if down[i]:
                    try:
                        release(i)
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

        def _read_dark():
            frame = src_grab(strip)
            means = [float(frame[:, x0:x1].mean()) for x0, x1 in bands]
            active = tiles_dark_lanes(means, cfg.tiles_margin)
            for bgr in cfg.tiles_note_colors:  # OR in coloured notes / slides
                col = tiles_color_lanes(frame, bands, bgr, cfg.tiles_note_tol)
                active = [a or c for a, c in zip(active, col)]
            return active

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

        # prime: lanes already dark at start must NOT fire
        light_streak = [cfg.tiles_release_frames] * lanes
        prev = _read_dark()
        self.on_status("running (tiles/background) — Esc to stop")
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                if win is not None:       # follow the window if it's moved
                    ox, oy = win.origin()

                if now - last_helper >= cfg.tiles_helper_interval:
                    last_helper = now
                    if not locked:           # auto-lock onto the real board
                        _recalibrate(src_grab(mon))
                    if helpers and _scan_helpers(src_grab(None)):
                        prev = [False] * lanes
                        self._stop.wait(0.4)
                        continue

                dark = tiles_hysteresis(
                    _read_dark(), light_streak,
                    cfg.tiles_release_frames + cfg.tiles_hold_extra)

                # independent per-lane multi-touch -> true multi-hold + chords
                for act, i in tiles_kb_step(
                    prev, dark, down, held_since, now, cfg.tiles_max_hold
                ):
                    (release if act == "release" else press)(i)

                prev = dark
                self._stop.wait(cfg.tiles_poll)
        finally:
            release_all()
            if touch is not None:
                touch.close()
            if listener is not None:
                listener.stop()
            if win is not None:
                win.close()
