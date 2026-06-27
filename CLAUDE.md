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

Data flows: **capture → per-lane detection → per-lane state machine → input**,
all inside `BotEngine._run_tiles` running on a daemon thread.

- `main.py` → `src/gui.py` `App` (customtkinter, fixed-size two-column window).
  The GUI builds a `BotConfig` in `_build_config`, validates, then runs a 3s
  countdown and starts a `BotEngine`. Status flows back via an `on_status`
  callback that marshals to Tk with `root.after` (the engine runs off-thread).

- `src/bot.py` is the core. `BotConfig` (dataclass) holds every tunable. Module-
  level **pure functions** carry the detection/decision logic and are what the
  smoke tests exercise:
  - `tiles_lane_geometry` / `tiles_board_edges` — auto-detect the board's left/
    right edges (vertical-Sobel) so side margins don't shift the lanes; fall back
    to an even split.
  - `tiles_dark_lanes` — a lane is "active" when it is `tiles_margin` darker than
    the **median** lane (relative → skin-independent for dark tiles).
  - `tiles_color_lanes` — OR-in detection for **bright/colored notes and slides**
    by hue match; `BotConfig.tiles_note_colors` is a **list** (pick several, e.g.
    cyan notes + pink slides). Empty list = darkness only.
  - `tiles_hysteresis` — debounces release (`tiles_release_frames` +
    `tiles_hold_extra`) so long notes with light trails aren't dropped early.
  - `tiles_kb_step` / `tiles_rising` / `tiles_should_release` — the press/release
    state machine. Per-lane independent (one touch finger each), so it does true
    multi-hold for chords / simultaneous long notes.
  - `_run_tiles` ties it together: sample a thin strip at the hit line, run
    detection, drive the actuator, plus a throttled helper scan that clicks the
    START / unlock screens between songs (`tiles_helpers`).

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
- **Latency drives accuracy** in fast songs. BitBlt (low latency) is the default;
  `tiles_lead` samples a few px *above* the hit line so the press fires early
  enough. PrintWindow's higher latency can miss everything ("nothing presses").
- **Input is background multi-touch only** (`src/touch.py` `TouchInjector` via
  Win32 `InjectTouchInput`): one finger per lane, **no focus needed**, real
  cursor never moves, but LDPlayer must stay **visible/uncovered** (touch hits
  the topmost window at the point). Driven by the per-lane state machine
  `tiles_kb_step` (multi-hold / chords). The old mouse (pyautogui) and keyboard
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
