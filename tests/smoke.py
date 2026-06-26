"""Smoke test: detector + capture + scale + clicker backend selection.

Run: python -m tests.smoke   (or `make test`)
No real clicks are performed.
"""

from __future__ import annotations

import numpy as np

from src import detector, clicker
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


def main() -> None:
    for name, fn in [
        ("template/color", test_template_match),
        ("capture/region", test_capture_and_scale),
        ("clicker/scale", test_clicker_scale),
    ]:
        print(f"[{name}]")
        fn()
    print("ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
