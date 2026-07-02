"""
app.py — หน้าต่างควบคุมบอท (GUI, tkinter)
==========================================
ปุ่มเริ่ม/หยุด + ตั้งค่า ADB + จำนวนรอบ + ตัวนับเหรียญ + log เรียลไทม์

รัน:  python app.py   (หรือดับเบิลคลิก run_gui.bat)
"""
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext

import config
from adb import Adb
from bot import CookieBot


class App:
    def __init__(self, root):
        self.root = root
        self.log_queue = queue.Queue()

        self.stop_event = threading.Event()
        self.bot_thread = None
        self.running = False
        self.closing = False
        self._max_loops = 0

        # log ของ ADB/บอท วิ่งเข้า queue (thread-safe) แล้ว pump ขึ้นจอที่ main thread
        self.adb = Adb(log=self._enqueue)

        self._build_ui()
        self._poll_log()

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
        r.geometry("560x740")
        r.minsize(520, 680)
        r.configure(bg="#2b2b3a")

        tk.Label(r, text="🍪  CookiePilot", font=("Segoe UI", 20, "bold"),
                 bg="#2b2b3a", fg="#ffd966").pack(pady=(14, 2))
        tk.Label(r, text="บอทเล่นเกมอัตโนมัติ (LDPlayer + ADB + OpenCV)",
                 font=("Segoe UI", 9, "italic"), bg="#2b2b3a", fg="#7ec8ff").pack()

        # --- กล่องตั้งค่า ADB ---
        cfg = tk.Frame(r, bg="#34344a")
        cfg.pack(fill="x", padx=16, pady=10)

        tk.Label(cfg, text="ADB path:", bg="#34344a", fg="#dddde8",
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.adb_var = tk.StringVar(value=self.adb.path)
        tk.Entry(cfg, textvariable=self.adb_var, width=42,
                 font=("Consolas", 9)).grid(row=0, column=1, padx=4, pady=6)
        tk.Button(cfg, text="หาอัตโนมัติ", command=self.auto_find_adb,
                  font=("Segoe UI", 8)).grid(row=0, column=2, padx=6)

        tk.Label(cfg, text="Device:", bg="#34344a", fg="#dddde8",
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", padx=8, pady=6)
        self.dev_var = tk.StringVar(value=self.adb.device)
        tk.Entry(cfg, textvariable=self.dev_var, width=22,
                 font=("Consolas", 9)).grid(row=1, column=1, sticky="w", padx=4, pady=6)
        tk.Button(cfg, text="ทดสอบเชื่อมต่อ", command=self.test_connection,
                  font=("Segoe UI", 8)).grid(row=1, column=2, padx=6)

        tk.Label(cfg, text="จำนวนรอบ:", bg="#34344a", fg="#dddde8",
                 font=("Segoe UI", 9)).grid(row=2, column=0, sticky="w", padx=8, pady=6)
        self.loops_var = tk.StringVar(value="0")
        tk.Entry(cfg, textvariable=self.loops_var, width=8, justify="center",
                 font=("Consolas", 9)).grid(row=2, column=1, sticky="w", padx=4, pady=6)
        tk.Label(cfg, text="(0 = ไม่จำกัด รันจนกดหยุด)", bg="#34344a", fg="#9a9ab0",
                 font=("Segoe UI", 8)).grid(row=2, column=2, sticky="w", padx=6)

        # --- สถานะ + ปุ่มหลัก ---
        self.status_var = tk.StringVar(value="● หยุดอยู่")
        self.status_lbl = tk.Label(r, textvariable=self.status_var,
                                   font=("Segoe UI", 11, "bold"), bg="#2b2b3a", fg="#ff6b6b")
        self.status_lbl.pack(pady=(2, 6))

        self.toggle_btn = tk.Button(r, text="▶  เริ่มบอท", command=self.toggle,
                                    font=("Segoe UI", 14, "bold"), bg="#4caf50", fg="white",
                                    activebackground="#43a047", width=20, height=1, bd=0,
                                    cursor="hand2")
        self.toggle_btn.pack(pady=4)

        self.coins_var = tk.StringVar(value="🪙 เหรียญรอบล่าสุด: -    รวม: 0")
        tk.Label(r, textvariable=self.coins_var, font=("Segoe UI", 12, "bold"),
                 bg="#2b2b3a", fg="#ffd966").pack(pady=(2, 6))

        tk.Label(r, text="บันทึกการทำงาน (log):", bg="#2b2b3a", fg="#b8b8c8",
                 font=("Segoe UI", 9)).pack(anchor="w", padx=18, pady=(8, 0))
        self.log = scrolledtext.ScrolledText(r, height=12, font=("Consolas", 9),
                                             bg="#1e1e28", fg="#d4d4d4",
                                             insertbackground="white", wrap="word")
        self.log.pack(fill="both", expand=True, padx=16, pady=(2, 14))

        r.protocol("WM_DELETE_WINDOW", self.on_close)

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
                self.log.insert("end", self.log_queue.get_nowait())
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
        self._apply_config()
        self._enqueue("[app] กำลังทดสอบการเชื่อมต่อ...")

        def worker():
            if self.adb.connected():
                dev = self.adb.device or ""
                self._safe_after(lambda: self.dev_var.set(dev))
                self._enqueue("[app] ✅ เชื่อมต่อสำเร็จ! แคปหน้าจอได้")
                if config.save_settings({"DEFAULT_ADB": self.adb.path,
                                         "DEFAULT_DEVICE": self.adb.device}):
                    self._enqueue("[app] จำค่า ADB path/Device ลง settings.json แล้ว")
            else:
                self._enqueue("[app] ❌ เชื่อมต่อไม่ได้ — เปิด LDPlayer และเช็ค ADB path/Device")

        threading.Thread(target=worker, daemon=True).start()

    # ============================================================
    # เริ่ม/หยุด บอท
    # ============================================================
    def toggle(self):
        if self.running:
            self.stop_bot()
        else:
            self.start_bot()

    def start_bot(self):
        self._apply_config()

        try:
            max_loops = max(0, int(self.loops_var.get().strip() or "0"))
        except ValueError:
            max_loops = 0
        self._max_loops = max_loops

        self.stop_event = threading.Event()
        self.bot = CookieBot(self.adb, log=self._enqueue,
                             on_coins=self._on_coins, on_loop=self._on_loop,
                             stop_event=self.stop_event)

        self.running = True
        self.toggle_btn.config(text="■  หยุดบอท", bg="#ff5252", activebackground="#e53935")
        self.status_var.set("● กำลังทำงาน")
        self.status_lbl.config(fg="#69f0ae")
        self.coins_var.set("🪙 เหรียญรอบล่าสุด: -    รวม: 0")
        if max_loops:
            self._enqueue(f"\n[app] ===== เริ่มบอท (จะเล่น {max_loops} รอบแล้วหยุด) =====")
        else:
            self._enqueue("\n[app] ===== เริ่มบอท (ไม่จำกัดรอบ) =====")

        def worker():
            try:
                if not self.adb.connected():
                    self._enqueue("[app] ❌ เชื่อมต่อ ADB ไม่ได้ — หยุด")
                    return
                # จำค่าที่ใช้ได้จริงไว้ เปิดโปรแกรมครั้งหน้าไม่ต้องกรอกใหม่
                config.save_settings({"DEFAULT_ADB": self.adb.path,
                                      "DEFAULT_DEVICE": self.adb.device})
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
        self.status_var.set("● กำลังหยุด...")
        self.status_lbl.config(fg="#ffd166")
        self.toggle_btn.config(state="disabled")
        self._enqueue("[app] กำลังหยุด (รอจบ state ปัจจุบัน)...")

    def _on_bot_stopped(self):
        self.running = False
        self.toggle_btn.config(text="▶  เริ่มบอท", bg="#4caf50",
                               activebackground="#43a047", state="normal")
        self.status_var.set("● หยุดอยู่")
        self.status_lbl.config(fg="#ff6b6b")

    # ============================================================
    # callbacks จากบอท (เรียกจาก bot thread → เด้งกลับ main thread)
    # ============================================================
    def _on_coins(self, coins, total):
        def upd():
            last = f"{coins:,}" if coins is not None else "อ่านไม่ได้"
            self.coins_var.set(f"🪙 เหรียญรอบล่าสุด: {last}    รวม: {total:,}")
        self._safe_after(upd)

    def _on_loop(self, loops_done):
        if self._max_loops:
            remaining = max(0, self._max_loops - loops_done)
            self._safe_after(lambda: self.loops_var.set(str(remaining)))

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
                config.IMG_MODE_POPUP, config.IMG_SENDLIFE_POPUP,
                config.IMG_MULTI_CHECK] + [it["check_img"] for it in config.BOOST_ITEMS]
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
    print(out)


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
