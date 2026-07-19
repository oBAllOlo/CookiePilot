"""
app.py — หน้าต่างควบคุมบอท (GUI, tkinter) — V3
==============================================
โครงใหม่ทั้งหมด (จาก V2 cockpit 2 คอลัมน์):
  - แถบควบคุมหลัก (เริ่ม/หยุด + โหมด + จำนวนรอบ + สรุปบูสต์) อยู่บนสุด "ตลอดเวลา"
  - เนื้อหาแบ่ง 3 แท็บ: 📊 แดชบอร์ด / 🎁 ตั้งค่าบูสต์ / ⚙️ ระบบ
  - log อยู่ล่างสุดเสมอ ไม่ว่าเปิดแท็บไหน
  - ตั้งค่าบูสต์ "บันทึกอัตโนมัติ" ทันทีที่ติ๊ก (ไม่มีปุ่มบันทึกให้ลืมกด)
    แก้ตอนบอทรันได้ มีผลตั้งแต่ด่านถัดไป
  - พรีเซ็ต: เซฟชุดตั้งค่าบูสต์เป็นชื่อ เลือกจากรายการแล้วใช้ทันที

รัน:  python app.py   (หรือดับเบิลคลิก run_gui.bat)
"""
import os
import queue
import threading
import time
import tkinter as tk
from collections import deque
from tkinter import scrolledtext, ttk

import config
from adb import Adb
from bot import CookieBot
from activities import Activities

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
C_EMERALD  = "#10b981"
C_EMER_HV  = "#059669"


def bind_hover(btn, bg, hover_bg, fg="#ffffff", hover_fg="#ffffff"):
    """สลับสีปุ่มตอนเมาส์เข้า/ออก (เฉพาะตอน state=normal) — ใช้ร่วมกันทุกปุ่มในแอป"""
    btn.bind("<Enter>", lambda e: btn.config(bg=hover_bg, fg=hover_fg) if btn["state"] == "normal" else None)
    btn.bind("<Leave>", lambda e: btn.config(bg=bg, fg=fg) if btn["state"] == "normal" else None)


class PillSelector:
    """แถวปุ่มแบบ pill เลือกได้ 1 ค่า (ใช้กับโหมดบอท / แท็บ / ขนาด UI)"""

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
        for val, btn in self.buttons.items():
            btn.config(state=state)
            if state == "disabled":
                if val == self.variable.get():
                    # ล็อกอยู่ก็ต้องยังเห็นว่า "เลือกค่าไหนอยู่" (น้ำเงินหม่น ตัวอักษรสว่าง)
                    # — เดิมเทาหมดทุกปุ่ม ผู้ใช้ดูไม่ออกว่าบอทกำลังรันโหมดไหน
                    btn.config(bg="#1e40af", disabledforeground="#e2e8f0")
                else:
                    btn.config(bg=C_CARD, disabledforeground="#475569")
        if state == "normal":
            self.update_ui()


