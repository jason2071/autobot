# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`autobot` is a desktop GUI bot that **autoplays Magic Tiles 3** (and similar
piano-tile games) running in an Android emulator (LDPlayer) on Windows. It is
**tiles-mode only** — older template/color/pixel auto-clicker modes were removed.
Python + customtkinter GUI, OpenCV/numpy detection, pyautogui/pynput input.

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
.venv/Scripts/python.exe main.py          # run GUI
.venv/Scripts/python.exe -m tests.smoke    # run tests
```

**Tests:** `tests/smoke.py` is a hand-rolled runner (a `main()` that calls each
`test_*` and asserts) — there is **no pytest**. Run the whole file with
`python -m tests.smoke`; to run one check, call it inline, e.g.
`python -c "from tests.smoke import test_tiles_logic as t; t()"`.
Tests of detection on real captures **skip themselves** when the asset is
missing (`templates/*.png` and `*.mp4` are gitignored), so a clean checkout
still passes.

## Architecture

Data flows: **capture → per-lane segmentation → velocity + scheduling → input**,
all inside `BotEngine._run_tiles` running on a daemon thread. Detection is
**predictive**: it tracks each tile's fall and schedules the press for when the
tile will reach the hit line, instead of reacting once it is already there.

- `main.py` → `src/gui.py` `App` (customtkinter, fixed-size two-column window).
  The GUI builds a `BotConfig` in `_build_config`, validates, then runs a 3s
  countdown and starts a `BotEngine`. Status flows back via an `on_status`
  callback that marshals to Tk with `root.after` (the engine runs off-thread).

- `src/bot.py` is the core. `BotConfig` (dataclass) holds every tunable. Geometry
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

- `src/predict.py` is the **predictive detection core** (pure, replay-tested):
  - `lane_segments` — per-lane vertical tile spans `(y_top, y_bottom)` over the
    WHOLE board; crops the score-header / keyboard UI (`tiles_play_top`) and
    merges guide-line gaps (`tiles_merge_gap`).
  - `leading_bottoms` + `update_velocity` — one **board-wide fall velocity**
    (px/s), the EMA-median of the leading edges' per-frame motion. Tracks the
    song accelerating, so timing stays correct as it speeds up.
  - `occupancy_at` + `schedule_edges` — a single **trigger line** (`tiles_trig_
    lead` above the hit line) is the dedup: a rising edge → schedule a press for
    `now + (hit−trig)/v − lead`; a falling edge → a release. One tile = one
    press + one release; multi-hold / chords fall out for free (one finger per
    lane). `tiles_lead_ms` is the fixed input+emulator latency offset (tune live).
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

- **Capture** is window-bound. `src/window_capture.py` `WindowCapture` grabs one
  HWND directly so coordinates are **window-local** and other windows don't
  interfere. Three methods: **`dxcam`** (default) — DXGI desktop duplication of
  the window's screen rect, ~0.1ms/grab and pixel-correct; low capture latency is
  what lets the bot keep up as a song speeds up (PrintWindow's ~20ms/grab made it
  tap too late). `printwindow` (~20ms, overlap-proof) is the fallback when dxcam
  is unavailable. `bitblt` grabs the WRONG GPU layer for LDPlayer (verified: a
  full-frame mismatch) so it is never used for the emulator. dxcam needs the
  window visible/uncovered — already required for touch. `src/capture.py`
  `ScreenCapture` (mss) is used for the eyedropper / scale. `src/window_picker.py`
  lists windows and `focus_window`s the target (Win32 / AppleScript).

- `src/detector.py` (`match_template`, `load_template`) backs the helper-template
  scan (START/unlock buttons). `src/clicker.py` is legacy (tiles uses pyautogui
  directly) but still imported by the smoke test.

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
- **Input is background multi-touch only** (`src/touch.py` `TouchInjector` via
  Win32 `InjectTouchInput`): one finger per lane, **no focus needed**, real
  cursor never moves, but LDPlayer must stay **visible/uncovered** (touch hits
  the topmost window at the point). Driven by the scheduled per-lane event queue
  in `_run_tiles` (multi-hold / chords). The old mouse (pyautogui) and keyboard
  (pynput) backends were removed; pynput is still used only for the Esc
  emergency-stop listener.
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
