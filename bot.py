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
import math
import time
import random
import datetime
import threading
import traceback
from enum import Enum, auto

import cv2

import config
import vision
import humanizer
from paths import data_path


class State(Enum):
    REROLL = auto()
    RUN = auto()
    RESULT = auto()


class CookieBot:
    def __init__(self, adb, log=print, on_coins=None, on_loop=None,
                 stop_event=None, mode=None, on_status=None):
        self.adb = adb
        self.log = log
        self.on_coins = on_coins          # callback(coins, total) — อัปเดต GUI
        self.on_loop = on_loop            # callback(loops_done)    — นับถอยหลัง GUI
        self.on_status = on_status        # callback(dict) — สถานะ V2 (พัก/ความล้า) ให้ GUI
        self.stop = stop_event or threading.Event()
        self.coin_reader = vision.CoinReader(log)
        self.coin_total = 0
        self._tpl_warned = set()   # template ทางเลือกที่เตือนว่า "ยังไม่มีไฟล์" ไปแล้ว (เตือนครั้งเดียวพอ)
        self._cap_fails = 0        # แคปจอพลาดติดกัน (ไว้ trigger เช็ค device ใหม่)
        self._nav_fail_streak = 0  # นำทางล้มเหลวติดกัน (watchdog กันวนกดมั่วไม่สิ้นสุด)
        self._nav_saw_frame = True # รอบนำทางล่าสุดเคยแคปจอได้ไหม (แยก ADB ล่ม ออกจากหลงหน้าจอ)
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

    def _emit(self, **ev):
        """ส่ง event สถานะให้ GUI (ถ้ามี) — callback พังห้ามล้มบอท"""
        if self.on_status:
            try:
                self.on_status(ev)
            except Exception:
                pass

    def _msleep(self, base):
        """หลับตามจังหวะเมนูแบบคน — ยืดจาก base เสมอ ไม่หด (ดู humanizer.menu_pause)"""
        time.sleep(humanizer.menu_pause(base))

    def _pause(self, seconds):
        """หลับยาวแบบขัดจังหวะได้ (เช็ค stop ทุก ~0.2s) — ใช้กับ pause ที่นานเกิน 1-2 วิ"""
        end = time.time() + seconds
        while not self._stopping():
            remaining = end - time.time()
            if remaining <= 0:
                break
            time.sleep(min(0.2, remaining))

    def _required_templates(self):
        """รายชื่อ template ที่ "ต้องมี" สำหรับโหมดปัจจุบัน (ไว้ตรวจครั้งเดียวก่อนเริ่มรัน)
        — ป๊อปอัปใน DISMISS_POPUPS ไม่รวม เพราะเป็นทางเลือก (บอทข้ามให้เองถ้าไฟล์ไม่มี)"""
        req = [config.IMG_BOOST_SCREEN, config.IMG_OK_BUTTON, config.IMG_RESULT,
               config.IMG_LOBBY_PLAY, config.IMG_RELAY]
        req += [it["check_img"] for it in config.BOOST_ITEMS]
        if self.mode == "box":
            req += [config.IMG_FAST_START, config.IMG_FAST_START_BUY,
                    config.IMG_FAST_START_ACTIVATE]
        else:
            req += [config.IMG_TARGET_ITEM, config.IMG_MULTI_CHECK]
        return req

    def _cap(self):
        img = self.adb.screencap()
        if img is None:
            self._cap_fails += 1
            if self._cap_fails % 3 == 0 and not self._stopping():
                self.log("[adb] แคปจอพลาดติดกันหลายครั้ง → เช็ค device ใหม่ (เผื่อหลุด/พอร์ตเปลี่ยน)")
                self.adb.ensure_device()
        else:
            self._cap_fails = 0
        return img

    def _nav_failed(self, msg):
        """นับนำทางล้มเหลวติดกัน — เกิน NAV_FAIL_LIMIT ให้หยุดบอท
        (จอที่ไม่รู้จัก เช่น เกมเด้ง/หน้าอัปเดตสโตร์ ไม่ raise exception
        err_streak ใน run() จึงจับไม่ได้ — ปล่อยไว้บอทจะวนกดมั่วไม่สิ้นสุด)"""
        if not self._nav_saw_frame:
            # มองไม่เห็นจอเลยทั้งรอบ = ADB/อีมูเลเตอร์ล่มชั่วคราว ไม่ใช่บอทหลงหน้าจอ
            # → รอไปเรื่อย ๆ ห้ามนับ streak (_cap จะ ensure_device กู้ให้เองเมื่อ device กลับมา)
            self.log(f"[WARN] {msg} — แคปจอไม่ได้เลย (ADB/อีมูเลเตอร์ล่ม?) → รอจนกว่าจะกลับมา")
            time.sleep(3)
            return State.REROLL
        self._nav_fail_streak += 1
        self.log(f"[WARN] {msg} (ล้มเหลวติดกัน {self._nav_fail_streak}/{config.NAV_FAIL_LIMIT})")
        if self._nav_fail_streak >= config.NAV_FAIL_LIMIT:
            self.log("[FATAL] นำทางล้มเหลวติดกันเกินกำหนด → หยุดบอท (เช็คว่าเกมอยู่หน้าไหน)")
            return None
        time.sleep(3)
        return State.REROLL

    # ============================================================
    # นำทางเข้า "หน้าเตรียมตัว"
    # ============================================================
    def ensure_on_boost_screen(self, max_tries=15):
        """
        พาไปอยู่หน้าเตรียมตัว (Buy some Boosts):
          - ปิดป๊อปอัปที่รู้จัก, ค้างหน้า Result → กด OK, อยู่ล็อบบี้ → กด Play,
            มีป๊อปอัปรางวัลบัง → กดปุ่ม Confirm กลางล่าง 2 จุด
          - กด Play แล้วจอไม่ขยับ = มีป๊อปอัปแจ้งเตือน (modal เช่น "entered in a League")
            กลืนการแตะทั้งจอทั้งที่ปุ่ม Play ยังมองเห็น → ไล่กด Confirm กลางจอสลับกับ Play
        (ไม่ใช้ปุ่ม Back เพราะที่ล็อบบี้จะเด้ง "Exit game?")
        คืน True ถ้าถึงหน้าเตรียมตัว
        """
        x_close_tries = 0
        play_stuck = 0     # กด Play ไปแล้วกี่ครั้งโดยที่รอบถัดมายังเห็นล็อบบี้เดิม
        confirm_idx = 0    # ไล่กดจุด Confirm กลางจอถึงจุดไหนแล้ว
        self._nav_saw_frame = False   # ให้ _nav_failed แยกออก: ADB ล่ม (รอ) vs หลงหน้าจอ (นับ streak)
        for i in range(max_tries):
            if self._stopping():
                return False
            screen = self._cap()
            if screen is not None:
                self._nav_saw_frame = True
            if screen is None:
                # แคปจอไม่ได้ (adb สะดุด) — ไม่ได้แปลว่าจอเปลี่ยน อย่ารีเซ็ตตัวนับ/กดมั่ว
                self.log("[nav] แคปหน้าจอไม่ได้ (adb สะดุด) → รอแล้วลองใหม่")
                time.sleep(1.0)
                continue

            # 1) ปิดป๊อปอัปที่รู้จัก (template ไหนยังไม่มีไฟล์/อ่านไม่ได้ → ข้าม พร้อมเตือนครั้งเดียว)
            dismissed = False
            popup_stuck = False
            for pop in config.DISMISS_POPUPS:
                if not vision.has_template(pop["img"]):
                    if pop["img"] not in self._tpl_warned:
                        self._tpl_warned.add(pop["img"])
                        self.log(f"[nav] ไม่มีไฟล์ {pop['img']} หรือไฟล์อ่านไม่ได้ (ป๊อปอัป {pop['name']}) → ข้าม "
                                 "(แคปเพิ่มได้เพื่อให้ปิดป๊อปอัปแม่นขึ้น)")
                    continue
                m = vision.find(screen, pop["img"], pop["th"])
                if not m.found:
                    continue
                if x_close_tries < 3:
                    self.log(f"[nav] เจอป๊อปอัป {pop['name']} (score={m.score:.2f}) → กดปิดที่ {pop['x']}")
                    self.adb.tap(*pop["x"], jitter=config.SAFE_TAP_JITTER)
                    x_close_tries += 1
                    self._msleep(0.9)
                    dismissed = True
                else:
                    # จุดปิดที่ตั้งไว้กดแล้วป๊อปอัปไม่หาย → เลิกกดจุดเดิม ปล่อยไหลลง
                    # branch 4/5 ให้บันได Confirm กลางจอไล่จุดอื่นแทน
                    self.log(f"[nav] กดปิด {pop['name']} หลายครั้งแล้วไม่หาย → ใช้บันได Confirm กลางจอแทน")
                    popup_stuck = True
                break
            if dismissed:
                play_stuck = confirm_idx = 0
                continue
            if popup_stuck:
                # รู้แน่ว่ามีป๊อปอัปค้างบังจอ → ไม่ต้องเสียรอบกด Play ให้ modal กลืน
                play_stuck = max(play_stuck, config.NAV_PLAY_STUCK_TRIES)
            else:
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
                self._msleep(2.5)
                play_stuck = confirm_idx = 0
                continue

            # 4) อยู่ล็อบบี้ → กด Play
            #    ถ้ากด Play หลายครั้งแล้วยังวนเห็นล็อบบี้เดิม = มีป๊อปอัปแจ้งเตือนแบบ modal บัง
            #    (เช่น League Notice) → ไล่กดจุด Confirm กลางจอทีละจุด สลับกับลองกด Play
            lobby = vision.find(screen, config.IMG_LOBBY_PLAY)
            if lobby.found:
                if play_stuck >= config.NAV_PLAY_STUCK_TRIES:
                    pts = config.NAV_POPUP_CONFIRM_POINTS
                    if confirm_idx < len(pts):
                        pt = pts[confirm_idx]
                        confirm_idx += 1
                        self.log(f"[nav] กด Play แล้วจอไม่ขยับ — น่าจะมีป๊อปอัปแจ้งเตือนบัง "
                                 f"(เช่น League) → กด Confirm กลางจอ {pt}")
                        self.adb.tap(*pt)
                        # ให้รอบถัดไปลองกด Play ก่อน 1 ครั้ง — ถ้ายังไม่ขยับค่อยไล่จุดต่อไป
                        play_stuck = config.NAV_PLAY_STUCK_TRIES - 1
                        self._msleep(1.2)
                        continue
                    confirm_idx = 0   # ไล่ครบทุกจุดแล้ว → เริ่มชุดใหม่ (กด Play ต่อด้านล่าง)
                play_stuck += 1
                self.log(f"[nav] อยู่ล็อบบี้ (ครั้งที่ {i + 1}) → กด Play")
                self.adb.tap(*lobby.center)
                self._msleep(config.DELAY_AFTER_PLAY)
                continue
            play_stuck = confirm_idx = 0

            # 5) มีป๊อปอัปบัง → กดปุ่ม Confirm/Open all 2 จุด
            self.log(f"[nav] มีป๊อปอัปบัง (ครั้งที่ {i + 1}) → กด Confirm/Open all 2 จุด")
            self.adb.tap(*config.BTN_POPUP_CONFIRM)
            self._msleep(0.4)
            self.adb.tap(*config.BTN_POPUP_CONFIRM_LOW)
            self._msleep(1.2)

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
        self._msleep(0.8)
        self.log("[reroll] เปิดหน้า Multi (เลือกบูสต์ที่ต้องการ)")
        self.adb.tap(*config.BTN_MULTI)
        self._msleep(1.0)

        dlg = self._cap()
        if dlg is None:
            dlg = self._cap()   # adb สะดุดชั่วคราว → ลองอีกครั้ง
        if dlg is None:
            # มองไม่เห็นหน้า Multi ห้ามกดต่อ — กดทั้งที่ตาบอดอาจสลับติ๊ก Double Coins ออก
            self.log("[reroll] แคปหน้า Multi ไม่ได้ → ปิดหน้าต่างแล้วเริ่มใหม่")
            self.adb.tap(*config.BTN_MULTI_CLOSE, jitter=config.SAFE_TAP_JITTER)
            self._msleep(1.0)
            return False
        for cx, cy in config.MULTI_SELECT_TARGETS:
            roi = (cx - 30, cy - 30, cx + 30, cy + 30)
            checked, sc = vision.find_in_roi(dlg, config.IMG_MULTI_CHECK, roi,
                                             config.MULTI_CHECK_THRESHOLD)
            if checked:
                self.log(f"    บูสต์ ({cx},{cy}) ติ๊กอยู่แล้ว (score={sc:.2f}) → ข้าม")
                continue
            self.log(f"    บูสต์ ({cx},{cy}) ยังไม่ติ๊ก (score={sc:.2f}) → กดเลือก")
            self.adb.tap(cx, cy, jitter=config.SAFE_TAP_JITTER)
            self._msleep(0.4)

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
        self.adb.tap(*config.BTN_MULTI_CLOSE, jitter=config.SAFE_TAP_JITTER)
        self._msleep(1.0)
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
            if screen is None:
                # ตาบอดห้ามกด — score=0.00 จะดูเหมือน "ยังไม่ติ๊ก" ทั้งสามอัน
                # แล้วบอทกดสลับบูสต์ที่ติ๊กอยู่แล้วให้ปิด (เหตุผลเดียวกับ guard หน้า Multi)
                self.log("[*] แคปจอไม่ได้ระหว่างเช็คบูสต์ → รอแล้วลองรอบถัดไป")
                time.sleep(1.0)
                continue
            all_on = True
            for item in config.BOOST_ITEMS:
                checked, sc = vision.find_in_roi(screen, item["check_img"],
                                                 item["check_roi"], config.CHECK_THRESHOLD)
                if checked:
                    self.log(f"    [{item['name']}] ติ๊กแล้ว (score={sc:.2f})")
                    continue
                self.log(f"    [{item['name']}] ยังไม่ติ๊ก (score={sc:.2f}) → กดเปิดใช้")
                self.adb.tap(*item["tap"], jitter=config.SAFE_TAP_JITTER)
                self._msleep(0.7)
                all_on = False
            if all_on:
                self.log("[*] Boost ครบทั้ง 3 อันแล้ว")
                return
        self.log("[*] จบการตรวจ Boost (อาจมีบางอันของหมด)")

    def state_reroll(self):
        self.log("\n===== [STATE 1] REROLL — Multi-Buy หา Double Coins =====")
        if not self.ensure_on_boost_screen():
            return self._nav_failed("นำทางยังไม่สำเร็จ → รอแล้ววนลองใหม่")
        self._nav_fail_streak = 0

        m = vision.find(self._cap(), config.IMG_TARGET_ITEM)
        if m.found:
            self.log(f"[OK] มี Double Coins อยู่แล้ว (score={m.score:.3f}) → ข้ามการสุ่ม")
        elif not self.multibuy_until_target():
            self.log("[WARN] Multi-Buy ไม่สำเร็จ → วนกลับมานำทาง/ลองใหม่")
            return State.REROLL

        self.ensure_boosts_selected()
        self.log("[OK] → กด Play เริ่มวิ่ง")
        time.sleep(random.uniform(*config.PLAY_PRESS_DELAY))   # คนขยับนิ้วไปหาปุ่ม
        self.adb.tap(*config.BTN_PLAY)
        self._msleep(config.DELAY_AFTER_PLAY)
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
            # บรรทัดนี้อยู่นอก try ของลูปด้านล่าง — BTN_JUMP ผิดรูปแบบ (เช่นใส่เลขเดียว
            # ใน settings.json) ห้ามทำให้เธรดตายเงียบเหมือนบั๊กเดิม
            try:
                base = [float(config.BTN_JUMP[0]), float(config.BTN_JUMP[1])]
            except Exception as e:
                self.log(f"[jump][FATAL] BTN_JUMP ตั้งค่าผิดรูปแบบ ({config.BTN_JUMP!r}): {e} "
                         "→ ไม่กระโดดรอบนี้ (แก้ใน settings.json)")
                return

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
                """แตะปุ่มกระโดด 1 ครั้ง (เลือกจุดตามโหมด) — นับเฉพาะครั้งที่คำสั่งถึง device จริง
                นาน ๆ ที "กดหลุดปุ่ม" (fumble): แตะเยื้องไกลจนเกมไม่รับ = เสียจังหวะแบบคนนิ้วลื่น"""
                if config.PREVENT_INACTIVE:
                    px, py = random.choice(config.JUMP_TAP_POINTS)
                elif config.HUMAN_DRIFT:
                    drift_base()
                    px, py = int(base[0]), int(base[1])
                else:
                    px, py = config.BTN_JUMP
                if config.HUMANLIKE_JUMP and random.random() < config.HUMAN_FUMBLE_CHANCE:
                    d = random.uniform(*config.HUMAN_FUMBLE_DIST)
                    a = random.uniform(0, 2 * math.pi)
                    px, py = int(px + d * math.cos(a)), int(py + d * math.sin(a))
                ok = self.adb.tap(px, py, jitter=config.JUMP_JITTER)
                if ok:
                    jump_count[0] += 1

            def slide_once():
                """สไลด์ 1 ครั้ง — ระยะกดค้างสุ่มทุกครั้ง (ปกติสั้น นาน ๆ ทีสไลด์ยาว)"""
                if random.random() < config.HUMAN_SLIDE_LONG_CHANCE:
                    hold = random.uniform(*config.HUMAN_SLIDE_LONG_RANGE)
                else:
                    hold = random.uniform(*config.HUMAN_SLIDE_HOLD)
                if self.adb.slide(hold_sec=hold):
                    jump_count[0] += 1

            def one_cycle():
                # โหมดเดิม: กดคงที่ + สุ่มดีเลย์ uniform
                if not config.HUMANLIKE_JUMP:
                    tap_once()
                    nap(random.uniform(config.JUMP_DELAY_MIN, config.JUMP_DELAY_MAX))
                    return

                # โหมดเลียนแบบคน
                # 1) การกด: สไลด์ / คอมโบ jump→slide / เบิร์สต์รัว (double-triple jump) / กดเดี่ยว
                roll = random.random()
                p_slide = config.HUMAN_SLIDE_CHANCE
                p_combo = p_slide + config.HUMAN_COMBO_CHANCE
                p_burst = p_combo + config.HUMAN_BURST_CHANCE
                if roll < p_slide:
                    slide_once()
                elif roll < p_combo:
                    tap_once()
                    nap(random.uniform(*config.HUMAN_COMBO_GAP))
                    if still_running():
                        slide_once()
                elif roll < p_burst:
                    taps = random.randint(*config.HUMAN_BURST_TAPS)
                    for k in range(taps):
                        if not still_running():
                            break
                        tap_once()
                        if k < taps - 1:
                            nap(random.uniform(*config.HUMAN_BURST_GAP))
                else:
                    tap_once()

                # 2) หน่วงถัดไป: ปกติ log-normal, บางครั้งเงียบยาว (วิ่งเก็บของ),
                #    นาน ๆ ทีเผลอ/หลุดโฟกัส (lapse — ยาวกว่า gap ปกติแต่สั้นกว่า idle)
                r = random.random()
                if r < config.HUMAN_IDLE_CHANCE:
                    nap(random.uniform(*config.HUMAN_IDLE_RANGE))
                elif r < config.HUMAN_IDLE_CHANCE + config.HUMAN_LAPSE_CHANCE:
                    nap(random.uniform(*config.HUMAN_LAPSE_RANGE))
                else:
                    g = random.lognormvariate(config.HUMAN_GAP_MU, config.HUMAN_GAP_SIGMA)
                    nap(max(config.HUMAN_GAP_MIN, min(config.HUMAN_GAP_MAX, g)))

            err_streak = 0
            while still_running():
                # เธรดนี้ห้ามตายเงียบ — .exe แบบ windowed ไม่มี stderr ให้เห็น traceback
                # (ตายไปคุกกี้จะไม่กระโดดอีกเลยทั้งรอบโดยไม่มีใครรู้)
                try:
                    one_cycle()
                    err_streak = 0
                except Exception as e:
                    err_streak += 1
                    self.log(f"[jump] เธรดกระโดดสะดุด (ครั้งที่ {err_streak}): {e}")
                    if err_streak >= 30:
                        self.log("[jump][FATAL] สะดุดติดกันมากเกิน → เลิกกระโดดรอบนี้ (เช็ค ADB path/device)")
                        break
                    nap(1.0)

        start_time = time.time()
        jt = threading.Thread(target=worker_loop, daemon=True)
        jt.start()

        last_sig = None
        last_change = time.time()
        try:
            while not self._stopping():
                # timeout เช็คบนสุด — ให้ relay ใช้ continue กดซ้ำรัวได้โดยไม่ค้างลูปเลย timeout
                # (v2 เดิมตัด continue เพราะกลัวจุดนี้ → ย้าย timeout มาบน แก้ได้ทั้งคู่)
                t = time.time() - start_time
                if t >= config.RUN_STATE_TIMEOUT:
                    self.log(f"[WARN] State 2 เกิน {config.RUN_STATE_TIMEOUT}s → บังคับไป STATE 3")
                    return State.RESULT

                screen = self._cap()

                # เจอนินจา relay → กดทันที + continue กดซ้ำรัว ๆ ตอนนินจายังโชว์ (แบบ v1)
                # ต้องเช็ค "ก่อน" ทุกอย่าง + ใช้ find (สเกลเดียว เร็ว) ไม่ใช่ find_multiscale —
                # ยิ่งหน่วง capture→tap นาน นินจา (เป้าเคลื่อนที่) ยิ่งวิ่งพ้นจุด กดไม่ทัน
                relay = vision.find(screen, config.IMG_RELAY, config.RELAY_THRESHOLD)
                if relay.found:
                    # นินจาเป็น sprite วิ่งเคลื่อนที่ → กดตรงตำแหน่งที่ "ตรวจเจอจริง" (relay.center)
                    # และต้องใช้ tap ดิบ (input tap) ไม่ใช่ adb.tap() ที่ humanize เป็น
                    # swipe-กดค้าง-ลากนิ้ว — เกมไม่รับ swipe เป็นการแตะปุ่มนินจา (กดไม่ติด)
                    # รัว 3 ทีเร็ว ๆ กันนินจาขยับพ้นจุด
                    cx, cy = relay.center or config.BTN_RELAY
                    for _ in range(3):
                        self.adb._input(["tap", cx, cy])
                        time.sleep(0.05)
                    self.log(f"    [relay] เจอนินจาที่ ({cx},{cy}) score={relay.score:.3f} → กด")
                    continue

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

                # เจอหน้า Result → ไป STATE 3
                result = vision.find(screen, config.IMG_RESULT)
                if result.found:
                    self.log(f"[OK] เจอหน้า Result (score={result.score:.3f}) "
                             f"หลังกด {jump_count[0]} ครั้ง → STATE 3")
                    return State.RESULT

                # poll ถี่ (0.12s) ให้ตรวจเจอนินจา + กดไว ไม่ต้องรอ RESULT_CHECK_INTERVAL (0.5s)
                # นินจาโผล่แวบเดียว — loop ยิ่งเร็ว ยิ่งจับทันก่อนวิ่งพ้น
                time.sleep(config.RELAY_POLL_INTERVAL)
        finally:
            jump_stop.set()
            # รอ thread กระโดดจบก่อน — กันยิง tap ค้างท่อไปโดนปุ่มบนหน้า Result
            # (คำสั่งค้างนานสุด = slide/hold: SLIDE_HOLD_SEC + ADB_CMD_TIMEOUT — ต้องรอเกินนั้น)
            max_hold = max(config.SLIDE_HOLD_SEC, config.HUMAN_SLIDE_LONG_RANGE[1])
            jt.join(timeout=config.ADB_CMD_TIMEOUT + max_hold + 2.0)
            if jt.is_alive():
                self.log("[WARN] jump thread ยังไม่หยุดตามเวลา (adb อาจค้าง) — ไปต่อ")

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
            time.sleep(random.uniform(*config.BOX_REACT_RANGE))   # เห็นก่อนแล้วค่อยขยับนิ้ว
            self.adb.tap(*slot.center)
        elif config.BTN_FAST_START:
            self.log(f"[box] หาไอคอน Fast Start ไม่เจอ (best={slot.score:.2f}) "
                     f"→ ใช้พิกัดสำรอง BTN_FAST_START {tuple(config.BTN_FAST_START)}")
            time.sleep(random.uniform(*config.BOX_REACT_RANGE))
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
        time.sleep(random.uniform(*config.BOX_REACT_RANGE))   # เห็นปุ่มก่อนแล้วค่อยกด
        self.adb.tap(*buy.center)

        # หลังซื้อ: toast "Purchase complete!" เด้งทับกลางจอแล้วหายเองใน ~3 วิ
        # ห้ามตีความ "ปุ่ม Buy ยังอยู่" เป็นซื้อไม่สำเร็จ — แผงซื้อเปิดค้างเป็นเรื่องปกติ
        self.log("[box] กดซื้อแล้ว → รอ toast 'Purchase complete!' หายเอง (~3 วิ)")
        self._msleep(2.0)
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
            return self._nav_failed("นำทางยังไม่สำเร็จ → รอแล้ววนลองใหม่")

        self.ensure_fast_start()

        # กลับให้ถึงหน้าเตรียมตัวชัวร์ ๆ ก่อนติ๊กบูสต์ (เผื่อมีป๊อปอัปหลังซื้อ)
        # (streak รีเซ็ตเมื่อผ่านครบทั้ง state — ถ้ารีเซ็ตตรงนี้ การพังซ้ำที่จุดนี้จะไม่ถูกจับ)
        if not self.ensure_on_boost_screen():
            return self._nav_failed("หลังซื้อ Fast Start กลับหน้าเตรียมตัวไม่ได้ → วนลองใหม่")
        self._nav_fail_streak = 0

        self.ensure_boosts_selected()
        self.log("[OK] → กด Play เริ่มวิ่งเก็บกล่อง")
        time.sleep(random.uniform(*config.PLAY_PRESS_DELAY))   # คนขยับนิ้วไปหาปุ่ม
        self.adb.tap(*config.BTN_PLAY)
        self._msleep(config.DELAY_AFTER_PLAY)
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
                act = vision.find_multiscale(screen, config.IMG_FAST_START_ACTIVATE,
                                             config.FAST_START_THRESHOLD)
                if act.found:
                    self.log(f"    [box] เจอปุ่ม activate Fast Start (score={act.score:.2f}) → กดเปิดบูสต์")
                    # กดทันทีไม่หน่วง react — ปุ่มค้างแค่ ~3 วิ พลาดคือเสียบูสต์ทั้งด่าน
                    # (ความหน่วงจาก screencap+จับภาพเองก็สุ่มพอไม่ให้เป๊ะระดับเฟรมอยู่แล้ว)
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

            # ช่วงหน้าต่าง activate เช็คจอถี่ขึ้น — ปุ่มค้างแค่ ~3 วิ ต้องเจอและกดทันทุกครั้ง
            time.sleep(0.2 if t < config.FAST_START_ACTIVATE_WINDOW
                       else config.RESULT_CHECK_INTERVAL)
        return None

    # ============================================================
    # STATE 3 — RESULT
    # ============================================================
    def record_result_coins(self, screen, readable=True):
        """บันทึกผลรอบนี้ลง coins.csv + แจ้ง GUI (จบ 1 เกม = 1 แถวเสมอ แม้อ่านเลขไม่ได้)
        readable=False = รู้อยู่แล้วว่าเฟรมนี้อ่านเลขไม่ได้ (ไม่ใช่หน้า Result / หา OK ไม่เจอ)
        → ลงแถวว่างกันรอบหายจาก log + เซฟภาพไว้ดู"""
        coins = self.coin_reader.read(screen) if (readable and screen is not None) else None
        if coins is not None:
            self.coin_total += coins
        try:
            csv_path = data_path(config.COIN_CSV)
            log_dir = os.path.dirname(csv_path)
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            with open(csv_path, "a", encoding="utf-8") as f:
                f.write(f"{ts},{coins if coins is not None else ''},{self.coin_total}\n")
            if coins is not None:
                self.log(f"[coins] เหรียญรอบนี้: {coins:,}  (รวม {self.coin_total:,})")
            elif screen is not None:
                cv2.imwrite(os.path.join(log_dir, f"result_FAIL_{ts}.png"), screen)
                self.log(f"[coins] อ่านเลขไม่ได้ → เซฟภาพ result_FAIL_{ts}.png")
            else:
                self.log("[coins] อ่านเลขไม่ได้ (ไม่มีภาพหน้าจอ) → ลงแถวว่างไว้")
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
        screen = None
        while not self._stopping():
            screen = self._cap()
            ok = vision.find(screen, config.IMG_OK_BUTTON)
            if ok.found:
                # ปุ่ม OK เขียวเป็น asset ที่เกมใช้ซ้ำหลาย dialog และ state นี้เข้ามาแบบ
                # ถูกบังคับด้วย RUN_STATE_TIMEOUT ได้ — อ่านเลขเฉพาะเมื่อเป็นหน้า Result จริง
                # กันอ่านค่ามั่วจาก dialog อื่นเข้า CSV (threshold หลวมกว่าปกติ — เทมเพลตเพี้ยน
                # เล็กน้อยต้องไม่ทำให้เหรียญถูกลงเป็นแถวว่างทุกรอบ)
                if vision.find(screen, config.IMG_RESULT, config.RESULT_CONFIRM_THRESHOLD).found:
                    self.record_result_coins(screen)
                else:
                    self.log("[WARN] เจอปุ่ม OK แต่ไม่ใช่หน้า Result → ไม่อ่านเลข (ลงแถวว่าง+เซฟภาพไว้ดู)")
                    self.record_result_coins(screen, readable=False)
                # คนจริงหยุดดูตัวเลขคะแนน/เหรียญก่อนกด OK เสมอ — ไม่กดเฟรมแรกที่ปุ่มโผล่
                if random.random() < config.READ_RESULT_LONG_CHANCE:
                    look = random.uniform(*config.READ_RESULT_LONG_RANGE)
                else:
                    look = random.uniform(*config.READ_RESULT_RANGE)
                self._pause(look)
                if self._stopping():
                    return None   # บันทึกเหรียญไปแล้วข้างบน — ออกได้เลยไม่ต้องกด
                self.log(f"[OK] เจอปุ่ม OK (score={ok.score:.3f}) → ดูผล {look:.1f} วิ แล้วกดกลับล็อบบี้")
                self.adb.tap(*ok.center)
                self._msleep(2.5)
                return State.REROLL

            attempts += 1
            if attempts >= MAX_ATTEMPTS:
                self.log("[WARN] หาปุ่ม OK ไม่เจอเกินกำหนด → บันทึกรอบนี้เป็นอ่านไม่ได้ แล้ววนกลับ STATE 1")
                self.record_result_coins(screen, readable=False)
                return State.REROLL
            self.log(f"[..] ยังไม่เจอปุ่ม OK (best={ok.score:.3f}) attempt {attempts}/{MAX_ATTEMPTS}")
            time.sleep(config.LOOP_SLEEP)

        # ถูกสั่งหยุดระหว่างหาปุ่ม OK — เกมรอบนี้จบไปแล้ว ต้องบันทึกก่อนออก ไม่งั้นรอบหายจาก log
        if screen is not None and vision.find(screen, config.IMG_RESULT,
                                              config.RESULT_CONFIRM_THRESHOLD).found:
            self.record_result_coins(screen)
        else:
            self.record_result_coins(screen, readable=False)
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
        # Session Planner (V2): พักสั้นหลังจบเกม + fatigue + สุ่มจังหวะใหม่เป็นช่วง ๆ
        # สร้างใหม่ทุกครั้งที่กดเริ่ม — 1 การกดเริ่ม = 1 เซสชัน (ความล้าเริ่มนับใหม่)
        planner = humanizer.SessionPlanner(self.log) if config.SESSION_PLANNER else None

        # ตรวจ template ที่จำเป็นครั้งเดียวก่อนเริ่ม — ไฟล์หาย/เสีย (เช่นเพิ่งแคปทับพลาด)
        # จะได้เตือนชัดทันที ไม่ใช่วนพัง 30 รอบ/อ่านเหรียญไม่ได้เงียบ ๆ กลางดึก (ไม่ abort — เตือนแล้วไปต่อ)
        ok, missing = vision.validate_templates(self._required_templates(), self.log)
        if not ok:
            self.log(f"[check][WARN] template จำเป็นขาด/เสีย {len(missing)} ไฟล์ "
                     "→ นำทาง/อ่านผลอาจล้มเหลวจนกว่าจะแคปไฟล์เหล่านี้ให้ครบ (ดูรายชื่อด้านบน)")
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
                    # พักสั้นแบบคนวางมือถือ — เฉพาะตรงนี้ (จบเกมแล้ว อยู่ล็อบบี้/หน้าปลอดภัย)
                    if planner:
                        pause = planner.on_game_end()
                        self._emit(type="fatigue", frac=planner.fatigue_frac())
                        if pause >= 1.0:
                            self.log(f"[พัก] จบเกม → พัก {pause:.0f} วิ ก่อนเริ่มรอบใหม่")
                            self._emit(type="break", secs=pause)
                            end = time.time() + pause
                            while not self._stopping() and time.time() < end:
                                time.sleep(0.5)
                            self._emit(type="break_end")

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
