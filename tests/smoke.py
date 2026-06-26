"""Smoke test: detector + capture + scale + clicker backend selection.

Run: python -m tests.smoke   (or `make test`)
No real clicks are performed.
"""

from __future__ import annotations

import glob
import os

import cv2
import numpy as np

from src import detector, clicker, bot
from src.capture import ScreenCapture


def test_template_match() -> None:
    rng = np.random.default_rng(0)
    scene = rng.integers(0, 80, (300, 400, 3), dtype=np.uint8)
    patch = rng.integers(150, 255, (30, 60, 3), dtype=np.uint8)
    scene[40:70, 60:120] = patch  # button at center (90, 55)
    scene[100:140, 200:240] = (0, 0, 255)  # red blob

    hits = detector.match_template(scene, patch.copy(), threshold=0.95)
    assert len(hits) == 1, f"expected 1 hit, got {len(hits)}"
    x, y, _ = hits[0]
    assert abs(x - 90) < 5 and abs(y - 55) < 5, f"wrong center {x},{y}"
    print(f"  template match OK -> ({x}, {y})")

    red = detector.find_color(scene, (0, 0, 255), tolerance=20)
    assert red and abs(red[0][0] - 220) < 6 and abs(red[0][1] - 120) < 6
    print(f"  color detect OK   -> {red[0][:2]}")

    # pixel check: the red blob center is (0,0,255); a bg pixel is not
    assert detector.check_pixel(scene, 220, 120, (0, 0, 255), tolerance=10)
    assert not detector.check_pixel(scene, 5, 5, (0, 0, 255), tolerance=10)
    assert not detector.check_pixel(scene, 9999, 9999, (0, 0, 255))  # out of bounds
    print("  pixel check OK")


def test_capture_and_scale() -> None:
    cap = ScreenCapture()
    mon = cap.primary_monitor
    frame = cap.grab()
    assert frame.shape[2] == 3
    assert frame.shape[0] == mon["height"] and frame.shape[1] == mon["width"]

    region = {"top": 0, "left": 0, "width": 200, "height": 150}
    f = cap.grab(region)
    assert f.shape[:2] == (150, 200), f.shape
    cap.close()
    print(f"  capture OK -> {mon['width']}x{mon['height']}, region {f.shape[:2]}")


def test_clicker_scale() -> None:
    cap = ScreenCapture()
    c = clicker.Clicker(capture_width=cap.primary_monitor["width"])
    cap.close()
    assert c.scale > 0
    print(
        f"  clicker scale={c.scale:.3f}  background_supported="
        f"{clicker.BACKGROUND_SUPPORTED}"
    )


def _lane_darks(img, lanes=4, hit=0.80, sample_h=18, lead=12, margin=40):
    """Replicate the bot's per-lane sampling for a frame, return dark flags.

    Mirrors the runtime path: a thin band `lead` px above the hit line, mean
    brightness per lane vs the lane median.
    """
    h = img.shape[0]
    _centers, bands = bot.tiles_lane_geometry(img, lanes)
    hy = int(h * hit)
    top = hy - lead - sample_h // 2
    strip = img[top: top + sample_h]
    means = [float(strip[:, x0:x1].mean()) for x0, x1 in bands]
    return bot.tiles_dark_lanes(means, margin)


def test_tiles_logic() -> None:
    # state machine: rising-edge press, falling-edge release, max-hold cap
    assert bot.tiles_rising([False, False], [False, True]) == [1], "rising edge"
    assert bot.tiles_rising([True, False], [True, False]) == [], "no new edge"
    assert bot.tiles_rising([True, True], [True, True]) == [], "primed dark"
    assert bot.tiles_rising([False, False, False, False],
                            [True, False, True, False]) == [0, 2], "chord"

    assert bot.tiles_should_release(0, [False], 0.0, 0.01, 1.5) is True, "falling"
    assert bot.tiles_should_release(0, [True], 0.0, 0.01, 1.5) is False, "still held"
    assert bot.tiles_should_release(0, [True], 0.0, 2.0, 1.5) is True, "max hold"
    assert bot.tiles_should_release(None, [True], 0.0, 9.0, 1.5) is False, "nothing held"

    # relative darkness: a blue tile (mean 90) among bright lanes is still a tile
    assert bot.tiles_dark_lanes([152, 90, 130, 158], 40) == [False, True, False, False]

    # dark-fraction detector: a band that is mostly dark (a tile) vs a bright
    # band (background) vs a mostly-bright band with a thin dark guide line.
    bg = np.full((20, 30), 200, np.uint8)
    tile = np.full((20, 30), 20, np.uint8)
    guide = bg.copy(); guide[:, 14:16] = 20  # thin dark line on a bright lane
    assert bot.tiles_dark_frac([tile, bg, bg, bg], 40) == [True, False, False, False]
    # the thin guide line must NOT read as a tile (robust hold past centre lines)
    assert bot.tiles_dark_frac([guide, bg, bg, bg], 40) == [False, False, False, False]
    print("  tiles state machine + relative darkness + dark-fraction OK")


