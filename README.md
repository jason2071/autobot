# autobot

A desktop GUI bot that **autoplays Magic Tiles 3** (and similar piano-tile
games) running in an Android emulator (**LDPlayer**) on **Windows**. It is
**tiles-mode only** — the older template / color / pixel auto-clicker modes were
removed. Start/Stop with a small GUI; stop any time with **Esc**.

## Install

Windows (PowerShell):
```powershell
cd autobot
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`requirements.txt` pulls in the Windows deps (pywin32, dxcam, OpenCV, numpy,
customtkinter).

> Capture (dxcam / PrintWindow) and background touch (`InjectTouchInput`) are
> **Win32-only**, so the bot runs on Windows. Some pure-geometry modules are
> cross-platform but the app as a whole targets Windows + LDPlayer.

## System permissions

Usually no setup. But if **LDPlayer runs as Administrator**, run Python as
Administrator too — otherwise injected touch won't reach it.

## Usage

1. Start your song in LDPlayer and leave the emulator **visible / uncovered**.
2. Run the GUI:
   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```
3. In the window:
   - **TARGET** — pick the play area (see below)
   - **Lanes** — number of columns (4 for Magic Tiles)
   - **Hit line** — % of board height where you tap
   - **Contrast** — how much darker a tile is than the lane background (relative,
     so it works on any skin: black, blue, etc.)
   - **LEAD (ms)** / **TRIG LEAD %** — timing knobs (see *Predictive timing*)
   - **◎ Preview lanes** — verify the auto-detected lane columns
   - **Start** / **Stop**

The lane columns are **auto-detected** from the board edges (a side margin won't
shift them); fall back to an even split if edges can't be found.

## Target — bind to the emulator window

Press **🔄 Refresh**, then pick the LDPlayer window from the dropdown. The bot
captures that **HWND directly** (works on the GPU surface LDPlayer renders to)
and the region becomes **window-local** (`0,0,width,height` = whole window).
Trim it to the play area by hand. If you move/resize the window, Refresh and
pick it again.

Capture uses **dxcam** (DXGI desktop duplication) — ~0.1ms/grab, the correct GPU
layer for LDPlayer, and the low latency is what lets the bot keep up as a song
speeds up. **PrintWindow** (~20ms, renders even when covered) is the automatic
fallback if dxcam is unavailable. **BitBlt grabs the wrong GPU layer for
LDPlayer and is never used.**

## Predictive timing

The bot doesn't wait for a tile to reach the hit line. It detects tiles across
the **whole board**, measures the **fall velocity**, and **schedules** each tap
for when the tile *will* arrive — so it stays on time even as the song speeds
up.

- **LEAD (ms)** — the fixed input + emulator latency offset. Raise it if taps
  land late, lower it if they fire too early.
- **TRIG LEAD %** — how far above the hit line tiles are sensed (the velocity
  head-start).
- **Auto-lead** — when on, the bot sweeps a set of LEAD values across attempts,
  measures how long each *survives*, and locks the best to
  `~/.autobot_lead_cal.json`. Just retry and it converges; delete that file to
  recalibrate.

A **long** tile is **held** until its tail clears the hit-line band (reactive
release), so multiple long notes / chords hold at once. A short tile is a quick
**tap**.

## Background touch

Input is **background multi-touch** via Win32 `InjectTouchInput` — one finger
per lane injected straight at the lane points. So:

- multiple long tiles / chords **hold at once**
- **no focus needed** (play while you work in another window)
- the **real cursor never moves** (a low-level mouse hook swallows the synthetic
  mouse events Windows would otherwise generate)

The game must stay **visible / uncovered** — touch lands on whatever window is
topmost at each lane point. No LDPlayer key-mapping required.

Limitations:
- apps that read raw HID input or have anti-cheat may **ignore** synthetic events
- the target must be a normal, visible window under each lane point

## Emergency stop

Press **Esc** (works even while fingers are held) or the **Stop** button. The
real mouse never moves, so pyautogui's corner FAILSAFE does not apply.

## Develop

```bash
make install   # create .venv + install requirements.txt
make run        # launch GUI  (== .venv/Scripts/python main.py)
make test       # smoke test  (python -m tests.smoke)
make clean      # remove .venv + __pycache__
```

The Makefile recipes use Unix shell utils, so on Windows run `make` from **Git
Bash / WSL**. Direct invocation works in PowerShell too:

```powershell
.\.venv\Scripts\python.exe main.py            # run GUI
.\.venv\Scripts\python.exe -m tests.smoke      # smoke test
.\.venv\Scripts\python.exe -m tests.predict_replay   # offline timing gate
```

Tests that need real captures (`templates/*.png`, `*.mp4`) **skip themselves**
when the asset is missing, so a clean checkout still passes.

## Structure

```
main.py                — entry
src/gui.py             — customtkinter App (config form, lane preview, countdown)
src/bot.py             — BotEngine + BotConfig; the tiles loop (_run_tiles) + auto-lead tuner
src/predict.py         — predictive detection core (tile mask, segments, velocity, scheduling)
src/window_capture.py  — WindowCapture (dxcam / PrintWindow, window-bound HWND grab)
src/touch.py           — TouchInjector (InjectTouchInput) + cursor-guard mouse hook
src/capture.py         — ScreenCapture (mss) for eyedropper / scale
src/window_picker.py   — list_windows() + focus_window() (Win32)
src/detector.py        — match_template() for the START / unlock helper buttons
src/clicker.py         — legacy (imported by the smoke test only)
```

See `CLAUDE.md` for the full architecture notes and the non-obvious gotchas.
