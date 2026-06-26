"""Screen capture via mss. Returns BGR numpy arrays ready for OpenCV."""

from __future__ import annotations

import numpy as np
import mss


class ScreenCapture:
    """Wraps a single mss instance for fast repeated grabs.

    Note: mss is not thread-safe. Create one ScreenCapture per thread
    (the bot loop creates its own).
    """

    def __init__(self) -> None:
        self._sct = mss.mss()

    @property
    def primary_monitor(self) -> dict:
        # monitors[0] is the virtual "all monitors" box; [1] is the primary.
        return self._sct.monitors[1]

    def grab(self, region: dict | None = None) -> np.ndarray:
        """Grab a region and return a BGR image.

        region: {"top", "left", "width", "height"} in physical pixels,
                or None for the full primary monitor.
        """
        mon = region if region else self.primary_monitor
        shot = self._sct.grab(mon)
        # mss returns BGRA; drop alpha and keep BGR for OpenCV.
        frame = np.asarray(shot)[:, :, :3]
        return np.ascontiguousarray(frame)

    def close(self) -> None:
        self._sct.close()

    def __enter__(self) -> "ScreenCapture":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
