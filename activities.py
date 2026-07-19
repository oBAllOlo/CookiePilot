"""
activities.py — กิจกรรมเสริม (แยกจากบอทฟาร์มหลัก กดจากแท็บ "กิจกรรม")
====================================================================
รวม 7 กิจกรรมที่ทำแทนมือ (แต่ละอันเปิดหน้าจอในเกมให้ตรงก่อนกดเริ่ม):
  1. send_hearts()        💗 ส่งหัวใจให้เพื่อน (เปิดหน้ารายชื่อเพื่อนก่อน)
  2. mail_hearts()        📬 รับ+ส่งหัวใจจากจดหมาย (เริ่มจากล็อบบี้ที่เห็นไอคอนเมล)
  3. add_friends(count)   👥 เพิ่มเพื่อนจากหน้าแนะนำ (count<=0 = ไม่จำกัด)
  4. treasure_gacha(count) 🔮 สุ่มกาชาสมบัติ (เปิดร้านสมบัติก่อน; คลังเต็มจะไปย่อยผงให้เอง)
  5. salvage(limit)       ♻️ ย่อยผงสมบัติทีละหลายชิ้น (เปิดตู้เก็บก่อน; limit ต้อง > 0)
  6. treasure_upgrade()   💎 ตีบวกสมบัติจน +9 ไล่ทีละชิ้น (เปิดหน้าสมบัติก่อน)
  7. open_gift_box(count) 🎁 เปิดกล่องของขวัญวนไป (count<=0 = ไม่จำกัด)

template ชุดนี้ (templates/ 38 ไฟล์) นำเข้าจากบอทอ้างอิง — สเกลอาจไม่ตรงจอเรา 100%
จึงใช้ find_multiscale ช่วงกว้าง (config.ACT_SCALES) + threshold หลวมกว่าบอทหลัก
ถ้า log ฟ้อง score ต่ำ/หาปุ่มไม่เจอ ให้แคปปุ่มจากจอจริงทับไฟล์เดิมใน templates/

ใช้งาน:
    from adb import Adb
    from activities import Activities
    acts = Activities(Adb(), log=print)
    acts.send_hearts()
หยุดด้วย stop_event.set() (ส่ง threading.Event เข้ามาตอนสร้าง)
"""
import os
import time
import random
import threading
import traceback

import cv2
import numpy as np

import config
import vision
from paths import data_path


