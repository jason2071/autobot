# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`autobot` is a **general OpenCV vision-bot foundation** for autoplaying
rhythm/tile games by *seeing the screen* (no adb, no memory reads) — meant to be
reused across games, including PC titles. Two integrations exist today:

- **Magic Tiles 3** (the original; an Android game in the LDPlayer emulator) —
  predictive tile tracking + touch / WM-message input. See `src/core/`.
- **Where Winds Meet** (a PC game; the instrument minigame) — a 6-lane keyboard
  rhythm autoplayer. See `src/games/wwm.py` + `run_wwm.py`.

Python + customtkinter GUI (Magic Tiles), OpenCV/numpy detection, pynput/Win32
input. The predictive/segmentation core in `src/core/predict.py` is shared.

## Commands

The venv lives in `.venv`. The Makefile auto-detects OS for the venv path
(`Scripts/` on Windows, `bin/` elsewhere) but its recipe bodies use Unix shell
utils, so on Windows run `make` from **Git Bash / WSL**.

```bash
make install   # create .venv + install requirements.txt
make run       # launch the GUI  (== .venv/Scripts/python main.py)
make test      # run the smoke test
make clean     # remove .venv + __pycache__
```

Direct invocation (works in PowerShell too):
```
.venv/Scripts/python.exe main.py             # run Magic Tiles GUI
.venv/Scripts/python.exe run_wwm.py          # run Where Winds Meet autoplayer
.venv/Scripts/python.exe run_wwm.py --list   # list windows to target
.venv/Scripts/python.exe -m tests.smoke      # run tests
.venv/Scripts/python.exe -m tests.wwm_replay # WWM offline sanity gate
```

**Tests:** `tests/smoke.py` is a hand-rolled runner (a `main()` that calls each
`test_*` and asserts) — there is **no pytest**. Run the whole file with
`python -m tests.smoke`; to run one check, call it inline, e.g.
`python -c "from tests.smoke import test_tiles_logic as t; t()"`.
Tests of detection on real captures **skip themselves** when the asset is
missing (`templates/*.png` and `*.mp4` are gitignored), so a clean checkout
still passes.

`tests/predict_replay.py` is the **offline timing gate** for the predictive
tracker — it replays `predict.py` over `templates/gameplay*.mp4` and asserts on
press-time jitter. Run with `python -m tests.predict_replay`; it also skips
itself on a clean checkout (no clip present).

## Architecture

Data flows: **capture → per-lane segmentation → velocity + scheduling → input**,
all inside `BotEngine._run_tiles` running on a daemon thread. Detection is
**predictive**: it tracks each tile's fall and schedules the press for when the
tile will reach the hit line, instead of reacting once it is already there.

**Package layout** (`src/`, grouped by concern):
- `core/` — `bot.py` (BotEngine / BotConfig + the `_run_tiles` loop + auto-lead
  tuner), `predict.py` (pure predictive-detection primitives)
- `capture/` — `window_capture.py` (WindowCapture: dxcam / PrintWindow),
  `screen.py` (ScreenCapture: mss), `window_picker.py`
- `detect/` — `detector.py` (template + color/pixel match)
- `input/` — `touch.py` (TouchInjector — Magic Tiles primary), `ld_click.py`
  (LDPlayer message-click fallback), `key.py` (KeyInjector — keyboard, for WWM)
- `games/` — `wwm.py` (Where Winds Meet integration: geometry + note mask +
  reactive engine)
- `toolkit/` — `ezcbot.py` (reusable EzCBot port; re-exports the modules above)
- `ui/` — `gui.py` (customtkinter App)