def test_tiles_keyboard_multihold() -> None:
    # simulate two long tiles falling at once in lanes 0 and 2 (keyboard mode)
    down = [False] * 4
    since = [0.0] * 4
    prev = [False] * 4
    mh = 1.5

    # frame 1: lanes 0 and 2 go dark together -> press both, hold both
    dark = [True, False, True, False]
    acts = bot.tiles_kb_step(prev, dark, down, since, 0.0, mh)
    assert sorted(acts) == [("press", 0), ("press", 2)], acts
    assert down == [True, False, True, False], "both keys held at once"
    prev = dark

    # frame 2..N: still dark -> no new actions, stays held (the multi-hold)
    acts = bot.tiles_kb_step(prev, dark, down, since, 0.05, mh)
    assert acts == [], "no churn while both held"
    assert down == [True, False, True, False]
    prev = dark

    # lane 0 clears, lane 2 still long -> release only 0, keep holding 2
    dark = [False, False, True, False]
    acts = bot.tiles_kb_step(prev, dark, down, since, 0.10, mh)
    assert acts == [("release", 0)], acts
    assert down == [False, False, True, False]
    prev = dark

    # lane 2 clears -> release 2
    dark = [False, False, False, False]
    acts = bot.tiles_kb_step(prev, dark, down, since, 0.20, mh)
    assert acts == [("release", 2)], acts
    assert down == [False, False, False, False]

    # max-hold safety: a stuck-dark lane is force-released
    down = [True, False, False, False]
    since = [0.0, 0, 0, 0]
    acts = bot.tiles_kb_step([True, False, False, False], [True, False, False, False],
                             down, since, 2.0, mh)
    assert acts == [("release", 0)], acts
    print("  keyboard multi-hold (2 long tiles at once) OK")


def test_tiles_hysteresis() -> None:
    # a long tile with a 2-frame bright flicker must NOT release (release_frames=3)
    streak = [3]
    assert bot.tiles_hysteresis([True], streak, 3) == [True]   # dark
    assert bot.tiles_hysteresis([False], streak, 3) == [True]  # 1 light, still held
    assert bot.tiles_hysteresis([False], streak, 3) == [True]  # 2 light, still held
    assert bot.tiles_hysteresis([True], streak, 3) == [True]   # dark again -> reset
    assert bot.tiles_hysteresis([False], streak, 3) == [True]
    assert bot.tiles_hysteresis([False], streak, 3) == [True]
    assert bot.tiles_hysteresis([False], streak, 3) == [False]  # 3 light -> release
    print("  release debounce (long-tile flicker) OK")


def test_tiles_on_screenshots() -> None:
    shots = sorted(glob.glob("templates/**/Screenshot*.png", recursive=True))
    if not shots:
        print("  (no Magic Tiles screenshots — skipped)")
        return
    for path in shots:
        img = cv2.imread(path)
        dark = _lane_darks(img)
        n = sum(dark)
        # each captured frame has at least one tile crossing the hit band
        assert 1 <= n <= 3, f"{os.path.basename(path)}: {n} dark lanes {dark}"
        print(f"  {os.path.basename(path)} -> dark lanes {dark}")


def test_helper_templates() -> None:
    helpers = [p for p in ("templates/retry.png", "templates/start.png")
               if os.path.isfile(p)]
    if not helpers:
        print("  (no retry/start templates — skipped)")
        return
    for path in helpers:
        tpl = detector.load_template(path)
        # embed the template in a larger black scene and confirm we find it
        th, tw = tpl.shape[:2]
        scene = np.zeros((th + 80, tw + 80, 3), dtype=np.uint8)
        scene[40:40 + th, 30:30 + tw] = tpl
        hits = detector.match_template(scene, tpl, threshold=0.9)
        assert hits, f"{os.path.basename(path)} not found in scene"
        x, y, score = hits[0]
        assert abs(x - (30 + tw // 2)) < 4 and abs(y - (40 + th // 2)) < 4
        print(f"  {os.path.basename(path)} match OK -> ({x},{y}) score={score:.3f}")


def main() -> None:
    for name, fn in [
        ("template/color", test_template_match),
        ("capture/region", test_capture_and_scale),
        ("clicker/scale", test_clicker_scale),
        ("tiles/logic", test_tiles_logic),
        ("tiles/kb-multihold", test_tiles_keyboard_multihold),
        ("tiles/hysteresis", test_tiles_hysteresis),
        ("tiles/screenshots", test_tiles_on_screenshots),
        ("tiles/helpers", test_helper_templates),
    ]:
        print(f"[{name}]")
        fn()
    print("ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
