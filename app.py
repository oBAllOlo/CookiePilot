"""
app.py — หน้าต่างควบคุมบอท (GUI, tkinter) — V2 Cockpit layout
==============================================================
2 คอลัมน์: ซ้าย = ควบคุม/ตั้งค่า | ขวา = สถิติสด + สถานะ V2 + กราฟเหรียญ + log
ของใหม่ V2: ไฟสถานะ ADB + ปุ่มกู้การเชื่อมต่อ, แถบพัก/ความล้า, กราฟเหรียญ 20 รอบ,
ปรับขนาด UI ได้ (จำค่าลง settings.json)

รัน:  python app.py   (หรือดับเบิลคลิก run_gui.bat)
"""
import os
import queue
import threading
import time
import tkinter as tk
from collections import deque
from tkinter import scrolledtext

import config
from adb import Adb
from bot import CookieBot

# ---------- โทนสี (slate dark) — อ้างที่เดียว แก้ธีมง่าย ----------
C_BG       = "#0f172a"   # พื้นหลังหลัก
C_BAR      = "#0b1220"   # แถบหัว
C_CARD     = "#1e293b"   # การ์ด
C_CARD_IN  = "#0f1a2e"   # chip ในการ์ด
C_FIELD    = "#0b0f19"   # ช่องกรอก/log
C_LINE     = "#334155"   # เส้นขอบ
C_TEXT     = "#f8fafc"   # ตัวอักษรหลัก
C_MUTED    = "#94a3b8"   # ตัวอักษรรอง
C_DIM      = "#64748b"   # ตัวอักษรจาง
C_GOLD     = "#fbbf24"
C_GREEN    = "#34d399"
C_RED      = "#f87171"
C_BLUE     = "#3b82f6"
C_BLUE_HV  = "#2563eb"


def bind_hover(btn, bg, hover_bg, fg="#ffffff", hover_fg="#ffffff"):
    """สลับสีปุ่มตอนเมาส์เข้า/ออก (เฉพาะตอน state=normal) — ใช้ร่วมกันทุกปุ่มในแอป"""
    btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg, fg=hover_fg) if btn["state"] == "normal" else None)
    btn.bind("<Leave>", lambda e: btn.config(bg=bg, fg=fg) if btn["state"] == "normal" else None)


class PillSelector:
    def __init__(self, parent, variable, options, command=None, font=("Segoe UI", 9, "bold")):
        self.variable = variable
        self.command = command

        self.frame = tk.Frame(parent, bg=C_BG, highlightthickness=1, highlightbackground=C_LINE)
        self.buttons = {}

        for text, val in options:
            btn = tk.Button(self.frame, text=text, font=font, bd=0, relief="flat",
                            cursor="hand2", command=lambda v=val: self.select(v))
            btn.pack(side="left", fill="both", expand=True, padx=2, pady=2)
            self.buttons[val] = btn

        self.update_ui()

    def select(self, value):
        if self.buttons[value]["state"] == "disabled":
            return
        self.variable.set(value)
        self.update_ui()
        if self.command:
            self.command()

    def update_ui(self):
        current_val = self.variable.get()
        for val, btn in self.buttons.items():
            if val == current_val:   # ปุ่มที่เลือกอยู่ = ไม่มี hover (bg == hover)
                btn.config(bg=C_BLUE, fg="#ffffff", activebackground=C_BLUE_HV, activeforeground="#ffffff")
                bind_hover(btn, C_BLUE, C_BLUE, "#ffffff", "#ffffff")
            else:
                btn.config(bg=C_CARD, fg=C_MUTED, activebackground=C_LINE, activeforeground=C_TEXT)
                bind_hover(btn, C_CARD, C_LINE, C_MUTED, C_TEXT)

    def set_state(self, state):
        for btn in self.buttons.values():
            btn.config(state=state)
            if state == "disabled":
                btn.config(bg=C_CARD, fg="#475569")
        if state == "normal":
            self.update_ui()


