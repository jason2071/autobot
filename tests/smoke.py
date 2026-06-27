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
from tests.predict_replay import test_predict_replay


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
    # relative darkness: a blue tile (mean 90) among bright lanes is still a tile
    assert bot.tiles_dark_lanes([152, 90, 130, 158], 40) == [False, True, False, False]
    print("  relative darkness OK")


def test_predict_logic() -> None:
    from src import predict

    # segmentation: a synthetic board, lane 0 holds a tall dark tile (a long
    # note), lane 1 a short tile, lanes 2/3 empty. Header above y_lo is ignored.
    board = np.full((400, 400), 200, np.uint8)
    bands = [(10, 90), (110, 190), (210, 290), (310, 390)]
    board[:30, 10:90] = 20            # score-header strip (must be cropped out)
    board[120:300, 10:90] = 20        # lane0 long note
    board[140:170, 110:190] = 20      # lane1 short tile
    segs = predict.lane_segments(board, bands, margin=40, min_run=12,
                                  y_lo=40, y_hi=360, merge_gap=10)
    assert segs[0] == [(120, 299)], segs[0]          # header excluded, tile kept
    assert segs[1] == [(140, 169)], segs[1]
    assert segs[2] == [] and segs[3] == [], segs

    # leading edge = bottom of the lowest tile above the hit line
    assert predict.leading_bottoms(segs, hit_y=380) == [299.0, 169.0, None, None]

    # velocity: a tile moving 20px between frames at dt=0.02s -> 1000 px/s
    v = predict.update_velocity(0.0, [100.0, None, None, None],
                                [120.0, None, None, None], dt=0.02)
    assert abs(v - 1000.0) < 1e-6, v

    # occupancy at a trigger band: tile spanning the band counts
    occ = predict.occupancy_at(segs, 150, 160)
    assert occ == [True, True, False, False], occ

    # scheduling: a rising edge in lane 0 schedules a press; with v=1000 px/s and
    # 200px from trigger to hit, the press is 0.2s out (minus lead).
    evs = predict.schedule_edges([False] * 4, [True, False, False, False],
                                 v=1000.0, y_trig=200, hit_y=400, now=10.0,
                                 lead_s=0.05)
    assert len(evs) == 1 and evs[0].kind == "press" and evs[0].lane == 0
    assert abs(evs[0].t - (10.0 + 0.2 - 0.05)) < 1e-6, evs[0].t
    # a falling edge schedules a release; no edge -> nothing
    rel = predict.schedule_edges([True, False, False, False], [False] * 4,
                                 v=1000.0, y_trig=200, hit_y=400, now=11.0,
                                 lead_s=0.0)
    assert len(rel) == 1 and rel[0].kind == "release"
    # velocity unknown -> no scheduling (never fire blind)
    assert predict.schedule_edges([False] * 4, [True] * 4, None, 200, 400, 0, 0) == []
    print("  predict segments + velocity + edge scheduling OK")


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


def test_tiles_game_cases() -> None:
    """Real captures from other skins: long-note songs (game2/game3) and a
    diagonal-slide song (game1, unsupported). Skipped if the assets are absent
    (templates/*.png are gitignored)."""
    # long notes: the dark note body is detected in lanes 0 & 2
    for name in ("game2", "game3"):
        p = f"templates/{name}.png"
        if not os.path.isfile(p):
            print(f"  ({name} missing — skipped)")
            continue
        dark = _lane_darks(cv2.imread(p), hit=0.70)
        assert dark == [True, False, True, False], f"{name}: {dark}"
        print(f"  {name} long notes -> {[int(x) for x in dark]}")
    # diagonal slide: invisible to darkness, but the colour detector follows it
    if os.path.isfile("templates/game1.png"):
        img = cv2.imread("templates/game1.png")
        h = img.shape[0]
        _c, bands = bot.tiles_lane_geometry(img, 4)
        # darkness alone must NOT false-fire on this bright skin
        assert not any(_lane_darks(img, hit=0.70)), "game1 dark false-fire"
        # colour detector follows the slide across lanes (L2 high -> L3 low)
        note = tuple(int(v) for v in img[int(h * 0.45),
                     (bands[2][0] + bands[2][1]) // 2])
        top_hi = int(h * 0.45) - 9
        top_lo = int(h * 0.82) - 9
        hi = bot.tiles_color_lanes(img[top_hi:top_hi + 18], bands, note, 18)
        lo = bot.tiles_color_lanes(img[top_lo:top_lo + 18], bands, note, 18)
        assert hi[2] and not hi[3], f"slide top should be lane 2: {hi}"
        assert lo[3] and not lo[2], f"slide bottom should be lane 3: {lo}"
        print(f"  game1 slide via color -> top{[int(x) for x in hi]} "
              f"bottom{[int(x) for x in lo]}")
    else:
        print("  (game1 missing — skipped)")


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
        ("predict/logic", test_predict_logic),
        ("tiles/hysteresis", test_tiles_hysteresis),
        ("tiles/screenshots", test_tiles_on_screenshots),
        ("tiles/game-cases", test_tiles_game_cases),
        ("tiles/helpers", test_helper_templates),
        ("predict/replay", test_predict_replay),
    ]:
        print(f"[{name}]")
        fn()
    print("ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
