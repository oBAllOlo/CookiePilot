"""
app.py — หน้าต่างควบคุมบอท (GUI, tkinter)
==========================================
ปุ่มเริ่ม/หยุด + ตั้งค่า ADB + จำนวนรอบ + แดชบอร์ดสถิติสด + log เรียลไทม์

รัน:  python app.py   (หรือดับเบิลคลิก run_gui.bat)
"""
import queue
import threading
import time
import tkinter as tk
from tkinter import scrolledtext

import config
from adb import Adb
from bot import CookieBot


class PillSelector:
    def __init__(self, parent, variable, options, command=None):
        self.parent = parent
        self.variable = variable
        self.options = options
        self.command = command

        self.frame = tk.Frame(parent, bg="#0f172a", highlightthickness=1, highlightbackground="#334155")
        self.buttons = {}

        for text, val in options:
            btn = tk.Button(self.frame, text=text, font=("Segoe UI", 9, "bold"), bd=0, relief="flat", cursor="hand2")
            btn.config(command=lambda v=val: self.select(v))
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
            if val == current_val:
                btn.config(bg="#3b82f6", fg="#ffffff", activebackground="#2563eb", activeforeground="#ffffff")
                btn.unbind("<Enter>")
                btn.unbind("<Leave>")
            else:
                btn.config(bg="#1e293b", fg="#94a3b8", activebackground="#334155", activeforeground="#f8fafc")
                btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#334155", fg="#f8fafc") if b["state"] != "disabled" else None)
                btn.bind("<Leave>", lambda e, b=btn: b.config(bg="#1e293b", fg="#94a3b8") if b["state"] != "disabled" else None)

    def set_state(self, state):
        for btn in self.buttons.values():
            btn.config(state=state)
            if state == "disabled":
                btn.config(bg="#1e293b", fg="#475569")
        if state == "normal":
            self.update_ui()


