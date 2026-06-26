"""Tkinter GUI: Start/Stop, template picker, threshold, interval, region."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

from .bot import BotConfig, BotEngine


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("autobot — auto click")
        self.root.resizable(False, False)

        self.template_paths: list[str] = []
        self.bot: BotEngine | None = None

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- layout ------------------------------------------------------------
    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self.root, padding=12)
        frm.grid(row=0, column=0, sticky="nsew")

        # templates
        ttk.Button(frm, text="เลือก template…", command=self._pick_templates).grid(
            row=0, column=0, sticky="w", **pad
        )
        self.templates_label = ttk.Label(frm, text="(ยังไม่ได้เลือก)")
        self.templates_label.grid(row=0, column=1, columnspan=2, sticky="w", **pad)

        # threshold
        ttk.Label(frm, text="Threshold").grid(row=1, column=0, sticky="w", **pad)
        self.threshold = tk.DoubleVar(value=0.8)
        self.thr_label = ttk.Label(frm, text="0.80")
        ttk.Scale(
            frm, from_=0.5, to=1.0, variable=self.threshold,
            command=lambda v: self.thr_label.config(text=f"{float(v):.2f}"),
        ).grid(row=1, column=1, sticky="ew", **pad)
        self.thr_label.grid(row=1, column=2, sticky="w", **pad)

        # interval
        ttk.Label(frm, text="Interval (ms)").grid(row=2, column=0, sticky="w", **pad)
        self.interval_ms = tk.StringVar(value="500")
        ttk.Entry(frm, textvariable=self.interval_ms, width=8).grid(
            row=2, column=1, sticky="w", **pad
        )

        # click mode
        ttk.Label(frm, text="Click mode").grid(row=3, column=0, sticky="w", **pad)
        self.click_mode = tk.StringVar(value="first")
        ttk.Combobox(
            frm, textvariable=self.click_mode, values=["first", "all"],
            width=6, state="readonly",
        ).grid(row=3, column=1, sticky="w", **pad)

        # region
        ttk.Label(frm, text="Region (top,left,w,h)").grid(row=4, column=0, sticky="w", **pad)
        self.region = tk.StringVar(value="")
        ttk.Entry(frm, textvariable=self.region, width=20).grid(
            row=4, column=1, columnspan=2, sticky="w", **pad
        )
        ttk.Label(frm, text="ว่าง = ทั้งจอ", foreground="gray").grid(
            row=5, column=1, sticky="w", padx=8
        )

        # background click
        self.background = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frm, text="Background click (ไม่ขยับเมาส์)", variable=self.background,
        ).grid(row=6, column=0, columnspan=3, sticky="w", **pad)

        # start/stop
        self.toggle_btn = tk.Button(
            frm, text="Start", width=12, command=self._toggle,
            bg="#2e7d32", fg="white", activebackground="#1b5e20",
        )
        self.toggle_btn.grid(row=7, column=0, columnspan=3, pady=(12, 4))

        # status
        self.status = tk.StringVar(value="พร้อม")
        ttk.Label(frm, textvariable=self.status, foreground="#555").grid(
            row=8, column=0, columnspan=3, sticky="w", padx=8
        )

    # --- actions -----------------------------------------------------------
    def _pick_templates(self) -> None:
        paths = filedialog.askopenfilenames(
            title="เลือกรูป template",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")],
        )
        if paths:
            self.template_paths = list(paths)
            names = ", ".join(p.split("/")[-1] for p in self.template_paths)
            self.templates_label.config(text=names)

    def _parse_region(self) -> dict | None:
        text = self.region.get().strip()
        if not text:
            return None
        parts = [p.strip() for p in text.replace(" ", ",").split(",") if p.strip()]
        if len(parts) != 4:
            raise ValueError("region ต้องมี 4 ค่า: top,left,width,height")
        top, left, w, h = (int(p) for p in parts)
        return {"top": top, "left": left, "width": w, "height": h}

    def _build_config(self) -> BotConfig:
        try:
            interval = max(int(self.interval_ms.get()), 50) / 1000.0
        except ValueError:
            interval = 0.5
        return BotConfig(
            template_paths=self.template_paths,
            threshold=round(self.threshold.get(), 2),
            interval=interval,
            region=self._parse_region(),
            click_mode=self.click_mode.get(),
            background=self.background.get(),
        )

    def _toggle(self) -> None:
        if self.bot and self.bot.running:
            self._stop_bot()
            return
        try:
            config = self._build_config()
        except ValueError as e:
            self._set_status(f"error: {e}")
            return
        if not config.template_paths:
            self._set_status("error: ยังไม่ได้เลือก template")
            return

        self.bot = BotEngine(config, on_status=self._set_status)
        self.bot.start()
        self.toggle_btn.config(text="Stop", bg="#c62828", activebackground="#8e0000")

    def _stop_bot(self) -> None:
        if self.bot:
            self.bot.stop()
        self.toggle_btn.config(text="Start", bg="#2e7d32", activebackground="#1b5e20")

    def _set_status(self, msg: str) -> None:
        # called from bot thread; marshal to GUI thread
        self.root.after(0, self.status.set, msg)

    def _on_close(self) -> None:
        if self.bot:
            self.bot.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