class ModernCheck(tk.Frame):
    """เช็คบ็อกซ์สไตล์โมเดิร์น: กล่องสี่เหลี่ยม ✓ ขาวบนพื้นน้ำเงิน + กดได้ทั้งแถว + ไฮไลต์ตอนชี้
    — แทน tk.Checkbutton เดิมที่ indicator เป็นกล่อง 3D สีเทายุคเก่า (ตัวการทำแอปดูโบราณ)"""

    def __init__(self, parent, text, variable, command=None, font=None, bg=C_CARD):
        super().__init__(parent, bg=bg, cursor="hand2", padx=2, pady=3)
        self.var = variable
        self.command = command
        self.box = tk.Label(self, text=" ", width=2, bd=0, font=("Segoe UI", 9, "bold"),
                            highlightthickness=1, highlightbackground=C_LINE)
        self.box.pack(side="left", padx=(6, 0))
        self.lbl = tk.Label(self, text=text, bg=bg, fg=C_TEXT, anchor="w",
                            font=font or ("Segoe UI", 10))
        self.lbl.pack(side="left", fill="x", expand=True, padx=(9, 6))
        for w in (self, self.box, self.lbl):
            w.bind("<Button-1>", self._toggle)
            w.bind("<Enter>", self._hover_on)
            w.bind("<Leave>", self._hover_off)
        # sync ตามค่า var เสมอ (รวมถึงตอนพรีเซ็ตเซ็ตค่าจากข้างนอก)
        self.var.trace_add("write", lambda *a: self._sync())
        self._sync()

    def _toggle(self, *_):
        self.var.set(not self.var.get())   # trace จะเรียก _sync ให้เอง
        if self.command:
            self.command()

    def _hover_on(self, *_):
        try:
            self.box.config(highlightbackground=C_BLUE)
            self.lbl.config(fg="#ffffff")
        except tk.TclError:
            pass

    def _hover_off(self, *_):
        try:
            self.box.config(highlightbackground=C_BLUE if self.var.get() else C_LINE)
            self.lbl.config(fg=C_TEXT)
        except tk.TclError:
            pass

    def _sync(self):
        try:
            if self.var.get():
                self.box.config(text="✓", bg=C_BLUE, fg="#ffffff",
                                highlightbackground=C_BLUE)
            else:
                self.box.config(text=" ", bg=C_FIELD, fg=C_FIELD,
                                highlightbackground=C_LINE)
        except tk.TclError:
            pass   # widget ถูกทำลายไปแล้ว (เช่นตอนเปลี่ยนขนาด UI) — เงียบไว้


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

        # กิจกรรมเสริม (แท็บ 🧩) — รันคนละ thread กับบอทหลัก ห้ามรันพร้อมกัน
        self.act_running = False
        self.act_thread = None
        self.act_stop_event = threading.Event()

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
        self.tab_var   = tk.StringVar(value="dash")   # แท็บที่เปิดอยู่ (จำข้ามการ rebuild)
        self.boost_saved_var   = tk.StringVar(value="")  # ข้อความ "บันทึกอัตโนมัติแล้ว" ในแท็บบูสต์
        self.boost_summary_var = tk.StringVar(value="")  # สรุปบูสต์บนแถบควบคุม
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
        # แท็บกิจกรรมเสริม: ช่องจำนวน + ป้ายสถานะ (อยู่ตรงนี้เพื่อรอด _apply_scale rebuild)
        self.act_count_var  = tk.StringVar(value="0")
        self.act_salvage_batch_var = tk.StringVar(value=str(getattr(config, "ACT_SALVAGE_BATCH", 10)))
        self.act_status_var = tk.StringVar(value="ยังไม่ได้รันกิจกรรม")

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
    # ตัวช่วยสร้าง widget (ใช้ร่วมทุกแท็บ)
    # ============================================================
    def _F(self, size):
        """ขนาดฟอนต์ตามสเกล UI ที่เลือก"""
        try:
            s = float(self.scale_var.get())
        except Exception:
            s = 1.0
        return max(7, int(round(size * s)))

    def _make_card(self, parent, **kwargs):
        return tk.Frame(parent, bg=C_CARD, highlightthickness=1,
                        highlightbackground=C_LINE, **kwargs)

    def _card_header(self, card, text, hint=None):
        """หัวข้อการ์ด + คำอธิบายสั้น (hint) ใต้หัวข้อ"""
        tk.Label(card, text=text, bg=C_CARD, fg=C_GOLD,
                 font=("Segoe UI", self._F(10), "bold")).pack(anchor="w", padx=14, pady=(10, 0))
        if hint:
            tk.Label(card, text=hint, bg=C_CARD, fg=C_MUTED, justify="left",
                     font=("Segoe UI", self._F(8))).pack(anchor="w", padx=14, pady=(1, 4))

    def _make_btn(self, parent, text, command, bg=C_BLUE, hover_bg=C_BLUE_HV,
                  fg="#ffffff", hover_fg="#ffffff", size=9, **kwargs):
        btn = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                        activebackground=hover_bg, activeforeground=hover_fg,
                        disabledforeground=C_DIM, font=("Segoe UI", self._F(size), "bold"),
                        bd=0, relief="flat", cursor="hand2", **kwargs)
        bind_hover(btn, bg, hover_bg, fg, hover_fg)
        return btn

    def _make_entry(self, parent, textvariable, width, justify="left"):
        border_frame = tk.Frame(parent, bg=C_LINE, highlightthickness=0)
        inner_frame = tk.Frame(border_frame, bg=C_FIELD, padx=6, pady=4)
        inner_frame.pack(fill="both", expand=True, padx=1, pady=1)
        entry = tk.Entry(inner_frame, textvariable=textvariable, width=width,
                         bg=C_FIELD, fg=C_TEXT, insertbackground=C_TEXT,
                         font=("Consolas", self._F(10)), bd=0, relief="flat", justify=justify)
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

    def _make_check(self, parent, text, var, command=None):
        """เช็คบ็อกซ์สไตล์โมเดิร์น (ดู class ModernCheck) — .pack/.grid ได้เหมือน widget ปกติ"""
        return ModernCheck(parent, text, var, command=command,
                           font=("Segoe UI", self._F(10)))

    # ============================================================
    # โครง UI หลัก
    # ============================================================
    def _build_ui(self):
        r = self.root
        F = self._F
        try:
            s = float(self.scale_var.get())
        except Exception:
            s = 1.0
        r.title(f"{config.APP_NAME} v{config.APP_VERSION}")
        r.geometry(f"{int(980 * s)}x{int(690 * s)}")
        r.minsize(int(900 * s), int(600 * s))
        r.configure(bg=C_BG)

        # ttk (Combobox) ธีมมืดให้เข้ากับแอป — ค่า default ของ Windows เป็นกล่องขาวยุคเก่า
        style = ttk.Style(r)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Dark.TCombobox",
                        fieldbackground=C_FIELD, background=C_CARD,
                        foreground=C_TEXT, arrowcolor=C_TEXT,
                        bordercolor=C_LINE, lightcolor=C_CARD, darkcolor=C_CARD,
                        insertcolor=C_TEXT,
                        selectbackground=C_FIELD, selectforeground=C_TEXT)
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", C_FIELD), ("disabled", C_CARD)],
                  foreground=[("disabled", C_DIM)])
        r.option_add("*TCombobox*Listbox.background", C_FIELD)
        r.option_add("*TCombobox*Listbox.foreground", C_TEXT)
        r.option_add("*TCombobox*Listbox.selectBackground", C_BLUE)
        r.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

        # ---------- 1) แถบหัว: ชื่อแอป | ไฟ ADB | ป้ายสถานะบอท ----------
        bar = tk.Frame(r, bg=C_BAR)
        bar.pack(fill="x")
        bar_in = tk.Frame(bar, bg=C_BAR)
        bar_in.pack(fill="x", padx=18, pady=8)

        tk.Label(bar_in, text="🍪 CookiePilot", font=("Segoe UI", F(14), "bold"),
                 bg=C_BAR, fg=C_GOLD).pack(side="left")
        tk.Label(bar_in, text=f"v{config.APP_VERSION}", font=("Segoe UI", F(9)),
                 bg=C_BAR, fg=C_DIM).pack(side="left", padx=(6, 0))

        self.status_pill = tk.Frame(bar_in, bg="#3f1d1d")
        self.status_pill.pack(side="right")
        self.status_lbl = tk.Label(self.status_pill, textvariable=self.status_var,
                                   font=("Segoe UI", F(9), "bold"), bg="#3f1d1d",
                                   fg=C_RED, padx=12, pady=3)
        self.status_lbl.pack()

        self.adb_dot_lbl = tk.Label(bar_in, textvariable=self.adb_dot_var,
                                    font=("Segoe UI", F(9), "bold"), bg=C_BAR, fg=C_DIM)
        self.adb_dot_lbl.pack(side="right", padx=(0, 12))
        tk.Frame(r, bg=C_LINE, height=1).pack(fill="x")

        # ---------- 2) แถบควบคุมหลัก (เห็นตลอดเวลา ไม่ว่าอยู่แท็บไหน) ----------
        ctrl = self._make_card(r)
        ctrl.pack(fill="x", padx=14, pady=(10, 0))
        ctrl_in = tk.Frame(ctrl, bg=C_CARD)
        ctrl_in.pack(fill="x", padx=10, pady=8)

        self.toggle_btn = tk.Button(ctrl_in, command=self.toggle, font=("Segoe UI", F(11), "bold"),
                                    bd=0, relief="flat", cursor="hand2")
        self._update_toggle_btn("stopped")
        self.toggle_btn.pack(side="left", ipadx=18, ipady=6)

        tk.Label(ctrl_in, text="โหมด", bg=C_CARD, fg=C_MUTED,
                 font=("Segoe UI", F(9), "bold")).pack(side="left", padx=(16, 6))
        self.mode_selector = PillSelector(ctrl_in, self.mode_var, [
            ("🪙 เหรียญ", "coin"),
            ("📦 กล่อง", "box"),
            ("⭐ EXP", "exp"),
        ], command=self._apply_mode_labels, font=("Segoe UI", F(9), "bold"))
        self.mode_selector.frame.pack(side="left")

        tk.Label(ctrl_in, text="รอบ", bg=C_CARD, fg=C_MUTED,
                 font=("Segoe UI", F(9), "bold")).pack(side="left", padx=(14, 6))
        loops_border, self.loops_entry = self._make_entry(ctrl_in, self.loops_var,
                                                          width=5, justify="center")
        loops_border.pack(side="left")
        tk.Label(ctrl_in, text="(0 = ไม่จำกัด)", bg=C_CARD, fg=C_DIM,
                 font=("Segoe UI", F(8))).pack(side="left", padx=(5, 0))

        # สรุปบูสต์ที่ตั้งไว้ — คลิกแล้วเด้งไปแท็บตั้งค่าบูสต์
        self.boost_summary_lbl = tk.Label(ctrl_in, textvariable=self.boost_summary_var,
                                          bg=C_CARD, fg=C_MUTED, cursor="hand2",
                                          font=("Segoe UI", F(8)))
        self.boost_summary_lbl.pack(side="right")
        self.boost_summary_lbl.bind("<Button-1>",
                                    lambda e: self.tab_selector.select("boost"))

        # ---------- 3) แถบแท็บ ----------
        tabs_row = tk.Frame(r, bg=C_BG)
        tabs_row.pack(fill="x", padx=14, pady=(8, 0))
        self.tab_selector = PillSelector(tabs_row, self.tab_var, [
            ("📊 แดชบอร์ด", "dash"),
            ("🎁 ตั้งค่าบูสต์", "boost"),
            ("🧩 กิจกรรม", "act"),
            ("⚙️ ระบบ", "sys"),
        ], command=self._on_tab_changed, font=("Segoe UI", F(10), "bold"))
        self.tab_selector.frame.pack(fill="x")

        # ---------- 4) เนื้อหาแท็บ ----------
        cont = tk.Frame(r, bg=C_BG)
        cont.pack(fill="both", expand=True, padx=14, pady=(8, 0))
        cont.rowconfigure(0, weight=1)
        cont.columnconfigure(0, weight=1)
        self.tab_frames = {}
        for key, builder in (("dash", self._build_tab_dashboard),
                             ("boost", self._build_tab_boosts),
                             ("act", self._build_tab_activities),
                             ("sys", self._build_tab_system)):
            f = tk.Frame(cont, bg=C_BG)
            f.grid(row=0, column=0, sticky="nsew")
            builder(f)
            self.tab_frames[key] = f

        # ---------- 5) Log (ล่างเสมอ) ----------
        card_log = self._make_card(r)
        card_log.pack(fill="x", padx=14, pady=(8, 12))
        tk.Label(card_log, text="📝 บันทึกการทำงาน (Log)", font=("Segoe UI", F(9), "bold"),
                 bg=C_CARD, fg=C_MUTED).pack(anchor="w", padx=12, pady=(6, 2))
        self.log = scrolledtext.ScrolledText(card_log, font=("Consolas", F(9)), bg=C_FIELD,
                                             fg="#e2e8f0", insertbackground="white", wrap="word",
                                             bd=0, highlightthickness=0, height=9)
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 8))

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
        self._refresh_boost_summary()
        self._on_tab_changed()
        self._draw_graph()
        r.protocol("WM_DELETE_WINDOW", self.on_close)

    def _on_tab_changed(self):
        tab = self.tab_var.get()
        if tab not in self.tab_frames:
            tab = "dash"
        self.tab_frames[tab].tkraise()

    # ============================================================
    # แท็บ 1: แดชบอร์ด (สถิติสด + สถานะ V2 + กราฟ)
    # ============================================================
    def _build_tab_dashboard(self, parent):
        F = self._F
        try:
            s = float(self.scale_var.get())
        except Exception:
            s = 1.0

        def make_stat(row, col, caption, var, value_fg, framed):
            """ช่องสถิติ 1 ช่อง — framed=True มีกรอบ (chip หลัก) / False ไม่มีกรอบ (สถิติย่อย)
            caption เป็น str หรือ StringVar ก็ได้ (ป้ายเหรียญ/EXP เปลี่ยนตามโหมด)"""
            bg = C_CARD_IN if framed else C_CARD
            box = tk.Frame(row, bg=bg, highlightthickness=1 if framed else 0,
                           highlightbackground=C_LINE)
            box.grid(row=0, column=col, sticky="nsew", padx=4)
            cap_kw = ({"textvariable": caption} if isinstance(caption, tk.StringVar)
                      else {"text": caption})
            tk.Label(box, font=("Segoe UI", F(8), "bold"),
                     bg=bg, fg=C_MUTED, **cap_kw).pack(pady=(7, 0) if framed else 0)
            tk.Label(box, textvariable=var, font=("Segoe UI", F(13) if framed else F(12), "bold"),
                     bg=bg, fg=value_fg).pack(pady=(1, 8) if framed else (2, 0))

        hero = self._make_card(parent)
        hero.pack(fill="x")
        hero_top = tk.Frame(hero, bg=C_CARD)
        hero_top.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(hero_top, textvariable=self.unit_total_var, font=("Segoe UI", F(9), "bold"),
                 bg=C_CARD, fg=C_MUTED).pack(side="left")
        tk.Label(hero, textvariable=self.total_coins_var,
                 font=("Segoe UI", F(28), "bold"), bg=C_CARD, fg=C_GOLD).pack(anchor="w", padx=12)

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
        v2 = self._make_card(parent)
        v2.pack(fill="both", expand=True, pady=(8, 0))
        v2_row = tk.Frame(v2, bg=C_CARD)
        v2_row.pack(fill="x", padx=12, pady=(8, 4))
        self.v2_state_lbl = tk.Label(v2_row, textvariable=self.v2_state_var,
                                     font=("Segoe UI", F(10), "bold"), bg=C_CARD, fg=C_MUTED)
        self.v2_state_lbl.pack(side="left")
        tk.Label(v2_row, textvariable=self.fatigue_var, font=("Segoe UI", F(9)),
                 bg=C_CARD, fg=C_DIM).pack(side="right")

        tk.Label(v2, textvariable=self.unit_graph_var, font=("Segoe UI", F(8), "bold"),
                 bg=C_CARD, fg=C_DIM).pack(anchor="w", padx=12)
        self.graph = tk.Canvas(v2, height=int(70 * s), bg=C_CARD_IN, bd=0,
                               highlightthickness=1, highlightbackground=C_LINE)
        self.graph.pack(fill="both", expand=True, padx=12, pady=(2, 10))
        self.graph.bind("<Configure>", self._draw_graph)

    # ============================================================
    # แท็บ 2: ตั้งค่าบูสต์ — ติ๊กแล้ว "บันทึกอัตโนมัติ" ทันที + พรีเซ็ต
    # ============================================================
    def _build_tab_boosts(self, parent):
        F = self._F

        # ---------- พรีเซ็ต (บนสุด) ----------
        pcard = self._make_card(parent)
        pcard.pack(fill="x")
        prow = tk.Frame(pcard, bg=C_CARD)
        prow.pack(fill="x", padx=12, pady=8)
        tk.Label(prow, text="📁 พรีเซ็ต", bg=C_CARD, fg=C_GOLD,
                 font=("Segoe UI", F(9), "bold")).pack(side="left")
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(prow, textvariable=self.preset_var, width=16,
                                         font=("Segoe UI", F(9)), style="Dark.TCombobox",
                                         values=sorted(self._presets_dict()))
        self.preset_combo.pack(side="left", padx=(10, 6))
        self.preset_combo.bind("<<ComboboxSelected>>", self._load_preset)
        b1 = self._make_btn(prow, "💾 เซฟชุดนี้เป็นชื่อ", self._save_preset, size=8, pady=3)
        b1.pack(side="left", padx=(0, 6), ipadx=8)
        b2 = self._make_btn(prow, "🗑 ลบ", self._delete_preset,
                            bg="#7f1d1d", hover_bg="#991b1b", size=8, pady=3)
        b2.pack(side="left", ipadx=8)
        tk.Label(prow, text="เลือกชื่อจากรายการ = ใช้ชุดนั้นทันที",
                 bg=C_CARD, fg=C_DIM, font=("Segoe UI", F(8))).pack(side="left", padx=(10, 0))
        # ป้าย "บันทึกอัตโนมัติแล้ว" มุมขวา
        tk.Label(prow, textvariable=self.boost_saved_var, bg=C_CARD, fg=C_GREEN,
                 font=("Segoe UI", F(8))).pack(side="right")

        # ---------- 2 คอลัมน์: ซ้าย = หน้าเตรียมตัว + ตอนเริ่มวิ่ง | ขวา = กล่องสุ่ม ----------
        cols = tk.Frame(parent, bg=C_BG)
        cols.pack(fill="both", expand=True, pady=(8, 0))
        cols.columnconfigure(0, weight=2, uniform="b")
        cols.columnconfigure(1, weight=3, uniform="b")
        cols.rowconfigure(0, weight=1)

        left = tk.Frame(cols, bg=C_BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = tk.Frame(cols, bg=C_BG)
        right.grid(row=0, column=1, sticky="nsew")

        # การ์ด: บูสต์หน้าเตรียมตัว
        prep = self._make_card(left)
        prep.pack(fill="x")
        self._card_header(prep, "🧪 บูสต์หน้าเตรียมตัว — ติ๊กก่อนกด Play",
                          "ใช้กับโหมดเหรียญ/กล่อง (โหมด EXP ติ๊กเฉพาะ Star x2 เสมอ)\n"
                          "บอทปรับให้ตรงเป๊ะ: ตัวที่ไม่เลือกแต่ติ๊กค้างในเกม จะกดเอาออกให้")
        prep_selected = {str(n) for n in (config.PREP_BOOST_TARGETS or [])}
        self._prep_vars = {}
        hints = {"Stopwatch": " (ไม่มีสต็อก = 800 เหรียญ/ด่าน)"}
        for it in config.BOOST_ITEMS:
            name = str(it["name"])
            var = tk.BooleanVar(value=name in prep_selected)
            self._prep_vars[name] = var
            self._make_check(prep, name + hints.get(name, ""), var,
                             command=self._save_boosts).pack(fill="x", padx=10, pady=1)
        tk.Frame(prep, bg=C_CARD, height=8).pack()

        # การ์ด: Fast Start (คุมทั้งการซื้อ + การกดปุ่ม activate ตอนเริ่มวิ่ง)
        act = self._make_card(left)
        act.pack(fill="x", pady=(8, 0))
        self._card_header(act, "⚡ Fast Start (โหมดกล่อง/EXP)",
                          "ติ๊ก = โหมดกล่องซื้อก่อนเล่น + กดปุ่ม activate ตอนเริ่มด่าน\n"
                          "ไม่ติ๊ก = ไม่ซื้อและไม่กดเลย (ไม่เปลืองของทุกด่าน)")
        self._act_var = tk.BooleanVar(value=bool(config.TAP_FAST_START_ACTIVATE))
        self._make_check(act, "ใช้ Fast Start (ซื้อ + กดปุ่ม activate)",
                         self._act_var, command=self._save_boosts
                         ).pack(fill="x", padx=10, pady=(0, 1))
        tk.Frame(act, bg=C_CARD, height=8).pack()

        # การ์ด: บูสต์กล่องสุ่ม (Multi-Buy)
        box = self._make_card(right)
        box.pack(fill="both", expand=True)
        self._card_header(box, "🎲 กล่องสุ่ม — Multi-Buy ก่อนเล่น (โหมดกล่อง)",
                          "บอทปรับติ๊กหน้า \"Pick desired Boosts!\" ให้ตรงตามนี้เป๊ะ (ติ๊กเกินเอาออกให้)\n"
                          "แล้วกด Multi-Buy จนได้ (ซื้อแรก 1,200 / ซื้อซ้ำ 600 เหรียญ) — ไม่ติ๊กเลย = ไม่ซื้อ")
        grid = tk.Frame(box, bg=C_CARD)
        grid.pack(fill="x", padx=8, pady=(2, 8))
        grid.columnconfigure(0, weight=1, uniform="g")
        grid.columnconfigure(1, weight=1, uniform="g")
        box_selected = {str(n) for n in (config.BOX_MULTI_TARGETS or [])}
        self._box_vars = {}
        # เรียง 2 คอลัมน์ตามผังจริงในเกม (ซ้าย 6 / ขวา 5)
        for i, opt in enumerate(config.MULTI_BOOST_OPTIONS):
            name = str(opt["name"])
            var = tk.BooleanVar(value=name in box_selected)
            self._box_vars[name] = var
            self._make_check(grid, name, var, command=self._save_boosts
                             ).grid(row=i % 6, column=i // 6, sticky="ew", padx=4, pady=1)

    # ============================================================
    # แท็บ 3: ระบบ (ADB + ขนาด UI)
    # ============================================================
    def _build_tab_system(self, parent):
        F = self._F
        cols = tk.Frame(parent, bg=C_BG)
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=1, uniform="s")
        cols.columnconfigure(1, weight=1, uniform="s")

        # การ์ด: การเชื่อมต่อ ADB
        conn = self._make_card(cols)
        conn.grid(row=0, column=0, sticky="new", padx=(0, 8))
        self._card_header(conn, "🔌 การเชื่อมต่อ (ADB / LDPlayer)")
        tk.Label(conn, text="ADB Path", bg=C_CARD, fg=C_DIM,
                 font=("Segoe UI", F(8))).pack(anchor="w", padx=12, pady=(4, 0))
        adb_border, self.adb_entry = self._make_entry(conn, self.adb_var, width=30)
        adb_border.pack(fill="x", padx=12, pady=(2, 6))
        tk.Label(conn, text="Device", bg=C_CARD, fg=C_DIM,
                 font=("Segoe UI", F(8))).pack(anchor="w", padx=12)
        dev_border, self.dev_entry = self._make_entry(conn, self.dev_var, width=18)
        dev_border.pack(fill="x", padx=12, pady=(2, 8))

        btn_row = tk.Frame(conn, bg=C_CARD)
        btn_row.pack(fill="x", padx=12)
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        self.auto_find_btn = self._make_btn(btn_row, "หาอัตโนมัติ", self.auto_find_adb, pady=4)
        self.auto_find_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.test_btn = self._make_btn(btn_row, "ทดสอบ", self.test_connection, pady=4)
        self.test_btn.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        # ปุ่มกู้: รีสตาร์ต adb server → ถ้ายัง offline สั่งรีบูต LDPlayer ผ่าน ldconsole
        self.recover_btn = self._make_btn(conn, "🔌 กู้การเชื่อมต่อ (device offline)",
                                          self.recover_connection,
                                          bg="#7c3aed", hover_bg="#6d28d9", pady=4)
        self.recover_btn.pack(fill="x", padx=12, pady=(6, 10))

        # การ์ด: หน้าตา + ข้อมูลไฟล์
        right = tk.Frame(cols, bg=C_BG)
        right.grid(row=0, column=1, sticky="new")

        ui = self._make_card(right)
        ui.pack(fill="x")
        self._card_header(ui, "🖥 ขนาดหน้าต่าง (UI)")
        self.scale_selector = PillSelector(ui, self.scale_var, [
            ("90%", "0.9"), ("100%", "1.0"), ("115%", "1.15"), ("130%", "1.3"),
        ], command=self._apply_scale, font=("Segoe UI", F(8), "bold"))
        self.scale_selector.frame.pack(fill="x", padx=12, pady=(4, 10))

        info = self._make_card(right)
        info.pack(fill="x", pady=(8, 0))
        self._card_header(info, "ℹ️ ไฟล์ / การตั้งค่าละเอียด")
        tk.Label(info, justify="left", bg=C_CARD, fg=C_DIM, font=("Segoe UI", F(8)),
                 text=("• การตั้งค่าทั้งหมดเก็บใน settings.json (ข้างโปรแกรม)\n"
                       "• พิกัดปุ่ม/ความไว/ดีเลย์ จูนละเอียดได้ในไฟล์เดียวกัน\n"
                       "• ผลเหรียญรายรอบเก็บที่ coin_logs/coins.csv\n"
                       "• พิกัดจูนมาสำหรับ LDPlayer 1280x720 (DPI 240)")
                 ).pack(anchor="w", padx=12, pady=(2, 10))

    # ============================================================
    # แท็บ 4: กิจกรรมเสริม (ส่งหัวใจ / เมล / เพื่อน / สมบัติ / กล่องของขวัญ)
    # ============================================================
    def _build_tab_activities(self, parent):
        F = self._F

        card = self._make_card(parent)
        card.pack(fill="x")
        self._card_header(card, "🧩 กิจกรรมเสริม",
                          hint="เปิดหน้าจอในเกมให้ตรงกับกิจกรรมก่อนกด — template ชุดนี้นำเข้าจากบอทอื่น "
                               "ถ้าหาปุ่มไม่เจอดู score ใน log แล้วแคปทับ")

        # แถวควบคุม: จำนวน + ปุ่มหยุด + ป้ายสถานะ
        row = tk.Frame(card, bg=C_CARD)
        row.pack(fill="x", padx=12, pady=(4, 6))
        tk.Label(row, text="จำนวน (0 = ไม่จำกัด):", bg=C_CARD, fg=C_MUTED,
                 font=("Segoe UI", F(9), "bold")).pack(side="left")
        count_border, self.act_count_entry = self._make_entry(row, self.act_count_var,
                                                              width=6, justify="center")
        count_border.pack(side="left", padx=(6, 10))
        self.act_stop_btn = self._make_btn(row, "■ หยุดกิจกรรม", self._stop_activity,
                                           bg="#ef4444", hover_bg="#dc2626", pady=3)
        self.act_stop_btn.pack(side="left", ipadx=10)
        tk.Label(row, textvariable=self.act_status_var, bg=C_CARD, fg=C_MUTED,
                 font=("Segoe UI", F(9))).pack(side="left", padx=(12, 0))

        # แถวตั้งค่าย่อยผงตอนกาชาคลังเต็ม — กี่ชิ้นต่อรอบ (บันทึกลง settings.json อัตโนมัติ)
        row2 = tk.Frame(card, bg=C_CARD)
        row2.pack(fill="x", padx=12, pady=(0, 6))
        tk.Label(row2, text="กาชาคลังเต็ม → ย่อยครั้งละ (ชิ้น):", bg=C_CARD, fg=C_MUTED,
                 font=("Segoe UI", F(9), "bold")).pack(side="left")
        sb_border, self.act_salvage_batch_entry = self._make_entry(
            row2, self.act_salvage_batch_var, width=6, justify="center")
        sb_border.pack(side="left", padx=(6, 10))
        self.act_salvage_batch_entry.bind("<FocusOut>", lambda e: self._save_salvage_batch())
        self.act_salvage_batch_entry.bind("<Return>", lambda e: self._save_salvage_batch())
        self.act_salvage_batch_saved_var = tk.StringVar(value="")
        tk.Label(row2, textvariable=self.act_salvage_batch_saved_var, bg=C_CARD, fg=C_MUTED,
                 font=("Segoe UI", F(9))).pack(side="left", padx=(4, 0))

        # ปุ่มกิจกรรม 7 ปุ่ม (2 คอลัมน์) — rebuild ใหม่ทุกครั้งที่เปลี่ยนขนาด UI (ไม่เป็นไร
        # เพราะ _apply_scale ถูกล็อกไม่ให้ทำงานระหว่างกิจกรรมรันอยู่)
        grid = tk.Frame(card, bg=C_CARD)
        grid.pack(fill="x", padx=8, pady=(2, 10))
        grid.columnconfigure(0, weight=1, uniform="a")
        grid.columnconfigure(1, weight=1, uniform="a")
        items = [
            ("💗 ส่งหัวใจ (เปิดหน้ารายชื่อเพื่อนก่อน)", "send_hearts"),
            ("📬 รับหัวใจเมล (จากล็อบบี้)", "mail_hearts"),
            ("👥 เพิ่มเพื่อน", "add_friends"),
            ("🔮 กาชาสมบัติ (เปิดร้านสมบัติก่อน)", "treasure_gacha"),
            ("♻️ ย่อยผง (เปิดตู้เก็บก่อน)", "salvage"),
            ("💎 อัพเกรด +9 (เปิดหน้าสมบัติก่อน)", "treasure_upgrade"),
            ("🎁 เปิดกล่องของขวัญ", "open_gift_box"),
        ]
        self._act_btns = []
        for i, (text, key) in enumerate(items):
            b = self._make_btn(grid, text, lambda k=key: self._start_activity(k), pady=5)
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=4, pady=3)
            self._act_btns.append(b)

    def _save_salvage_batch(self):
        """บันทึกจำนวนชิ้นที่ย่อยต่อรอบตอนกาชาคลังเต็ม → config + settings.json (มีผลทันที ไม่ต้อง restart)
        ค่าต่ำสุด 1 (0/ติดลบ/ไม่ใช่ตัวเลข → ปัดเป็น 1 กันย่อย 0 ชิ้นแล้ววนไม่รู้จบ)"""
        try:
            n = max(1, int(self.act_salvage_batch_var.get().strip() or "1"))
        except ValueError:
            n = 1
        self.act_salvage_batch_var.set(str(n))   # normalize ค่าในช่องให้ตรง
        config.ACT_SALVAGE_BATCH = n             # อัพเดตค่าที่บอทอ่านตอนรัน (มีผลด่านถัดไปทันที)
        if config.save_settings({"ACT_SALVAGE_BATCH": n}):
            self.act_salvage_batch_saved_var.set(f"✓ ย่อยครั้งละ {n} • {time.strftime('%H:%M:%S')}")
        else:
            self.act_salvage_batch_saved_var.set("❌ บันทึกไม่สำเร็จ")

    # ============================================================
    # ตั้งค่าบูสต์: บันทึกอัตโนมัติ + สรุป + พรีเซ็ต
    # ============================================================
    def _refresh_boost_summary(self):
        """สรุปบูสต์บนแถบควบคุม — คลิกแล้วเด้งไปแท็บตั้งค่าบูสต์"""
        p = len(config.PREP_BOOST_TARGETS or [])
        n = len(config.BOX_MULTI_TARGETS or [])
        box = f"กล่องสุ่ม {n}" if n else "ไม่ซื้อกล่อง"
        fs = "กด FS" if config.TAP_FAST_START_ACTIVATE else "ไม่กด FS"
        self.boost_summary_var.set(
            f"🎁 ติ๊ก {p}/{len(config.BOOST_ITEMS)} • {box} • {fs} ▸")

    def _save_boosts(self):
        """เซฟค่าบูสต์ทั้งหมดลง settings.json ทันทีที่ติ๊ก (auto-save)
        — บอทอ่านค่าใหม่ตอนเริ่มด่านถัดไป ไม่ต้องรีสตาร์ต"""
        prep = [n for n, v in self._prep_vars.items() if v.get()]
        box = [n for n, v in self._box_vars.items() if v.get()]
        ok = config.save_settings({"PREP_BOOST_TARGETS": prep,
                                   "BOX_MULTI_TARGETS": box,
                                   "TAP_FAST_START_ACTIVATE": bool(self._act_var.get())})
        if ok:
            note = " • มีผลด่านถัดไป" if self.running else ""
            self.boost_saved_var.set(f"✓ บันทึกแล้ว {time.strftime('%H:%M:%S')}{note}")
        else:
            self.boost_saved_var.set("❌ เขียน settings.json ไม่สำเร็จ")
            self._enqueue("[app] ❌ เขียน settings.json ไม่สำเร็จ — ค่าบูสต์ยังไม่ถูกบันทึก")
        self._refresh_boost_summary()

    def _presets_dict(self):
        d = config.BOOST_PRESETS
        return dict(d) if isinstance(d, dict) else {}

    def _refresh_preset_combo(self):
        try:
            self.preset_combo["values"] = sorted(self._presets_dict())
        except tk.TclError:
            pass

    def _load_preset(self, *_):
        """เลือกพรีเซ็ตจากรายการ → ติ๊กเด้งตาม + ใช้งานทันที (auto-save ต่อเลย)"""
        name = self.preset_var.get().strip()
        p = self._presets_dict().get(name)
        if not isinstance(p, dict):
            return
        prep = {str(x) for x in (p.get("PREP_BOOST_TARGETS") or [])}
        box = {str(x) for x in (p.get("BOX_MULTI_TARGETS") or [])}
        for n, v in self._prep_vars.items():
            v.set(n in prep)
        for n, v in self._box_vars.items():
            v.set(n in box)
        if "TAP_FAST_START_ACTIVATE" in p:   # พรีเซ็ตเก่าไม่มี key นี้ → คงค่าเดิมไว้
            self._act_var.set(bool(p["TAP_FAST_START_ACTIVATE"]))
        self._save_boosts()
        self._enqueue(f"[app] ใช้พรีเซ็ต '{name}' แล้ว")

    def _save_preset(self):
        name = self.preset_var.get().strip()
        if not name:
            self._enqueue("[app] พิมพ์ชื่อพรีเซ็ตในช่องก่อน แล้วค่อยกด 💾")
            return
        d = self._presets_dict()
        d[name] = {"PREP_BOOST_TARGETS": [n for n, v in self._prep_vars.items() if v.get()],
                   "BOX_MULTI_TARGETS": [n for n, v in self._box_vars.items() if v.get()],
                   "TAP_FAST_START_ACTIVATE": bool(self._act_var.get())}
        if config.save_settings({"BOOST_PRESETS": d}):
            self._refresh_preset_combo()
            self._enqueue(f"[app] เซฟพรีเซ็ต '{name}' แล้ว ({len(d)} พรีเซ็ตทั้งหมด)")
        else:
            self._enqueue("[app] ❌ เขียน settings.json ไม่สำเร็จ — พรีเซ็ตยังไม่ถูกเซฟ")

    def _delete_preset(self):
        name = self.preset_var.get().strip()
        d = self._presets_dict()
        if name not in d:
            self._enqueue(f"[app] ไม่มีพรีเซ็ตชื่อ '{name}' ให้ลบ")
            return
        d.pop(name)
        if config.save_settings({"BOOST_PRESETS": d}):
            self.preset_var.set("")
            self._refresh_preset_combo()
            self._enqueue(f"[app] ลบพรีเซ็ต '{name}' แล้ว")
        else:
            self._enqueue("[app] ❌ เขียน settings.json ไม่สำเร็จ — ยังไม่ถูกลบ")

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

    def _mode_txt(self):
        return {"coin": "🪙 เหรียญ", "box": "📦 กล่อง", "exp": "⭐ EXP"}.get(
            self.mode_var.get(), self.mode_var.get())

    def _set_status(self, state):
        """อัปเดตป้ายสถานะบนแถบหัว (ข้อความ + สี ตัวอักษร/พื้นหลัง) — ตอนรันบอกโหมดด้วย"""
        cfg = {
            "stopped":  ("● หยุดอยู่",     C_RED,   "#3f1d1d"),
            "running":  (f"● กำลังทำงาน • {self._mode_txt()}", C_GREEN, "#123524"),
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
        if self.running or self.testing or self.act_running:
            self._enqueue("[app] เปลี่ยนขนาด UI ได้ตอนบอท/กิจกรรมหยุดอยู่เท่านั้น")
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
                self.v2_state_var.set(f"🎮 กำลังเล่น — โหมด{self._mode_txt()}")
                self.v2_state_lbl.config(fg=C_GREEN)
        self.root.after(1000, self._tick_uptime)

    def _tick_adb(self):
        """เช็คไฟสถานะ ADB ทุก 15 วิ (เฉพาะตอนบอทไม่รัน — ตอนรันใช้การอ่านจาก log แทน)"""
        if (not self.running and not self.testing and not self.closing
                and not self.act_running and not self._adb_checking):
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
        # เติมเวลา [HH:MM:SS.mmm] หน้าทุกบรรทัด — ไว้ดูว่าสเต็ปไหนใช้เวลานาน
        # (ดึง \n ที่คั่นหัวข้อออกไว้หน้าสุดก่อน ไม่งั้น timestamp ไปอยู่หน้าบรรทัดว่าง)
        msg = str(msg)
        lead = ""
        while msg.startswith("\n"):
            lead += "\n"
            msg = msg[1:]
        now = time.time()
        ts = time.strftime("%H:%M:%S", time.localtime(now)) + f".{int((now % 1) * 1000):03d}"
        self.log_queue.put(f"{lead}[{ts}] {msg}\n")

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

                # ตอนบอท/กิจกรรมรัน ใช้ log เป็นตัวบอกไฟ ADB (เช็คตรง ๆ ระหว่างรันจะไปกวน adb
                # และ _tick_adb ถูกข้ามระหว่าง act_running — ไม่งั้นไฟค้างเขียวทั้งที่หลุด)
                if self.running or self.act_running:
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
        if self.act_running:
            self._enqueue("[app] กิจกรรมเสริมกำลังรันอยู่ — หยุดกิจกรรมก่อนค่อยทดสอบ ADB")
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
        if self.act_running:
            self._enqueue("[app] กิจกรรมเสริมกำลังรันอยู่ — หยุดกิจกรรมก่อนค่อยกู้การเชื่อมต่อ")
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
            "stopped":  ("▶  เริ่มทำงานบอท",  C_EMERALD, C_EMER_HV, "normal"),
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
        if self.act_running:
            self._enqueue("[app] กิจกรรมเสริมกำลังรันอยู่ — กด ■ หยุดกิจกรรม ก่อนค่อยเริ่มบอท")
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
                    self._enqueue("[app] ❌ เชื่อมต่อ ADB ไม่ได้ — หยุด (ลองปุ่ม 🔌 กู้การเชื่อมต่อ ในแท็บ ⚙️ ระบบ)")
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
        self._enqueue("[app] สั่งหยุดแล้ว — บอทจะหยุดทันที "
                      "(อย่างช้าไม่เกินคำสั่ง ADB ที่ค้างท่ออยู่ ~1-2 วิ)")

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
    # กิจกรรมเสริม (แท็บ 🧩) — รันทีละกิจกรรม แยกจากบอทหลัก
    # ============================================================
    def _set_act_btns(self, state):
        """เปิด/ปิดปุ่มกิจกรรมทั้ง 7 พร้อมสี (สไตล์เดียวกับ _set_conn_btns)"""
        for b in getattr(self, "_act_btns", []):
            try:
                if state == "disabled":
                    b.config(state="disabled", bg=C_CARD, fg=C_DIM)
                else:
                    b.config(state="normal", bg=C_BLUE, fg="#ffffff")
            except tk.TclError:
                pass

    def _start_activity(self, key):
        if self.running:
            self._enqueue("[app] หยุดบอทหลักก่อน แล้วค่อยรันกิจกรรมเสริม")
            return
        if self.testing:
            self._enqueue("[app] กำลังทดสอบ/กู้การเชื่อมต่ออยู่ — รอให้เสร็จก่อนค่อยรันกิจกรรม")
            return
        if self.act_running:
            self._enqueue("[app] มีกิจกรรมรันอยู่ — กด ■ หยุดกิจกรรม ก่อน")
            return
        self._apply_config()
        self._save_salvage_batch()   # ยึดค่าย่อย/รอบ ในช่องล่าสุด (เผื่อยังไม่ blur ออกจากช่อง)
        try:
            count = max(0, int(self.act_count_var.get().strip() or "0"))
        except ValueError:
            count = 0

        labels = {"send_hearts": "💗 ส่งหัวใจ", "mail_hearts": "📬 รับหัวใจเมล",
                  "add_friends": "👥 เพิ่มเพื่อน", "treasure_gacha": "🔮 กาชาสมบัติ",
                  "salvage": "♻️ ย่อยผง", "treasure_upgrade": "💎 อัพเกรด +9",
                  "open_gift_box": "🎁 เปิดกล่องของขวัญ"}
        label = labels.get(key, key)

        # Event ใหม่ทุกครั้ง — อันเก่าถูก set ค้างไว้จากการหยุดรอบก่อน
        self.act_stop_event = threading.Event()
        self.act_running = True
        self._set_act_btns("disabled")
        self.toggle_btn.config(state="disabled")
        # กันกดเปลี่ยนขนาด UI ระหว่างกิจกรรม — ไฮไลต์ pill จะเลื่อนแต่ _apply_scale ไม่ทำงาน
        self.scale_selector.set_state("disabled")
        self.act_status_var.set(f"กำลังรัน: {label}...")

        def worker():
            try:
                if not self.adb.connected():
                    self._enqueue("[app] ❌ เชื่อมต่อ ADB ไม่ได้ — ยกเลิกกิจกรรม "
                                  "(ลองปุ่ม 🔌 กู้การเชื่อมต่อ ในแท็บ ⚙️ ระบบ)")
                    return
                acts = Activities(self.adb, log=self._enqueue,
                                  stop_event=self.act_stop_event)
                if key == "send_hearts":
                    acts.send_hearts()
                elif key == "mail_hearts":
                    acts.mail_hearts()
                elif key == "add_friends":
                    acts.add_friends(count)
                elif key == "treasure_gacha":
                    acts.treasure_gacha(count)
                elif key == "salvage":
                    acts.salvage(count)
                elif key == "treasure_upgrade":
                    acts.treasure_upgrade()
                elif key == "open_gift_box":
                    acts.open_gift_box(count)
            except Exception as e:
                import traceback
                self._enqueue(f"[app] ❌ กิจกรรมหยุดเพราะข้อผิดพลาด: {e}\n{traceback.format_exc()}")
            finally:
                self.act_running = False
                self._safe_after(self._on_activity_done)

        self.act_thread = threading.Thread(target=worker, daemon=True)
        self.act_thread.start()

    def _stop_activity(self):
        if not self.act_running:
            self._enqueue("[app] ไม่มีกิจกรรมกำลังรัน")
            return
        self.act_stop_event.set()
        self._enqueue("[app] สั่งหยุดกิจกรรม → รอจบขั้นที่ค้างอยู่...")
        self.act_status_var.set("กำลังหยุด...")

    def _on_activity_done(self):
        self._set_act_btns("normal")
        if not self.running:   # กันเคสประหลาด — ห้ามปลดล็อกปุ่มบอทถ้าบอทหลักรันอยู่
            try:
                self.toggle_btn.config(state="normal")
                self.scale_selector.set_state("normal")
            except tk.TclError:
                pass
        self.act_status_var.set("จบแล้ว — ดูสรุปใน log")

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
        self.act_stop_event.set()
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
