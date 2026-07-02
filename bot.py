"""
bot.py — บอทหลัก (State Machine 3 สถานะ, 2 โหมด)
================================================
โหมด "coin" (เดิม — รีโรลเหรียญ):
  STATE 1 REROLL : นำทางไปหน้าเตรียมตัว → ใช้ Multi-Buy สุ่มหา Double Coins → ติ๊กบูสต์ → กด Play
  STATE 2 RUN    : กดกระโดดสุ่มดีเลย์ + คอยกด relay + กันจอค้าง → จนเจอหน้า Result
  STATE 3 RESULT : กด OK กลับล็อบบี้ + อ่านจำนวนเหรียญบันทึกลง CSV → วนกลับ STATE 1

โหมด "box" (วิ่งเก็บกล่อง — Fast Start):
  STATE 1 PREP   : นำทางไปหน้าเตรียมตัว → ซื้อ Fast Start (ไม่รีโรล) → ติ๊กบูสต์ → กด Play
  STATE 2 RUN    : ไม่กดอะไรเลย ปล่อยคุกกี้วิ่งเก็บกล่องเอง (ไม่กดกระโดด/ไม่กดนินจา relay)
  STATE 3 RESULT : เหมือนโหมดเดิม

ใช้งาน:
    from adb import Adb
    from bot import CookieBot
    bot = CookieBot(Adb(), mode="box")   # ไม่ใส่ mode = ใช้ config.BOT_MODE
    bot.run(max_loops=10)      # 0 = ไม่จำกัด
หยุดด้วย bot.stop.set()  (หรือส่ง threading.Event เข้ามาเอง)
"""
import os
import time
import random
import datetime
import threading
import traceback
from enum import Enum, auto

import cv2

import config
import vision
from paths import data_path


class State(Enum):
    REROLL = auto()
    RUN = auto()
    RESULT = auto()


