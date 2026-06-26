"""BotEngine: capture -> detect -> click loop running on a background thread."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .capture import ScreenCapture
from .clicker import Clicker
from . import detector


@dataclass
class BotConfig:
    template_paths: list[str] = field(default_factory=list)
    threshold: float = 0.8
    interval: float = 0.5  # seconds between scans
    region: dict | None = None  # {"top","left","width","height"} physical px, or None
    click_mode: str = "first"  # "first" or "all"
    # optional color mode
    color_target: tuple[int, int, int] | None = None  # BGR
    color_tolerance: int = 25
    min_click_interval: float = 0.3
    jitter: int = 0
    background: bool = False  # click without moving the real cursor (macOS)


StatusCallback = Callable[[str], None]


class BotEngine:
    def __init__(self, config: BotConfig, on_status: StatusCallback | None = None) -> None:
        self.config = config
        self.on_status = on_status or (lambda _msg: None)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # --- core loop ---------------------------------------------------------
    def _run(self) -> None:
        cfg = self.config
        try:
            templates = [detector.load_template(p) for p in cfg.template_paths]
        except ValueError as e:
            self.on_status(f"error: {e}")
            return

        if not templates and cfg.color_target is None:
            self.on_status("error: no templates or color target set")
            return

        # mss must be created inside this thread.
        cap = ScreenCapture()
        mon = cfg.region if cfg.region else cap.primary_monitor
        offset = (mon["left"], mon["top"])
        try:
            clicker = Clicker(
                capture_width=cap.primary_monitor["width"],
                min_interval=cfg.min_click_interval,
                jitter=cfg.jitter,
                background=cfg.background,
            )
        except RuntimeError as e:
            self.on_status(f"error: {e}")
            cap.close()
            return
        self.on_status("running")

        try:
            while not self._stop.is_set():
                frame = cap.grab(cfg.region)
                matches = self._detect(frame, templates)

                if matches:
                    targets = matches if cfg.click_mode == "all" else matches[:1]
                    clicked = 0
                    for x, y, _score in targets:
                        if clicker.click_at(x, y, region_offset=offset):
                            clicked += 1
                    self.on_status(f"clicked {clicked} of {len(matches)} match(es)")
                else:
                    self.on_status("idle — no match")

                self._stop.wait(cfg.interval)
        except Exception as e:  # surface failsafe / runtime errors to GUI
            self.on_status(f"stopped: {e}")
        finally:
            cap.close()
            self.on_status("stopped")

    def _detect(self, frame, templates) -> list[detector.Match]:
        cfg = self.config
        matches: list[detector.Match] = []
        for tpl in templates:
            matches.extend(detector.match_template(frame, tpl, cfg.threshold))
        if cfg.color_target is not None:
            matches.extend(
                detector.find_color(frame, cfg.color_target, cfg.color_tolerance)
            )
        # highest score first
        matches.sort(key=lambda m: m[2], reverse=True)
        return matches