`main.py` (Magic Tiles entry), `run_wwm.py` (Where Winds Meet entry) and
`reference/EzCBot.cs` (the original C# toolkit this was ported from) live at the
repo root.

### Where Winds Meet (`src/games/wwm.py`)

A 6-lane keyboard rhythm minigame: bright translucent note-circles fall down six
fixed lanes (keys **S D F J K L**) onto a target-circle row; press the lane's key
as a note lands, holding for the long "capsule" notes.

- **VISION-ONLY by default, on purpose (`WWMConfig.dry_run=True`).** Where Winds
  Meet runs ELEVATED (verified: its process is admin) — i.e. it ships anti-cheat.
  Two consequences: (1) Windows UIPI silently DROPS injected input from our
  non-elevated process, so keys never arrive (capture + focus still work — this
  is why a live run looked like "misses everywhere" while scoring 0); (2) even if
  we elevated to get past UIPI, `SendInput` keys carry an OS "injected" flag a
  kernel anti-cheat can read, so auto-playing risks an account BAN. So the engine
  DEFAULTS to dry_run: it captures + detects + decides and reports the lane it
  WOULD hit via the `on_event` callback (a passive on-screen visualiser lights
  it), but constructs no `KeyInjector` and sends nothing. Screen capture is
  passive and low-risk; injected input is not. `--actuate` / `dry_run=False`
  exists only for an OFFLINE / non-protected target — never point it at an
  anti-cheat game. `src/input/key.py` `KeyInjector` (Win32 `SendInput` scancodes,
  true simultaneous keys) is the actuation backend used only in that mode.
- **Capture is dxcam, multi-output.** `WindowCapture` picks the dxcam OUTPUT
  showing the target window (matched to its monitor via `MonitorFromWindow`) and
  grabs in that output's local coords — a window on a SECOND monitor works
  (plain `dxcam.create()` only sees the primary and raised "Invalid Region").
  PrintWindow returns BLACK for this game's DirectX surface, so dxcam is the only
  capture path. The engine segments only a thin STRIP around the target row, not
  the whole frame (~6x faster: 19ms→3ms), so a falling note can't skip the band
  between frames. `window_picker.focus_hwnd` force-foregrounds via
  AttachThreadInput (a plain SetForegroundWindow from the background is refused);
  `input_blocked_by_uipi(hwnd)` flags the elevated-game/non-elevated-bot case.
- **Geometry is resolution- and aspect-independent.** Measured on real captures
  at 1920x1080 *and* 3440x1440, the rhythm UI scales with screen HEIGHT and is
  horizontally CENTERED: each lane sits at `x = W/2 + k*H` (the `LANE_K` constants
  are identical across both resolutions to <0.5%), the target row at `y = 0.865*H`.
  So one model drives 16:9 and 21:9. `calibrate()` refines it from the actual
  frame (the S D F J K L letter glyphs) and falls back to the model.
- **Play is purely REACTIVE** (unlike Magic Tiles' predictive schedule): segment
  each lane on a bright-note mask (`V > note_v_min & S < note_s_max`), and press a
  lane the moment a segment reaches the target band (`hit_band` around `hit_y`),
  held until the band clears. A measured sweep showed the predictive schedule
  added zero coverage here — these notes fall slow and steady (~520 px/s) onto a
  target with generous tolerance, so reacting on the band lands "Perfect". The one
  live latency knob is `press_offset_px` (shift the band up to press earlier).
- `release_frames` debounces the band so a one/two-frame mask flicker (the
  flower-icon hole in a note) doesn't release+re-press a single note as a
  double-tap. `tests/wwm_replay.py` is the offline sanity gate (presses sane +
  spread across all lanes + low duplicate rate); per-note timing is verified
  visually (annotated frames) and live.

- `main.py` → `src/ui/gui.py` `App` (customtkinter, fixed-size two-column window).
  The GUI builds a `BotConfig` in `_build_config`, validates, then runs a 3s
  countdown and starts a `BotEngine`. Status flows back via an `on_status`
  callback that marshals to Tk with `root.after` (the engine runs off-thread).

- `src/core/bot.py` is the core. `BotConfig` (dataclass) holds every tunable. Geometry
  + helper-detection **pure functions** live here:
  - `tiles_lane_geometry` / `tiles_board_edges` — auto-detect the board's left/
    right edges (vertical-Sobel) so side margins don't shift the lanes; fall back
    to an even split.
  - `tiles_dark_lanes` — relative-darkness primitive (a value is "dark" when it
    is `tiles_margin` below the **median** lane → skin-independent).
  - `tiles_color_lanes` — OR-in detection for **bright/colored notes and slides**
    by hue match; `BotConfig.tiles_note_colors` is a **list** (empty = darkness
    only).
  - `tiles_hysteresis` — debounces the trigger-line occupancy (`tiles_release_
    frames`) so flicker doesn't fire phantom edges.

- `src/core/predict.py` is the **predictive detection core** (pure, replay-tested):
  - `tile_mask` — a PRECISE boolean tile mask: a pixel is a tile when very DARK
    (`V < tiles_dark_v` → black taps) OR a VIVID cool-coloured note (hue in
    `tiles_hue_lo..hi`, **wide** 86–170 = cyan→blue→navy→magenta, AND `S >=
    tiles_sat_min`, a **high** floor of 200; `tiles_note_colors` adds more). The
    sat floor is the real discriminator: measured across skins every coloured
    note is S≥216 (cyan long notes 240–255, magenta slides 216–236, dark-navy
    long notes 255) while every busy background stays S≤193 (incl. the
    blue/purple Party-Rock bg at H102–105 — which the OLD tight `[90,102]` band
    false-fired on at S155+, a phantom tap = death). So `S>=200` separates note
    from bg, and the wide hue then admits the navy long notes + magenta slides
    the old band missed ENTIRELY (a slide rendered a fully-blank mask → the bot
    couldn't see it → death; that was the main "เล่นไม่จบเพลง" cause). Warm
    backgrounds (orange/green, H<86) are excluded by the hue floor. Verified on
    real clips: the pink-slide frame went 0.001→0.218 cover (invisible→seen)
    while the blue-bg Party-Rock frames stayed unchanged (no new false-fire).
  - `lane_segments` — per-lane vertical tile spans `(y_top, y_bottom)` over the
    WHOLE board from that mask (falls back to relative darkness if no mask given);
    crops the score-header / keyboard UI (`tiles_play_top`) and merges guide-line
    gaps (`tiles_merge_gap`).
  - `leading_bottoms` + `update_velocity` — one **board-wide fall velocity**
    (px/s), the EMA-median of the leading edges' per-frame motion. Tracks the
    song accelerating, so timing stays correct as it speeds up.
  - `occupancy_at` + `schedule_edges` — a single **trigger line** (`tiles_trig_
    lead` above the hit line) is the dedup: a tile's bottom crossing it (rising
    edge) schedules a **press** for `now + (hit−trig)/v − lead`. `tiles_lead_ms`
    is the fixed input+emulator latency offset (tune live).
  - **Auto-lead tuner** (`_LeadTuner` in `src/core/bot.py`): the press LEAD must match
    the real input+emulator latency (too low → taps land late and miss; too high
    → taps fire on empty). When `tiles_auto_lead` is on, the bot sweeps a fixed
    set of lead values across attempts, measuring how long each SURVIVES, then
    locks the best — persisted to `~/.autobot_lead_cal.json` so the user just
    retries and it converges. The sweep is a fixed set (`_LeadTuner.SWEEP`) walked
    low→high, but survival is unimodal (rises to the lead matching this machine's
    latency, then falls as taps fire on empty), so it **early-stops** once clearly
    past the peak (last two leads each survived `< EARLY_FRAC` of the best) — a
    low-latency emulator (best = lead 0) converges in ~3 attempts instead of 8.
    The GUI LEAD value is used only when `tiles_auto_lead` is OFF. Delete the cal
    file to recalibrate.
  - **Reactive press floor** (in `_run_tiles`): besides the scheduled presses, a
    tile sitting ON the hit line that the prediction missed is tapped immediately,
    **but only while `v > 0`** (the board is actually falling). For a moving tile
    the predictive press already fired, so the lane is down and this is a no-op;
    the floor is the safety net for one the prediction missed. The `v>0` gate
    matters between songs: a static result / reward / song-select screen has dark
    UI (buttons, text) in the lane bands at the hit line, and WITHOUT the gate the
    floor tapped them — navigating the bot off into random menus (observed: it
    wandered from the dead song into the Summer-Pass / daily-song screens and
    never retried). A static screen has `v==0`, so the gate suppresses it; the
    song-start tile is handled by the START / unlock **helper templates**, not the
    floor. Release is gated on the hit band going empty, so it never double-taps.
  - **Release is reactive, not scheduled** (in `_run_tiles`): a press is held
    until the tile actually clears the hit-line band (`occupancy_at(hit±band)`
    falls, debounced). A press fired a few frames early (prediction jitter) is
    held through the gap until the tile is first SEEN at the line; a press with
    no tile behind it (phantom) is dropped after `tiles_confirm_ms` once the lane
    is empty. A LATE release is harmless; an EARLY one drops a long note — which
    was the "ตายตอนกดยาว" death (a velocity overshoot made a *scheduled* release
    fire before the note's tail left the line). One tile = one press + one
    release; multi-hold / chords fall out for free (one finger per lane).
  - `_run_tiles` ties it together: grab the whole board, segment, update
    velocity, sense+debounce the trigger occupancy, push scheduled events onto a
    per-lane queue, and actuate events whose time has arrived (with a `tiles_min_
    tap_ms` floor so taps register). Plus a throttled helper scan that clicks the
    START / unlock screens between songs (`tiles_helpers`); a fresh board resets
    velocity + the event queue.

  Validated offline by `tests/predict_replay.py` against `gameplay*.mp4`: timing
  jitter 1–2 frames (~25ms) after removing the constant (live-correctable) bias,
  while `v` tracks the song from ~1400→3100 px/s. The old reactive path
  (thin-strip occupancy at the hit line, a `tiles_kb_step` state machine) was
  removed — it could only react once a tile was at the line and plateaued as
  songs sped up.

- **Capture** is window-bound. `src/capture/window_capture.py` `WindowCapture` grabs one
  HWND directly so coordinates are **window-local** and other windows don't
  interfere. Three methods: **`dxcam`** (default) — DXGI desktop duplication of
  the window's screen rect, ~0.1ms/grab and pixel-correct; low capture latency is
  what lets the bot keep up as a song speeds up (PrintWindow's ~20ms/grab made it
  tap too late). `printwindow` (~20ms, overlap-proof) is the fallback when dxcam
  is unavailable. `bitblt` grabs the WRONG GPU layer for LDPlayer (verified: a
  full-frame mismatch) so it is never used for the emulator. dxcam needs the
  window visible/uncovered — already required for touch. `src/capture/screen.py`
  `ScreenCapture` (mss) is used for the eyedropper / scale. `src/capture/window_picker.py`
  lists windows and `focus_window`s the target (Win32 / AppleScript).

- `src/detect/detector.py` (`match_template`, `load_template`) backs the helper-template
  scan (START/unlock buttons). The legacy pyautogui `clicker` module was removed
  in the subpackage refactor (tiles input is `input/touch.py` only).

## Non-obvious things that bite

- **`WindowCapture` is stateful** (caches a GDI DC/bitmap) and is **not thread-
  safe**. Two captures of the same HWND from different threads → GDI crash. When
  instrumenting a running bot, do not also capture its window from your script.
- **Coordinate scale**: `ScreenCapture.primary_monitor` picks the `is_primary`
  display (not `monitors[1]`) so the logical↔physical `scale` is right on multi-
  monitor setups. Region is window-local; clicks map back via window origin × scale.
- **Prediction, not latency-racing.** The old reactive path raced to detect a
  tile at the hit line, so it needed minimum capture latency (dxcam) and still
  plateaued. The predictive path schedules presses from velocity, so loop rate
  matters far less — it runs ~60fps (full-board segmentation costs more than the
  old thin strip) yet taps on time because it fires ahead by `(hit−trig)/v`.
  Residual constant offset (capture+input+emulator lag) is absorbed by the one
  live knob `tiles_lead_ms`. dxcam is still the default capture (correct GPU
  layer); BitBlt grabs the WRONG layer for LDPlayer and is never used.
- **The `touch` input backend** (`src/input/touch.py` `TouchInjector` via Win32
  `InjectTouchInput`) is background multi-touch: one finger per lane, **no focus
  needed**, real cursor never moves, but LDPlayer must stay **visible/uncovered**
  (touch hits the topmost window at the point). It is now OPT-IN — the default is
  the `wm` backend (see "Background mode" below); pick `touch` for real
  multi-touch when the window is kept clear. Driven by the scheduled per-lane event queue
  in `_run_tiles` (multi-hold / chords). The old mouse (pyautogui) and keyboard
  (pynput) backends were removed; pynput is still used only for the Esc
  emergency-stop listener.
- **dxcam grabs the SCREEN RECT, not the window — so a COVERED / moved / off-
  monitor window gives WRONG pixels** (it captures whatever is on top at that
  rect). This bit hard: a "the bot misses everything / score 0" was misdiagnosed
  as a gameplay bug when dxcam was actually capturing *another window* (a code
  editor) over the covered emulator, and the taps were landing on it too. A
  `printwindow` grab of the SAME HWND showed the real game — **printwindow asks
  the window to render itself, so it is cover- and monitor-proof** (and the
  window can sit on a secondary / negative-coordinate monitor). When a run looks
  like total failure, FIRST grab via printwindow to rule out a capture-target
  mismatch before touching detection/timing.
- **Background mode is the DEFAULT** = play while the game is COVERED by other
  windows (`BotConfig.tiles_input="wm"` + `window_method="printwindow"`; GUI
  checkbox "Background mode", checked by default). Capture via PrintWindow
  (cover-proof) + input via `ld_click.WMInjector` — WM-message clicks POSTED to
  the render-child HWND, not delivered to the topmost window at the screen point.
  Verified: with LDPlayer pushed to the z-bottom it still captures gameplay and
  scores (PERFECT combos). Trade-off: WM is a single mouse button → **no true
  simultaneous multi-touch**, so survival is lower than InjectTouchInput on
  chord-heavy charts. **Cover-proof multi-touch is not achievable** on Windows:
  WM_POINTER messages are IGNORED by LDPlayer (tested — WM_LBUTTON registers in
  ~127ms, WM_POINTERDOWN does nothing) because posted pointer messages have no
  system pointer-info backing, and InjectTouchInput is screen-point/topmost-only.
  Uncheck the box (→ `tiles_input="touch"` + `window_method="dxcam"`) for real
  multi-touch + lowest-latency capture when you keep LDPlayer visible/uncovered
  (best gameplay — e.g. park it on a second monitor where nothing overlaps it).
- **The target window MOVES and the desktop is multi-monitor — never hardcode the
  window origin.** Read it live every loop (`win.origin()` → GetWindowRect);
  `_run_tiles` already refreshes `ox, oy` so touches follow a dragged window. (Bit
  me in a throwaway test harness: a hardcoded origin captured + tapped the wrong
  screen spot after the window had moved; the live origin is the only safe source.
  Note negative-x monitors exist — an ultrawide primary at (0,0) with a second
  display at x=-1920 — so screen coords can be negative.)
- **Why the cursor stays put** (`_CursorGuard` in `src/touch.py`): Windows
  promotes the *primary* touch pointer to synthetic mouse input, so injected
  touch would otherwise jerk the real cursor to each lane (and could click
  another window). You can't dodge it by demoting the contact — LDPlayer only
  registers the *primary* touch, so a held "anchor" contact gets ignored and
  taps stop landing. Instead a `WH_MOUSE_LL` hook on a dedicated pumped thread
  **swallows injected mouse events** (`LLMHF_INJECTED`) and passes real input
  through. Verified: 200 rapid taps move the cursor zero pixels; the user's own
  mouse keeps working. **Capture must stay PrintWindow** — BitBlt grabs the
  wrong layer for LDPlayer, so detection fails and nothing taps (the GUI no
  longer exposes a BitBlt/"Fast capture" toggle).
- `templates/` and `*.mp4` are gitignored (game assets, gameplay recordings used
  only for offline analysis).