class CookieBot:
    def __init__(self, adb, log=print, on_coins=None, on_loop=None,
                 stop_event=None, mode=None):
        self.adb = adb
        self.log = log
        self.on_coins = on_coins          # callback(coins, total) — อัปเดต GUI
        self.on_loop = on_loop            # callback(loops_done)    — นับถอยหลัง GUI
        self.stop = stop_event or threading.Event()
        self.coin_reader = vision.CoinReader(log)
        self.coin_total = 0
        # โหมดบอท: "coin" = รีโรลเหรียญ (เดิม) / "box" = วิ่งเก็บกล่อง (Fast Start)
        # str() กันค่าใน settings.json ที่ไม่ใช่ string (เช่น true/123) ทำ .lower() พัง
        self.mode = str(mode or config.BOT_MODE or "coin").strip().lower()
        if self.mode not in ("coin", "box"):
            self.log(f"[bot] ไม่รู้จักโหมด '{self.mode}' → ใช้โหมด coin แทน")
            self.mode = "coin"

    # ============================================================
    # ตัวช่วย
    # ============================================================
    def _stopping(self):
        return self.stop.is_set()

    def _cap(self):
        return self.adb.screencap()

    # ============================================================
    # นำทางเข้า "หน้าเตรียมตัว"
    # ============================================================
    def ensure_on_boost_screen(self, max_tries=15):
        """
        พาไปอยู่หน้าเตรียมตัว (Buy some Boosts):
          - ปิดป๊อปอัปที่รู้จัก, ค้างหน้า Result → กด OK, อยู่ล็อบบี้ → กด Play,
            มีป๊อปอัปรางวัลบัง → กดปุ่ม Confirm กลางล่าง 2 จุด
        (ไม่ใช้ปุ่ม Back เพราะที่ล็อบบี้จะเด้ง "Exit game?")
        คืน True ถ้าถึงหน้าเตรียมตัว
        """
        x_close_tries = 0
        for i in range(max_tries):
            if self._stopping():
                return False
            screen = self._cap()

            # 1) ปิดป๊อปอัปที่รู้จัก
            dismissed = False
            for pop in config.DISMISS_POPUPS:
                m = vision.find(screen, pop["img"], pop["th"])
                if not m.found:
                    continue
                if x_close_tries < 3:
                    self.log(f"[nav] เจอป๊อปอัป {pop['name']} (score={m.score:.2f}) → กดปิด X ที่ {pop['x']}")
                    self.adb.tap(*pop["x"])
                    x_close_tries += 1
                    time.sleep(0.9)
                else:
                    self.log(f"[nav] กดปิด X หลายครั้งแล้วยังเจอ {pop['name']} → หยุดกด X")
                    time.sleep(0.8)
                dismissed = True
                break
            if dismissed:
                continue
            x_close_tries = 0

            # 2) ถึงหน้าเตรียมตัวแล้ว → จบ
            if vision.find(screen, config.IMG_BOOST_SCREEN).found:
                if i > 0:
                    self.log("[nav] ถึงหน้าเตรียมตัวแล้ว")
                return True

            # 3) ค้างหน้า Result → กด OK
            ok = vision.find(screen, config.IMG_OK_BUTTON)
            if ok.found:
                self.log("[nav] ค้างหน้า Result → กด OK")
                self.adb.tap(*ok.center)
                time.sleep(2.5)
                continue

            # 4) อยู่ล็อบบี้ → กด Play
            lobby = vision.find(screen, config.IMG_LOBBY_PLAY)
            if lobby.found:
                self.log(f"[nav] อยู่ล็อบบี้ (ครั้งที่ {i + 1}) → กด Play")
                self.adb.tap(*lobby.center)
                time.sleep(config.DELAY_AFTER_PLAY)
                continue

            # 5) มีป๊อปอัปบัง → กดปุ่ม Confirm/Open all 2 จุด
            self.log(f"[nav] มีป๊อปอัปบัง (ครั้งที่ {i + 1}) → กด Confirm/Open all 2 จุด")
            self.adb.tap(*config.BTN_POPUP_CONFIRM)
            time.sleep(0.4)
            self.adb.tap(*config.BTN_POPUP_CONFIRM_LOW)
            time.sleep(1.2)

        self.log("[WARN] เข้าหน้าเตรียมตัวไม่ได้ภายในที่กำหนด")
        return False

    # ============================================================
    # STATE 1 — REROLL
    # ============================================================
    def multibuy_until_target(self):
        """
        ใช้ระบบ Multi-Buy ในเกมสุ่มซื้อบูสต์จนได้ Double Coins:
          1) เปิดกล่อง Random Boost → เปิดหน้า Multi
          2) ติ๊กบูสต์ที่ยอมรับ (config.MULTI_SELECT_TARGETS)
          3) กด Multi-Buy → เกมสุ่มซื้อเองจนได้ แล้วรอจนเจอ Double Coins
        คืน True ถ้าเจอ Double Coins
        """
        self.log("[reroll] เลือกกล่อง Random Boost")
        self.adb.tap(*config.BTN_BOX)
        time.sleep(0.8)
        self.log("[reroll] เปิดหน้า Multi (เลือกบูสต์ที่ต้องการ)")
        self.adb.tap(*config.BTN_MULTI)
        time.sleep(1.0)

        dlg = self._cap()
        for cx, cy in config.MULTI_SELECT_TARGETS:
            roi = (cx - 30, cy - 30, cx + 30, cy + 30)
            checked, sc = vision.find_in_roi(dlg, config.IMG_MULTI_CHECK, roi,
                                             config.MULTI_CHECK_THRESHOLD)
            if checked:
                self.log(f"    บูสต์ ({cx},{cy}) ติ๊กอยู่แล้ว (score={sc:.2f}) → ข้าม")
                continue
            self.log(f"    บูสต์ ({cx},{cy}) ยังไม่ติ๊ก (score={sc:.2f}) → กดเลือก")
            self.adb.tap(cx, cy)
            time.sleep(0.4)

        self.log("[reroll] กด Multi-Buy → ให้เกมสุ่มซื้อเองจนได้บูสต์ที่เลือก")
        self.adb.tap(*config.BTN_MULTI_BUY)

        start = time.time()
        while time.time() - start < config.MULTIBUY_TIMEOUT:
            if self._stopping():
                return False
            time.sleep(1.0)
            m = vision.find(self._cap(), config.IMG_TARGET_ITEM)
            if m.found:
                self.log(f"[reroll] ได้ Double Coins แล้ว (score={m.score:.3f})")
                return True

        self.log("[reroll] หมดเวลา Multi-Buy → ปิดหน้า Multi")
        self.adb.tap(*config.BTN_MULTI_CLOSE)
        time.sleep(1.0)
        return False

    def ensure_boosts_selected(self):
        """
        ติ๊กบูสต์ทั้ง 3 ก่อนเริ่มเกม:
          - ไอเทมไหนยังไม่เห็นเครื่องหมายถูก → กดเปิดใช้
          - เห็นถูกแล้ว → ข้าม (กันกดซ้ำจน toggle ปิด)
        เช็คซ้ำได้สูงสุด 3 รอบ (เผื่อรอแอนิเมชัน)
        """
        self.log("[*] ตรวจสอบ Boost 3 ไอเทม...")
        for _ in range(3):
            screen = self._cap()
            all_on = True
            for item in config.BOOST_ITEMS:
                checked, sc = vision.find_in_roi(screen, item["check_img"],
                                                 item["check_roi"], config.CHECK_THRESHOLD)
                if checked:
                    self.log(f"    [{item['name']}] ติ๊กแล้ว (score={sc:.2f})")
                    continue
                self.log(f"    [{item['name']}] ยังไม่ติ๊ก (score={sc:.2f}) → กดเปิดใช้")
                self.adb.tap(*item["tap"])
                time.sleep(0.7)
                all_on = False
            if all_on:
                self.log("[*] Boost ครบทั้ง 3 อันแล้ว")
                return
        self.log("[*] จบการตรวจ Boost (อาจมีบางอันของหมด)")

    def state_reroll(self):
        self.log("\n===== [STATE 1] REROLL — Multi-Buy หา Double Coins =====")
        if not self.ensure_on_boost_screen():
            self.log("[WARN] นำทางยังไม่สำเร็จ → รอแล้ววนลองใหม่")
            time.sleep(3)
            return State.REROLL

        m = vision.find(self._cap(), config.IMG_TARGET_ITEM)
        if m.found:
            self.log(f"[OK] มี Double Coins อยู่แล้ว (score={m.score:.3f}) → ข้ามการสุ่ม")
        elif not self.multibuy_until_target():
            self.log("[WARN] Multi-Buy ไม่สำเร็จ → วนกลับมานำทาง/ลองใหม่")
            return State.REROLL

        self.ensure_boosts_selected()
        self.log("[OK] → กด Play เริ่มวิ่ง")
        self.adb.tap(*config.BTN_PLAY)
        time.sleep(config.DELAY_AFTER_PLAY)
        return State.RUN

    # ============================================================
    # STATE 2 — RUN
    # ============================================================
    def state_run(self):
        jump_stop = threading.Event()
        jump_count = [0]

        mode = "เลียนแบบคน" if config.HUMANLIKE_JUMP else "สุ่มดีเลย์"
        if config.PREVENT_INACTIVE:
            self.log(f"\n===== [STATE 2] RUN — กระโดด{mode}+สุ่มตำแหน่ง (กัน inactive) + relay =====")
        else:
            self.log(f"\n===== [STATE 2] RUN — กระโดด{mode} + คอยกด relay =====")

        def worker_loop():
            def still_running():
                return not jump_stop.is_set() and not self._stopping()

            def nap(seconds):
                """หลับแบบขัดจังหวะได้ (เช็ค stop ทุก ~0.1s) เพื่อหยุดบอทได้ไว"""
                end = time.time() + seconds
                while still_running():
                    remaining = end - time.time()
                    if remaining <= 0:
                        break
                    time.sleep(min(0.1, remaining))

            # จุดฐานกระโดดที่ค่อย ๆ เลื่อน (คนไม่จิ้มจุดเป๊ะเดิมทุกครั้ง)
            base = [float(config.BTN_JUMP[0]), float(config.BTN_JUMP[1])]

            def drift_base():
                """เลื่อนจุดฐานแบบสุ่มช้า ๆ + ดึงกลับเข้าจุดตั้งต้น + จำกัดระยะห่าง"""
                ox, oy = config.BTN_JUMP
                base[0] += random.gauss(0, config.HUMAN_DRIFT_STEP)
                base[1] += random.gauss(0, config.HUMAN_DRIFT_STEP)
                base[0] += (ox - base[0]) * config.HUMAN_DRIFT_PULL
                base[1] += (oy - base[1]) * config.HUMAN_DRIFT_PULL
                dx, dy = base[0] - ox, base[1] - oy
                dist = (dx * dx + dy * dy) ** 0.5
                if dist > config.HUMAN_DRIFT_MAX:
                    s = config.HUMAN_DRIFT_MAX / dist
                    base[0], base[1] = ox + dx * s, oy + dy * s

            def tap_once():
                """แตะปุ่มกระโดด 1 ครั้ง (เลือกจุดตามโหมด) + นับ"""
                if config.PREVENT_INACTIVE:
                    self.adb.tap(*random.choice(config.JUMP_TAP_POINTS),
                                 jitter=config.JUMP_JITTER)
                elif config.HUMAN_DRIFT:
                    drift_base()
                    self.adb.tap(int(base[0]), int(base[1]), jitter=config.JUMP_JITTER)
                else:
                    self.adb.tap(*config.BTN_JUMP, jitter=config.JUMP_JITTER)
                jump_count[0] += 1

            while still_running():
                # โหมดเดิม: กดคงที่ + สุ่มดีเลย์ uniform
                if not config.HUMANLIKE_JUMP:
                    tap_once()
                    nap(random.uniform(config.JUMP_DELAY_MIN, config.JUMP_DELAY_MAX))
                    continue

                # โหมดเลียนแบบคน
                # 1) การกด: บางครั้งเป็นเบิร์สต์รัว (double/triple jump)
                if random.random() < config.HUMAN_BURST_CHANCE:
                    taps = random.randint(*config.HUMAN_BURST_TAPS)
                    for k in range(taps):
                        if not still_running():
                            break
                        tap_once()
                        if k < taps - 1:
                            nap(random.uniform(*config.HUMAN_BURST_GAP))
                else:
                    tap_once()

                # 2) หน่วงถัดไป: ปกติ log-normal, บางครั้งเงียบยาว (วิ่งเก็บของ)
                if random.random() < config.HUMAN_IDLE_CHANCE:
                    nap(random.uniform(*config.HUMAN_IDLE_RANGE))
                else:
                    g = random.lognormvariate(config.HUMAN_GAP_MU, config.HUMAN_GAP_SIGMA)
                    nap(max(config.HUMAN_GAP_MIN, min(config.HUMAN_GAP_MAX, g)))

        start_time = time.time()
        jt = threading.Thread(target=worker_loop, daemon=True)
        jt.start()

        last_sig = None
        last_change = time.time()
        try:
            while not self._stopping():
                t = time.time() - start_time
                screen = self._cap()

                # ตรวจจอค้าง (inactive) — เฉพาะเมื่อเปิดโหมด
                if config.PREVENT_INACTIVE and screen is not None:
                    sig = vision.frame_signature(screen)
                    if last_sig is not None and float(abs(sig - last_sig).mean()) < config.FREEZE_DIFF:
                        if time.time() - last_change >= config.FREEZE_SECS:
                            self.log("[recover] จอค้าง/ป๊อปอัป → กด Confirm กลางจอ")
                            self.adb.tap(*config.BTN_INACTIVE_CONFIRM)
                            time.sleep(1.2)
                            last_sig = None
                            last_change = time.time()
                            continue
                    else:
                        last_change = time.time()
                    last_sig = sig

                # เจอนินจา relay → กดวิ่งต่อ
                relay = vision.find(screen, config.IMG_RELAY, config.RELAY_THRESHOLD)
                if relay.found:
                    self.log(f"    [relay] เจอนินจา (score={relay.score:.3f}) → กดวิ่งต่อ")
                    self.adb.tap(*config.BTN_RELAY)
                    time.sleep(0.5)
                    continue

                # เจอหน้า Result → ไป STATE 3
                result = vision.find(screen, config.IMG_RESULT)
                if result.found:
                    self.log(f"[OK] เจอหน้า Result (score={result.score:.3f}) "
                             f"หลังกด {jump_count[0]} ครั้ง → STATE 3")
                    return State.RESULT

                if t >= config.RUN_STATE_TIMEOUT:
                    self.log(f"[WARN] State 2 เกิน {config.RUN_STATE_TIMEOUT}s → บังคับไป STATE 3")
                    return State.RESULT

                time.sleep(config.RESULT_CHECK_INTERVAL)
        finally:
            jump_stop.set()
            # รอ thread กระโดดจบก่อน — กันยิง tap ค้างท่อไปโดนปุ่มบนหน้า Result
            jt.join(timeout=5.0)
            if jt.is_alive():
                self.log("[WARN] jump thread ยังไม่หยุดใน 5s (adb อาจช้า) — ไปต่อ")

    # ============================================================
    # โหมดวิ่งเก็บกล่อง (box) — STATE 1: ซื้อ Fast Start (ไม่รีโรล)
    # ============================================================
    def ensure_fast_start(self):
        """
        ซื้อ Fast Start บนหน้าเตรียมตัว (ลำดับตามพฤติกรรมเกมที่วัดจากจอจริง):
          1) แตะไอคอน Fast Start → แผงซื้อเปิดด้านขวา (ถ้าเปิดค้างอยู่แล้วก็แค่เลือกซ้ำ)
          2) รอปุ่ม Buy → กดซื้อ (เกมหักเหรียญทันที + เด้ง toast "Purchase complete!" กลางจอ)
          3) toast หายเองใน ~3 วิ — สำคัญ: "แผงซื้อไม่ปิดเอง" ปุ่ม Buy ยังโชว์อยู่หลังซื้อ
             ซึ่งเป็นเรื่องปกติ ไม่ใช่ซื้อไม่สำเร็จ และแผงนี้ไม่บังบูสต์/ปุ่ม Play จึงไม่ต้องปิด
        คืน True เมื่อซื้อแล้วหน้าจอกลับมาปกติ (หรือไม่มีปุ่ม Buy = อาจเปิดใช้อยู่แล้ว)
        """
        screen = self._cap()
        slot = vision.find_multiscale(screen, config.IMG_FAST_START,
                                      config.FAST_START_THRESHOLD)
        if slot.found:
            self.log(f"[box] เจอไอคอน Fast Start (score={slot.score:.2f}) → แตะเลือก")
            self.adb.tap(*slot.center)
        elif config.BTN_FAST_START:
            self.log(f"[box] หาไอคอน Fast Start ไม่เจอ (best={slot.score:.2f}) "
                     f"→ ใช้พิกัดสำรอง BTN_FAST_START {tuple(config.BTN_FAST_START)}")
            self.adb.tap(*config.BTN_FAST_START)
        else:
            self.log(f"[box][WARN] หาไอคอน Fast Start ไม่เจอ (best={slot.score:.2f}) → ข้ามการซื้อ "
                     "(แคป templates/fast_start_item.png ใหม่ หรือตั้ง BTN_FAST_START ใน settings.json)")
            return False

        # รอปุ่ม Buy ในแผงด้านขวา
        buy = None
        start = time.time()
        while time.time() - start < config.FAST_START_BUY_TIMEOUT:
            if self._stopping():
                return False
            time.sleep(0.6)
            m = vision.find_multiscale(self._cap(), config.IMG_FAST_START_BUY,
                                       config.FAST_START_THRESHOLD)
            if m.found:
                buy = m
                break
        if buy is None:
            if vision.find(self._cap(), config.IMG_BOOST_SCREEN).found:
                self.log("[box] ไม่เจอปุ่ม Buy แต่หน้าเตรียมตัวปกติ — อาจเปิดใช้อยู่แล้ว → ไปต่อ")
                return True
            self.log("[box][WARN] ไม่เจอปุ่ม Buy และมีอะไรบังหน้าเตรียมตัว → ให้ระบบนำทางแก้ต่อ "
                     "(ถ้าเกิดซ้ำ แคป templates/fast_start_buy.png ใหม่จากจอจริง)")
            return False

        self.log(f"[box] เจอปุ่ม Buy (score={buy.score:.2f}) → กดซื้อ Fast Start")
        self.adb.tap(*buy.center)

        # หลังซื้อ: toast "Purchase complete!" เด้งทับกลางจอแล้วหายเองใน ~3 วิ
        # ห้ามตีความ "ปุ่ม Buy ยังอยู่" เป็นซื้อไม่สำเร็จ — แผงซื้อเปิดค้างเป็นเรื่องปกติ
        self.log("[box] กดซื้อแล้ว → รอ toast 'Purchase complete!' หายเอง (~3 วิ)")
        time.sleep(2.0)
        deadline = time.time() + config.FAST_START_TOAST_TIMEOUT
        while time.time() < deadline:
            if self._stopping():
                return False
            if vision.find(self._cap(), config.IMG_BOOST_SCREEN).found:
                self.log("[box] ซื้อ Fast Start เรียบร้อย (แผงซื้อเปิดค้างไว้ได้ ไม่บังปุ่มอะไร)")
                return True
            time.sleep(0.8)
        self.log("[box][WARN] หน้าจอยังไม่กลับมาปกติหลังซื้อ → ให้ระบบนำทางแก้ต่อ")
        return False

    def state_prepare_box(self):
        self.log("\n===== [STATE 1] PREP — ซื้อ Fast Start (โหมดวิ่งเก็บกล่อง ไม่รีโรล) =====")
        if not self.ensure_on_boost_screen():
            self.log("[WARN] นำทางยังไม่สำเร็จ → รอแล้ววนลองใหม่")
            time.sleep(3)
            return State.REROLL

        self.ensure_fast_start()

        # กลับให้ถึงหน้าเตรียมตัวชัวร์ ๆ ก่อนติ๊กบูสต์ (เผื่อมีป๊อปอัปหลังซื้อ)
        if not self.ensure_on_boost_screen():
            self.log("[WARN] หลังซื้อ Fast Start กลับหน้าเตรียมตัวไม่ได้ → วนลองใหม่")
            time.sleep(3)
            return State.REROLL

        self.ensure_boosts_selected()
        self.log("[OK] → กด Play เริ่มวิ่งเก็บกล่อง")
        self.adb.tap(*config.BTN_PLAY)
        time.sleep(config.DELAY_AFTER_PLAY)
        return State.RUN

    # ============================================================
    # โหมดวิ่งเก็บกล่อง (box) — STATE 2: ปล่อยวิ่งเอง ไม่กดอะไรเลย
    # ============================================================
    def state_run_box(self):
        self.log("\n===== [STATE 2] RUN — กดเปิด Fast Start แล้วปล่อยคุกกี้วิ่งเอง (ไม่กระโดด/ไม่กดนินจา) =====")
        start_time = time.time()
        last_sig = None
        last_change = time.time()
        relay_was_visible = False

        while not self._stopping():
            t = time.time() - start_time
            screen = self._cap()

            # ช่วงต้นเกม: เกมขึ้นปุ่ม "Tap to activate Fast Start Boost!" (~5-7 วิแรก
            # และค้างแค่ ~3 วิ) → ต้องกดถึงจะได้ Magnet Aura วิ่งเก็บของทั้งด่าน 1
            if t < config.FAST_START_ACTIVATE_WINDOW:
                act = vision.find(screen, config.IMG_FAST_START_ACTIVATE,
                                  config.FAST_START_THRESHOLD)
                if act.found:
                    self.log(f"    [box] เจอปุ่ม activate Fast Start (score={act.score:.2f}) → กดเปิดบูสต์")
                    self.adb.tap(*act.center)
                    time.sleep(0.4)
                    continue

            # ตรวจจอค้าง (inactive) — เฉพาะเมื่อเปิดโหมด (เหมือน state_run เดิม)
            if config.PREVENT_INACTIVE and screen is not None:
                sig = vision.frame_signature(screen)
                if last_sig is not None and float(abs(sig - last_sig).mean()) < config.FREEZE_DIFF:
                    if time.time() - last_change >= config.FREEZE_SECS:
                        self.log("[recover] จอค้าง/ป๊อปอัป → กด Confirm กลางจอ")
                        self.adb.tap(*config.BTN_INACTIVE_CONFIRM)
                        time.sleep(1.2)
                        last_sig = None
                        last_change = time.time()
                        continue
                else:
                    last_change = time.time()
                last_sig = sig

            # เจอนินจา relay → ตามสเปกโหมดนี้ "ไม่กด" (ไม่เปลี่ยนไม้ 2) — log ไว้เฉย ๆ
            relay = vision.find(screen, config.IMG_RELAY, config.RELAY_THRESHOLD)
            if relay.found and not relay_was_visible:
                self.log(f"    [relay] เจอนินจา (score={relay.score:.3f}) → ไม่กด ปล่อยผ่าน")
            relay_was_visible = relay.found

            # เจอหน้า Result → ไป STATE 3
            result = vision.find(screen, config.IMG_RESULT)
            if result.found:
                self.log(f"[OK] เจอหน้า Result (score={result.score:.3f}) → STATE 3")
                return State.RESULT

            if t >= config.RUN_STATE_TIMEOUT:
                self.log(f"[WARN] State 2 เกิน {config.RUN_STATE_TIMEOUT}s → บังคับไป STATE 3")
                return State.RESULT

            time.sleep(config.RESULT_CHECK_INTERVAL)
        return None

    # ============================================================
    # STATE 3 — RESULT
    # ============================================================
    def record_result_coins(self, screen):
        """อ่านเหรียญรอบนี้ → บันทึก coins.csv + แจ้ง GUI. อ่านพลาดเซฟภาพไว้ดู"""
        if screen is None:
            return
        coins = self.coin_reader.read(screen)
        if coins is not None:
            self.coin_total += coins
        try:
            log_dir = data_path("coin_logs")
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            with open(os.path.join(log_dir, "coins.csv"), "a", encoding="utf-8") as f:
                f.write(f"{ts},{coins if coins is not None else ''},{self.coin_total}\n")
            if coins is not None:
                self.log(f"[coins] เหรียญรอบนี้: {coins:,}  (รวม {self.coin_total:,})")
            else:
                cv2.imwrite(os.path.join(log_dir, f"result_FAIL_{ts}.png"), screen)
                self.log(f"[coins] อ่านเลขไม่ได้ → เซฟภาพ result_FAIL_{ts}.png")
        except Exception as e:
            self.log(f"[coins] บันทึกไม่สำเร็จ: {e}")

        if self.on_coins:
            try:
                self.on_coins(coins, self.coin_total)
            except Exception:
                pass

    def state_result(self):
        self.log("\n===== [STATE 3] RESULT — กำลังหาปุ่ม OK =====")
        MAX_ATTEMPTS = 40
        attempts = 0
        while not self._stopping():
            screen = self._cap()
            ok = vision.find(screen, config.IMG_OK_BUTTON)
            if ok.found:
                self.record_result_coins(screen)
                self.log(f"[OK] เจอปุ่ม OK (score={ok.score:.3f}) → กดกลับล็อบบี้")
                self.adb.tap(*ok.center)
                time.sleep(2.5)
                return State.REROLL

            attempts += 1
            if attempts >= MAX_ATTEMPTS:
                self.log("[WARN] หาปุ่ม OK ไม่เจอเกินกำหนด → วนกลับ STATE 1")
                return State.REROLL
            self.log(f"[..] ยังไม่เจอปุ่ม OK (best={ok.score:.3f}) attempt {attempts}/{MAX_ATTEMPTS}")
            time.sleep(config.LOOP_SLEEP)
        return None

    # ============================================================
    # ลูปหลัก
    # ============================================================
    def run(self, max_loops=0):
        """
        รัน state machine จนกว่าจะ stop / ครบรอบ
        max_loops = 0 → ไม่จำกัด ; > 0 → หยุดเมื่อจบครบจำนวนรอบ (1 รอบ = จบ 1 เกม)
        """
        self.coin_total = 0
        current = State.REROLL
        loops_done = 0
        err_streak = 0
        box_mode = self.mode == "box"
        self.log(f"[bot] โหมด: {'วิ่งเก็บกล่อง (box — Fast Start)' if box_mode else 'รีโรลเหรียญ (coin)'}")
        try:
            while not self._stopping():
                prev = current
                try:
                    if current == State.REROLL:
                        current = self.state_prepare_box() if box_mode else self.state_reroll()
                    elif current == State.RUN:
                        current = self.state_run_box() if box_mode else self.state_run()
                    elif current == State.RESULT:
                        current = self.state_result()
                    err_streak = 0
                except Exception as e:
                    err_streak += 1
                    self.log(f"[ERR] ข้อผิดพลาดใน {prev} (ครั้งที่ {err_streak}) → ลองใหม่: {e}")
                    self.log(traceback.format_exc())
                    if err_streak >= 30:
                        self.log("[FATAL] ผิดพลาดติดกันเยอะมาก → หยุด (เช็ก LDPlayer/ADB)")
                        break
                    time.sleep(1.5)
                    current = State.REROLL
                    continue

                # นับรอบเมื่อจบเกม (RESULT → REROLL)
                if prev == State.RESULT and current == State.REROLL:
                    loops_done += 1
                    msg = f"[loop] เล่นจบรอบที่ {loops_done}"
                    if max_loops:
                        msg += f" / {max_loops}"
                    self.log(msg)
                    if self.on_loop:
                        try:
                            self.on_loop(loops_done)
                        except Exception:
                            pass
                    if max_loops and loops_done >= max_loops:
                        self.log(f"[loop] ครบ {max_loops} รอบแล้ว → หยุดบอท")
                        break

                if current is None:
                    break
        except KeyboardInterrupt:
            self.log("\n[!] Ctrl+C — หยุดบอท")
        finally:
            self.stop.set()
            self.log("\n===== บอทหยุดทำงานแล้ว =====")


# ============================================================
# รันตรงแบบ CLI (ไม่มี GUI) — กด Ctrl+C เพื่อหยุด
# ============================================================
def main():
    from adb import Adb

    print("=" * 60)
    print(f" {config.APP_NAME} v{config.APP_VERSION} — CLI")
    print("=" * 60)
    if config.SETTINGS_ERROR:
        print(f"[!] {config.SETTINGS_ERROR}")
    elif config.SETTINGS_APPLIED:
        print("[i] settings.json override:", ", ".join(config.SETTINGS_APPLIED))

    adb = Adb()
    if not adb.connected():
        print("[FATAL] เชื่อมต่อ ADB/แคปหน้าจอไม่ได้ — เปิด LDPlayer และเช็ค 'adb devices'")
        return

    bot = CookieBot(adb)
    try:
        bot.run(max_loops=0)
    except KeyboardInterrupt:
        bot.stop.set()


if __name__ == "__main__":
    main()
