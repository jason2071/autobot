# autobot

Auto-click bot that finds a target on screen via **template/image match**
(plus **color/pixel** detection) and clicks it automatically. Controlled with a
Start/Stop GUI. Supports **macOS + Windows**.

## Install

macOS / Linux:
```bash
cd autobot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):
```powershell
cd autobot
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`requirements.txt` installs OS-specific deps automatically (Quartz on macOS,
pywin32 on Windows).

## System permissions

**macOS** — System Settings → Privacy & Security:

1. **Screen Recording** — lets the terminal (or the app running Python) capture the screen
2. **Accessibility** — lets it send mouse clicks

Add **Terminal.app** / **iTerm** (or the IDE you run from) to both lists, then
restart the terminal.

**Windows** — usually no setup needed. But if the target app runs as
Administrator, run Python as Administrator too, otherwise clicks won't reach it.

## Usage

1. Capture the button/item to look for, save it as `.png` (crop tightly, little
   background) into `templates/`.
2. Run:
   ```bash
   python main.py
   ```
3. In the window:
   - **Detection** — `template` / `color` / `pixel` (see below)
   - **Interval (ms)** — delay between scans
   - **Click mode** — `first` clicks the first match / `all` clicks every match
   - **Target** — area to scan/click (see below)
   - **Background click** — on = click without moving the real cursor (see below)
   - **Start** / **Stop**

### Detection modes
- **template** — match a cropped image on screen (`Choose template files` +
  **Threshold** strictness). Best for icons/buttons with a fixed look.
- **color** — scan the region for a **colored blob** and click its center; the
  position can be anywhere. Press **🎨 Pick color** (eyedropper) to sample a
  color off the screen, then set **Tolerance** (hue degrees). Good for brightly
  colored items/buttons that appear at random positions.
- **pixel** — watch **one fixed point** and click when its color matches. Press
  **🎯 Pick pixel** (eyedropper — one click samples both the point and its
  color), set **Tolerance** (per-channel). Fastest/most precise. Good for a
  button that changes color when ready, a cooldown/health bar, etc.

| mode | knows position? | scans | best for |
|------|-----------------|-------|----------|
| template | no | whole region | fixed-look icons/buttons |
| color | no | whole region | bright items at random spots |
| pixel | yes (x,y) | one point | a point that changes color |

### Target — games that aren't fullscreen
You don't have to scan the whole screen. Three options:
- **Full screen** (default) — scan every pixel
- **Pick a window** — press **🔄 Refresh**, then pick the game/app window from
  the dropdown → the region is filled with that window's bounds automatically.
  If you move/resize the window, press Refresh and pick it again
- **◰ Drag area** — drag a rectangle on screen yourself (Esc cancels)

Both fill the **region** field (`top,left,width,height` in physical px), which
you can edit by hand. Empty = full screen. Retina coordinates are scaled
automatically.

### Background click
With **Background click** on, the bot posts the click directly to the window
under the target point **without moving your real cursor** — so you can keep
using the machine for something else.

- macOS: Quartz `CGEventPostToPid`
- Windows: Win32 `PostMessage` (WM_LBUTTONDOWN/UP) to the window under the point

Limitations:
- games/apps that read raw HID input or have anti-cheat may **ignore** synthetic events
- the target must be a normal, visible window under that point

With it off = foreground mode (pyautogui) moves the real cursor to click; works
with any app but takes over your mouse.

### Emergency stop
- foreground mode: drag the mouse to a screen corner (pyautogui FAILSAFE) or press **Stop**
- background mode: FAILSAFE doesn't apply (mouse never moves) — use the **Stop** button

## Retina note

Retina displays are captured in physical pixels (2x) but clicks use logical
points. The scale is computed automatically in `clicker.py`
(logical_width / physical_width). Region coordinates you enter are in
**physical px**.

## Makefile (mac/Linux, or Git Bash/WSL on Windows)

```bash
make install   # create venv + install deps
make run        # launch GUI
make test       # smoke test
make detect IMG=shot.png TPL=btn.png   # test template match
make clean      # remove venv + __pycache__
make help       # list all targets
```

## Test the detector (no real clicks)

```bash
python -m src.detector screenshot.png template.png
```
Prints the positions + scores found.

## Structure

```
src/capture.py       — ScreenCapture (mss)
src/detector.py      — match_template() + find_color() + check_pixel()
src/clicker.py       — Clicker (Retina scaling + rate limit + failsafe + background backend)
src/window_picker.py — list_windows() (macOS Quartz / Windows Win32)
src/bot.py           — BotEngine (template/color/pixel modes; loop on a thread, start/stop)
src/gui.py           — customtkinter App (eyedropper for color/pixel)
main.py              — entry
```

## Limitations / TODO
- no multi-monitor switching yet
- OCR not supported