class App:
    def __init__(self, root):
        self.root = root
        self.log_queue = queue.Queue()

        self.stop_event = threading.Event()
        self.bot_thread = None
        self.running = False
        self.testing = False   # มี worker ทดสอบเชื่อมต่อค้างอยู่ไหม (กันสตาร์ตบอทซ้อน)
        self.closing = False
        self._max_loops = 0

        # log ของ ADB/บอท วิ่งเข้า queue (thread-safe) แล้ว pump ขึ้นจอที่ main thread
        self.adb = Adb(log=self._enqueue)

        # ตัวนับสถิติของ session ปัจจุบัน (ใช้คำนวณ uptime / เหรียญต่อชม. / เฉลี่ย / สูงสุด)
        self.session_start = None      # เวลาที่กดเริ่มบอท (time.time()) — None = ยังไม่เริ่ม
        self._total_coins = 0          # เหรียญสะสมรวม (ตัวเลขล้วน ไว้คำนวณ rate/avg)
        self.coin_readable_count = 0   # จำนวนรอบที่อ่านเลขเหรียญได้ (ตัวหารของค่าเฉลี่ย)
        self.coin_best = 0             # เหรียญสูงสุดที่เคยได้ใน 1 รอบ

        self._build_ui()
        self._poll_log()
        self._tick_uptime()            # นาฬิกาเดินเวลารัน + เหรียญต่อชม. (อัปเดตทุก 1 วิ)

        # แจ้งผลการโหลด settings.json (override ค่า / ไฟล์เสีย)
        if config.SETTINGS_ERROR:
            self._enqueue(f"[app] ⚠ {config.SETTINGS_ERROR}")
        elif config.SETTINGS_APPLIED:
            self._enqueue("[app] โหลด settings.json แล้ว (override: "
                          + ", ".join(config.SETTINGS_APPLIED) + ")")

    # ============================================================
    # UI
    # ============================================================
    def _build_ui(self):
        r = self.root
        r.title(f"{config.APP_NAME} v{config.APP_VERSION}")
        r.geometry("580x830")
        r.minsize(540, 720)
        r.configure(bg="#0f172a")

        # ---------- ตัวช่วยจัดสไตล์ ----------
        def make_card(parent, **kwargs):
            return tk.Frame(parent, bg="#1e293b", highlightthickness=1,
                            highlightbackground="#334155", **kwargs)

        def make_btn(parent, text, command, bg="#3b82f6", fg="#ffffff",
                     hover_bg="#2563eb", hover_fg="#ffffff",
                     font=("Segoe UI", 9, "bold"), **kwargs):
            btn = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                            activebackground=hover_bg, activeforeground=hover_fg,
                            disabledforeground="#64748b", font=font, bd=0,
                            relief="flat", cursor="hand2", **kwargs)
            def on_enter(e):
                if btn["state"] == "normal":
                    btn.config(bg=hover_bg, fg=hover_fg)
            def on_leave(e):
                if btn["state"] == "normal":
                    btn.config(bg=bg, fg=fg)
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)
            return btn

        def make_entry(parent, textvariable, width, font=("Consolas", 10), justify="left"):
            border_frame = tk.Frame(parent, bg="#334155", highlightthickness=0)
            inner_frame = tk.Frame(border_frame, bg="#0b0f19", padx=6, pady=4)
            inner_frame.pack(fill="both", expand=True, padx=1, pady=1)
            entry = tk.Entry(inner_frame, textvariable=textvariable, width=width,
                             bg="#0b0f19", fg="#f8fafc", insertbackground="#f8fafc",
                             font=font, bd=0, relief="flat", justify=justify)
            entry.pack(fill="both", expand=True)
            def on_focus_in(e):
                if entry["state"] == "normal":
                    border_frame.config(bg="#3b82f6")
            def on_focus_out(e):
                if entry["state"] == "normal":
                    border_frame.config(bg="#334155")
            entry.bind("<FocusIn>", on_focus_in)
            entry.bind("<FocusOut>", on_focus_out)
            return border_frame, entry

        def make_chip(parent, col, caption, var, value_fg):
            """ช่องสถิติแบบมีกรอบ (เวลารัน / รอบ / เหรียญต่อชม.)"""
            box = tk.Frame(parent, bg="#0f1a2e", highlightthickness=1, highlightbackground="#334155")
            box.grid(row=0, column=col, sticky="nsew", padx=4)
            tk.Label(box, text=caption, font=("Segoe UI", 8, "bold"),
                     bg="#0f1a2e", fg="#94a3b8").pack(pady=(7, 0))
            tk.Label(box, textvariable=var, font=("Segoe UI", 13, "bold"),
                     bg="#0f1a2e", fg=value_fg).pack(pady=(1, 8))

        def make_mini(parent, col, caption, var, value_fg):
            """สถิติย่อยไม่มีกรอบ (รอบล่าสุด / เฉลี่ย / สูงสุด)"""
            cell = tk.Frame(parent, bg="#1e293b")
            cell.grid(row=0, column=col, sticky="nsew", padx=4)
            tk.Label(cell, text=caption, font=("Segoe UI", 8, "bold"),
                     bg="#1e293b", fg="#94a3b8").pack(anchor="center")
            tk.Label(cell, textvariable=var, font=("Segoe UI", 12, "bold"),
                     bg="#1e293b", fg=value_fg).pack(anchor="center", pady=(2, 0))

        # ---------- 1) แถบหัว + ป้ายสถานะ (ติดบนสุดเสมอ) ----------
        bar = tk.Frame(r, bg="#0b1220")
        bar.pack(fill="x")
        bar_in = tk.Frame(bar, bg="#0b1220")
        bar_in.pack(fill="x", padx=18, pady=12)

        tk.Label(bar_in, text="🍪 CookiePilot", font=("Segoe UI", 15, "bold"),
                 bg="#0b1220", fg="#fbbf24").pack(side="left")
        tk.Label(bar_in, text=f"v{config.APP_VERSION}", font=("Segoe UI", 9),
                 bg="#0b1220", fg="#64748b").pack(side="left", padx=(6, 0))

        self.status_pill = tk.Frame(bar_in, bg="#3f1d1d")
        self.status_pill.pack(side="right")
        self.status_var = tk.StringVar(value="● หยุดอยู่")
        self.status_lbl = tk.Label(self.status_pill, textvariable=self.status_var,
                                   font=("Segoe UI", 9, "bold"), bg="#3f1d1d",
                                   fg="#f87171", padx=12, pady=4)
        self.status_lbl.pack()
        tk.Frame(r, bg="#334155", height=1).pack(fill="x")

        # ---------- 2) แดชบอร์ดสถิติสด (hero) ----------
        hero = make_card(r)
        hero.pack(fill="x", padx=18, pady=(14, 8))

        tk.Label(hero, text="🪙 เหรียญสะสมรวม", font=("Segoe UI", 9, "bold"),
                 bg="#1e293b", fg="#94a3b8").pack(pady=(12, 0))
        self.total_coins_var = tk.StringVar(value="0")
        self.total_lbl = tk.Label(hero, textvariable=self.total_coins_var,
                                  font=("Segoe UI", 34, "bold"), bg="#1e293b", fg="#fbbf24")
        self.total_lbl.pack(pady=(0, 8))

        chips = tk.Frame(hero, bg="#1e293b")
        chips.pack(fill="x", padx=10, pady=(0, 10))
        for i in range(3):
            chips.columnconfigure(i, weight=1)
        self.uptime_var = tk.StringVar(value="00:00:00")
        self.loops_done_var = tk.StringVar(value="-")
        self.rate_var = tk.StringVar(value="-")
        make_chip(chips, 0, "⏱ เวลารัน", self.uptime_var, "#e2e8f0")
        make_chip(chips, 1, "🔁 รอบที่เล่น", self.loops_done_var, "#fbbf24")
        make_chip(chips, 2, "⚡ เหรียญ/ชม.", self.rate_var, "#34d399")

        tk.Frame(hero, bg="#334155", height=1).pack(fill="x", padx=12, pady=(2, 0))
        mini = tk.Frame(hero, bg="#1e293b")
        mini.pack(fill="x", padx=6, pady=(8, 12))
        for i in range(3):
            mini.columnconfigure(i, weight=1)
        self.recent_coins_var = tk.StringVar(value="-")
        self.avg_var = tk.StringVar(value="-")
        self.best_var = tk.StringVar(value="-")
        make_mini(mini, 0, "เหรียญรอบล่าสุด", self.recent_coins_var, "#34d399")
        make_mini(mini, 1, "เฉลี่ย/รอบ", self.avg_var, "#e2e8f0")
        make_mini(mini, 2, "สูงสุด/รอบ", self.best_var, "#fbbf24")

        # ---------- 3) ควบคุมการทำงาน ----------
        ctrl = make_card(r)
        ctrl.pack(fill="x", padx=18, pady=8)

        tk.Label(ctrl, text="โหมดบอท", bg="#1e293b", fg="#94a3b8",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 6))
        saved_mode = str(config.BOT_MODE or "coin").strip().lower()
        self.mode_var = tk.StringVar(value=saved_mode if saved_mode in ("coin", "box") else "coin")
        self.mode_selector = PillSelector(ctrl, self.mode_var, [
            ("🪙 รีโรลเหรียญ (Coin Reroll)", "coin"),
            ("📦 วิ่งเก็บกล่อง (Fast Start)", "box"),
        ])
        self.mode_selector.frame.pack(fill="x", padx=10, pady=(0, 10))

        self.toggle_btn = tk.Button(ctrl, command=self.toggle, font=("Segoe UI", 13, "bold"),
                                    bd=0, relief="flat", cursor="hand2")
        self._update_toggle_btn("stopped")
        self.toggle_btn.pack(fill="x", padx=10, pady=(0, 12), ipady=8)

        # ---------- 4) ตั้งค่า ADB (พับเก็บได้ — คลิกหัวข้อเพื่อย่อ/ขยาย) ----------
        self.settings_card = make_card(r)
        self.settings_card.pack(fill="x", padx=18, pady=8)

        self.settings_open = True
        self.settings_chevron = tk.StringVar(value="▾")
        head = tk.Frame(self.settings_card, bg="#1e293b", cursor="hand2")
        head.pack(fill="x", padx=6, pady=8)
        head_title = tk.Label(head, text="⚙️ ตั้งค่าการเชื่อมต่อ (ADB)", font=("Segoe UI", 10, "bold"),
                              bg="#1e293b", fg="#f8fafc", cursor="hand2")
        head_title.pack(side="left", padx=6)
        head_chev = tk.Label(head, textvariable=self.settings_chevron, font=("Segoe UI", 10, "bold"),
                             bg="#1e293b", fg="#94a3b8", cursor="hand2")
        head_chev.pack(side="right", padx=8)
        for w in (head, head_title, head_chev):
            w.bind("<Button-1>", lambda e: self._toggle_settings())

        body = self.settings_body = tk.Frame(self.settings_card, bg="#1e293b")
        body.pack(fill="x", padx=6, pady=(0, 8))

        # ADB Path
        tk.Label(body, text="ADB Path:", bg="#1e293b", fg="#94a3b8",
                 font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w", padx=6, pady=6)
        self.adb_var = tk.StringVar(value=self.adb.path)
        adb_border, self.adb_entry = make_entry(body, self.adb_var, width=30)
        adb_border.grid(row=0, column=1, padx=4, pady=6, sticky="ew")
        self.auto_find_btn = make_btn(body, text="หาอัตโนมัติ", command=self.auto_find_adb, padx=10, pady=2)
        self.auto_find_btn.grid(row=0, column=2, padx=6)

        # Device
        tk.Label(body, text="Device:", bg="#1e293b", fg="#94a3b8",
                 font=("Segoe UI", 9, "bold")).grid(row=1, column=0, sticky="w", padx=6, pady=6)
        self.dev_var = tk.StringVar(value=self.adb.device)
        dev_border, self.dev_entry = make_entry(body, self.dev_var, width=18)
        dev_border.grid(row=1, column=1, sticky="w", padx=4, pady=6)
        self.test_btn = make_btn(body, text="ทดสอบเชื่อมต่อ", command=self.test_connection, padx=10, pady=2)
        self.test_btn.grid(row=1, column=2, padx=6)

        # จำนวนรอบ
        tk.Label(body, text="จำนวนรอบ:", bg="#1e293b", fg="#94a3b8",
                 font=("Segoe UI", 9, "bold")).grid(row=2, column=0, sticky="w", padx=6, pady=6)
        self.loops_var = tk.StringVar(value="0")
        loops_border, self.loops_entry = make_entry(body, self.loops_var, width=8, justify="center")
        loops_border.grid(row=2, column=1, sticky="w", padx=4, pady=6)
        tk.Label(body, text="(0 = ไม่จำกัด รันจนกดหยุด)", bg="#1e293b", fg="#64748b",
                 font=("Segoe UI", 9)).grid(row=2, column=2, sticky="w", padx=6)
        body.columnconfigure(1, weight=1)

        # ---------- 5) Log Viewer ----------
        card_log = make_card(r)
        card_log.pack(fill="both", expand=True, padx=18, pady=(8, 18))
        tk.Label(card_log, text="📝 บันทึกการทำงาน (Log Terminal)", font=("Segoe UI", 9, "bold"),
                 bg="#1e293b", fg="#94a3b8").pack(anchor="w", padx=12, pady=(10, 4))
        self.log = scrolledtext.ScrolledText(card_log, font=("Consolas", 9), bg="#0b0f19",
                                             fg="#e2e8f0", insertbackground="white", wrap="word",
                                             bd=0, highlightthickness=0)
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # สีข้อความ log ตามประเภท
        self.log.tag_config("tag_ok", foreground="#34d399")
        self.log.tag_config("tag_err", foreground="#f87171")
        self.log.tag_config("tag_nav", foreground="#60a5fa")
        self.log.tag_config("tag_box", foreground="#fb923c")
        self.log.tag_config("tag_info", foreground="#fbbf24")
        self.log.tag_config("tag_app", foreground="#c084fc")
        self.log.tag_config("tag_normal", foreground="#e2e8f0")

        self._set_status("stopped")
        r.protocol("WM_DELETE_WINDOW", self.on_close)

    # ============================================================
    # ตัวช่วย UI / สถิติสด
    # ============================================================
    def _set_status(self, state):
        """อัปเดตป้ายสถานะบนแถบหัว (ข้อความ + สี ตัวอักษร/พื้นหลัง)"""
        cfg = {
            "stopped":  ("● หยุดอยู่",     "#f87171", "#3f1d1d"),
            "running":  ("● กำลังทำงาน",   "#34d399", "#123524"),
            "stopping": ("● กำลังหยุด...",  "#fbbf24", "#3a2e0a"),
        }
        text, fg, bg = cfg[state]
        self.status_var.set(text)
        self.status_pill.config(bg=bg)
        self.status_lbl.config(fg=fg, bg=bg)

    def _toggle_settings(self):
        """ย่อ/ขยายกล่องตั้งค่า ADB"""
        if self.settings_open:
            self.settings_body.pack_forget()
            self.settings_chevron.set("▸")
        else:
            self.settings_body.pack(fill="x", padx=6, pady=(0, 8))
            self.settings_chevron.set("▾")
        self.settings_open = not self.settings_open

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
        """เดินนาฬิกาเวลารัน + รีเฟรชเหรียญ/ชม. ทุก 1 วินาที (อัปเดตเฉพาะตอนบอททำงาน)"""
        if self.running and self.session_start is not None:
            elapsed = time.time() - self.session_start
            self.uptime_var.set(self._fmt_hms(elapsed))
            self._refresh_rate(elapsed)
        self.root.after(1000, self._tick_uptime)

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
                elif "[*]" in msg_lower:
                    tag = "tag_info"
                elif "[app]" in msg_lower:
                    tag = "tag_app"

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

    def test_connection(self):
        if self.running:
            self._enqueue("[app] บอทกำลังทำงานอยู่ — หยุดบอทก่อนค่อยทดสอบ/แก้ค่า ADB")
            return
        if self.testing:
            self._enqueue("[app] กำลังทดสอบอยู่แล้ว — รอผลสักครู่")
            return
        self._apply_config()
        self._enqueue("[app] กำลังทดสอบการเชื่อมต่อ...")
        self.testing = True

        self.test_btn.config(state="disabled", bg="#1e293b", fg="#64748b")
        self.auto_find_btn.config(state="disabled", bg="#1e293b", fg="#64748b")

        def worker():
            try:
                if self.adb.connected():
                    dev = self.adb.device or ""
                    self._safe_after(lambda: self.dev_var.set(dev))
                    self._enqueue("[app] ✅ เชื่อมต่อสำเร็จ! แคปหน้าจอได้")
                    if config.save_settings({"DEFAULT_ADB": self.adb.path,
                                             "DEFAULT_DEVICE": self.adb.device}):
                        self._enqueue("[app] จำค่า ADB path/Device ลง settings.json แล้ว")
                else:
                    self._enqueue("[app] ❌ เชื่อมต่อไม่ได้ — เปิด LDPlayer และเช็ค ADB path/Device")
            finally:
                self.testing = False
                def restore_btns():
                    self.test_btn.config(state="normal", bg="#3b82f6", fg="#ffffff")
                    self.auto_find_btn.config(state="normal", bg="#3b82f6", fg="#ffffff")
                self._safe_after(restore_btns)

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
        if state_type == "stopped":
            self.toggle_btn.config(text="▶  เริ่มทำงานบอท", bg="#10b981", fg="#ffffff", activebackground="#059669", activeforeground="#ffffff", state="normal")
            self.toggle_btn_bg = "#10b981"
            self.toggle_btn_hover = "#059669"
        elif state_type == "running":
            self.toggle_btn.config(text="■  หยุดทำงานบอท", bg="#ef4444", fg="#ffffff", activebackground="#dc2626", activeforeground="#ffffff", state="normal")
            self.toggle_btn_bg = "#ef4444"
            self.toggle_btn_hover = "#dc2626"
        elif state_type == "stopping":
            self.toggle_btn.config(text="●  กำลังหยุดบอท...", bg="#f59e0b", fg="#ffffff", activebackground="#d97706", activeforeground="#ffffff", state="disabled")
            self.toggle_btn_bg = "#f59e0b"
            self.toggle_btn_hover = "#d97706"

        # Update/rebind hover bindings to match active states
        def on_enter(e):
            if self.toggle_btn["state"] == "normal":
                self.toggle_btn.config(bg=self.toggle_btn_hover)
        def on_leave(e):
            if self.toggle_btn["state"] == "normal":
                self.toggle_btn.config(bg=self.toggle_btn_bg)

        self.toggle_btn.bind("<Enter>", on_enter)
        self.toggle_btn.bind("<Leave>", on_leave)

    def start_bot(self):
        if self.testing:
            self._enqueue("[app] กำลังทดสอบเชื่อมต่ออยู่ — รอให้เสร็จก่อนค่อยเริ่มบอท")
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
                             stop_event=self.stop_event, mode=mode)

        self.running = True
        self._update_toggle_btn("running")

        self.test_btn.config(state="disabled", bg="#1e293b", fg="#64748b")
        self.auto_find_btn.config(state="disabled", bg="#1e293b", fg="#64748b")
        self.adb_entry.config(state="disabled", fg="#64748b")
        self.dev_entry.config(state="disabled", fg="#64748b")
        self.loops_entry.config(state="disabled", fg="#64748b")
        self.mode_selector.set_state("disabled")
        if self.settings_open:   # พับตั้งค่าเก็บระหว่างรัน ให้เห็นแดชบอร์ด/log เต็มตา
            self._toggle_settings()

        self._set_status("running")

        # รีเซ็ตสถิติของ session ใหม่
        self.session_start = time.time()
        self._total_coins = 0
        self.coin_readable_count = 0
        self.coin_best = 0
        self.uptime_var.set("00:00:00")
        self.rate_var.set("-")
        self.avg_var.set("-")
        self.best_var.set("-")
        self.recent_coins_var.set("-")
        self.total_coins_var.set("0")
        if max_loops:
            self.loops_done_var.set(f"0 / {max_loops}")
        else:
            self.loops_done_var.set("0")

        mode_txt = "วิ่งเก็บกล่อง (Fast Start)" if mode == "box" else "รีโรลเหรียญ"
        if max_loops:
            self._enqueue(f"\n[app] ===== เริ่มบอท โหมด{mode_txt} (จะเล่น {max_loops} รอบแล้วหยุด) =====")
        else:
            self._enqueue(f"\n[app] ===== เริ่มบอท โหมด{mode_txt} (ไม่จำกัดรอบ) =====")

        def worker():
            try:
                if not self.adb.connected():
                    self._enqueue("[app] ❌ เชื่อมต่อ ADB ไม่ได้ — หยุด")
                    return
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
        self._update_toggle_btn("stopped")

        self.test_btn.config(state="normal", bg="#3b82f6", fg="#ffffff")
        self.auto_find_btn.config(state="normal", bg="#3b82f6", fg="#ffffff")
        self.adb_entry.config(state="normal", fg="#f8fafc")
        self.dev_entry.config(state="normal", fg="#f8fafc")
        self.loops_entry.config(state="normal", fg="#f8fafc")
        self.mode_selector.set_state("normal")
        if not self.settings_open:   # คลี่ตั้งค่ากลับมาให้พร้อมปรับก่อนรันรอบใหม่
            self._toggle_settings()

        self._set_status("stopped")

    # ============================================================
    # callbacks จากบอท (เรียกจาก bot thread → เด้งกลับ main thread)
    # ============================================================
    def _on_coins(self, coins, total):
        def upd():
            self._total_coins = total
            self.total_coins_var.set(f"{total:,}")
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
        self._safe_after(upd)

    def _on_loop(self, loops_done):
        if self._max_loops:
            self._safe_after(lambda: self.loops_done_var.set(f"{loops_done} / {self._max_loops}"))
        else:
            self._safe_after(lambda: self.loops_done_var.set(str(loops_done)))

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
