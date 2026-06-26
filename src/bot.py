"""BotEngine: capture -> detect -> click loop running on a background thread."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .capture import ScreenCapture
from .clicker import Clicker
from . import detector


@dataclass
class BotConfig:
    template_paths: list[str] = field(default_factory=list)
    threshold: float = 0.8
    interval: float = 0.5  # seconds between scans
    region: dict | None = None  # {"top","left","width","height"} physical px, or None
    click_mode: str = "first"  # "first" or "all"
    mode: str = "template"  # "template" | "color" | "pixel" | "tiles"
    # color mode (scan a region for a colored blob)
    color_target: tuple[int, int, int] | None = None  # BGR
    color_tolerance: int = 25
    # pixel mode (watch one point; click when its color matches)
    pixel_point: tuple[int, int] | None = None  # physical screen px (x, y)
    pixel_color: tuple[int, int, int] | None = None  # BGR
    pixel_tolerance: int = 20  # per-channel BGR
    # tiles mode (Magic Tiles 3 style: N lanes, dark tile reaches hit line)
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
    # board, and the per-lane state machine follows it). None = darkness only.
    tiles_note_color: tuple[int, int, int] | None = None
    tiles_note_tol: int = 18       # hue tolerance (degrees) for the note colour
    # input backend: "mouse" (single finger) or "keyboard" (per-lane keys, so
    # multiple long tiles / chords can be held at once via LDPlayer key mapping)
    tiles_input: str = "mouse"
    tiles_keys: list[str] = field(default_factory=lambda: ["d", "f", "j", "k"])
    # in keyboard mode, press this key to start a song (map it to START in
    # LDPlayer) instead of mouse-clicking — keeps the cursor off the game. Empty
    # = click as usual.
    tiles_start_key: str = "f"
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
    min_click_interval: float = 0.3
    jitter: int = 0
    background: bool = False  # click without moving the real cursor (macOS)


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
        cfg = self.config
        if cfg.mode == "color" and cfg.color_target is None:
            return "no color picked"
        if cfg.mode == "pixel" and (cfg.pixel_point is None or cfg.pixel_color is None):
            return "no pixel picked"
        if cfg.mode == "template" and not cfg.template_paths:
            return "no templates set"
        if cfg.mode == "tiles" and cfg.region is None:
            return "set the game region first (TARGET)"
        return None

    def _run(self) -> None:
        cfg = self.config
        err = self._validate()
        if err:
            self.on_status(f"error: {err}")
            return

        templates: list = []
        if cfg.mode == "template":
            try:
                templates = [detector.load_template(p) for p in cfg.template_paths]
            except ValueError as e:
                self.on_status(f"error: {e}")
                return

        # mss must be created inside this thread.
        cap = ScreenCapture()

        if cfg.mode == "tiles":
            try:
                self._run_tiles(cap)
            except Exception as e:  # surface failsafe / runtime errors to GUI
                self.on_status(f"stopped: {e}")
            finally:
                cap.close()
                self.on_status("stopped")
            return

        mon = cfg.region if cfg.region else cap.primary_monitor
        region_offset = (mon["left"], mon["top"])
        try:
            clicker = Clicker(
                capture_width=cap.primary_monitor["width"],
                min_interval=cfg.min_click_interval,
                jitter=cfg.jitter,
                background=cfg.background,
            )
        except RuntimeError as e:
            self.on_status(f"error: {e}")
            cap.close()
            return
        self.on_status("running")

        try:
            while not self._stop.is_set():
                if cfg.mode == "pixel":
                    matches, offset = self._scan_pixel(cap)
                else:
                    frame = cap.grab(cfg.region)
                    matches = self._detect(frame, templates)
                    offset = region_offset

                if matches:
                    targets = matches if cfg.click_mode == "all" else matches[:1]
                    clicked = 0
                    for x, y, _score in targets:
                        if clicker.click_at(x, y, region_offset=offset):
                            clicked += 1
                    self.on_status(f"clicked {clicked} of {len(matches)} match(es)")
                else:
                    self.on_status("idle — no match")

                self._stop.wait(cfg.interval)
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
        import pyautogui

        pyautogui.PAUSE = 0  # no artificial delay between mouse events

        cfg = self.config
        mon = cfg.region  # validated non-None for tiles mode
        lanes = max(1, cfg.tiles_lanes)
        scale = pyautogui.size().width / cap.primary_monitor["width"]
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
        # The click/keypress position (ly below) stays on the true hit line.
        sh = max(2, cfg.tiles_sample_h)
        hit_y = mon["top"] + int(H * cfg.tiles_hit)
        strip = {"top": hit_y - cfg.tiles_lead - sh // 2, "left": mon["left"],
                 "width": mon["width"], "height": sh}

        # lane geometry: even split until the real board is confidently
        # detected (edges near the region borders), then lock onto it. This way
        # starting on a menu / start screen doesn't lock in a wrong layout.
        ly = (oy + hit_y) * scale
        centers, bands = tiles_lane_geometry(src_grab(mon), lanes)
        lx = [(ox + mon["left"] + cx) * scale for cx in centers]
        locked = tiles_board_edges(src_grab(mon)) is not None

        def _recalibrate(board) -> None:
            nonlocal centers, bands, lx, locked
            if tiles_board_edges(board) is None:
                return
            centers, bands = tiles_lane_geometry(board, lanes)
            lx = [(ox + mon["left"] + cx) * scale for cx in centers]
            locked = True

        # --- per-lane actuator (mouse single-finger vs keyboard multi-key) ----
        use_kb = cfg.tiles_input == "keyboard"
        kb = None
        keys = list(cfg.tiles_keys)
        if use_kb:
            try:
                from pynput.keyboard import Controller
                kb = Controller()
            except Exception:
                use_kb = False  # fall back to mouse if pynput missing

        down = [False] * lanes          # which lanes are currently held
        held_since = [0.0] * lanes

        def press(i):
            if use_kb:
                kb.press(keys[i % len(keys)])
            else:
                pyautogui.mouseDown(lx[i], ly)

        def release(i):
            if use_kb:
                kb.release(keys[i % len(keys)])
            else:
                pyautogui.mouseUp()

        def tap(i):
            if use_kb:
                kb.press(keys[i % len(keys)])
                kb.release(keys[i % len(keys)])
            else:
                pyautogui.click(lx[i], ly)

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
            if cfg.tiles_note_color is not None:  # OR in coloured notes / slides
                col = tiles_color_lanes(frame, bands, cfg.tiles_note_color,
                                        cfg.tiles_note_tol)
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
                release_all()  # drop any holds before clicking
                if "start" in path.lower() and use_kb and cfg.tiles_start_key:
                    # press a mapped key to start — keeps the mouse off the game
                    kb.press(cfg.tiles_start_key)
                    kb.release(cfg.tiles_start_key)
                elif "unlock" in path.lower():
                    # leave the locked-song popup -> first bottom thumbnail
                    pyautogui.click((ox + fw * 0.066) * scale,
                                    (oy + fh * 0.95) * scale)
                else:
                    pyautogui.click((ox + hx) * scale, (oy + hy) * scale)
                return True
            return False

        # prime: lanes already dark at start must NOT fire
        light_streak = [cfg.tiles_release_frames] * lanes
        prev = _read_dark()
        backend = "keyboard" if use_kb else "mouse"
        self.on_status(f"running (tiles/{backend}) — Esc to stop")
        try:
            while not self._stop.is_set():
                now = time.monotonic()

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

                if use_kb:
                    # independent per-lane state -> true multi-hold + chords
                    for act, i in tiles_kb_step(
                        prev, dark, down, held_since, now, cfg.tiles_max_hold
                    ):
                        (release if act == "release" else press)(i)
                else:
                    # single pointer: one hold; chords are quick-tapped
                    cur = down.index(True) if any(down) else None
                    if cur is not None and (not dark[cur] or now - held_since[cur] > cfg.tiles_max_hold):
                        release(cur)
                        down[cur] = False
                        cur = None
                    if cur is None:
                        new = tiles_rising(prev, dark)
                        if len(new) == 1:
                            i = new[0]
                            press(i)
                            down[i] = True
                            held_since[i] = now
                        elif len(new) > 1:
                            for i in new:
                                tap(i)

                prev = dark
                self._stop.wait(cfg.tiles_poll)
        finally:
            release_all()
            if listener is not None:
                listener.stop()
            if win is not None:
                win.close()

    def _scan_pixel(self, cap) -> tuple[list[detector.Match], tuple[int, int]]:
        """Grab a 1x1 region at pixel_point and test its color."""
        cfg = self.config
        px, py = cfg.pixel_point
        frame = cap.grab({"top": py, "left": px, "width": 1, "height": 1})
        if detector.check_pixel(frame, 0, 0, cfg.pixel_color, cfg.pixel_tolerance):
            return [(0, 0, 1.0)], (px, py)
        return [], (px, py)

    def _detect(self, frame, templates) -> list[detector.Match]:
        cfg = self.config
        matches: list[detector.Match] = []
        if cfg.mode == "template":
            for tpl in templates:
                matches.extend(detector.match_template(frame, tpl, cfg.threshold))
        elif cfg.mode == "color":
            matches.extend(
                detector.find_color(frame, cfg.color_target, cfg.color_tolerance)
            )
        # highest score first
        matches.sort(key=lambda m: m[2], reverse=True)
        return matches
