"""Tkinter GUI — dark, modern layout for the auto-click bot."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, font, ttk

import pyautogui

from .bot import BotConfig, BotEngine
from .capture import ScreenCapture
from . import window_picker

# --- palette ------------------------------------------------------------------
BG = "#181a20"        # window background
CARD = "#22252e"      # panel background
FIELD = "#2b2f3a"     # input background
TEXT = "#e6e8ee"      # primary text
MUTED = "#8b8f9c"     # secondary text
ACCENT = "#4f8cff"    # accent / sliders
GREEN = "#27c08a"     # start / ok
GREEN_HOVER = "#1fa476"
RED = "#ef5350"       # stop / error
RED_HOVER = "#d33f3c"
AMBER = "#f2b84b"     # idle / waiting


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("autobot")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        self.template_paths: list[str] = []
        self.bot: BotEngine | None = None
        self.windows: list[window_picker.Window] = []

        # ratio to convert logical screen points -> physical pixels (mss region)
        cap = ScreenCapture()
        phys_w = cap.primary_monitor["width"]
        cap.close()
        self.ratio = phys_w / pyautogui.size().width  # 1.0, or 2.0 on Retina

        self._setup_fonts()
        self._setup_style()
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- theme -------------------------------------------------------------
    def _setup_fonts(self) -> None:
        self.f_title = font.Font(family="SF Pro Display", size=18, weight="bold")
        self.f_sub = font.Font(family="SF Pro Text", size=10)
        self.f_label = font.Font(family="SF Pro Text", size=11)
        self.f_value = font.Font(family="SF Mono", size=10)
        self.f_btn = font.Font(family="SF Pro Text", size=13, weight="bold")

    def _setup_style(self) -> None:
        st = ttk.Style()
        st.theme_use("clam")

        st.configure("TFrame", background=CARD)
        st.configure("Bg.TFrame", background=BG)
        st.configure("TLabel", background=CARD, foreground=TEXT, font=self.f_label)
        st.configure("Card.TLabel", background=CARD, foreground=TEXT)
        st.configure("Muted.TLabel", background=CARD, foreground=MUTED, font=self.f_sub)
        st.configure("Value.TLabel", background=CARD, foreground=ACCENT, font=self.f_value)
        st.configure("Title.TLabel", background=BG, foreground=TEXT, font=self.f_title)
        st.configure("Sub.TLabel", background=BG, foreground=MUTED, font=self.f_sub)

        # secondary button (template picker)
        st.configure(
            "Soft.TButton", background=FIELD, foreground=TEXT, font=self.f_label,
            borderwidth=0, focuscolor=CARD, padding=(12, 7),
        )
        st.map("Soft.TButton", background=[("active", "#343846")])

        # entries
        st.configure(
            "Dark.TEntry", fieldbackground=FIELD, foreground=TEXT,
            insertcolor=TEXT, borderwidth=0, padding=6,
        )

        # combobox
        st.configure(
            "Dark.TCombobox", fieldbackground=FIELD, background=FIELD,
            foreground=TEXT, arrowcolor=TEXT, borderwidth=0, padding=5,
        )
        st.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", FIELD)],
            selectbackground=[("readonly", FIELD)],
            selectforeground=[("readonly", TEXT)],
        )

        # checkbutton
        st.configure(
            "Dark.TCheckbutton", background=CARD, foreground=TEXT,
            font=self.f_label, focuscolor=CARD,
        )
        st.map(
            "Dark.TCheckbutton",
            background=[("active", CARD)],
            indicatorcolor=[("selected", GREEN), ("!selected", FIELD)],
        )

        # scale
        st.configure(
            "Dark.Horizontal.TScale", background=CARD, troughcolor=FIELD,
            borderwidth=0, lightcolor=ACCENT, darkcolor=ACCENT,
        )

    # --- layout ------------------------------------------------------------
    def _card(self, parent: tk.Widget) -> ttk.Frame:
        c = ttk.Frame(parent, style="TFrame", padding=14)
        c.columnconfigure(1, weight=1)
        return c

    def _build(self) -> None:
        root = ttk.Frame(self.root, style="Bg.TFrame", padding=18)
        root.grid(row=0, column=0)

        # header
        ttk.Label(root, text="autobot", style="Title.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            root, text="template / color auto-clicker", style="Sub.TLabel"
        ).grid(row=1, column=0, sticky="w", pady=(0, 14))

        card = self._card(root)
        card.grid(row=2, column=0, sticky="ew")
        r = 0

        # templates
        ttk.Label(card, text="Templates", style="Card.TLabel").grid(
            row=r, column=0, sticky="w", pady=6
        )
        ttk.Button(
            card, text="เลือกไฟล์…", style="Soft.TButton",
            command=self._pick_templates,
        ).grid(row=r, column=1, sticky="e", pady=6)
        r += 1
        self.templates_label = ttk.Label(
            card, text="ยังไม่ได้เลือก", style="Muted.TLabel"
        )
        self.templates_label.grid(row=r, column=0, columnspan=2, sticky="w", pady=(0, 8))
        r += 1
        self._sep(card, r); r += 1

        # threshold
        ttk.Label(card, text="Threshold", style="Card.TLabel").grid(
            row=r, column=0, sticky="w", pady=8
        )
        self.threshold = tk.DoubleVar(value=0.8)
        self.thr_label = ttk.Label(card, text="0.80", style="Value.TLabel")
        self.thr_label.grid(row=r, column=1, sticky="e", pady=8)
        r += 1
        ttk.Scale(
            card, from_=0.5, to=1.0, variable=self.threshold,
            style="Dark.Horizontal.TScale",
            command=lambda v: self.thr_label.config(text=f"{float(v):.2f}"),
        ).grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        r += 1
        self._sep(card, r); r += 1

        # interval
        ttk.Label(card, text="Interval (ms)", style="Card.TLabel").grid(
            row=r, column=0, sticky="w", pady=8
        )
        self.interval_ms = tk.StringVar(value="500")
        ttk.Entry(
            card, textvariable=self.interval_ms, width=10,
            style="Dark.TEntry", justify="center",
        ).grid(row=r, column=1, sticky="e", pady=8)
        r += 1

        # click mode
        ttk.Label(card, text="Click mode", style="Card.TLabel").grid(
            row=r, column=0, sticky="w", pady=8
        )
        self.click_mode = tk.StringVar(value="first")
        ttk.Combobox(
            card, textvariable=self.click_mode, values=["first", "all"],
            width=8, state="readonly", style="Dark.TCombobox", justify="center",
        ).grid(row=r, column=1, sticky="e", pady=8)
        r += 1

        # target window
        ttk.Label(card, text="Target", style="Card.TLabel").grid(
            row=r, column=0, sticky="w", pady=8
        )
        self.window_choice = tk.StringVar(value="ทั้งจอ")
        self.window_box = ttk.Combobox(
            card, textvariable=self.window_choice, values=["ทั้งจอ"],
            width=22, state="readonly", style="Dark.TCombobox",
        )
        self.window_box.grid(row=r, column=1, sticky="e", pady=8)
        self.window_box.bind("<<ComboboxSelected>>", self._on_window_pick)
        r += 1
        btns = ttk.Frame(card, style="TFrame")
        btns.grid(row=r, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Button(
            btns, text="🔄 refresh", style="Soft.TButton",
            command=self._refresh_windows,
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            btns, text="◰ ตีกรอบพื้นที่", style="Soft.TButton",
            command=self._drag_region,
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))
        r += 1

        # region (resolved / manual)
        self.region = tk.StringVar(value="")
        ttk.Entry(
            card, textvariable=self.region, width=22,
            style="Dark.TEntry", justify="center",
        ).grid(row=r, column=0, columnspan=2, sticky="ew", pady=(2, 2))
        r += 1
        ttk.Label(
            card, text="top,left,width,height (px) — ว่าง = ทั้งจอ", style="Muted.TLabel"
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(0, 6))
        r += 1
        self._refresh_windows()
        self._sep(card, r); r += 1

        # background click
        self.background = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            card, text="Background click — ไม่ขยับเมาส์",
            variable=self.background, style="Dark.TCheckbutton",
        ).grid(row=r, column=0, columnspan=2, sticky="w", pady=8)
        r += 1

        # start/stop button
        self.toggle_btn = tk.Button(
            root, text="▶  Start", command=self._toggle,
            font=self.f_btn, bg=GREEN, fg="white",
            activebackground=GREEN_HOVER, activeforeground="white",
            relief="flat", bd=0, cursor="hand2", height=2,
        )
        self.toggle_btn.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        self.toggle_btn.bind("<Enter>", lambda _e: self._hover(True))
        self.toggle_btn.bind("<Leave>", lambda _e: self._hover(False))

        # status bar
        status_row = ttk.Frame(root, style="Bg.TFrame")
        status_row.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self.dot = tk.Label(status_row, text="●", bg=BG, fg=MUTED, font=("", 12))
        self.dot.grid(row=0, column=0, padx=(0, 6))
        self.status = tk.StringVar(value="พร้อม")
        tk.Label(
            status_row, textvariable=self.status, bg=BG, fg=MUTED,
            font=self.f_sub, anchor="w",
        ).grid(row=0, column=1, sticky="w")

    def _sep(self, parent: tk.Widget, row: int) -> None:
        tk.Frame(parent, height=1, bg="#30343f").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=2
        )

    # --- visual helpers ----------------------------------------------------
    def _running(self) -> bool:
        return bool(self.bot and self.bot.running)

    def _hover(self, on: bool) -> None:
        if self._running():
            self.toggle_btn.config(bg=RED_HOVER if on else RED)
        else:
            self.toggle_btn.config(bg=GREEN_HOVER if on else GREEN)

    def _dot_color(self, msg: str) -> str:
        m = msg.lower()
        if m.startswith("error") or "stopped:" in m:
            return RED
        if "clicked" in m or m == "running":
            return GREEN
        if "idle" in m:
            return AMBER
        return MUTED

    # --- target window / region -------------------------------------------
    def _refresh_windows(self) -> None:
        self.windows = window_picker.list_windows()
        titles = [w.title for w in self.windows]
        self.window_box.config(values=["ทั้งจอ"] + titles)
        if self.window_choice.get() not in titles:
            self.window_choice.set("ทั้งจอ")

    def _set_region_logical(self, b: dict) -> None:
        """Write a region (logical points) into the entry as physical pixels."""
        rr = self.ratio
        self.region.set(
            f"{int(b['top']*rr)},{int(b['left']*rr)},"
            f"{int(b['width']*rr)},{int(b['height']*rr)}"
        )

    def _on_window_pick(self, _e=None) -> None:
        choice = self.window_choice.get()
        if choice == "ทั้งจอ":
            self.region.set("")
            return
        win = next((w for w in self.windows if w.title == choice), None)
        if win:
            self._set_region_logical(win.bounds)

    def _drag_region(self) -> None:
        """Fullscreen overlay; drag a rectangle to set the region."""
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
            text="ลากเพื่อเลือกพื้นที่  •  Esc ยกเลิก",
            fill="white", font=self.f_label,
        )
        s = {"x": 0, "y": 0, "rect": None}

        def press(e):
            s["x"], s["y"] = e.x, e.y
            s["rect"] = canvas.create_rectangle(
                e.x, e.y, e.x, e.y, outline=GREEN, width=2
            )

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
            self.window_choice.set("ทั้งจอ")
            self._set_region_logical(result)

    # --- actions -----------------------------------------------------------
    def _pick_templates(self) -> None:
        paths = filedialog.askopenfilenames(
            title="เลือกรูป template",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")],
        )
        if paths:
            self.template_paths = list(paths)
            names = ", ".join(p.split("/")[-1] for p in self.template_paths)
            self.templates_label.config(text=f"✓ {names}", foreground=GREEN)

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
        if self._running():
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
        self.toggle_btn.config(text="■  Stop", bg=RED, activebackground=RED_HOVER)

    def _stop_bot(self) -> None:
        if self.bot:
            self.bot.stop()
        self.toggle_btn.config(text="▶  Start", bg=GREEN, activebackground=GREEN_HOVER)

    def _set_status(self, msg: str) -> None:
        # called from bot thread; marshal to GUI thread
        def apply() -> None:
            self.status.set(msg)
            self.dot.config(fg=self._dot_color(msg))
            if msg in ("stopped", "พร้อม") or msg.startswith("error"):
                self.toggle_btn.config(
                    text="▶  Start", bg=GREEN, activebackground=GREEN_HOVER
                )

        self.root.after(0, apply)

    def _on_close(self) -> None:
        if self.bot:
            self.bot.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
