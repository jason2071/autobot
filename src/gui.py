"""Modern GUI built with customtkinter (rounded, dark, themed)."""

from __future__ import annotations

import os
import time
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
import numpy as np
import pyautogui

from .bot import BotConfig, BotEngine
from .capture import ScreenCapture
from . import window_picker

# --- palette ------------------------------------------------------------------
BG = "#15171e"
CARD = "#1f222b"
FIELD = "#2a2e39"
TEXT = "#e8eaf0"
MUTED = "#7e8294"
ACCENT = "#4f8cff"
ACCENT_HOVER = "#3f78e6"
GREEN = "#27c08a"
GREEN_HOVER = "#1fa476"
RED = "#ef5350"
RED_HOVER = "#d33f3c"
AMBER = "#f2b84b"

ctk.set_appearance_mode("dark")


class App:
    def __init__(self) -> None:
        self.root = ctk.CTk()
        self.root.title("autobot")
        self.root.configure(fg_color=BG)
        self.root.resizable(False, False)

        self.template_paths: list[str] = []
        self.bot: BotEngine | None = None
        self._pending_id: str | None = None  # scheduled start-delay countdown
        self.target_hwnd: int | None = None  # set when a window is the target
        self.tiles_note_bgr: tuple[int, int, int] | None = None  # slide/note color
        self.windows: list[window_picker.Window] = []
        self.color_bgr: tuple[int, int, int] | None = None
        self.pixel_point: tuple[int, int] | None = None  # physical px
        self.pixel_bgr: tuple[int, int, int] | None = None

        cap = ScreenCapture()
        phys_w = cap.primary_monitor["width"]
        cap.close()
        self.ratio = phys_w / pyautogui.size().width  # logical -> physical

        self._fonts()
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- fonts -------------------------------------------------------------
    def _fonts(self) -> None:
        self.f_title = ctk.CTkFont("SF Pro Display", 22, "bold")
        self.f_sub = ctk.CTkFont("SF Pro Text", 12)
        self.f_label = ctk.CTkFont("SF Pro Text", 13)
        self.f_value = ctk.CTkFont("SF Mono", 13, "bold")
        self.f_btn = ctk.CTkFont("SF Pro Text", 15, "bold")
        self.f_section = ctk.CTkFont("SF Pro Text", 11, "bold")

    # --- small builders ----------------------------------------------------
    def _label(self, master, text, **kw):
        kw.setdefault("font", self.f_label)
        kw.setdefault("text_color", TEXT)
        return ctk.CTkLabel(master, text=text, **kw)

    def _muted(self, master, text):
        return ctk.CTkLabel(master, text=text, font=self.f_sub, text_color=MUTED)

    def _row(self, parent) -> ctk.CTkFrame:
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(fill="x", pady=7)
        f.columnconfigure(0, weight=1)
        return f

    # --- layout ------------------------------------------------------------
    def _build(self) -> None:
        outer = ctk.CTkFrame(self.root, fg_color="transparent")
        outer.pack(padx=22, pady=20, fill="both")

        # header
        head = ctk.CTkFrame(outer, fg_color="transparent")
        head.pack(fill="x")
        ctk.CTkLabel(head, text="🎯", font=ctk.CTkFont(size=26)).pack(side="left")
        htext = ctk.CTkFrame(head, fg_color="transparent")
        htext.pack(side="left", padx=(10, 0))
        ctk.CTkLabel(htext, text="autobot", font=self.f_title, text_color=TEXT).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            htext, text="template / color auto-clicker",
            font=self.f_sub, text_color=MUTED,
        ).pack(anchor="w")

        card = ctk.CTkFrame(outer, fg_color=CARD, corner_radius=16)
        card.pack(fill="x", pady=(16, 0))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=16)

        # detection mode
        ctk.CTkLabel(inner, text="DETECTION", font=self.f_section,
                     text_color=MUTED).pack(anchor="w")
        self.det_mode = tk.StringVar(value="template")
        ctk.CTkSegmentedButton(
            inner, values=["template", "color", "pixel", "tiles"],
            variable=self.det_mode,
            command=self._switch_panel, font=self.f_label, height=36, corner_radius=10,
            fg_color=FIELD, selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=FIELD, unselected_hover_color="#343846",
        ).pack(fill="x", pady=(6, 10))

        # swappable detection panels (host keeps the position fixed)
        host = ctk.CTkFrame(inner, fg_color="transparent")
        host.pack(fill="x", pady=(0, 4))
        self.panels: dict[str, ctk.CTkFrame] = {}
        self._build_template_panel(host)
        self._build_color_panel(host)
        self._build_pixel_panel(host)
        self._build_tiles_panel(host)
        self._switch_panel("template")

        # interval + click mode (two columns)
        grid = ctk.CTkFrame(inner, fg_color="transparent")
        grid.pack(fill="x", pady=(0, 6))
        grid.columnconfigure((0, 1), weight=1, uniform="g")

        col_i = ctk.CTkFrame(grid, fg_color="transparent")
        col_i.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkLabel(col_i, text="INTERVAL (ms)", font=self.f_section,
                     text_color=MUTED).pack(anchor="w")
        self.interval_ms = tk.StringVar(value="500")
        ctk.CTkEntry(
            col_i, textvariable=self.interval_ms, font=self.f_label,
            fg_color=FIELD, border_width=0, corner_radius=10, height=36,
            justify="center",
        ).pack(fill="x", pady=(6, 0))

        col_m = ctk.CTkFrame(grid, fg_color="transparent")
        col_m.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ctk.CTkLabel(col_m, text="CLICK MODE", font=self.f_section,
                     text_color=MUTED).pack(anchor="w")
        self.click_mode = tk.StringVar(value="first")
        ctk.CTkSegmentedButton(
            col_m, values=["first", "all"], variable=self.click_mode,
            font=self.f_label, height=36, corner_radius=10,
            fg_color=FIELD, selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=FIELD, unselected_hover_color="#343846",
        ).pack(fill="x", pady=(6, 0))

        # start delay (countdown after pressing Start, to switch to the game)
        ctk.CTkLabel(inner, text="START DELAY (s)", font=self.f_section,
                     text_color=MUTED).pack(anchor="w", pady=(10, 0))
        self.start_delay = tk.StringVar(value="3")
        ctk.CTkEntry(
            inner, textvariable=self.start_delay, font=self.f_label,
            fg_color=FIELD, border_width=0, corner_radius=10, height=36,
            justify="center",
        ).pack(fill="x", pady=(6, 0))

        # target
        ctk.CTkLabel(inner, text="TARGET", font=self.f_section,
                     text_color=MUTED).pack(anchor="w", pady=(12, 0))
        self.window_choice = tk.StringVar(value="Full screen")
        self.window_menu = ctk.CTkOptionMenu(
            inner, variable=self.window_choice, values=["Full screen"],
            font=self.f_label, fg_color=FIELD, button_color=FIELD,
            button_hover_color="#343846", corner_radius=10, height=36,
            command=self._on_window_pick,
        )
        self.window_menu.pack(fill="x", pady=(6, 6))

        tbtns = ctk.CTkFrame(inner, fg_color="transparent")
        tbtns.pack(fill="x")
        tbtns.columnconfigure((0, 1), weight=1, uniform="t")
        ctk.CTkButton(
            tbtns, text="🔄  Refresh", font=self.f_sub, fg_color=FIELD,
            hover_color="#343846", text_color=TEXT, corner_radius=10, height=32,
            command=self._refresh_windows,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            tbtns, text="◰  Drag area", font=self.f_sub, fg_color=FIELD,
            hover_color="#343846", text_color=TEXT, corner_radius=10, height=32,
            command=self._drag_region,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.region = tk.StringVar(value="")
        ctk.CTkEntry(
            inner, textvariable=self.region, font=self.f_value,
            placeholder_text="top, left, width, height  —  empty = full screen",
            fg_color=FIELD, border_width=0, corner_radius=10, height=36,
            justify="center",
        ).pack(fill="x", pady=(8, 4))
        self._refresh_windows()

        # background switch
        sw_row = ctk.CTkFrame(inner, fg_color="transparent")
        sw_row.pack(fill="x", pady=(12, 0))
        sw_row.columnconfigure(0, weight=1)
        ctk.CTkLabel(sw_row, text="Background click", font=self.f_label,
                     text_color=TEXT).grid(row=0, column=0, sticky="w")
        self._muted(sw_row, "don't move the real cursor").grid(row=1, column=0, sticky="w")
        self.background = tk.BooleanVar(value=True)
        ctk.CTkSwitch(
            sw_row, text="", variable=self.background, onvalue=True, offvalue=False,
            progress_color=GREEN, button_color="#ffffff", fg_color=FIELD, width=48,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        # start/stop
        self.toggle_btn = ctk.CTkButton(
            outer, text="▶   Start", font=self.f_btn, fg_color=GREEN,
            hover_color=GREEN_HOVER, text_color="#ffffff", corner_radius=12,
            height=52, command=self._toggle,
        )
        self.toggle_btn.pack(fill="x", pady=(16, 0))

        # status
        status = ctk.CTkFrame(outer, fg_color="transparent")
        status.pack(fill="x", pady=(12, 0))
        self.dot = ctk.CTkLabel(status, text="●", font=ctk.CTkFont(size=13),
                                text_color=MUTED, width=14)
        self.dot.pack(side="left")
        self.status = tk.StringVar(value="Ready")
        ctk.CTkLabel(status, textvariable=self.status, font=self.f_sub,
                     text_color=MUTED).pack(side="left", padx=(4, 0))

    # --- detection panels --------------------------------------------------
    def _build_template_panel(self, host) -> None:
        p = ctk.CTkFrame(host, fg_color="transparent")
        self.panels["template"] = p
        ctk.CTkButton(
            p, text="＋  Choose template files", font=self.f_label,
            fg_color=FIELD, hover_color="#343846", text_color=TEXT,
            corner_radius=10, height=38, anchor="w", command=self._pick_templates,
        ).pack(fill="x", pady=(0, 4))
        self.templates_label = self._muted(p, "No template selected")
        self.templates_label.pack(anchor="w", pady=(0, 6))

        thr_head = ctk.CTkFrame(p, fg_color="transparent")
        thr_head.pack(fill="x", pady=(4, 0))
        thr_head.columnconfigure(0, weight=1)
        ctk.CTkLabel(thr_head, text="THRESHOLD", font=self.f_section,
                     text_color=MUTED).grid(row=0, column=0, sticky="w")
        self.threshold = tk.DoubleVar(value=0.8)
        self.thr_label = ctk.CTkLabel(thr_head, text="0.80", font=self.f_value,
                                      text_color=ACCENT)
        self.thr_label.grid(row=0, column=1, sticky="e")
        ctk.CTkSlider(
            p, from_=0.5, to=1.0, number_of_steps=50, variable=self.threshold,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            progress_color=ACCENT, fg_color=FIELD, height=16,
            command=lambda v: self.thr_label.configure(text=f"{v:.2f}"),
        ).pack(fill="x", pady=(2, 0))

    def _build_color_panel(self, host) -> None:
        p = ctk.CTkFrame(host, fg_color="transparent")
        self.panels["color"] = p
        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(fill="x", pady=(0, 6))
        row.columnconfigure(0, weight=1)
        ctk.CTkButton(
            row, text="🎨  Pick color", font=self.f_label, fg_color=FIELD,
            hover_color="#343846", text_color=TEXT, corner_radius=10, height=38,
            command=self._pick_color,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.color_swatch = ctk.CTkFrame(row, width=38, height=38, corner_radius=8,
                                         fg_color=FIELD)
        self.color_swatch.grid(row=0, column=1)
        self.color_swatch.grid_propagate(False)
        self.color_label = self._muted(p, "No color picked")
        self.color_label.pack(anchor="w", pady=(0, 6))

        head = ctk.CTkFrame(p, fg_color="transparent")
        head.pack(fill="x")
        head.columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="TOLERANCE (hue°)", font=self.f_section,
                     text_color=MUTED).grid(row=0, column=0, sticky="w")
        self.color_tol = tk.IntVar(value=25)
        self.color_tol_label = ctk.CTkLabel(head, text="25", font=self.f_value,
                                            text_color=ACCENT)
        self.color_tol_label.grid(row=0, column=1, sticky="e")
        ctk.CTkSlider(
            p, from_=5, to=60, number_of_steps=55, variable=self.color_tol,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            progress_color=ACCENT, fg_color=FIELD, height=16,
            command=lambda v: self.color_tol_label.configure(text=f"{int(v)}"),
        ).pack(fill="x", pady=(2, 0))

    def _build_pixel_panel(self, host) -> None:
        p = ctk.CTkFrame(host, fg_color="transparent")
        self.panels["pixel"] = p
        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(fill="x", pady=(0, 6))
        row.columnconfigure(0, weight=1)
        ctk.CTkButton(
            row, text="🎯  Pick pixel", font=self.f_label, fg_color=FIELD,
            hover_color="#343846", text_color=TEXT, corner_radius=10, height=38,
            command=self._pick_pixel,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.pixel_swatch = ctk.CTkFrame(row, width=38, height=38, corner_radius=8,
                                         fg_color=FIELD)
        self.pixel_swatch.grid(row=0, column=1)
        self.pixel_swatch.grid_propagate(False)
        self.pixel_label = self._muted(p, "No pixel picked")
        self.pixel_label.pack(anchor="w", pady=(0, 6))

        head = ctk.CTkFrame(p, fg_color="transparent")
        head.pack(fill="x")
        head.columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="TOLERANCE (±/channel)", font=self.f_section,
                     text_color=MUTED).grid(row=0, column=0, sticky="w")
        self.pixel_tol = tk.IntVar(value=20)
        self.pixel_tol_label = ctk.CTkLabel(head, text="20", font=self.f_value,
                                            text_color=ACCENT)
        self.pixel_tol_label.grid(row=0, column=1, sticky="e")
        ctk.CTkSlider(
            p, from_=0, to=60, number_of_steps=60, variable=self.pixel_tol,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            progress_color=ACCENT, fg_color=FIELD, height=16,
            command=lambda v: self.pixel_tol_label.configure(text=f"{int(v)}"),
        ).pack(fill="x", pady=(2, 0))

    def _build_tiles_panel(self, host) -> None:
        p = ctk.CTkFrame(host, fg_color="transparent")
        self.panels["tiles"] = p

        self._muted(
            p, "Magic Tiles 3 — set TARGET to the play area (4 lanes).\n"
               "Foreground only: keeps the real cursor for tap & hold.",
        ).pack(anchor="w", pady=(0, 8))

        # lanes
        lane_row = ctk.CTkFrame(p, fg_color="transparent")
        lane_row.pack(fill="x", pady=(0, 6))
        lane_row.columnconfigure(0, weight=1)
        ctk.CTkLabel(lane_row, text="LANES", font=self.f_section,
                     text_color=MUTED).grid(row=0, column=0, sticky="w")
        self.tiles_lanes = tk.IntVar(value=4)
        self.tiles_lanes_label = ctk.CTkLabel(lane_row, text="4", font=self.f_value,
                                              text_color=ACCENT)
        self.tiles_lanes_label.grid(row=0, column=1, sticky="e")
        ctk.CTkSlider(
            p, from_=1, to=8, number_of_steps=7, variable=self.tiles_lanes,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            progress_color=ACCENT, fg_color=FIELD, height=16,
            command=lambda v: self.tiles_lanes_label.configure(text=f"{int(v)}"),
        ).pack(fill="x", pady=(2, 8))

        # hit line position
        hit_row = ctk.CTkFrame(p, fg_color="transparent")
        hit_row.pack(fill="x", pady=(0, 6))
        hit_row.columnconfigure(0, weight=1)
        ctk.CTkLabel(hit_row, text="HIT LINE (% of height)", font=self.f_section,
                     text_color=MUTED).grid(row=0, column=0, sticky="w")
        self.tiles_hit = tk.IntVar(value=80)
        self.tiles_hit_label = ctk.CTkLabel(hit_row, text="80", font=self.f_value,
                                            text_color=ACCENT)
        self.tiles_hit_label.grid(row=0, column=1, sticky="e")
        ctk.CTkSlider(
            p, from_=50, to=98, number_of_steps=48, variable=self.tiles_hit,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            progress_color=ACCENT, fg_color=FIELD, height=16,
            command=lambda v: self.tiles_hit_label.configure(text=f"{int(v)}"),
        ).pack(fill="x", pady=(2, 8))

        # contrast margin (tile darkness vs lane background)
        dk_row = ctk.CTkFrame(p, fg_color="transparent")
        dk_row.pack(fill="x", pady=(0, 6))
        dk_row.columnconfigure(0, weight=1)
        ctk.CTkLabel(dk_row, text="CONTRAST (vs background)", font=self.f_section,
                     text_color=MUTED).grid(row=0, column=0, sticky="w")
        self.tiles_margin = tk.IntVar(value=40)
        self.tiles_margin_label = ctk.CTkLabel(dk_row, text="40", font=self.f_value,
                                               text_color=ACCENT)
        self.tiles_margin_label.grid(row=0, column=1, sticky="e")
        ctk.CTkSlider(
            p, from_=15, to=120, number_of_steps=105, variable=self.tiles_margin,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            progress_color=ACCENT, fg_color=FIELD, height=16,
            command=lambda v: self.tiles_margin_label.configure(text=f"{int(v)}"),
        ).pack(fill="x", pady=(2, 8))

        # opt-in hold extension (helps long notes with a light trail; 0 = off)
        he_row = ctk.CTkFrame(p, fg_color="transparent")
        he_row.pack(fill="x", pady=(0, 6))
        he_row.columnconfigure(0, weight=1)
        ctk.CTkLabel(he_row, text="HOLD EXTRA (long notes)", font=self.f_section,
                     text_color=MUTED).grid(row=0, column=0, sticky="w")
        self.tiles_hold_extra = tk.IntVar(value=0)
        self.tiles_hold_extra_label = ctk.CTkLabel(he_row, text="0", font=self.f_value,
                                                   text_color=ACCENT)
        self.tiles_hold_extra_label.grid(row=0, column=1, sticky="e")
        ctk.CTkSlider(
            p, from_=0, to=40, number_of_steps=40, variable=self.tiles_hold_extra,
            button_color=ACCENT, button_hover_color=ACCENT_HOVER,
            progress_color=ACCENT, fg_color=FIELD, height=16,
            command=lambda v: self.tiles_hold_extra_label.configure(text=f"{int(v)}"),
        ).pack(fill="x", pady=(2, 8))

        # optional note/slide colour: detect bright/coloured notes & slides
        nc_row = ctk.CTkFrame(p, fg_color="transparent")
        nc_row.pack(fill="x", pady=(0, 8))
        nc_row.columnconfigure(0, weight=1)
        ctk.CTkButton(
            nc_row, text="🎨  Pick slide / note color", font=self.f_sub,
            fg_color=FIELD, hover_color="#343846", text_color=TEXT,
            corner_radius=10, height=32, command=self._pick_note_color,
        ).grid(row=0, column=0, sticky="ew")
        self.tiles_note_swatch = ctk.CTkLabel(nc_row, text="", width=32, height=32,
                                              corner_radius=8, fg_color=FIELD)
        self.tiles_note_swatch.grid(row=0, column=1, padx=(8, 0))
        ctk.CTkButton(
            nc_row, text="✕", font=self.f_sub, fg_color=FIELD,
            hover_color="#343846", text_color=MUTED, corner_radius=8,
            width=32, height=32, command=self._clear_note_color,
        ).grid(row=0, column=2, padx=(6, 0))
        self.tiles_note_label = self._muted(
            p, "optional: for bright notes / diagonal slides (off = dark tiles only)")
        self.tiles_note_label.pack(anchor="w", pady=(0, 8))

        # input backend: mouse (single finger) or keyboard (per-lane keys)
        ctk.CTkLabel(p, text="INPUT", font=self.f_section,
                     text_color=MUTED).pack(anchor="w", pady=(2, 0))
        self.tiles_input = tk.StringVar(value="mouse")
        ctk.CTkSegmentedButton(
            p, values=["mouse", "keyboard"], variable=self.tiles_input,
            command=self._on_tiles_input, font=self.f_label, height=34,
            corner_radius=10, fg_color=FIELD, selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER, unselected_color=FIELD,
            unselected_hover_color="#343846",
        ).pack(fill="x", pady=(6, 6))

        # keyboard-only controls live in a frame so visibility toggles in place
        self.tiles_kb_frame = ctk.CTkFrame(p, fg_color="transparent")
        self.tiles_keys = tk.StringVar(value="d, f, j, k")
        ctk.CTkEntry(
            self.tiles_kb_frame, textvariable=self.tiles_keys, font=self.f_label,
            fg_color=FIELD, border_width=0, corner_radius=10, height=34,
            justify="center", placeholder_text="lane keys, e.g. d, f, j, k",
        ).pack(fill="x")
        self._muted(
            self.tiles_kb_frame,
            "map these keys to the lanes in LDPlayer.\n"
            "holds multiple keys -> 2+ long tiles at once.",
        ).pack(anchor="w", pady=(4, 0))
        self.tiles_start_key = tk.StringVar(value="f")
        ctk.CTkEntry(
            self.tiles_kb_frame, textvariable=self.tiles_start_key, font=self.f_label,
            fg_color=FIELD, border_width=0, corner_radius=10, height=34,
            justify="center", placeholder_text="start key (map to START)",
        ).pack(fill="x", pady=(6, 0))
        self._muted(
            self.tiles_kb_frame,
            "key to start a song (map to START in LDPlayer).\n"
            "keeps the mouse off the game. empty = click instead.",
        ).pack(anchor="w", pady=(4, 0))

        # default = reliable PrintWindow (overlap-proof). Toggle ON for faster
        # BitBlt capture (only if the game stays uncovered on top).
        ovl = ctk.CTkFrame(p, fg_color="transparent")
        ovl.pack(fill="x", pady=(8, 0))
        ovl.columnconfigure(0, weight=1)
        ctk.CTkLabel(ovl, text="Fast capture", font=self.f_sub,
                     text_color=TEXT).grid(row=0, column=0, sticky="w")
        self._muted(ovl, "on = fast/low-latency (keep game uncovered on top)").grid(
            row=1, column=0, sticky="w")
        self.tiles_fast = tk.BooleanVar(value=True)  # default fast (needed to keep up)
        ctk.CTkSwitch(
            ovl, text="", variable=self.tiles_fast, onvalue=True, offvalue=False,
            progress_color=GREEN, button_color="#ffffff", fg_color=FIELD, width=48,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        self._tiles_preview_btn = ctk.CTkButton(
            p, text="◎  Preview lanes / hit line", font=self.f_sub,
            fg_color=FIELD, hover_color="#343846", text_color=TEXT,
            corner_radius=10, height=32, command=self._preview_tiles,
        )
        self._tiles_preview_btn.pack(fill="x", pady=(8, 0))
        # kb frame sits between the segmented button and the preview button
        self._on_tiles_input("mouse")

    def _pick_note_color(self) -> None:
        res = self._eyedropper()
        if not res:
            return
        _x, _y, bgr = res
        self.tiles_note_bgr = bgr
        self.tiles_note_swatch.configure(fg_color=self._bgr_hex(bgr))
        self.tiles_note_label.configure(
            text=f"✓ slide/note color {self._bgr_hex(bgr)}  (✕ to clear)")

    def _clear_note_color(self) -> None:
        self.tiles_note_bgr = None
        self.tiles_note_swatch.configure(fg_color=FIELD)
        self.tiles_note_label.configure(
            text="optional: for bright notes / diagonal slides (off = dark tiles only)")

    def _on_tiles_input(self, choice: str) -> None:
        """Show the key field only for the keyboard backend."""
        if choice == "keyboard":
            self.tiles_kb_frame.pack(fill="x", pady=(0, 4),
                                     before=self._tiles_preview_btn)
        else:
            self.tiles_kb_frame.pack_forget()

    def _preview_tiles(self) -> None:
        """Capture the target region and overlay the lane points + hit line so
        the user can verify calibration before starting."""
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            self._set_status("preview needs Pillow")
            return
        region = self._parse_region()
        if region is None:
            self._set_status("set the TARGET region first")
            return
        if self.target_hwnd is not None:  # capture the window directly
            from .window_capture import WindowCapture
            method = "bitblt" if self.tiles_fast.get() else "printwindow"
            if method == "bitblt":  # BitBlt reads on-screen pixels -> raise it
                self._focus_target()
                time.sleep(0.15)  # let it come to front before grabbing
            cap = WindowCapture(self.target_hwnd, method)
        else:
            cap = ScreenCapture()
        frame = cap.grab(region)
        cap.close()
        h, w = frame.shape[:2]
        img = Image.fromarray(np.ascontiguousarray(frame[:, :, ::-1]))  # BGR->RGB
        d = ImageDraw.Draw(img)
        lanes = max(1, self.tiles_lanes.get())
        hit_y = int(h * self.tiles_hit.get() / 100)
        # same auto lane detection the bot uses, so the preview is truthful
        from .bot import tiles_lane_geometry, tiles_board_edges
        centers, bands = tiles_lane_geometry(frame, lanes)
        edges = tiles_board_edges(frame)
        if edges:  # mark detected board edges
            for ex in edges:
                d.line([(ex, 0), (ex, h)], fill=(0, 255, 120), width=1)
        d.line([(0, hit_y), (w, hit_y)], fill=(255, 60, 60), width=3)
        for cx, (x0, x1) in zip(centers, bands):
            cx = int(cx)
            d.rectangle([x0, hit_y - 6, x1, hit_y + 6], outline=(60, 200, 255), width=2)
            d.ellipse([cx - 5, hit_y - 5, cx + 5, hit_y + 5], fill=(60, 200, 255))

        win = tk.Toplevel(self.root)
        win.title("Tiles preview")
        win.attributes("-topmost", True)
        # fit to a sane on-screen size
        maxw, maxh = 360, 640
        scale = min(maxw / w, maxh / h, 1.0)
        disp = img.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                          Image.NEAREST)
        tkimg = ImageTk.PhotoImage(disp)
        lbl = tk.Label(win, image=tkimg, bd=0)
        lbl.image = tkimg  # keep ref
        lbl.pack()

    def _switch_panel(self, mode: str) -> None:
        for name, panel in self.panels.items():
            if name == mode:
                panel.pack(fill="x")
            else:
                panel.pack_forget()

    @staticmethod
    def _bgr_hex(bgr: tuple[int, int, int]) -> str:
        b, g, r = (int(c) for c in bgr)
        return f"#{r:02x}{g:02x}{b:02x}"

    # --- eyedropper --------------------------------------------------------
    def _make_loupe(self, ov, frame, to_px) -> dict | None:
        """Borderless magnifier that follows the cursor over the overlay.

        Renders a zoomed crop of `frame` (the real, un-dimmed screen) around
        the pointer, with a crosshair on the center pixel and a hex/coord
        readout. `to_px(e)` maps a Tk event to (px, py) in the captured frame.
        Returns a dict with the loupe window + an `update` motion handler, or
        None if Pillow is unavailable (loupe is optional).
        """
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            return None

        h, w = frame.shape[:2]
        Z = 11           # zoom factor (screen px -> loupe px)
        HALF = 8         # crop half-size; crop is (2*HALF+1) px square
        side = 2 * HALF + 1
        size = side * Z
        rgb = np.ascontiguousarray(frame[:, :, ::-1])  # BGR -> RGB
        sw, sh = ov.winfo_screenwidth(), ov.winfo_screenheight()

        win = tk.Toplevel(ov)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-disabled", True)  # Windows: never take focus
        except tk.TclError:
            pass
        img_lbl = tk.Label(win, bd=0, highlightthickness=0, bg="black")
        img_lbl.pack()
        txt_lbl = tk.Label(win, bg="black", fg="white",
                           font=("SF Mono", 11), anchor="center")
        txt_lbl.pack(fill="x")

        def update(e) -> None:
            cx, cy = to_px(e)
            x0, y0 = cx - HALF, cy - HALF
            crop = rgb[max(y0, 0):min(y0 + side, h),
                       max(x0, 0):min(x0 + side, w)]
            tile = Image.new("RGB", (side, side), (0, 0, 0))
            tile.paste(Image.fromarray(crop), (max(0, -x0), max(0, -y0)))
            big = tile.resize((size, size), Image.NEAREST)
            d = ImageDraw.Draw(big)
            c = HALF * Z
            d.rectangle([c, c, c + Z - 1, c + Z - 1], outline=(255, 0, 0), width=2)
            tkimg = ImageTk.PhotoImage(big)
            img_lbl.configure(image=tkimg)
            img_lbl.image = tkimg  # keep ref
            b, g, r = (int(v) for v in frame[cy, cx])
            txt_lbl.configure(text=f"#{r:02x}{g:02x}{b:02x}  ({cx},{cy})")
            # place near cursor, flip away from screen edges
            sx = e.x_root + 24 if e.x_root + 24 + size <= sw else e.x_root - 24 - size
            sy = e.y_root + 24 if e.y_root + 24 + size + 24 <= sh else e.y_root - 24 - size - 24
            win.geometry(f"+{int(sx)}+{int(sy)}")

        return {"win": win, "update": update}

    def _eyedropper(self) -> tuple | None:
        """Single click samples a screen pixel — across ALL monitors.

        The whole virtual desktop is captured BEFORE the overlay is shown,
        then the color is read from that frame — so the dimmed overlay can
        never contaminate the sample (and there is no capture/repaint race).

        Returns (x_physical, y_physical, (b, g, r)) or None if cancelled.
        The physical coords are relative to the virtual-desktop origin.
        """
        # 1) capture the full virtual desktop first
        cap = ScreenCapture()
        vmon = cap.virtual_monitor
        frame = cap.grab(vmon)
        cap.close()
        h, w = frame.shape[:2]
        rr = self.ratio
        vleft, vtop = vmon["left"], vmon["top"]  # physical origin (may be < 0)

        # Map a Tk event (root coords, logical px) to a pixel in `frame`.
        def to_px(e) -> tuple[int, int]:
            px = min(max(int(e.x_root * rr - vleft), 0), w - 1)
            py = min(max(int(e.y_root * rr - vtop), 0), h - 1)
            return px, py

        # 2) one borderless overlay spanning every monitor (logical geometry).
        picked: dict = {}
        ov = tk.Toplevel(self.root)
        ov.overrideredirect(True)
        ov.geometry(
            f"{int(w / rr)}x{int(h / rr)}+{int(vleft / rr)}+{int(vtop / rr)}"
        )
        try:
            ov.attributes("-alpha", 0.12)  # light tint, real screen stays visible
        except tk.TclError:
            pass
        ov.configure(bg="black", cursor="crosshair")
        ov.attributes("-topmost", True)
        canvas = tk.Canvas(ov, bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        canvas.create_text(
            int(w / rr) // 2, 40,
            text="Click to sample a pixel  •  Esc / right-click to cancel",
            fill="white", font=("SF Pro Text", 16),
        )

        # 2b) live magnifier loupe drawn from the pre-captured (un-dimmed) frame.
        loupe = self._make_loupe(ov, frame, to_px)

        def _close() -> None:
            if loupe is not None:
                loupe["win"].destroy()
            ov.destroy()

        canvas.bind("<ButtonPress-1>",
                    lambda e: (picked.update(p=to_px(e)), _close()))
        if loupe is not None:
            canvas.bind("<Motion>", loupe["update"])
        # bind Escape on every widget in the overlay so a cancel works no
        # matter which one holds focus (the loupe can steal it on map).
        for wdg in (ov, canvas):
            wdg.bind("<Escape>", lambda _e: _close())
        ov.bind("<Button-3>", lambda _e: _close())  # right-click also cancels
        ov.grab_set()
        ov.focus_force()  # reclaim keyboard focus so Escape reaches the overlay
        self.root.wait_window(ov)

        if "p" not in picked:
            return None
        # 3) read color from the frame (frame-relative index), but return the
        #    coords in ABSOLUTE mss space (frame origin + virtual origin) so
        #    pixel mode can grab that exact point later.
        px, py = picked["p"]
        b, g, r = (int(c) for c in frame[py, px])
        return px + vleft, py + vtop, (b, g, r)

    def _pick_color(self) -> None:
        res = self._eyedropper()
        if not res:
            return
        _x, _y, bgr = res
        self.color_bgr = bgr
        hx = self._bgr_hex(bgr)
        self.color_swatch.configure(fg_color=hx)
        self.color_label.configure(text=f"✓ {hx}", text_color=GREEN)

    def _pick_pixel(self) -> None:
        res = self._eyedropper()
        if not res:
            return
        px, py, bgr = res
        self.pixel_point = (px, py)
        self.pixel_bgr = bgr
        hx = self._bgr_hex(bgr)
        self.pixel_swatch.configure(fg_color=hx)
        self.pixel_label.configure(text=f"✓ ({px},{py})  {hx}", text_color=GREEN)

    # --- target / region ---------------------------------------------------
    def _refresh_windows(self) -> None:
        self.windows = window_picker.list_windows()
        titles = [w.title for w in self.windows]
        self.window_menu.configure(values=["Full screen"] + titles)
        if self.window_choice.get() not in titles:
            self.window_choice.set("Full screen")

    def _set_region_logical(self, b: dict) -> None:
        rr = self.ratio
        self.region.set(
            f"{int(b['top']*rr)},{int(b['left']*rr)},"
            f"{int(b['width']*rr)},{int(b['height']*rr)}"
        )

    def _on_window_pick(self, choice: str | None = None) -> None:
        choice = choice or self.window_choice.get()
        if choice == "Full screen":
            self.target_hwnd = None
            self.region.set("")
            return
        win = next((w for w in self.windows if w.title == choice), None)
        if not win:
            return
        if win.hwnd is not None:
            # bind to the window: capture it directly. region is window-local;
            # auto-trim typical emulator chrome (title bar, side toolbar, bottom
            # thumbnails) to the play board so lanes land right out of the box.
            self.target_hwnd = win.hwnd
            b = win.bounds
            top = round(b["height"] * 0.023)
            left = round(b["width"] * 0.0125)
            width = round(b["width"] * 0.935)
            height = round(b["height"] * 0.89)
            self.region.set(f"{top}, {left}, {width}, {height}")
        else:
            self.target_hwnd = None
            self._set_region_logical(win.bounds)

    def _drag_region(self) -> None:
        result: dict = {}
        ov = tk.Toplevel(self.root)
        ov.attributes("-fullscreen", True)
        try:
            ov.attributes("-alpha", 0.25)
        except tk.TclError:
            pass
        ov.configure(bg="black", cursor="crosshair")
        ov.attributes("-topmost", True)
        canvas = tk.Canvas(ov, bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        canvas.create_text(
            ov.winfo_screenwidth() // 2, 40,
            text="Drag to select an area  •  Esc to cancel",
            fill="white", font=("SF Pro Text", 16),
        )
        s = {"x": 0, "y": 0, "rect": None}

        def press(e):
            s["x"], s["y"] = e.x, e.y
            s["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y,
                                                outline=GREEN, width=2)

        def drag(e):
            if s["rect"]:
                canvas.coords(s["rect"], s["x"], s["y"], e.x, e.y)

        def release(e):
            left, top = min(s["x"], e.x), min(s["y"], e.y)
            w, h = abs(e.x - s["x"]), abs(e.y - s["y"])
            if w > 5 and h > 5:
                result.update(top=top, left=left, width=w, height=h)
            ov.destroy()

        canvas.bind("<ButtonPress-1>", press)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", release)
        ov.bind("<Escape>", lambda _e: ov.destroy())
        ov.grab_set()
        self.root.wait_window(ov)

        if result:
            self.target_hwnd = None  # drag selects a screen region, not a window
            self.window_choice.set("Full screen")
            self._set_region_logical(result)

    # --- actions -----------------------------------------------------------
    def _pick_templates(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Choose template images",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")],
        )
        if paths:
            self.template_paths = list(paths)
            names = ", ".join(p.split("/")[-1] for p in self.template_paths)
            self.templates_label.configure(text=f"✓ {names}", text_color=GREEN)

    def _parse_region(self) -> dict | None:
        text = self.region.get().strip()
        if not text:
            return None
        parts = [p.strip() for p in text.replace(" ", ",").split(",") if p.strip()]
        if len(parts) != 4:
            raise ValueError("region needs 4 values: top,left,width,height")
        top, left, w, h = (int(p) for p in parts)
        return {"top": top, "left": left, "width": w, "height": h}

    def _build_config(self) -> BotConfig:
        try:
            interval = max(int(self.interval_ms.get()), 50) / 1000.0
        except ValueError:
            interval = 0.5
        mode = self.det_mode.get()
        # tiles needs the real cursor (hold) -> always foreground
        background = False if mode == "tiles" else self.background.get()
        return BotConfig(
            mode=mode,
            template_paths=self.template_paths if mode == "template" else [],
            threshold=round(self.threshold.get(), 2),
            interval=interval,
            region=self._parse_region(),
            click_mode=self.click_mode.get(),
            background=background,
            color_target=self.color_bgr if mode == "color" else None,
            color_tolerance=self.color_tol.get(),
            pixel_point=self.pixel_point if mode == "pixel" else None,
            pixel_color=self.pixel_bgr if mode == "pixel" else None,
            pixel_tolerance=self.pixel_tol.get(),
            tiles_lanes=self.tiles_lanes.get(),
            tiles_hit=self.tiles_hit.get() / 100.0,
            tiles_margin=self.tiles_margin.get(),
            tiles_input=self.tiles_input.get(),
            tiles_keys=self._parse_keys(),
            tiles_start_key=self.tiles_start_key.get().strip().lower(),
            tiles_hold_extra=self.tiles_hold_extra.get(),
            tiles_note_color=self.tiles_note_bgr if mode == "tiles" else None,
            tiles_helpers=self._helper_templates() if mode == "tiles" else [],
            target_hwnd=self.target_hwnd if mode == "tiles" else None,
            window_method="bitblt" if self.tiles_fast.get() else "printwindow",
        )

    def _parse_keys(self) -> list[str]:
        """Parse the lane-keys field into single-char key names."""
        raw = self.tiles_keys.get().replace(",", " ").split()
        keys = [k.strip().lower() for k in raw if k.strip()]
        return keys or ["d", "f", "j", "k"]

    @staticmethod
    def _helper_templates() -> list[str]:
        """Screens auto-handled between songs (match full window): the unlock
        popup is escaped to a playable song, START begins it. Order matters —
        unlock is checked before START."""
        return [p for p in ("templates/unlock.png", "templates/start.png")
                if os.path.isfile(p)]

    def _focus_target(self) -> None:
        """Bring the selected target window to the foreground before starting."""
        choice = self.window_choice.get()
        if choice and choice != "Full screen":
            window_picker.focus_window(choice)

    def _validate(self, cfg: BotConfig) -> str | None:
        if cfg.mode == "template" and not cfg.template_paths:
            return "no template selected"
        if cfg.mode == "color" and cfg.color_target is None:
            return "no color picked"
        if cfg.mode == "pixel" and (cfg.pixel_point is None or cfg.pixel_color is None):
            return "no pixel picked"
        if cfg.mode == "tiles" and cfg.region is None:
            return "set the game region (TARGET) first"
        if (cfg.mode == "tiles" and cfg.tiles_input == "keyboard"
                and len(cfg.tiles_keys) < cfg.tiles_lanes):
            return f"need {cfg.tiles_lanes} lane keys (got {len(cfg.tiles_keys)})"
        return None

    def _running(self) -> bool:
        return bool(self.bot and self.bot.running)

    def _toggle(self) -> None:
        if self._running():
            self._stop_bot()
            return
        if self._pending_id is not None:  # pressed during countdown -> cancel
            self._cancel_pending()
            self._set_status("Ready")
            return
        try:
            config = self._build_config()
        except ValueError as e:
            self._set_status(f"error: {e}")
            return
        err = self._validate(config)
        if err:
            self._set_status(f"error: {err}")
            return

        try:
            delay = max(int(self.start_delay.get()), 0)
        except ValueError:
            delay = 0
        self._countdown(delay, config)

    def _cancel_pending(self) -> None:
        if self._pending_id is not None:
            self.root.after_cancel(self._pending_id)
            self._pending_id = None
        self.toggle_btn.configure(text="▶   Start", fg_color=GREEN,
                                  hover_color=GREEN_HOVER)

    def _countdown(self, secs: int, config: BotConfig) -> None:
        if secs > 0:
            self.toggle_btn.configure(text="✕   Cancel", fg_color=AMBER,
                                      hover_color=AMBER)
            self._set_status(f"starting in {secs}…")
            self._pending_id = self.root.after(
                1000, lambda: self._countdown(secs - 1, config)
            )
            return
        self._pending_id = None
        self._focus_target()  # raise the game window so clicks land on it
        self.bot = BotEngine(config, on_status=self._set_status)
        self.bot.start()
        self.toggle_btn.configure(text="■   Stop", fg_color=RED, hover_color=RED_HOVER)

    def _stop_bot(self) -> None:
        if self.bot:
            self.bot.stop()
        self.toggle_btn.configure(text="▶   Start", fg_color=GREEN,
                                  hover_color=GREEN_HOVER)

    def _dot_color(self, msg: str) -> str:
        m = msg.lower()
        if m.startswith("error") or "stopped:" in m:
            return RED
        if "clicked" in m or m == "running":
            return GREEN
        if "idle" in m:
            return AMBER
        return MUTED

    def _set_status(self, msg: str) -> None:
        def apply() -> None:
            self.status.set(msg)
            self.dot.configure(text_color=self._dot_color(msg))
            if msg in ("stopped", "Ready") or msg.startswith("error"):
                self.toggle_btn.configure(text="▶   Start", fg_color=GREEN,
                                          hover_color=GREEN_HOVER)

        self.root.after(0, apply)

    def _on_close(self) -> None:
        if self.bot:
            self.bot.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