class App:
    def __init__(self, root):
        self.root = root
        self.log_queue = queue.Queue()

        self.stop_event = threading.Event()
        self.bot_thread = None
        self.running = False
        self.testing = False   # มี worker ทดสอบ/กู้การเชื่อมต่อค้างอยู่ไหม (กันสตาร์ตบอทซ้อน)
        self.closing = False
        self._max_loops = 0
        self._adb_state = "unknown"   # unknown / ok / bad — ไฟสถานะ ADB บนแถบหัว
        self._adb_checking = False
        self.break_until = None       # เวลาสิ้นสุดช่วงพักระหว่างเกม (None = ไม่ได้พัก)

        # log ของ ADB/บอท วิ่งเข้า queue (thread-safe) แล้ว pump ขึ้นจอที่ main thread
        self.adb = Adb(log=self._enqueue)

        # ตัวนับสถิติของ session ปัจจุบัน (ใช้คำนวณ uptime / เหรียญต่อชม. / เฉลี่ย / สูงสุด)
        self.session_start = None
        self._total_coins = 0
        self.coin_readable_count = 0
        self.coin_best = 0
        self.coin_history = deque(maxlen=20)   # เหรียญรายรอบ (None = อ่านไม่ได้) — วาดกราฟ

        # StringVar สร้างครั้งเดียวตรงนี้ (ไม่สร้างใน _build_ui) — ตอนเปลี่ยนขนาด UI
        # จะ rebuild widget ทั้งหมดโดยค่าที่โชว์อยู่ไม่หาย
        self.status_var       = tk.StringVar(value="● หยุดอยู่")
        self.adb_dot_var      = tk.StringVar(value="ADB ●")
        self.total_coins_var  = tk.StringVar(value="0")
        self.uptime_var       = tk.StringVar(value="00:00:00")
        self.loops_done_var   = tk.StringVar(value="-")
        self.rate_var         = tk.StringVar(value="-")
        self.recent_coins_var = tk.StringVar(value="-")
        self.avg_var          = tk.StringVar(value="-")
        self.best_var         = tk.StringVar(value="-")
        self.v2_state_var     = tk.StringVar(value="—")
        self.fatigue_var      = tk.StringVar(value="ความล้า -")
        saved_mode = str(config.BOT_MODE or "coin").strip().lower()
        self.mode_var  = tk.StringVar(value=saved_mode if saved_mode in ("coin", "box", "exp") else "coin")
        # ป้ายสถิติที่คำว่า "เหรียญ/EXP" เปลี่ยนตามโหมดที่เลือก (exp อ่านแถว XP หน้า Result)
        self.unit_total_var  = tk.StringVar()
        self.unit_rate_var   = tk.StringVar()
        self.unit_recent_var = tk.StringVar()
        self.unit_graph_var  = tk.StringVar()
        self._apply_mode_labels()
        self.adb_var   = tk.StringVar(value=self.adb.path)
        self.dev_var   = tk.StringVar(value=self.adb.device)
        self.loops_var = tk.StringVar(value="0")
        try:
            scale = float(config.UI_SCALE)
        except Exception:
            scale = 1.0
        self.scale_var = tk.StringVar(value=f"{scale:g}")

        self._build_ui()
        self._poll_log()
        self._tick_uptime()   # นาฬิกาเวลารัน + เหรียญ/ชม. + นับถอยหลังพัก (ทุก 1 วิ)
        self._tick_adb()      # เช็คไฟสถานะ ADB เป็นระยะ (เฉพาะตอนบอทไม่รัน)

        # แจ้งผลการโหลด settings.json (override ค่า / ไฟล์เสีย)
        if config.SETTINGS_ERROR:
            self._enqueue(f"[app] ⚠ {config.SETTINGS_ERROR}")
        elif config.SETTINGS_APPLIED:
            self._enqueue("[app] โหลด settings.json แล้ว (override: "
                          + ", ".join(config.SETTINGS_APPLIED) + ")")

    # ============================================================
    # UI
    # ============================================================
    def _F(self, size):
        """ขนาดฟอนต์ตามสเกล UI ที่เลือก"""
        try:
            s = float(self.scale_var.get())
        except Exception:
            s = 1.0
        return max(7, int(round(size * s)))

    def _build_ui(self):
        r = self.root
        F = self._F
        try:
            s = float(self.scale_var.get())
        except Exception:
            s = 1.0
        r.title(f"{config.APP_NAME} v{config.APP_VERSION}")
        r.geometry(f"{int(960 * s)}x{int(640 * s)}")
        r.minsize(int(860 * s), int(560 * s))
        r.configure(bg=C_BG)

        # ---------- ตัวช่วยจัดสไตล์ ----------
        def make_card(parent, **kwargs):
            return tk.Frame(parent, bg=C_CARD, highlightthickness=1,
                            highlightbackground=C_LINE, **kwargs)

        def make_btn(parent, text, command, bg=C_BLUE, fg="#ffffff",
                     hover_bg=C_BLUE_HV, hover_fg="#ffffff",
                     font=None, **kwargs):
            font = font or ("Segoe UI", F(9), "bold")
            btn = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                            activebackground=hover_bg, activeforeground=hover_fg,
                            disabledforeground=C_DIM, font=font, bd=0,
                            relief="flat", cursor="hand2", **kwargs)
            bind_hover(btn, bg, hover_bg, fg, hover_fg)
            return btn

        def make_entry(parent, textvariable, width, font=None, justify="left"):
            font = font or ("Consolas", F(10))
            border_frame = tk.Frame(parent, bg=C_LINE, highlightthickness=0)
            inner_frame = tk.Frame(border_frame, bg=C_FIELD, padx=6, pady=4)
            inner_frame.pack(fill="both", expand=True, padx=1, pady=1)
            entry = tk.Entry(inner_frame, textvariable=textvariable, width=width,
                             bg=C_FIELD, fg=C_TEXT, insertbackground=C_TEXT,
                             font=font, bd=0, relief="flat", justify=justify)
            entry.pack(fill="both", expand=True)
            def on_focus_in(e):
                if entry["state"] == "normal":
                    border_frame.config(bg=C_BLUE)
            def on_focus_out(e):
                if entry["state"] == "normal":
                    border_frame.config(bg=C_LINE)
            entry.bind("<FocusIn>", on_focus_in)
            entry.bind("<FocusOut>", on_focus_out)
            return border_frame, entry

        def side_label(parent, text, pady=(10, 4)):
            tk.Label(parent, text=text, bg=C_CARD, fg=C_MUTED,
                     font=("Segoe UI", F(9), "bold")).pack(anchor="w", padx=12, pady=pady)

        def make_stat(parent, col, caption, var, value_fg, framed):
            """ช่องสถิติ 1 ช่อง — framed=True มีกรอบ (chip หลัก) / False ไม่มีกรอบ (สถิติย่อย)
            caption เป็น str หรือ StringVar ก็ได้ (ป้ายเหรียญ/EXP เปลี่ยนตามโหมด)"""
            bg = C_CARD_IN if framed else C_CARD
            box = tk.Frame(parent, bg=bg, highlightthickness=1 if framed else 0,
                           highlightbackground=C_LINE)
            box.grid(row=0, column=col, sticky="nsew", padx=4)
            cap_kw = ({"textvariable": caption} if isinstance(caption, tk.StringVar)
                      else {"text": caption})
            tk.Label(box, font=("Segoe UI", F(8), "bold"),
                     bg=bg, fg=C_MUTED, **cap_kw).pack(pady=(7, 0) if framed else 0)
            tk.Label(box, textvariable=var, font=("Segoe UI", F(13) if framed else F(12), "bold"),
                     bg=bg, fg=value_fg).pack(pady=(1, 8) if framed else (2, 0))

        # ---------- 1) แถบหัว: ชื่อแอป | ไฟ ADB | ป้ายสถานะบอท ----------
        bar = tk.Frame(r, bg=C_BAR)
        bar.pack(fill="x")
        bar_in = tk.Frame(bar, bg=C_BAR)
        bar_in.pack(fill="x", padx=18, pady=10)

        tk.Label(bar_in, text="🍪 CookiePilot", font=("Segoe UI", F(15), "bold"),
                 bg=C_BAR, fg=C_GOLD).pack(side="left")
        tk.Label(bar_in, text=f"v{config.APP_VERSION}", font=("Segoe UI", F(9)),
                 bg=C_BAR, fg=C_DIM).pack(side="left", padx=(6, 0))

        self.status_pill = tk.Frame(bar_in, bg="#3f1d1d")
        self.status_pill.pack(side="right")
        self.status_lbl = tk.Label(self.status_pill, textvariable=self.status_var,
                                   font=("Segoe UI", F(9), "bold"), bg="#3f1d1d",
                                   fg=C_RED, padx=12, pady=4)
        self.status_lbl.pack()

        self.adb_dot_lbl = tk.Label(bar_in, textvariable=self.adb_dot_var,
                                    font=("Segoe UI", F(9), "bold"), bg=C_BAR, fg=C_DIM)
        self.adb_dot_lbl.pack(side="right", padx=(0, 12))
        tk.Frame(r, bg=C_LINE, height=1).pack(fill="x")

        # ---------- โครง 2 คอลัมน์ ----------
        body = tk.Frame(r, bg=C_BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)
        body.columnconfigure(0, minsize=int(280 * s), weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # ============ คอลัมน์ซ้าย: ควบคุม + ตั้งค่า ============
        left = make_card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        side_label(left, "โหมดบอท", pady=(12, 4))
        self.mode_selector = PillSelector(left, self.mode_var, [
            ("🪙 เหรียญ", "coin"),
            ("📦 กล่อง", "box"),
            ("⭐ EXP", "exp"),
        ], command=self._apply_mode_labels, font=("Segoe UI", F(9), "bold"))
        self.mode_selector.frame.pack(fill="x", padx=12)

        side_label(left, "จำนวนรอบ (0 = ไม่จำกัด)")
        loops_row = tk.Frame(left, bg=C_CARD)
        loops_row.pack(fill="x", padx=12)
        loops_border, self.loops_entry = make_entry(loops_row, self.loops_var, width=8, justify="center")
        loops_border.pack(side="left")

        self.toggle_btn = tk.Button(left, command=self.toggle, font=("Segoe UI", F(13), "bold"),
                                    bd=0, relief="flat", cursor="hand2")
        self._update_toggle_btn("stopped")
        self.toggle_btn.pack(fill="x", padx=12, pady=(14, 4), ipady=8)

        tk.Frame(left, bg=C_LINE, height=1).pack(fill="x", padx=12, pady=(12, 0))

        side_label(left, "⚙️ การเชื่อมต่อ (ADB)")
        tk.Label(left, text="ADB Path", bg=C_CARD, fg=C_DIM,
                 font=("Segoe UI", F(8))).pack(anchor="w", padx=12)
        adb_border, self.adb_entry = make_entry(left, self.adb_var, width=26)
        adb_border.pack(fill="x", padx=12, pady=(2, 6))
        tk.Label(left, text="Device", bg=C_CARD, fg=C_DIM,
                 font=("Segoe UI", F(8))).pack(anchor="w", padx=12)
        dev_border, self.dev_entry = make_entry(left, self.dev_var, width=18)
        dev_border.pack(fill="x", padx=12, pady=(2, 8))

        btn_row = tk.Frame(left, bg=C_CARD)
        btn_row.pack(fill="x", padx=12)
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        self.auto_find_btn = make_btn(btn_row, text="หาอัตโนมัติ", command=self.auto_find_adb, pady=4)
        self.auto_find_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.test_btn = make_btn(btn_row, text="ทดสอบ", command=self.test_connection, pady=4)
        self.test_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        # ปุ่มกู้: รีสตาร์ต adb server → ถ้ายัง offline สั่งรีบูต LDPlayer ผ่าน ldconsole
        self.recover_btn = make_btn(left, text="🔌 กู้การเชื่อมต่อ (device offline)",
                                    command=self.recover_connection,
                                    bg="#7c3aed", hover_bg="#6d28d9", pady=4)
        self.recover_btn.pack(fill="x", padx=12, pady=(6, 4))

        tk.Frame(left, bg=C_LINE, height=1).pack(fill="x", padx=12, pady=(12, 0))
        side_label(left, "ขนาดหน้าต่าง (UI)")
        self.scale_selector = PillSelector(left, self.scale_var, [
            ("90%", "0.9"), ("100%", "1.0"), ("115%", "1.15"), ("130%", "1.3"),
        ], command=self._apply_scale, font=("Segoe UI", F(8), "bold"))
        self.scale_selector.frame.pack(fill="x", padx=12, pady=(0, 12))

        # ============ คอลัมน์ขวา: สถิติ + สถานะ V2 + กราฟ + log ============
        right = tk.Frame(body, bg=C_BG)
        right.grid(row=0, column=1, sticky="nsew")

        # --- สถิติสด ---
        hero = make_card(right)
        hero.pack(fill="x")
        hero_top = tk.Frame(hero, bg=C_CARD)
        hero_top.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(hero_top, textvariable=self.unit_total_var, font=("Segoe UI", F(9), "bold"),
                 bg=C_CARD, fg=C_MUTED).pack(side="left")
        tk.Label(hero, textvariable=self.total_coins_var,
                 font=("Segoe UI", F(30), "bold"), bg=C_CARD, fg=C_GOLD).pack(anchor="w", padx=12)

        chips = tk.Frame(hero, bg=C_CARD)
        chips.pack(fill="x", padx=8, pady=(4, 8))
        for i in range(3):
            chips.columnconfigure(i, weight=1)
        make_stat(chips, 0, "⏱ เวลารัน", self.uptime_var, "#e2e8f0", framed=True)
        make_stat(chips, 1, "🔁 รอบที่เล่น", self.loops_done_var, C_GOLD, framed=True)
        make_stat(chips, 2, self.unit_rate_var, self.rate_var, C_GREEN, framed=True)

        mini = tk.Frame(hero, bg=C_CARD)
        mini.pack(fill="x", padx=8, pady=(0, 10))
        for i in range(3):
            mini.columnconfigure(i, weight=1)
        make_stat(mini, 0, self.unit_recent_var, self.recent_coins_var, C_GREEN, framed=False)
        make_stat(mini, 1, "เฉลี่ย/รอบ", self.avg_var, "#e2e8f0", framed=False)
        make_stat(mini, 2, "สูงสุด/รอบ", self.best_var, C_GOLD, framed=False)

        # --- แถบสถานะ V2 (พัก/ความล้า) + กราฟเหรียญ ---
        v2 = make_card(right)
        v2.pack(fill="x", pady=(8, 0))
        v2_row = tk.Frame(v2, bg=C_CARD)
        v2_row.pack(fill="x", padx=12, pady=(8, 4))
        self.v2_state_lbl = tk.Label(v2_row, textvariable=self.v2_state_var,
                                     font=("Segoe UI", F(10), "bold"), bg=C_CARD, fg=C_MUTED)
        self.v2_state_lbl.pack(side="left")
        tk.Label(v2_row, textvariable=self.fatigue_var, font=("Segoe UI", F(9)),
                 bg=C_CARD, fg=C_DIM).pack(side="right")

        tk.Label(v2, textvariable=self.unit_graph_var, font=("Segoe UI", F(8), "bold"),
                 bg=C_CARD, fg=C_DIM).pack(anchor="w", padx=12)
        self.graph = tk.Canvas(v2, height=int(64 * s), bg=C_CARD_IN, bd=0,
                               highlightthickness=1, highlightbackground=C_LINE)
        self.graph.pack(fill="x", padx=12, pady=(2, 10))
        self.graph.bind("<Configure>", self._draw_graph)

        # --- Log ---
        card_log = make_card(right)
        card_log.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(card_log, text="📝 บันทึกการทำงาน (Log)", font=("Segoe UI", F(9), "bold"),
                 bg=C_CARD, fg=C_MUTED).pack(anchor="w", padx=12, pady=(8, 2))
        self.log = scrolledtext.ScrolledText(card_log, font=("Consolas", F(9)), bg=C_FIELD,
                                             fg="#e2e8f0", insertbackground="white", wrap="word",
                                             bd=0, highlightthickness=0)
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        # สีข้อความ log ตามประเภท
        self.log.tag_config("tag_ok", foreground=C_GREEN)
        self.log.tag_config("tag_err", foreground=C_RED)
        self.log.tag_config("tag_nav", foreground="#60a5fa")
        self.log.tag_config("tag_box", foreground="#fb923c")
        self.log.tag_config("tag_info", foreground=C_GOLD)
        self.log.tag_config("tag_app", foreground="#c084fc")
        self.log.tag_config("tag_human", foreground="#a3e635")
        self.log.tag_config("tag_normal", foreground="#e2e8f0")

        self._set_status("running" if self.running else "stopped")
        self._set_adb_dot(self._adb_state)
        self._draw_graph()
        r.protocol("WM_DELETE_WINDOW", self.on_close)

    # ============================================================
    # ตัวช่วย UI / สถิติสด
    # ============================================================
    def _apply_mode_labels(self):
        """เปลี่ยนคำว่า เหรียญ/EXP บนป้ายสถิติตามโหมดที่เลือก
        (โหมด exp บอทอ่านตัวเลขแถว XP บนหน้า Result แทนแถว Coins)"""
        exp = self.mode_var.get() == "exp"
        icon, unit = ("⭐", "EXP") if exp else ("🪙", "เหรียญ")
        self.unit_total_var.set(f"{icon} {unit}สะสมรวม")
        self.unit_rate_var.set(f"⚡ {unit}/ชม.")
        self.unit_recent_var.set(f"{unit}รอบล่าสุด")
        self.unit_graph_var.set(f"{unit} 20 รอบล่าสุด")

    def _set_status(self, state):
        """อัปเดตป้ายสถานะบนแถบหัว (ข้อความ + สี ตัวอักษร/พื้นหลัง)"""
        cfg = {
            "stopped":  ("● หยุดอยู่",     C_RED,   "#3f1d1d"),
            "running":  ("● กำลังทำงาน",   C_GREEN, "#123524"),
            "stopping": ("● กำลังหยุด...",  C_GOLD,  "#3a2e0a"),
        }
        text, fg, bg = cfg[state]
        self.status_var.set(text)
        self.status_pill.config(bg=bg)
        self.status_lbl.config(fg=fg, bg=bg)

    def _set_adb_dot(self, state):
        """ไฟสถานะ ADB บนแถบหัว: ok=เขียว / bad=แดง / unknown=เทา"""
        self._adb_state = state
        spec = {
            "ok":      ("ADB ● เชื่อมต่อ", C_GREEN),
            "bad":     ("ADB ● หลุด",     C_RED),
            "unknown": ("ADB ● -",        C_DIM),
        }
        text, fg = spec.get(state, spec["unknown"])
        self.adb_dot_var.set(text)
        try:
            self.adb_dot_lbl.config(fg=fg)
        except tk.TclError:
            pass

    def _apply_scale(self):
        """เปลี่ยนขนาด UI — rebuild หน้าจอทันที (เฉพาะตอนบอทไม่รัน) + จำค่าลง settings.json"""
        if self.running or self.testing:
            self._enqueue("[app] เปลี่ยนขนาด UI ได้ตอนบอทหยุดอยู่เท่านั้น")
            return
        try:
            val = float(self.scale_var.get())
        except ValueError:
            return
        config.save_settings({"UI_SCALE": val})
        for w in self.root.winfo_children():
            w.destroy()
        self._build_ui()
        self._enqueue(f"[app] ปรับขนาด UI เป็น {int(val * 100)}% แล้ว")

    def _draw_graph(self, *_):
        """กราฟแท่งเหรียญ 20 รอบล่าสุด — แท่งล่าสุดอยู่ขวาสุด (สีสว่างกว่า), รอบที่อ่านเลขไม่ได้ = ขีดเทา"""
        c = getattr(self, "graph", None)
        if c is None:
            return
        try:
            c.delete("all")
            w, h = c.winfo_width(), c.winfo_height()
        except tk.TclError:
            return
        if w < 30 or h < 20:
            return
        data = list(self.coin_history)
        if not data:
            c.create_text(w // 2, h // 2, text="ยังไม่มีข้อมูล — จะขึ้นเมื่อจบเกมรอบแรก",
                          fill=C_DIM, font=("Segoe UI", self._F(8)))
            return
        n = self.coin_history.maxlen
        slot = w / n
        vals = [v for v in data if v]
        vmax = max(vals) if vals else 1
        pad_top, pad_bot = 6, 4
        for i, v in enumerate(data):
            # ชิดขวา: แท่งสุดท้ายของ data อยู่ช่องขวาสุดเสมอ
            x0 = w - (len(data) - i) * slot + 2
            x1 = x0 + slot - 4
            if x1 <= x0:
                x1 = x0 + 1
            if v is None:   # อ่านเลขไม่ได้ — ขีดเทาเตี้ย ๆ กันสับสนกับ "ได้ 0 เหรียญ"
                c.create_rectangle(x0, h - pad_bot - 3, x1, h - pad_bot, fill=C_DIM, width=0)
                continue
            bh = max(2, (h - pad_top - pad_bot) * (v / vmax))
            color = "#f59e0b" if i == len(data) - 1 else C_GOLD
            c.create_rectangle(x0, h - pad_bot - bh, x1, h - pad_bot, fill=color, width=0)

    @staticmethod
    def _fmt_hms(seconds):
        s = max(0, int(seconds))
        return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

    def _refresh_rate(self, elapsed=None):
        """คำนวณเหรียญต่อชั่วโมง = ยอดสะสม ÷ เวลารัน (โชว์ '-' ช่วงแรกที่ยังไม่มีข้อมูลพอ)"""
        if self.session_start is None:
            return
        if elapsed is None:
            elapsed = time.time() - self.session_start
        if elapsed >= 2 and self._total_coins > 0:
            per_hr = self._total_coins / (elapsed / 3600.0)
            self.rate_var.set(f"{int(round(per_hr)):,}")
        else:
            self.rate_var.set("-")

    def _tick_uptime(self):
        """ทุก 1 วิ: เดินนาฬิกาเวลารัน + เหรียญ/ชม. + ข้อความสถานะ V2 (พัก/เล่นอยู่)"""
        if self.running and self.session_start is not None:
            elapsed = time.time() - self.session_start
            self.uptime_var.set(self._fmt_hms(elapsed))
            self._refresh_rate(elapsed)
            if self.break_until and time.time() < self.break_until:
                remain = int(self.break_until - time.time())
                self.v2_state_var.set(f"😴 พักระหว่างเกม — เหลือ {remain} วิ")
                self.v2_state_lbl.config(fg=C_GOLD)
            else:
                self.v2_state_var.set("🎮 กำลังเล่น")
                self.v2_state_lbl.config(fg=C_GREEN)
        self.root.after(1000, self._tick_uptime)

    def _tick_adb(self):
        """เช็คไฟสถานะ ADB ทุก 15 วิ (เฉพาะตอนบอทไม่รัน — ตอนรันใช้การอ่านจาก log แทน)"""
        if (not self.running and not self.testing and not self.closing
                and not self._adb_checking):
            self._adb_checking = True

            def worker():
                try:
                    online = self.adb.list_online_devices()
                    state = "ok" if online else "bad"
                except Exception:
                    state = "bad"
                finally:
                    self._adb_checking = False
                self._safe_after(lambda: self._set_adb_dot(state))

            threading.Thread(target=worker, daemon=True).start()
        self.root.after(15000, self._tick_adb)

    # ============================================================
    # log (thread-safe ผ่าน queue)
    # ============================================================
    def _enqueue(self, msg):
        self.log_queue.put(str(msg) + "\n")

    def _safe_after(self, fn):
        """สั่งงาน main thread อย่างปลอดภัย (กันเรียกหลังหน้าต่างถูกปิด/ทำลาย)"""
        if self.closing:
            return
        try:
            self.root.after(0, fn)
        except (tk.TclError, RuntimeError):
            pass

    def _poll_log(self):
        inserted = False
        try:
            for _ in range(300):
                msg = self.log_queue.get_nowait()
                tag = "tag_normal"
                msg_lower = msg.lower()
                if "❌" in msg or "error" in msg_lower or "ล้มเหลว" in msg_lower:
                    tag = "tag_err"
                elif "✅" in msg or "สำเร็จ" in msg_lower or "[ok]" in msg_lower:
                    tag = "tag_ok"
                elif "[nav]" in msg_lower:
                    tag = "tag_nav"
                elif "[box]" in msg_lower:
                    tag = "tag_box"
                elif "[พัก]" in msg or "[human]" in msg_lower:
                    tag = "tag_human"
                elif "[*]" in msg_lower:
                    tag = "tag_info"
                elif "[app]" in msg_lower or "[กู้]" in msg:
                    tag = "tag_app"

                # ตอนบอทรัน ใช้ log เป็นตัวบอกไฟ ADB (เช็คตรง ๆ ระหว่างรันจะไปกวน adb)
                if self.running:
                    if "device offline" in msg_lower or "แคปหน้าจอไม่ได้" in msg or "แคปจอพลาด" in msg:
                        self._set_adb_dot("bad")
                    elif "[coins]" in msg_lower or "[ok]" in msg_lower:
                        self._set_adb_dot("ok")

                self.log.insert("end", msg, tag)
                inserted = True
        except queue.Empty:
            pass
        if inserted:
            try:
                self.log.see("end")
                if int(self.log.index("end-1c").split(".")[0]) > 800:
                    self.log.delete("1.0", "300.0")
            except Exception:
                pass
        self.root.after(150, self._poll_log)

    # ============================================================
    # ADB config
    # ============================================================
    def _apply_config(self):
        self.adb.path = self.adb_var.get().strip() or self.adb.path
        self.adb.device = self.dev_var.get().strip() or None

    def auto_find_adb(self):
        from adb import find_adb
        path = find_adb()
        self.adb_var.set(path)
        self._enqueue(f"[app] หา adb อัตโนมัติ: {path}")

    def _set_conn_btns(self, state):
        """เปิด/ปิดปุ่มกลุ่มเชื่อมต่อ (ทดสอบ/หาอัตโนมัติ/กู้) พร้อมสี"""
        if state == "disabled":
            for b in (self.test_btn, self.auto_find_btn):
                b.config(state="disabled", bg=C_CARD, fg=C_DIM)
            self.recover_btn.config(state="disabled", bg=C_CARD, fg=C_DIM)
        else:
            for b in (self.test_btn, self.auto_find_btn):
                b.config(state="normal", bg=C_BLUE, fg="#ffffff")
            self.recover_btn.config(state="normal", bg="#7c3aed", fg="#ffffff")

    def test_connection(self):
        if self.running:
            self._enqueue("[app] บอทกำลังทำงานอยู่ — หยุดบอทก่อนค่อยทดสอบ/แก้ค่า ADB")
            return
        if self.testing:
            self._enqueue("[app] กำลังทดสอบ/กู้อยู่แล้ว — รอผลสักครู่")
            return
        self._apply_config()
        self._enqueue("[app] กำลังทดสอบการเชื่อมต่อ...")
        self.testing = True
        self._set_conn_btns("disabled")

        def worker():
            try:
                if self.adb.connected():
                    dev = self.adb.device or ""
                    self._safe_after(lambda: self.dev_var.set(dev))
                    self._safe_after(lambda: self._set_adb_dot("ok"))
                    self._enqueue("[app] ✅ เชื่อมต่อสำเร็จ! แคปหน้าจอได้")
                    if config.save_settings({"DEFAULT_ADB": self.adb.path,
                                             "DEFAULT_DEVICE": self.adb.device}):
                        self._enqueue("[app] จำค่า ADB path/Device ลง settings.json แล้ว")
                else:
                    self._safe_after(lambda: self._set_adb_dot("bad"))
                    self._enqueue("[app] ❌ เชื่อมต่อไม่ได้ — เปิด LDPlayer และเช็ค ADB path/Device "
                                  "(หรือกดปุ่ม 🔌 กู้การเชื่อมต่อ)")
            finally:
                self.testing = False
                self._safe_after(lambda: self._set_conn_btns("normal"))

        threading.Thread(target=worker, daemon=True).start()

    def recover_connection(self):
        """กู้เคส device offline อัตโนมัติ:
        1) รีสตาร์ต adb server → ถ้ากลับมา online จบ
        2) ยัง offline = adbd ในอีมูเลเตอร์ค้าง → สั่งรีบูต LDPlayer ผ่าน ldconsole
           แล้วรอจนกลับมา online (สูงสุด ~2.5 นาที)"""
        if self.running:
            self._enqueue("[app] บอทกำลังทำงานอยู่ — หยุดบอทก่อนค่อยกู้การเชื่อมต่อ")
            return
        if self.testing:
            self._enqueue("[app] กำลังทดสอบ/กู้อยู่แล้ว — รอผลสักครู่")
            return
        self._apply_config()
        self.testing = True
        self._set_conn_btns("disabled")

        def worker():
            try:
                self._enqueue("[กู้] 1/2 รีสตาร์ต ADB server...")
                self.adb._run([self.adb.path, "kill-server"], timeout=10)
                time.sleep(2.0)
                online = self.adb.list_online_devices()
                if online:
                    if self.adb.device not in online:
                        self.adb.device = online[0]
                        self._safe_after(lambda: self.dev_var.set(self.adb.device))
                    self._enqueue(f"[กู้] ✅ device กลับมาออนไลน์: {', '.join(online)}")
                    self._safe_after(lambda: self._set_adb_dot("ok"))
                    return

                ld = os.path.join(os.path.dirname(self.adb.path) or ".", "ldconsole.exe")
                if not os.path.exists(ld):
                    self._enqueue("[กู้] ❌ ยังไม่ออนไลน์ และหา ldconsole.exe ข้าง adb ไม่เจอ "
                                  "— ปิด LDPlayer แล้วเปิดใหม่เองแล้วกดทดสอบอีกครั้ง")
                    self._safe_after(lambda: self._set_adb_dot("bad"))
                    return
                self._enqueue("[กู้] 2/2 adbd ในอีมูเลเตอร์น่าจะค้าง → สั่งรีบูต LDPlayer "
                              "(ใช้เวลา ~1 นาที เกมจะปิดแล้วเปิดใหม่)")
                self.adb._run([ld, "reboot", "--index", "0"], timeout=15)
                deadline = time.time() + 150
                while time.time() < deadline and not self.closing:
                    time.sleep(5.0)
                    online = self.adb.list_online_devices()
                    if online:
                        if self.adb.device not in online:
                            self.adb.device = online[0]
                            self._safe_after(lambda: self.dev_var.set(self.adb.device))
                        self._enqueue(f"[กู้] ✅ กลับมาออนไลน์แล้ว ({online[0]}) — "
                                      "รอเกม boot ขึ้นล็อบบี้ก่อนค่อยกดเริ่มบอท")
                        self._safe_after(lambda: self._set_adb_dot("ok"))
                        return
                self._enqueue("[กู้] ❌ รีบูตแล้วยังไม่ออนไลน์ภายใน 2.5 นาที — เช็คหน้าต่าง LDPlayer ด้วยตา")
                self._safe_after(lambda: self._set_adb_dot("bad"))
            except Exception as e:
                self._enqueue(f"[กู้] ❌ ผิดพลาดระหว่างกู้: {e}")
            finally:
                self.testing = False
                self._safe_after(lambda: self._set_conn_btns("normal"))

        threading.Thread(target=worker, daemon=True).start()

    # ============================================================
    # เริ่ม/หยุด บอท
    # ============================================================
    def toggle(self):
        if self.running:
            self.stop_bot()
        else:
            self.start_bot()

    def _update_toggle_btn(self, state_type):
        spec = {
            "stopped":  ("▶  เริ่มทำงานบอท",  "#10b981", "#059669", "normal"),
            "running":  ("■  หยุดทำงานบอท",   "#ef4444", "#dc2626", "normal"),
            "stopping": ("●  กำลังหยุดบอท...", "#f59e0b", "#d97706", "disabled"),
        }
        text, bg, hover, state = spec[state_type]
        self.toggle_btn.config(text=text, bg=bg, fg="#ffffff", activebackground=hover,
                               activeforeground="#ffffff", state=state)
        bind_hover(self.toggle_btn, bg, hover, "#ffffff", "#ffffff")

    def start_bot(self):
        if self.testing:
            self._enqueue("[app] กำลังทดสอบ/กู้การเชื่อมต่ออยู่ — รอให้เสร็จก่อนค่อยเริ่มบอท")
            return
        self._apply_config()

        try:
            max_loops = max(0, int(self.loops_var.get().strip() or "0"))
        except ValueError:
            max_loops = 0
        self._max_loops = max_loops

        mode = self.mode_var.get()
        self.stop_event = threading.Event()
        self.bot = CookieBot(self.adb, log=self._enqueue,
                             on_coins=self._on_coins, on_loop=self._on_loop,
                             stop_event=self.stop_event, mode=mode,
                             on_status=self._on_status)

        self.running = True
        self._update_toggle_btn("running")
        self._set_conn_btns("disabled")
        self.adb_entry.config(state="disabled", fg=C_DIM)
        self.dev_entry.config(state="disabled", fg=C_DIM)
        self.loops_entry.config(state="disabled", fg=C_DIM)
        self.mode_selector.set_state("disabled")
        self.scale_selector.set_state("disabled")

        self._set_status("running")

        # รีเซ็ตสถิติของ session ใหม่
        self.session_start = time.time()
        self._total_coins = 0
        self.coin_readable_count = 0
        self.coin_best = 0
        self.coin_history.clear()
        self.break_until = None
        self.uptime_var.set("00:00:00")
        self.rate_var.set("-")
        self.avg_var.set("-")
        self.best_var.set("-")
        self.recent_coins_var.set("-")
        self.total_coins_var.set("0")
        self.fatigue_var.set("ความล้า 0%")
        self._draw_graph()
        if max_loops:
            self.loops_done_var.set(f"0 / {max_loops}")
        else:
            self.loops_done_var.set("0")

        mode_txt = {"box": "วิ่งเก็บกล่อง (Fast Start)",
                    "exp": "เก็บ EXP (Star x2)"}.get(mode, "รีโรลเหรียญ")
        if max_loops:
            self._enqueue(f"\n[app] ===== เริ่มบอท โหมด{mode_txt} (จะเล่น {max_loops} รอบแล้วหยุด) =====")
        else:
            self._enqueue(f"\n[app] ===== เริ่มบอท โหมด{mode_txt} (ไม่จำกัดรอบ) =====")

        def worker():
            try:
                if not self.adb.connected():
                    self._enqueue("[app] ❌ เชื่อมต่อ ADB ไม่ได้ — หยุด (ลองปุ่ม 🔌 กู้การเชื่อมต่อ)")
                    self._safe_after(lambda: self._set_adb_dot("bad"))
                    return
                self._safe_after(lambda: self._set_adb_dot("ok"))
                config.save_settings({"DEFAULT_ADB": self.adb.path,
                                      "DEFAULT_DEVICE": self.adb.device,
                                      "BOT_MODE": mode})
                self.bot.run(max_loops)
            except Exception as e:
                import traceback
                self._enqueue(f"[app] ❌ บอทหยุดเพราะข้อผิดพลาด: {e}\n{traceback.format_exc()}")
            finally:
                self._safe_after(self._on_bot_stopped)

        self.bot_thread = threading.Thread(target=worker, daemon=True)
        self.bot_thread.start()

    def stop_bot(self):
        self.stop_event.set()
        self._set_status("stopping")
        self._update_toggle_btn("stopping")
        self._enqueue("[app] กำลังหยุด (รอจบ state ปัจจุบัน)...")

    def _on_bot_stopped(self):
        self.running = False
        self.break_until = None
        self._update_toggle_btn("stopped")
        self._set_conn_btns("normal")
        self.adb_entry.config(state="normal", fg=C_TEXT)
        self.dev_entry.config(state="normal", fg=C_TEXT)
        self.loops_entry.config(state="normal", fg=C_TEXT)
        self.mode_selector.set_state("normal")
        self.scale_selector.set_state("normal")
        self.v2_state_var.set("—")
        self.v2_state_lbl.config(fg=C_MUTED)
        self._set_status("stopped")

    # ============================================================
    # callbacks จากบอท (เรียกจาก bot thread → เด้งกลับ main thread)
    # ============================================================
    def _on_coins(self, coins, total):
        def upd():
            self._total_coins = total
            self.total_coins_var.set(f"{total:,}")
            self.coin_history.append(coins)   # None = อ่านไม่ได้ (โชว์เป็นขีดเทาในกราฟ)
            if coins is not None:
                self.recent_coins_var.set(f"+{coins:,}")
                self.coin_readable_count += 1
                if coins > self.coin_best:
                    self.coin_best = coins
                    self.best_var.set(f"{coins:,}")
            else:
                self.recent_coins_var.set("อ่านไม่ได้")
            if self.coin_readable_count > 0:
                self.avg_var.set(f"{int(round(total / self.coin_readable_count)):,}")
            self._refresh_rate()
            self._draw_graph()
        self._safe_after(upd)

    def _on_loop(self, loops_done):
        if self._max_loops:
            self._safe_after(lambda: self.loops_done_var.set(f"{loops_done} / {self._max_loops}"))
        else:
            self._safe_after(lambda: self.loops_done_var.set(str(loops_done)))

    def _on_status(self, ev):
        """event สถานะ V2 จากบอท: break/break_end/fatigue"""
        def upd():
            t = ev.get("type")
            if t == "break":
                self.break_until = time.time() + float(ev.get("secs", 0))
            elif t == "break_end":
                self.break_until = None
            elif t == "fatigue":
                self.fatigue_var.set(f"ความล้า {int(float(ev.get('frac', 0)) * 100)}%")
        self._safe_after(upd)

    # ============================================================
    def on_close(self):
        self.closing = True
        self.stop_event.set()
        self.root.after(120, self.root.destroy)


def _selftest():
    """ตรวจว่า (ตอน build เป็น .exe) template ถูก bundle มาครบและ import ได้ — เขียนผลลง selftest_result.txt"""
    import vision
    from paths import data_path
    lines, ok = [], True
    try:
        tpls = [config.IMG_TARGET_ITEM, config.IMG_OK_BUTTON, config.IMG_RESULT, config.IMG_RELAY,
                config.IMG_BOOST_SCREEN, config.IMG_LOBBY_PLAY, config.IMG_FRIEND_POPUP,
                config.IMG_MODE_POPUP, config.IMG_SENDLIFE_POPUP, config.IMG_MULTI_CHECK,
                config.IMG_FAST_START, config.IMG_FAST_START_BUY,
                config.IMG_FAST_START_ACTIVATE] \
               + [it["check_img"] for it in config.BOOST_ITEMS]
        for t in tpls:
            vision.load_template(t)
        n = len(vision.CoinReader(log=lambda m: None)._load_digits())
        lines.append(f"templates: {len(tpls)} OK | digit templates: {n}/10")
        ok = ok and (n == 10)
    except Exception as e:
        ok = False
        lines.append(f"ERROR: {e}")
    lines.append("RESULT: " + ("PASS" if ok else "FAIL"))
    out = "\n".join(lines)
    try:
        with open(data_path("selftest_result.txt"), "w", encoding="utf-8") as f:
            f.write(out + "\n")
    except Exception:
        pass
    try:
        print(out)
    except Exception:
        # console ที่ไม่ใช่ UTF-8 (เช่น cp1252) พิมพ์ไทยไม่ได้ — อย่าให้ selftest ล้มเพราะ print
        print(out.encode("ascii", "backslashreplace").decode("ascii"))


def main():
    import sys
    if "--selftest" in sys.argv:
        _selftest()
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