class Activities:
    def __init__(self, adb, log=print, stop_event=None, on_stat=None):
        self.adb = adb
        self.log = log
        self.stop = stop_event or threading.Event()
        self.on_stat = on_stat          # callback(kind:str, n:int) — ตัวนับใน GUI (ไม่มีก็ได้)
        self._tpl_warned = set()   # template ทางเลือกที่เตือนว่า "ยังไม่มีไฟล์" ไปแล้ว (เตือนครั้งเดียวพอ)
        self._cap_fails = 0        # แคปจอพลาดติดกัน (ไว้ trigger เช็ค device ใหม่)

    # ============================================================
    # ตัวช่วย
    # ============================================================
    def _stopping(self):
        return self.stop.is_set()

    def _pause(self, seconds):
        """หลับแบบขัดจังหวะได้ (เช็ค stop ทุก ~0.1s) — ใช้แทน time.sleep ทุกจุดในกิจกรรม
        ผู้ใช้กดหยุดแล้วต้องหยุดแทบทันที ไม่ใช่รอหลับจบ"""
        end = time.time() + seconds
        while not self._stopping():
            remaining = end - time.time()
            if remaining <= 0:
                break
            time.sleep(min(0.1, remaining))

    def _msleep(self, base):
        """หน่วงจังหวะเมนูคงที่ทุกกิจกรรม = config.ACT_MENU_DELAY (ผู้ใช้สั่งให้เป็น 1 วิเท่ากันหมด)
        เดิมยืดจาก base แบบ human (humanizer.menu_pause) — ตอนนี้ fix เท่ากันเพื่อจังหวะที่คุมได้
        (base ยังรับไว้ให้ผู้เรียกไม่ต้องแก้ แต่ไม่ใช้แล้ว) ปรับค่าได้ใน settings.json"""
        self._pause(config.ACT_MENU_DELAY)

    def _cap(self):
        img = self.adb.screencap()
        if img is None:
            self._cap_fails += 1
            if self._cap_fails % 3 == 0 and not self._stopping():
                self.log("[act][adb] แคปจอพลาดติดกันหลายครั้ง → เช็ค device ใหม่ "
                         "(เผื่อหลุด/พอร์ตเปลี่ยน)")
                self.adb.ensure_device()
        else:
            self._cap_fails = 0
        return img

    def _stat(self, kind, n=1):
        """แจ้งตัวนับสถิติให้ GUI — callback พังห้ามล้มกิจกรรม"""
        if not self.on_stat:
            return
        try:
            self.on_stat(kind, n)
        except Exception:
            pass

    def _find(self, screen, img, th=None):
        """หา template แบบ multi-scale — จอ None คืน "ไม่เจอ" เลย (find_multiscale ไม่กัน None ให้)"""
        if screen is None:
            return vision.Match(False, None, 0.0)
        return vision.find_multiscale(screen, img,
                                      th or config.ACT_MATCH_THRESHOLD,
                                      scales=config.ACT_SCALES)

    def _tap_center_of(self, m, jitter=None):
        """กดกึ่งกลางปุ่มที่หาเจอ — ไม่เจอ/ไม่มี center = ไม่กด (ตาบอดห้ามกด)"""
        if not m.found or m.center is None:
            return False
        return self.adb.tap(m.center[0], m.center[1], jitter=jitter)

    def _find_tap(self, img, name, th=None, timeout=8.0, settle=0.5):
        """รอปุ่มโผล่แล้วกด — คืน True เมื่อกดสำเร็จ / False เมื่อหมดเวลา
        เก็บ best score ที่เคยเห็นไว้ log ตอนพลาด (ไว้ดูว่า template ใกล้แมตช์แค่ไหน)"""
        end = time.time() + timeout
        best = 0.0
        while not self._stopping() and time.time() < end:
            screen = self._cap()
            if screen is None:
                self._pause(0.4)   # ตาบอดห้ามกด — รอเฟรมถัดไป
                continue
            m = self._find(screen, img, th)
            best = max(best, m.score)
            if m.found:
                self.log(f"[act] เจอ {name} (score={m.score:.2f}) → กด")
                self._tap_center_of(m)
                self._msleep(settle)
                return True
            self._pause(config.ACT_POLL * 0.8)
        if not self._stopping():
            self.log(f"[act][WARN] ไม่เจอ {name} ภายใน {timeout:g} วิ (best={best:.2f}) "
                     "→ เช็คว่าเปิดหน้าจอถูกหน้า / แคป template ใหม่จากจอจริง")
        return False

    def _tap_if_found(self, img, name, settle=0.4, optional=True):
        """แคปจอใหม่แล้วกดปุ่มถ้าเห็น "ตอนนี้เลย" — best-effort ครั้งเดียว ไม่รอเหมือน _find_tap
        ใช้กับลำดับเก็บกวาดสั้น ๆ (เช่นฉากได้รางวัลใหญ่) ที่ปุ่มอาจโผล่หรือไม่โผล่ก็ได้"""
        if optional and not self._optional(img):
            return False
        screen = self._cap()
        if screen is None:
            return False
        m = self._find(screen, img)
        if not m.found:
            return False
        self.log(f"[act] เจอ {name} (score={m.score:.2f}) → กด")
        self._tap_center_of(m)
        self._msleep(settle)
        return True

    def _clear_popups(self, screen):
        """เก็บป๊อปอัปตกค้าง (Okay → ยืนยันเขียว → ยืนยันฟ้า) — กดตัวแรกที่เจอ คืน True เมื่อได้กด
        ป๊อปอัปรางวัล/แจ้งเตือนโผล่ได้ทุกกิจกรรม ถ้าไม่เก็บจะบังปุ่มจนหาอะไรไม่เจอ"""
        if screen is None:
            return False
        for img, name in ((config.IMG_ACT_OKAY, "Okay"),
                          (config.IMG_ACT_CONFIRM_GREEN, "ยืนยัน (เขียว)"),
                          (config.IMG_ACT_CONFIRM, "ยืนยัน (ฟ้า)")):
            if not self._optional(img):
                continue
            m = self._find(screen, img)
            if m.found:
                self.log(f"[act] ปิดป๊อปอัป {name} (score={m.score:.2f})")
                self._tap_center_of(m)
                self._msleep(0.3)
                return True
        return False

    def _require(self, paths):
        """ตรวจ template ที่จำเป็นครั้งเดียวก่อนเริ่มกิจกรรม — ขาดตัวเดียวก็ยกเลิก
        (find* โยน FileNotFoundError กลางลูป = เด้งทั้งกิจกรรมแบบงง ๆ — กันไว้ตรงนี้ชัดกว่า)"""
        ok, missing = vision.validate_templates(paths, self.log)
        if not ok:
            self.log(f"[act][ERR] template ขาด: {', '.join(missing)} → ยกเลิกกิจกรรมนี้ "
                     "(แคปปุ่มจากจอจริงเซฟลง templates/ แล้วลองใหม่)")
            return False
        return True

    def _optional(self, img):
        """template ทางเลือก: มีไฟล์ใช้ได้ไหม — ไม่มีเตือนครั้งเดียวพอแล้วข้ามขั้นนั้นให้"""
        if vision.has_template(img):
            return True
        if img not in self._tpl_warned:
            self._tpl_warned.add(img)
            self.log(f"[act][WARN] ยังไม่มีไฟล์ {img} (ทางเลือก) → ข้ามขั้นนี้ไป "
                     "— แคปปุ่มจากจอจริงมาใส่ templates/ จะทำงานครบขึ้น")
        return False

    def _save_debug(self, tag, screen, points=None):
        """เซฟภาพจอไว้ใน coin_logs/ ให้ผู้ใช้เทียบจูน template/พิกัด
        points = จุดที่จะวงกลมสีแดงทับ (เช่นตำแหน่งช่องกริดที่บอทจะกด)"""
        if screen is None:
            return None
        try:
            log_dir = os.path.dirname(data_path(config.COIN_CSV))
            os.makedirs(log_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            p = os.path.join(log_dir, f"{tag}_{ts}.png")
            img = screen.copy()
            for (x, y) in (points or []):
                cv2.circle(img, (int(x), int(y)), 12, (0, 0, 255), 2)
            cv2.imwrite(p, img)
            self.log(f"[act] เซฟภาพ debug ไว้ที่ {p}")
            return p
        except Exception:
            self.log("[act][WARN] เซฟภาพ debug ไม่สำเร็จ: "
                     f"{traceback.format_exc().splitlines()[-1]}")
            return None

    def _close_window(self):
        """ปิดหน้าต่างจดหมาย/ร้าน — มี template ปุ่มปิดใช้ก่อน ไม่มี/ไม่เจอค่อย fallback
        แตะมุมขวาบน (ปุ่ม X ตำแหน่งตายตัวของเกม — กดพลาดสุดก็แค่ไม่เกิดอะไร)"""
        screen = self._cap()
        if screen is not None and self._optional(config.IMG_ACT_CLOSE_LIFE_SHOP):
            m = self._find(screen, config.IMG_ACT_CLOSE_LIFE_SHOP)
            if m.found:
                self.log(f"[act] ปิดหน้าต่างด้วยปุ่มปิด (score={m.score:.2f})")
                self._tap_center_of(m)
                self._msleep(0.4)
                return
        self.adb.tap(*config.ACT_BTN_MAIL_CLOSE, jitter=config.SAFE_TAP_JITTER)
        self._msleep(0.4)

    # ============================================================
    # 💗 ส่งหัวใจ (เปิดหน้ารายชื่อเพื่อนค้างไว้ก่อนกดเริ่ม)
    # ============================================================
    def send_hearts(self):
        """ไล่กดปุ่มส่งใจทีละคน เลื่อนรายชื่อลงจนถึงล่างสุดแล้วจบเอง"""
        self.log("\n===== [กิจกรรม] 💗 ส่งหัวใจ =====")
        self.log("[act] ต้องเปิดหน้ารายชื่อเพื่อน (หน้าส่งใจ) ค้างไว้ก่อนกดเริ่ม")
        if not self._require([config.IMG_ACT_SEND_HEART]):
            return None

        sent = 0
        # แนว y ของปุ่มที่กดไปแล้ว — เก็บสะสมทั้งรัน (ตามบอทอ้างอิง ไม่ล้างหลังเลื่อนจอ)
        # หลังเลื่อนแล้ว y ใหม่อาจบังเอิญชนของเก่า = ข้ามคนไปบ้าง ยอมรับได้
        # ดีกว่ากดซ้ำแถวเดิม (การ prune รายการตามจอเป็น overengineering — ไม่ทำ)
        tapped_ys = []
        stable = 0        # จอนิ่งติดกันกี่รอบหลังเลื่อน (ไว้ตัดสินว่าถึงล่างสุด)
        last_sig = None

        while not self._stopping():
            screen = self._cap()
            if screen is None:
                self._pause(0.4)   # ตาบอดห้ามกด
                continue

            # หาปุ่มส่งใจทุกจุดในแถบกลางจอ (คอลัมน์ตำแหน่งปุ่ม — ตัด match หลอกนอกโซน)
            hits = vision.find_all(screen, config.IMG_ACT_SEND_HEART,
                                   threshold=config.ACT_MATCH_THRESHOLD,
                                   region=config.ACT_HEART_BAND)
            fresh = [h for h in hits
                     if all(abs(h[1] - y) > config.ACT_HEART_Y_GAP for y in tapped_ys)]

            if fresh:
                cx, cy, sc = fresh[0]
                self.log(f"[act] เจอปุ่มส่งใจที่ ({cx},{cy}) (score={sc:.2f}) → กด")
                self.adb.tap(cx, cy, jitter=config.SAFE_TAP_JITTER)
                tapped_ys.append(cy)
                sent += 1
                self._stat("hearts")
                # รอป๊อปอัปยืนยัน (เขียว) สูงสุด 3 รอบ — บางเครื่องป๊อปอัปมาช้า
                for _ in range(3):
                    if self._stopping():
                        break
                    self._pause(0.3)
                    scr2 = self._cap()
                    if scr2 is None:
                        continue
                    if self._optional(config.IMG_ACT_CONFIRM_GREEN):
                        m = self._find(scr2, config.IMG_ACT_CONFIRM_GREEN)
                        if m.found:
                            self._tap_center_of(m)
                            self._msleep(0.3)
                            break
                continue   # 1 รอบลูป = ส่งใจ 1 คน — วนหาปุ่มถัดไปทันที

            # ไม่มีปุ่มใหม่บนจอ → เก็บป๊อปอัปตกค้างแล้วเลื่อนรายชื่อลง
            self._clear_popups(screen)
            self.adb.swipe(*config.ACT_HEART_SCROLL, duration_ms=400)
            self._msleep(0.5)

            # เช็คถึงล่างสุด: เลื่อนแล้วจอไม่เปลี่ยนติดกันหลายรอบ = สุดลิสต์แล้ว
            scr2 = self._cap()
            if scr2 is None:
                continue   # frame_signature โยน error ถ้าจอ None — ข้ามเช็ครอบนี้
            sig = vision.frame_signature(scr2)
            if (last_sig is not None
                    and float(np.abs(sig - last_sig).mean()) < config.ACT_LIST_STABLE_DIFF):
                stable += 1
                if stable >= config.ACT_LIST_STABLE_COUNT:
                    self.log("[act] ถึงล่างสุดของรายชื่อแล้ว")
                    break
            else:
                stable = 0
            last_sig = sig

        self.log(f"[act] 💗 จบส่งหัวใจ — ส่งไป {sent} ครั้ง")
        return sent

    # ============================================================
    # 📬 รับหัวใจจากเมล (เริ่มจากล็อบบี้ที่เห็นไอคอนจดหมาย)
    # ============================================================
    def mail_hearts(self):
        """เปิดจดหมาย → กด "Quick Receive & Send Lives" ครั้งเดียว → เกมเด้งไดอะล็อก
        "Send X a free Life?" ไล่ทีละคนเอง → กด Confirm วนจนหมด แล้วปิดหน้าต่าง
        (ยืนยันจากจอจริง 2026-07-18 — ไม่ต้องเลือกทีละคน ไม่มีขั้นกดเลือกแล้ว)"""
        self.log("\n===== [กิจกรรม] 📬 รับหัวใจเมล =====")
        self.log("[act] เริ่มจากหน้าล็อบบี้ที่เห็นไอคอนจดหมาย")
        req = [config.IMG_ACT_MAIL, config.IMG_ACT_RECEIVE_HEART, config.IMG_ACT_MAIL_CONFIRM]
        if not self._require(req):
            return None

        if not self._find_tap(config.IMG_ACT_MAIL, "ไอคอนจดหมาย", timeout=8.0):
            return None

        # ไม่เจอปุ่ม Quick Receive & Send = ไม่มีหัวใจค้างรับเลย (รายชื่อว่าง) — ปิดจบเงียบ ๆ
        if not self._find_tap(config.IMG_ACT_RECEIVE_HEART, 'ปุ่ม "Quick Receive & Send Lives"',
                              timeout=6.0):
            self.log("[act] ไม่มีหัวใจให้รับตอนนี้ (รายชื่อว่าง) → ปิดหน้าต่าง")
            self._close_window()
            return 0

        count = 0
        misses = 0   # หาปุ่ม Confirm ไม่เจอติดกัน — เกมไล่จบครบทุกคนแล้วก็หยุดโผล่ ต้องมีทางออก
        while not self._stopping():
            screen = self._cap()
            if screen is None:
                self._pause(0.4)   # ตาบอดห้ามกด
                continue

            m = self._find(screen, config.IMG_ACT_MAIL_CONFIRM)
            if m.found:
                self._tap_center_of(m)
                count += 1
                self._stat("hearts")
                misses = 0
                self._msleep(0.25)   # ไดอะล็อกคนถัดไปเด้งเร็ว — รอสั้น ๆ พอ
                continue

            # เผื่อบางเคสมีป้ายพิเศษโผล่ (หัวใจหมด/ครบทุกใบ) — ยังไม่เคยเจอบนจอจริง แต่กันไว้
            if self._optional(config.IMG_ACT_NO_LIVES):
                mn = self._find(screen, config.IMG_ACT_NO_LIVES)
                if mn.found:
                    self.log(f"[act] หัวใจหมดแล้ว (score={mn.score:.2f})")
                    break
            if self._optional(config.IMG_ACT_ALL_LIVES_DONE):
                md = self._find(screen, config.IMG_ACT_ALL_LIVES_DONE)
                if md.found:
                    self.log(f"[act] 📬 รับ/ส่งครบทุกใบแล้ว! (score={md.score:.2f})")
                    break

            misses += 1
            if misses >= config.ACT_MAIL_MISS_LIMIT:
                self.log(f"[act] หาปุ่ม Confirm ไม่เจอ {misses} รอบติด → ถือว่าจบแล้ว")
                break
            self._pause(config.ACT_POLL)

        self._close_window()
        self.log(f"[act] 📬 จบรับหัวใจเมล — กดยืนยันไป {count} ครั้ง")
        return count

    # ============================================================
    # 👥 เพิ่มเพื่อน
    # ============================================================
    def add_friends(self, count=0):
        """กดเพิ่มเพื่อนจากหน้าแนะนำ สลับกดรีเฟรชเปลี่ยนชุดรายชื่อ (count<=0 = ไม่จำกัด)"""
        self.log("\n===== [กิจกรรม] 👥 เพิ่มเพื่อน =====")
        if not self._require([config.IMG_ACT_ADD_FRIEND]):
            return None

        # นำทาง best-effort — ผู้ใช้อาจเปิดหน้าแนะนำเพื่อนค้างไว้เองแล้ว หาไม่เจอไม่ถือว่าพัง
        if self._optional(config.IMG_ACT_FRIENDS_BTN):
            if not self._find_tap(config.IMG_ACT_FRIENDS_BTN, "ปุ่มเพื่อน", timeout=4.0):
                self.log("[act] ไม่เจอปุ่มเพื่อน → ถือว่าเปิดพาเนลอยู่แล้ว ไปต่อ")
        if self._optional(config.IMG_ACT_FIND_FRIEND):
            if not self._find_tap(config.IMG_ACT_FIND_FRIEND, "แท็บแนะนำเพื่อน", timeout=4.0):
                self.log("[act] ไม่เจอแท็บแนะนำเพื่อน → ถือว่าอยู่หน้านั้นแล้ว ไปต่อ")

        added = 0
        # แนว y ที่กดไปแล้วในชุดรายชื่อปัจจุบัน — ปุ่ม Request ไม่เปลี่ยนสถานะแม้ขอไม่สำเร็จ
        # (เช่นป๊อปอัป "This player's friend list is full!" เด้งแล้วหายเองใน ~2 วิ) ถ้าไม่จำ
        # ตำแหน่งไว้ บอทจะกดคนเดิมซ้ำไม่รู้จบ (ยืนยันจากจอจริง 2026-07-18) — ล้างทิ้งตอนรีเฟรช
        # เพราะรายชื่อชุดใหม่ทั้งหมด ไม่ใช่ต่อจากของเดิม
        tapped_ys = []
        no_progress = 0   # ไม่เจอทั้งคนใหม่/refresh ติดกัน — รายชื่อหมด/หลงหน้าจอ ต้องเลิกเอง
        while not self._stopping():
            if count > 0 and added >= count:
                self.log(f"[act] ครบเป้า {count} คนแล้ว")
                break
            screen = self._cap()
            if screen is None:
                self._pause(0.4)   # ตาบอดห้ามกด
                continue

            hits = vision.find_all(screen, config.IMG_ACT_ADD_FRIEND,
                                   threshold=config.ACT_MATCH_THRESHOLD,
                                   region=config.ACT_FRIEND_BAND)
            fresh = [h for h in hits
                     if all(abs(h[1] - y) > config.ACT_FRIEND_Y_GAP for y in tapped_ys)]

            if fresh:
                cx, cy, sc = fresh[0]
                self.log(f"[act] เจอปุ่มขอเป็นเพื่อนที่ ({cx},{cy}) (score={sc:.2f}) → กด")
                self.adb.tap(cx, cy, jitter=config.SAFE_TAP_JITTER)
                tapped_ys.append(cy)
                added += 1
                self._stat("friends")
                no_progress = 0
                self._msleep(0.5)   # เผื่อป๊อปอัป "list เต็ม" เด้งขึ้นมาแล้วหายเอง
                continue

            # ไม่มีคนใหม่ในชุดนี้แล้ว → เก็บป๊อปอัปตกค้าง รอเกมหน่วง แล้วกดรีเฟรชสลับชุดรายชื่อ
            self._clear_popups(screen)
            self._pause(0.6)
            scr2 = self._cap()   # จอเปลี่ยนไปแล้วหลังรอ — ต้องแคปใหม่ก่อนหารีเฟรช
            refreshed = False
            if scr2 is not None and self._optional(config.IMG_ACT_REFRESH_FRIEND):
                m2 = self._find(scr2, config.IMG_ACT_REFRESH_FRIEND)
                if m2.found:
                    self.log(f"[act] กดรีเฟรชสลับรายชื่อ (score={m2.score:.2f})")
                    self._tap_center_of(m2)
                    refreshed = True
                    self._msleep(0.5)
            if refreshed:
                tapped_ys = []   # ชุดรายชื่อใหม่ทั้งหมด — เริ่มจำ y ใหม่
                no_progress = 0
            else:
                no_progress += 1
                if no_progress >= config.ACT_FRIEND_NO_PROGRESS:
                    self.log("[act] ไม่มีปุ่มให้กดต่อแล้ว")
                    break

        self.log(f"[act] 👥 จบเพิ่มเพื่อน — ส่งคำขอไป {added} คน "
                 "(นับตอนกด ไม่ใช่ตอนอีกฝ่ายรับ — เกมไม่บอกผลชัดเจน)")
        return added

    # ============================================================
    # 🔮 กาชาสมบัติ (เปิดร้านสมบัติก่อน — เอนจินไล่กดปุ่มเท่าที่เห็นบนจอ)
    # ============================================================
    def treasure_gacha(self, count=0):
        """สุ่มกล่อง 5000 วนไป (count<=0 = จนกว่าจะกดหยุด/เหรียญหมด)
        คลังเต็มจะพาไปย่อยผง (salvage) เคลียร์ที่แล้วกลับมาสุ่มต่อเอง"""
        self.log("\n===== [กิจกรรม] 🔮 กาชาสมบัติ =====")
        self.log("[act] ต้องเปิดหน้าร้านสมบัติค้างไว้ก่อนกดเริ่ม")
        req = [config.IMG_ACT_GACHA_5000, config.IMG_ACT_GACHA_DRAW,
               config.IMG_ACT_GACHA_CONFIRM]
        if not self._require(req):
            return None

        opened = 0
        batch = 0   # เปิดสะสมตั้งแต่ย่อยผงรอบก่อน — ใช้เป็นจำนวนชิ้นที่ต้องย่อยตอนคลังเต็ม
        idle = 0
        while not self._stopping():
            screen = self._cap()
            if screen is None:
                self._pause(0.4)   # ตาบอดห้ามกด
                continue

            # 1) คลังเต็ม → ต้องไปย่อยผงก่อน — เช็ค "ก่อน" confirm เพราะปุ่ม "Confirm" ของป๊อปอัปนี้
            #    ใช้ template เดียวกับปุ่มยืนยันซื้อ (button_gacha_confirm) เป๊ะ — ถ้าเช็ค confirm
            #    ก่อน บอทจะกดปิดป๊อปอัปแล้วนับเป็นซื้อ ไม่ไปย่อยผง วนไม่รู้จบ (ยืนยันจากจอจริง)
            if self._optional(config.IMG_ACT_NO_SPACE):
                m = self._find(screen, config.IMG_ACT_NO_SPACE)
                if m.found:
                    self.log(f"[act] คลังเต็ม → ไปย่อยผงก่อน (score={m.score:.2f})")
                    # ป๊อปอัป "Not enough space" เป็น modal — บังแท็บ Cabinet ด้านหลังไว้
                    # กดแท็บทั้งที่ป๊อปอัปยังค้าง = ไม่ติด ต้องกด Confirm ปิดก่อนแล้วปุ่มถึงสว่าง
                    # กดได้ (ยืนยันจากจอจริง 2026-07-18: template cabinet เป็นแบบสว่างหลังปิดป๊อปอัป)
                    self._find_tap(config.IMG_ACT_CONFIRM_GREEN, "ปิดป๊อปอัปคลังเต็ม", timeout=4.0)
                    if (self._optional(config.IMG_ACT_CABINET)
                            and self._find_tap(config.IMG_ACT_CABINET, "แท็บ Cabinet", timeout=6.0)):
                        got = self.salvage(limit=max(batch, config.ACT_SALVAGE_BATCH),
                                           _from_gacha=True)
                        if got is None:
                            # ย่อยไม่สำเร็จ (เช่นของติดดาวโดนเลือก) แต่คลังยังเต็ม —
                            # การเรียงตาม tier ทำให้วนกลับมาเลือกชิ้นเดิมซ้ำไม่รู้จบ → ต้องเลิก
                            self.log("[act][WARN] ย่อยผงไม่สำเร็จแต่คลังยังเต็ม → เลิกกาชา "
                                     "(เอาดาวออกจากของ tier ต่ำ หรือย่อยเองก่อน แล้วค่อยเริ่มใหม่)")
                            break
                        batch = 0
                        idle = 0
                        continue
                    # เข้าตู้เก็บไม่ได้ = เคลียร์ที่ไม่ได้ — ปล่อยนับ idle ให้เลิกเอง ดีกว่ากดมั่ว
                    idle += 1
                    if idle >= config.ACT_IDLE_LIMIT:
                        self.log(f"[act][WARN] คลังเต็มแต่เข้าตู้เก็บไม่ได้ {idle} รอบ → เลิก "
                                 "(แคป templates/button_cabinet.png ใหม่จากจอจริง)")
                        self._save_debug("act_gacha_idle", screen)
                        break
                    self._pause(config.ACT_POLL)
                    continue

            # ===== hot path: ปุ่มที่เจอบ่อยตอนซื้อวน — coin_zero ย้ายไปเช็คหลัง (ไม่ชน template) =====
            # 2) ปุ่มยืนยันซื้อ — จุดที่ "เสียเหรียญจริง" นับกล่องที่นี่จุดเดียว
            m = self._find(screen, config.IMG_ACT_GACHA_CONFIRM)
            if m.found:
                if self._stopping():
                    break   # สั่งหยุดแล้วห้ามกดซื้อเพิ่ม — เช็คก่อนเสียเหรียญเสมอ
                self.log(f"[act] เจอปุ่มยืนยันซื้อ (score={m.score:.2f}) → กด")
                self._tap_center_of(m)
                opened += 1
                batch += 1
                self._stat("gacha")
                self.log(f"[act] 🔮 เปิดกล่องที่ {opened}")
                if count > 0 and opened >= count:
                    self.log(f"[act] ครบเป้า {count} กล่องแล้ว")
                    break
                idle = 0
                self._msleep(0.15)   # แค่กดปิดป๊อปอัปเดิม รอสั้น ๆ พอ
                continue

            # 3) ปุ่มเปิดสุ่ม
            m = self._find(screen, config.IMG_ACT_GACHA_DRAW)
            if m.found:
                self.log(f"[act] เจอปุ่มเปิดสุ่ม (score={m.score:.2f}) → กด")
                self._tap_center_of(m)
                idle = 0
                self._msleep(0.3)
                continue

            # 4) เลือกกล่องราคา 5000 = ซื้อทันที (ไม่มีไดอะล็อกยืนยัน) → หีบปิดนั่งค้าง ~3.5 วิ
            #    กว่าจะ auto-open → สแปมแตะที่ "หีบ" (ACT_BTN_CHEST) ข้ามฉากทันที
            #    (ยืนยันจากจอจริง 2026-07-19: แตะซ้ำ ~5 ที Confirm รางวัลโผล่ ~2 วิ แทน ~5.4 วิ
            #     ประหยัด ~3 วิ/กล่อง; แตะกลางจอ (640,360) ครั้งเดียวแบบเดิมไม่โดนหีบ = รอเก้อ)
            m = self._find(screen, config.IMG_ACT_GACHA_5000)
            if m.found:
                self.log(f"[act] เจอกล่องราคา 5000 (score={m.score:.2f}) → กด+สแปมแตะหีบข้ามฉาก")
                self._tap_center_of(m)
                for _ in range(config.ACT_GACHA_CHEST_TAPS):
                    if self._stopping():
                        break
                    self.adb.tap(*config.ACT_BTN_CHEST)
                    self._pause(0.25)
                idle = 0
                continue

            # 5) เปิดหีบ (ฉากโชว์ของ) → แตะกลางจอเร่งอนิเมชันโชว์รางวัลให้ข้ามไว
            #    (เหมือนตอนเลือกกล่อง 5000 — ไม่งั้นบอทนั่งรอ poll จนฉากรางวัลจบเอง = ช้า)
            if self._optional(config.IMG_ACT_GACHA_CHEST):
                m = self._find(screen, config.IMG_ACT_GACHA_CHEST)
                if m.found:
                    self.log(f"[act] เจอหีบ (score={m.score:.2f}) → กดเปิด")
                    self._tap_center_of(m)
                    self._msleep(0.2)
                    self.adb.tap(*config.ACT_BTN_CENTER)   # เร่งข้ามฉากโชว์รางวัล
                    idle = 0
                    self._msleep(0.2)
                    continue

            # ===== สถานะพิเศษ (นาน ๆ เจอ เช็คหลัง hot path) =====
            # เหรียญไม่พอ → จบกาชา (เช็คก่อน _clear_popups ไม่งั้นโดนกด Okay ทิ้งแล้ววนซื้อต่อ
            #   ไม่รู้จบทั้งที่ไม่มีเหรียญ)
            if self._optional(config.IMG_ACT_COIN_ZERO):
                m = self._find(screen, config.IMG_ACT_COIN_ZERO)
                if m.found:
                    self.log(f"[act] ⚠ เหรียญหมด → จบกาชา (score={m.score:.2f})")
                    self._clear_popups(screen)   # เก็บ Okay ที่ค้างก่อนออก
                    break

            # 6) ป๊อปอัปรางวัล/ยืนยันทั่วไป
            if self._clear_popups(screen):
                idle = 0
                continue

            # 7) ปุ่มกลับเข้าโหมดสมบัติ (หลังกลับจากตู้เก็บ) — ไว้ท้ายสุด กันไปทับปุ่มกาชา
            if self._optional(config.IMG_ACT_TREASURE):
                m = self._find(screen, config.IMG_ACT_TREASURE)
                if m.found:
                    self.log(f"[act] กลับเข้าโหมดสมบัติ (score={m.score:.2f})")
                    self._tap_center_of(m)
                    idle = 0
                    self._msleep(0.3)
                    continue

            idle += 1
            if idle >= config.ACT_IDLE_LIMIT:
                self.log(f"[act][WARN] ไม่เจอปุ่มที่รู้จักเลย {idle} รอบ → เลิก "
                         "(จอไม่ตรง/template ไม่แมตช์ — เซฟภาพไว้ที่ coin_logs/ ดูแล้วแคปทับ)")
                self._save_debug("act_gacha_idle", screen)
                break
            self._pause(config.ACT_POLL)

        self.log(f"[act] 🔮 จบกาชา — เปิดไป {opened} กล่อง")
        return opened

    # ============================================================
    # ♻️ ย่อยผง (กดเดี่ยว ๆ ต้องเปิดหน้า "Treasures" ก่อน — กดปุ่ม "Cabinet" มุมซ้ายบนของ
    #    หน้าร้านสมบัติ (ไม่ใช่ปุ่ม "Change") จะเห็นปุ่ม Extract แถบล่าง ยังไม่ต้องกด)
    # ============================================================
    def salvage(self, limit=0, _from_gacha=False):
        """เลือกของ limit ชิ้นตามกริดในตู้ แล้ว Extract ทีเดียว
        _from_gacha=True = ถูกเรียกจาก treasure_gacha ตอนคลังเต็ม (ไม่ใช่กดเองจาก GUI)
        (ยืนยันจากจอจริง 2026-07-18: ปุ่ม Extract ในแท็บ "Ingredients" เป็นคนละฟีเจอร์ — สกัด
        วัตถุดิบคราฟต์ ไม่เกี่ยวกับสมบัติเลย ทางเข้าที่ถูกคือปุ่ม "Extract" แถบล่างของหน้า
        "Treasures" (เข้าทางปุ่ม "Cabinet" มุมซ้ายบน) — กดแล้วเข้าโหมดเลือกหลายชิ้นแบบที่ออกแบบไว้)"""
        self.log("\n===== [กิจกรรม] ♻️ ย่อยผง =====")
        if not _from_gacha:
            self.log('[act] ต้องเปิดหน้า "Treasures" ค้างไว้ก่อนกดเริ่ม '
                     '(กดปุ่ม "Cabinet" มุมซ้ายบนของหน้าร้านสมบัติ — ไม่ใช่ปุ่ม "Change")')
        if limit <= 0:
            self.log('[act][WARN] ใส่จำนวนชิ้นที่จะย่อยในช่อง "จำนวน" ก่อน (0 ไม่ได้)')
            return True   # ต้นฉบับ (doc): limit<=0 → return True (ไม่มีอะไรให้ย่อย ถือว่าผ่าน)
        # ต้นฉบับใช้ extract + confirm_extract + sort_tier + tier + popup_favorite
        # (ไดอะล็อกชั้นสอง extract_dialog เป็นของจอเราเพิ่มมา — ทำเป็น optional ตอนกด Extract)
        if not self._require([config.IMG_ACT_EXTRACT, config.IMG_ACT_CONFIRM_EXTRACT]):
            return None

        # 1) เข้าโหมดเลือกชิ้นย่อย
        if not self._find_tap(config.IMG_ACT_EXTRACT, "ปุ่มเข้าโหมดย่อย", timeout=8.0):
            return None

        # 2) เรียงตาม "Obtained" (ของที่เพิ่งได้มาล่าสุดมาต้นแถว) ก่อนเลือก — ผู้ใช้สั่งเปลี่ยน
        #    จากเดิมเรียง Tier มาเป็น Obtained (ของกากที่เพิ่งสุ่มได้จะอยู่ต้นแถว เลือกย่อยได้ตรงกว่า)
        #    เปิดเมนู Sort แล้วเลือกฟิลด์ Obtained — popup_favorite ยังเป็นตาข่ายกันย่อยของดีตอนท้าย
        if self._optional(config.IMG_ACT_SORT_TIER):
            self._find_tap(config.IMG_ACT_SORT_TIER, "เปิดเมนูเรียง", timeout=4.0)
        if self._optional(config.IMG_ACT_OBTAINED):
            self._find_tap(config.IMG_ACT_OBTAINED, "เลือกเรียงตาม Obtained", timeout=4.0)

        # 2.5) เซฟภาพตำแหน่งกริดไว้เทียบจูนพิกัด (ACT_SALVAGE_SLOT1 / STEP_X) ได้เอง
        screen = self._cap()
        points = [(config.ACT_SALVAGE_SLOT1[0] + c * config.ACT_SALVAGE_STEP_X,
                   config.ACT_SALVAGE_SLOT1[1])
                  for c in range(config.ACT_SALVAGE_COLS)]
        self._save_debug("act_salvage_grid", screen, points)
        self.log("[act] เซฟภาพตำแหน่งช่องที่จะกดไว้ที่ coin_logs/act_salvage_grid_*.png "
                 "— ถ้าวงกลมไม่ทับช่องของ ให้แก้ ACT_SALVAGE_SLOT1 / ACT_SALVAGE_STEP_X "
                 "ใน settings.json")

        # 3) ไล่กดเลือกช่องตามกริด — แตะ 1 ครั้ง/ช่อง (ตามต้นฉบับ) ครบแถวปัดจอขึ้นแถวใหม่
        for i in range(limit):
            if self._stopping():
                self.log("[act] สั่งหยุดระหว่างเลือกชิ้น → ยกเลิกย่อยผง")
                return None
            col = i % config.ACT_SALVAGE_COLS
            if col == 0 and i > 0:
                # แถวใหม่เลื่อนขึ้นมาแทนที่ — กดแถวเดิมตำแหน่งเดิมได้เลย ไม่ต้องคำนวณ y ใหม่
                self.adb.swipe(*config.ACT_SALVAGE_ROW_SWIPE, duration_ms=500)
                self._msleep(0.4)
            x = config.ACT_SALVAGE_SLOT1[0] + col * config.ACT_SALVAGE_STEP_X
            y = config.ACT_SALVAGE_SLOT1[1]
            self.adb.tap(x, y, jitter=config.SAFE_TAP_JITTER)
            self._pause(0.2)

        # 4) กด Extract (เขียวใหญ่) หลังเลือกครบ — ต้นฉบับเป็นชั้นเดียว แต่จอเรามีไดอะล็อกเตือน
        #    ชั้นสองด้วย จึงกดต่อแบบ optional (มีก็กด ไม่มีก็ข้าม ไม่บังคับ)
        if not self._find_tap(config.IMG_ACT_CONFIRM_EXTRACT, "ปุ่ม Extract", timeout=6.0):
            self.log("[act][WARN] เลือกของแล้วแต่หาปุ่ม Extract ไม่เจอ → ยกเลิก "
                     "(พิกัดกริดอาจเยื้องจนไม่ได้เลือกอะไรเลย — ดูภาพ act_salvage_grid_*.png)")
            return None
        self._tap_if_found(config.IMG_ACT_EXTRACT_DIALOG,
                           "ปุ่ม Extract (ยืนยันในไดอะล็อก)", settle=0.4)

        # 5) ตรวจผล 3 รอบ — ต้นฉบับ: เจอ popup_favorite = ย่อยไม่ได้ / เจอปุ่มยืนยัน = สำเร็จ
        #    หมายเหตุ: คง return None ตอนติดดาวไว้ (ต่างจาก doc ที่ return True) — เพราะถ้า
        #    return True เป๊ะตาม doc ลูปกาชาจะวนเรียกย่อยซ้ำไม่รู้จบเมื่อคลังเต็มด้วยของติดดาวหมด
        for _ in range(3):
            if self._stopping():
                break
            scr = self._cap()
            if scr is not None:
                if self._optional(config.IMG_ACT_FAVORITE):
                    m = self._find(scr, config.IMG_ACT_FAVORITE)
                    if m.found:
                        self.log(f"[act] ⚠ มีของติดดาวถูกเลือก → ย่อยไม่ได้ ยกเลิก "
                                 f"(score={m.score:.2f})")
                        self._clear_popups(scr)
                        if _from_gacha:
                            self._close_window()   # ปิดตู้กลับล็อบบี้ — บอทอ้างอิงก็ปิดคลังก่อนกลับ
                        return None
                if self._clear_popups(scr):
                    self._stat("salvage", limit)
                    self.log(f"[act] ♻️ ย่อยผงสำเร็จ {limit} ชิ้น")
                    break
            self._pause(0.5)

        # 7) มาจากกาชาต้องปิดตู้กลับล็อบบี้ก่อน — ปุ่มกลับโหมดสมบัติ (button_treasure)
        #    อยู่ที่ล็อบบี้ ไม่ใช่ในตู้ (บอทอ้างอิงก็ปิดคลังก่อน return เสมอ)
        #    ไม่งั้นลูปกาชามองไม่เห็นปุ่มอะไรเลย นับ idle จนเลิกทั้ง flow
        #    ส่วนกดเดี่ยว ๆ จบแค่นี้ ปล่อยหน้าจอไว้ตามเดิม
        if _from_gacha:
            self._close_window()
        return limit

    # ============================================================
    # 💎 อัพเกรด +9 (เปิดหน้าสมบัติก่อน — ไล่อัพทีละชิ้นจากช่องซ้ายบน)
    # ============================================================
    def treasure_upgrade(self):
        """วนตีบวกทีละชิ้นจน +9 → ชิ้นถัดไป — หยุดเมื่อเหรียญหมด/ปุ่มขั้นตอนหาย/สั่งหยุด"""
        self.log("\n===== [กิจกรรม] 💎 อัพเกรด +9 =====")
        self.log("[act] ต้องเปิดหน้าสมบัติค้างไว้ก่อนกดเริ่ม — จะไล่อัพชิ้นช่องซ้ายบนไปเรื่อย ๆ")
        req = [config.IMG_ACT_UPGRADE, config.IMG_ACT_SELECT, config.IMG_ACT_SELECT_CORRECT,
               config.IMG_ACT_REGULAR, config.IMG_ACT_FULLY_UPGRADE, config.IMG_ACT_COIN_ZERO]
        if not self._require(req):
            return None

        # best-effort: เผื่อผู้ใช้ยังอยู่ล็อบบี้ — เห็นปุ่มเข้าโหมดสมบัติก็กดเข้าให้ครั้งเดียว
        self._tap_if_found(config.IMG_ACT_TREASURE, "ปุ่มเข้าโหมดสมบัติ", settle=0.5)

        done = 0
        presses = 0
        stop_all = False   # เหรียญหมด/idle เกิน — จบทั้ง flow ไม่ใช่แค่ชิ้นนี้
        while not self._stopping() and not stop_all:
            # เข้าโหมดอัพเกรด → เลือกชิ้น (ปุ่มไหนหาย = จอเปลี่ยน/จบของ → เลิกทั้ง flow)
            if not self._find_tap(config.IMG_ACT_UPGRADE, "ปุ่มอัพเกรด", timeout=8.0):
                break
            if not self._find_tap(config.IMG_ACT_SELECT, "ปุ่มเลือกชิ้น", timeout=6.0):
                break
            # เลือกชิ้นช่องซ้ายบน (พิกัดเดียวกับกริดย่อยผง — จูนที่เดียวใช้ได้สองที่)
            self.adb.tap(*config.ACT_SALVAGE_SLOT1)
            self._msleep(0.4)
            if not self._find_tap(config.IMG_ACT_SELECT_CORRECT, "ปุ่มยืนยันชิ้น", timeout=6.0):
                break

            # ลูปตีบวก — วนกด regular จนกว่าจะ +9 เต็ม/เหรียญหมด
            idle = 0
            while not self._stopping():
                screen = self._cap()
                if screen is None:
                    self._pause(0.4)   # ตาบอดห้ามกด
                    continue

                m = self._find(screen, config.IMG_ACT_COIN_ZERO)
                if m.found:
                    self.log(f"[act] ⚠ เหรียญหมด → หยุดอัพเกรด (score={m.score:.2f})")
                    stop_all = True
                    break

                m = self._find(screen, config.IMG_ACT_FULLY_UPGRADE)
                if m.found:
                    self.log(f"[act] 🎉 +9 เต็ม! (ชิ้นที่ {done + 1}, score={m.score:.2f})")
                    self._tap_if_found(config.IMG_ACT_CANCEL_UPGRADE2,
                                       "ปุ่มปิดหน้า +9", settle=0.4)
                    done += 1
                    self._stat("upgraded")
                    break   # ไปชิ้นถัดไป

                if self._optional(config.IMG_ACT_CANCEL_UPGRADE):
                    m = self._find(screen, config.IMG_ACT_CANCEL_UPGRADE)
                    if m.found:
                        # ป๊อปอัปคั่นกลางระหว่างตี — ปิดแล้วตีต่อ (ไม่ใช่การหยุด)
                        self.log(f"[act] ปิดป๊อปอัปคั่นตีบวก (score={m.score:.2f})")
                        self._tap_center_of(m)
                        idle = 0
                        self._msleep(0.3)
                        continue

                m = self._find(screen, config.IMG_ACT_REGULAR)
                if m.found:
                    if self._stopping():
                        break   # ตีบวกเสียเหรียญ — สั่งหยุดแล้วห้ามกดเพิ่ม
                    self._tap_center_of(m)
                    presses += 1
                    if presses % 10 == 0:
                        self.log(f"[act] ตีไป {presses} ครั้ง")
                    idle = 0
                    self._pause(0.15)   # ตีถี่ได้ — ปุ่มเดิมอยู่ที่เดิม ไม่ต้องรอเมนู
                    continue

                if self._clear_popups(screen):
                    idle = 0
                    continue

                idle += 1
                if idle >= config.ACT_IDLE_LIMIT:
                    self.log(f"[act][WARN] ไม่เจอปุ่มที่รู้จักเลย {idle} รอบ → เลิก "
                             "(จอไม่ตรง/template ไม่แมตช์ — เซฟภาพไว้ที่ coin_logs/ ดูแล้วแคปทับ)")
                    self._save_debug("act_upgrade_idle", screen)
                    stop_all = True
                    break
                self._pause(config.ACT_POLL)

        self.log(f"[act] 💎 จบอัพเกรด — +9 สำเร็จ {done} ชิ้น (ตีรวม {presses} ครั้ง)")
        return done

    # ============================================================
    # 🎁 เปิดกล่องของขวัญ
    # ============================================================
    def open_gift_box(self, count=0):
        """เปิดกล่องของขวัญวนไป (count<=0 = ไม่จำกัด — หยุดเองเมื่อสั่งหยุด/ไม่มีปุ่มให้กด)"""
        self.log("\n===== [กิจกรรม] 🎁 เปิดกล่องของขวัญ =====")
        req = [config.IMG_ACT_PRESENT_BTN, config.IMG_ACT_DRAW, config.IMG_ACT_PRESENT_YELLOW]
        if not self._require(req):
            return None

        if not self._find_tap(config.IMG_ACT_PRESENT_BTN, "ไอคอนกล่องของขวัญ", timeout=8.0):
            return None
        if not self._find_tap(config.IMG_ACT_DRAW, "ปุ่มเปิดครั้งแรก", timeout=8.0):
            return None
        opened = 1
        self._stat("gift")

        idle = 0
        while not self._stopping():
            screen = self._cap()
            if screen is None:
                self._pause(0.4)   # ตาบอดห้ามกด
                continue

            # เลือกกล่องเหลือง → รออนิเมชันแบบสุ่มช่วง (คนจริงไม่กดถี่เท่ากันทุกครั้ง)
            m = self._find(screen, config.IMG_ACT_PRESENT_YELLOW)
            if m.found:
                self.log(f"[act] เลือกกล่องเหลือง (score={m.score:.2f})")
                self._tap_center_of(m)
                self._pause(random.uniform(0.4, 0.8))
                idle = 0
                continue

            # เปิดต่อรอบถัดไป — จุดที่เสียทรัพยากร ต้องเช็ค stop ก่อนกดเสมอ
            if self._optional(config.IMG_ACT_DRAW_AGAIN):
                m = self._find(screen, config.IMG_ACT_DRAW_AGAIN)
                if m.found:
                    if self._stopping():
                        break
                    # เช็คเป้าก่อนกด — กดคือเสียกล่องถัดไปทันที (เป้า 1 ห้ามเปิดใบที่ 2
                    # เพราะใบแรกถูกนับไปแล้วตอน "เปิดครั้งแรก")
                    if count > 0 and opened >= count:
                        self.log(f"[act] ครบเป้า {count} ครั้งแล้ว")
                        break
                    self._tap_center_of(m)
                    opened += 1
                    self._stat("gift")
                    self.log(f"[act] 🎁 เปิดไป {opened} ครั้ง")
                    if count > 0 and opened >= count:
                        self.log(f"[act] ครบเป้า {count} ครั้งแล้ว")
                        break
                    idle = 0
                    self._msleep(0.4)
                    continue

            # ฉากได้รางวัลใหญ่ — ป๊อปอัปซ้อนหลายชั้น ไล่เก็บตามลำดับที่บอทอ้างอิงใช้
            if self._optional(config.IMG_ACT_EGG_CONGRAT):
                m = self._find(screen, config.IMG_ACT_EGG_CONGRAT)
                if m.found:
                    self.log(f"[act] 🥚 ได้รางวัลใหญ่! (score={m.score:.2f})")
                    self._tap_if_found(config.IMG_ACT_CONFIRM_PRESENT,
                                       "ปุ่มยืนยันรับของ", settle=0.4)
                    self.adb.tap(*config.ACT_BTN_CENTER)   # เร่งฉากโชว์รางวัล
                    self._msleep(0.4)
                    self._tap_if_found(config.IMG_ACT_CONFIRM_PRESENT,
                                       "ปุ่มยืนยันรับของ (ตกค้าง)", settle=0.4)
                    self._tap_if_found(config.IMG_ACT_CANCEL_UPGRADE,
                                       "ปุ่มปิดป๊อปอัป", settle=0.4)
                    # ปุ่ม DRAW ต่อจากนี้ = เริ่มเปิดกล่องใหม่ (เสียทรัพยากร) —
                    # ต้องเช็ค stop + เป้า ก่อนกด และนับรอบเหมือน draw_again
                    if self._stopping():
                        break
                    if count > 0 and opened >= count:
                        self.log(f"[act] ครบเป้า {count} ครั้งแล้ว")
                        break
                    if self._tap_if_found(config.IMG_ACT_DRAW, "ปุ่มเปิดกล่อง",
                                          settle=0.4, optional=False):
                        opened += 1
                        self._stat("gift")
                        self.log(f"[act] 🎁 เปิดไป {opened} ครั้ง")
                        if count > 0 and opened >= count:
                            self.log(f"[act] ครบเป้า {count} ครั้งแล้ว")
                            break
                    idle = 0
                    continue

            # ยืนยันรับของธรรมดา → ถ้าปุ่มเปิดโผล่ต่อก็กดนับรอบใหม่เลย
            if self._optional(config.IMG_ACT_CONFIRM_PRESENT):
                m = self._find(screen, config.IMG_ACT_CONFIRM_PRESENT)
                if m.found:
                    self.log(f"[act] เจอปุ่มยืนยันรับของ (score={m.score:.2f}) → กด")
                    self._tap_center_of(m)
                    self._msleep(0.4)
                    # ปุ่ม DRAW ต่อจากนี้เสียทรัพยากร — เช็ค stop + เป้า ก่อนกด
                    if self._stopping():
                        break
                    if count > 0 and opened >= count:
                        self.log(f"[act] ครบเป้า {count} ครั้งแล้ว")
                        break
                    if self._tap_if_found(config.IMG_ACT_DRAW, "ปุ่มเปิดกล่อง",
                                          settle=0.4, optional=False):
                        opened += 1
                        self._stat("gift")
                        self.log(f"[act] 🎁 เปิดไป {opened} ครั้ง")
                        if count > 0 and opened >= count:
                            self.log(f"[act] ครบเป้า {count} ครั้งแล้ว")
                            break
                    idle = 0
                    continue

            # ป๊อปอัปทั่วไป (Okay / ยืนยัน)
            if self._clear_popups(screen):
                idle = 0
                continue

            idle += 1
            if idle >= config.ACT_IDLE_LIMIT:
                self.log(f"[act][WARN] ไม่เจอปุ่มที่รู้จักเลย {idle} รอบ → เลิก "
                         "(จอไม่ตรง/template ไม่แมตช์ — เซฟภาพไว้ที่ coin_logs/ ดูแล้วแคปทับ)")
                self._save_debug("act_gift_idle", screen)
                break
            self._pause(config.ACT_POLL)

        self.log(f"[act] 🎁 จบเปิดกล่องของขวัญ — เปิดไป {opened} ครั้ง")
        return opened
