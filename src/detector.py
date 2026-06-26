"""Detection: template matching + color/pixel detection.

Both functions return matches as a list of (x, y, score) where (x, y) is the
center of the match in the *frame's* pixel coordinates (relative to the grabbed
region, not the whole screen). score is the match confidence in [0, 1].
"""

from __future__ import annotations

import cv2
import numpy as np

Match = tuple[int, int, float]


def load_template(path: str) -> np.ndarray:
    """Load a template image as BGR. Raises ValueError if unreadable."""
    tpl = cv2.imread(path, cv2.IMREAD_COLOR)
    if tpl is None:
        raise ValueError(f"cannot read template: {path}")
    return tpl


def _dedupe(points: list[Match], min_dist: int) -> list[Match]:
    """Greedy non-max suppression: keep highest score, drop near neighbors."""
    kept: list[Match] = []
    for x, y, score in sorted(points, key=lambda p: p[2], reverse=True):
        if all((x - kx) ** 2 + (y - ky) ** 2 >= min_dist ** 2 for kx, ky, _ in kept):
            kept.append((x, y, score))
    return kept


def match_template(
    frame: np.ndarray,
    template: np.ndarray,
    threshold: float = 0.8,
) -> list[Match]:
    """Find all occurrences of `template` in `frame` above `threshold`."""
    th, tw = template.shape[:2]
    if frame.shape[0] < th or frame.shape[1] < tw:
        return []

    res = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(res >= threshold)

    matches = [
        (int(x + tw / 2), int(y + th / 2), float(res[y, x]))
        for x, y in zip(xs, ys)
    ]
    # collapse clusters within roughly one template size
    return _dedupe(matches, min_dist=max(min(tw, th) // 2, 5))


def find_color(
    frame: np.ndarray,
    bgr_target: tuple[int, int, int],
    tolerance: int = 25,
    min_area: int = 20,
) -> list[Match]:
    """Find blobs matching `bgr_target` within `tolerance` (HSV hue degrees).

    Returns the centroid of each blob with area >= min_area. score is the
    fraction of the blob area relative to the largest blob found (rough
    confidence, always in (0, 1]).
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    target = np.uint8([[list(bgr_target)]])
    h, s, v = cv2.cvtColor(target, cv2.COLOR_BGR2HSV)[0][0]

    lower = np.array([max(int(h) - tolerance, 0), 60, 60])
    upper = np.array([min(int(h) + tolerance, 179), 255, 255])
    mask = cv2.inRange(hsv, lower, upper)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    blobs = [(c, cv2.contourArea(c)) for c in contours]
    blobs = [(c, a) for c, a in blobs if a >= min_area]
    if not blobs:
        return []

    max_area = max(a for _, a in blobs)
    matches: list[Match] = []
    for c, area in blobs:
        m = cv2.moments(c)
        if m["m00"] == 0:
            continue
        cx = int(m["m10"] / m["m00"])
        cy = int(m["m01"] / m["m00"])
        matches.append((cx, cy, float(area / max_area)))
    return matches


def check_pixel(
    frame: np.ndarray,
    x: int,
    y: int,
    bgr: tuple[int, int, int],
    tolerance: int = 20,
) -> bool:
    """True if the pixel at (x, y) matches `bgr` within per-channel `tolerance`.

    Used by pixel-watch mode (typically on a 1x1 grab, so x=y=0).
    """
    if y < 0 or x < 0 or y >= frame.shape[0] or x >= frame.shape[1]:
        return False
    px = frame[y, x]
    return all(abs(int(px[i]) - int(bgr[i])) <= tolerance for i in range(3))


# Manual smoke test: python -m src.detector <screenshot.png> <template.png>
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("usage: python -m src.detector <screenshot.png> <template.png>")
        sys.exit(1)

    frame = cv2.imread(sys.argv[1], cv2.IMREAD_COLOR)
    tpl = load_template(sys.argv[2])
    hits = match_template(frame, tpl, threshold=0.8)
    print(f"found {len(hits)} match(es):")
    for x, y, score in hits:
        print(f"  ({x}, {y})  score={score:.3f}")
