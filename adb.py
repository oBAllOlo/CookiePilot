"""
adb.py — ชั้นสื่อสารกับอีมูเลเตอร์ผ่าน ADB
==========================================
ห่อคำสั่ง adb ทั้งหมดไว้ในคลาส Adb เพื่อไม่ต้องยุ่งกับ global แบบเดิม
  - screencap()  : แคปหน้าจอ → ภาพ OpenCV (BGR)
  - tap/hold/swipe/slide : สั่งแตะ/กดค้าง/ปัด (มี jitter สุ่มตำแหน่งกันดูเป็นบอท)
  - ensure_device() : ถ้า device ที่ตั้งไว้หลุด → เลือกตัวที่ออนไลน์ให้อัตโนมัติ

ทุกคำสั่งซ่อนหน้าต่าง console และ redirect stdout/stderr เสมอ
(สำคัญตอน build เป็น .exe แบบ windowed — ถ้าไม่ redirect คำสั่งจะล้มเพราะ handle ไม่ valid)
"""
import os
import sys
import math
import random
import threading
import subprocess

import cv2
import numpy as np

import config

# flag ซ่อนหน้าต่าง console (เฉพาะ Windows)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def find_adb():
    """
    ค้นหา adb.exe อัตโนมัติ:
      1) ค่า DEFAULT_ADB ใน config
      2) ไล่โฟลเดอร์ LDPlayer ที่พบบ่อย (config.LDPLAYER_ROOTS x SUBDIRS)
      3) คำว่า 'adb' เฉย ๆ (เผื่ออยู่ใน PATH)
    คืน path แรกที่มีอยู่จริง (หรือ DEFAULT_ADB ถ้าไม่เจอเลย)
    """
    candidates = [config.DEFAULT_ADB]
    for root in config.LDPLAYER_ROOTS:
        for sub in config.LDPLAYER_SUBDIRS:
            candidates.append(os.path.join(root, sub, "adb.exe"))
    candidates.append("adb")

    for c in candidates:
        if c == "adb" or os.path.exists(c):
            return c
    return config.DEFAULT_ADB


class Adb:
    """ตัวสื่อสารกับ 1 อีมูเลเตอร์ (path ของ adb.exe + ชื่อ device)"""

    def __init__(self, path=None, device=None, log=print):
        self.path = path or find_adb()
        self.device = device or config.DEFAULT_DEVICE
        self.log = log  # ฟังก์ชัน log (แทนที่ได้เพื่อส่งเข้า GUI)
        self._input_lock = threading.Lock()  # กัน 2 เธรด (กระโดด/เธรดหลัก) ยิง input ชนกัน
        self._input_fails = 0                # input ล้มเหลวติดกัน (ไว้ trigger ensure_device)

    # ------------------------------------------------------------
    # คำสั่งพื้นฐาน
    # ------------------------------------------------------------
    def _base(self):
        """สร้าง prefix คำสั่ง adb (รวม -s <device> ถ้ามี)"""
        cmd = [self.path]
        if self.device:
            cmd += ["-s", self.device]
        return cmd

    def _run(self, cmd, **kw):
        """
        เรียก subprocess.run โดยซ่อน console + redirect I/O + ใส่ timeout เสมอ
        (กัน adb ค้างเมื่ออีมูเลเตอร์/device หลุด — ถ้าเกินเวลาจะคืน None แทนการแขวนบอท)
        """
        kw.setdefault("stdin", subprocess.DEVNULL)
        kw.setdefault("stdout", subprocess.DEVNULL)
        kw.setdefault("stderr", subprocess.DEVNULL)
        kw.setdefault("timeout", config.ADB_CMD_TIMEOUT)
        try:
            return subprocess.run(cmd, creationflags=_NO_WINDOW, **kw)
        except subprocess.TimeoutExpired:
            self.log(f"[adb] คำสั่งค้างเกิน {kw['timeout']:.0f}s → ยกเลิก: "
                     + " ".join(map(str, cmd[-4:])))
            return None

    # ------------------------------------------------------------
    # การจัดการ device
    # ------------------------------------------------------------
    def list_online_devices(self):
        """คืนรายชื่อ device ที่สถานะ = device (ออนไลน์พร้อมใช้)"""
        try:
            r = self._run([self.path, "devices"],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10)
            if r is None:
                return []
            out = []
            for line in r.stdout.decode(errors="ignore").splitlines()[1:]:
                parts = line.split("\t")
                if len(parts) == 2 and parts[1].strip() == "device":
                    out.append(parts[0].strip())
            return out
        except Exception:
            return []

    def ensure_device(self):
        """
        ถ้า device ที่ตั้งไว้ไม่ออนไลน์ → เปลี่ยนไปใช้ตัวออนไลน์ตัวแรก (เผื่อพอร์ตเปลี่ยน)
        คืน True ถ้ามี device ออนไลน์อย่างน้อย 1 ตัว
        """
        online = self.list_online_devices()
        if not online:
            return False
        if self.device not in online:
            self.log(f"[adb] device '{self.device}' ไม่ออนไลน์ → เปลี่ยนเป็น '{online[0]}'")
            self.device = online[0]
        return True

    def connected(self):
        """ทดสอบว่าเชื่อมต่อ + แคปหน้าจอได้ไหม"""
        self.ensure_device()
        return self.screencap() is not None

    # ------------------------------------------------------------
    # ภาพหน้าจอ
    # ------------------------------------------------------------
    def screencap(self):
        """
        แคปหน้าจอผ่าน `exec-out screencap -p` (ส่ง PNG ทาง stdout ตรง ๆ เร็วและไม่ต้องเซฟไฟล์)
        คืน numpy array (BGR) หรือ None ถ้าล้มเหลว
        """
        cmd = self._base() + ["exec-out", "screencap", "-p"]
        try:
            r = self._run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
            if r is None:   # timeout (log แล้วใน _run)
                return None
            if not r.stdout:
                self.log("[adb] แคปหน้าจอไม่ได้: " + r.stderr.decode(errors="ignore").strip())
                return None
            arr = np.frombuffer(r.stdout, dtype=np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception as e:
            self.log(f"[adb] screencap error: {e}")
            return None

    # ------------------------------------------------------------
    # อินพุต
    # ------------------------------------------------------------
    @staticmethod
    def _jit(x, y, jitter):
        """
        สุ่มเยื้อง (x,y) ในรัศมี jitter px แล้ว clamp ให้อยู่ในจอ
          - gaussian (config.HUMAN_GAUSS_JITTER=True): กระจุกกลางจุดเหมือนคนเล็ง
          - uniform : กระจายเท่ากันทั้งสี่เหลี่ยม (แบบเดิม)
        """
        if jitter and jitter > 0:
            if getattr(config, "HUMAN_GAUSS_JITTER", False):
                x = int(x) + int(random.gauss(0, jitter / 2))
                y = int(y) + int(random.gauss(0, jitter / 2))
            else:
                x = int(x) + random.randint(-jitter, jitter)
                y = int(y) + random.randint(-jitter, jitter)
        x = min(config.SCREEN_W - 1, max(0, int(x)))
        y = min(config.SCREEN_H - 1, max(0, int(y)))
        return x, y

    @staticmethod
    def _travel_end(x, y, rng):
        """จุดปลายของนิ้วตอนยกออก — นิ้วคนจริงขยับเล็กน้อยระหว่างสัมผัสเสมอ ไม่นิ่งสนิท 0px
        (เดิม swipe จุดเดิม→จุดเดิมเป๊ะทุกครั้ง = ลายเซ็นหุ่นระดับ touch event)"""
        if not getattr(config, "HUMAN_TOUCH_TRAVEL", False):
            return int(x), int(y)
        lo, hi = rng
        d = random.uniform(float(lo), float(hi))
        a = random.uniform(0, 2 * math.pi)
        ex = min(config.SCREEN_W - 1, max(0, int(x + d * math.cos(a))))
        ey = min(config.SCREEN_H - 1, max(0, int(y + d * math.sin(a))))
        return ex, ey

    def _input(self, args, timeout=None):
        """
        ยิงคำสั่ง `adb shell input ...` — ปกติ serialize ด้วย lock เพราะเธรดกระโดดกับ
        เธรดหลัก (relay/นำทาง) กดพร้อมกันได้ event DOWN/UP ปนกันจนเกม reject
        แต่รอ lock ไม่เกิน 2s: ถ้าคำสั่งก่อนหน้าแขวน (adb ค้าง) ให้ยิงต่อแบบไม่รอ —
        อินพุตซ้อนกันตอน adb ค้างเสี่ยงน้อยกว่าดองปุ่ม relay/การกดหยุดไว้เป็นสิบวินาที
        คืน True เมื่อสำเร็จ (returncode 0)
        ล้มเหลวแบบ adb ตอบกลับมา (เช่น device not found — fail เงียบเพราะ stderr ถูก
        redirect) ติดกันหลายครั้ง → ลองหา device ใหม่ให้ (ไม่ทำตอน timeout: adb ค้าง
        ทั้งตัว เรียก `adb devices` ต่อมีแต่จะบล็อกเพิ่มอีก 10s ฟรี ๆ)
        """
        kw = {"timeout": timeout} if timeout is not None else {}
        cmd = self._base() + ["shell", "input"] + [str(a) for a in args]
        acquired = self._input_lock.acquire(timeout=2.0)
        try:
            r = self._run(cmd, **kw)
        finally:
            if acquired:
                self._input_lock.release()
        if r is not None and r.returncode == 0:
            self._input_fails = 0
            return True
        self._input_fails += 1
        if r is not None and self._input_fails % 5 == 0:
            self.log(f"[adb] คำสั่ง input ล้มเหลวติดกัน {self._input_fails} ครั้ง "
                     "(device หลุด/พอร์ตเปลี่ยน?) → ตรวจหา device ใหม่")
            self.ensure_device()
        return False

    def tap(self, x, y, jitter=None):
        """
        แตะที่ (x,y) + สุ่มเยื้องเล็กน้อย (jitter=None → ใช้ config.TAP_JITTER)
        ถ้า config.HUMAN_TAP_HOLD=True → ใส่ 'เวลาสัมผัสนิ้ว' สั้น ๆ (contact time)
        ผ่าน swipe จุดเดิม แทนการแตะแบบ 0 วินาที ให้เหมือนคนจิ้มจริง
        คืน True เมื่อคำสั่งถึง device สำเร็จ
        """
        j = config.TAP_JITTER if jitter is None else jitter
        x, y = self._jit(x, y, j)
        if getattr(config, "HUMAN_TAP_HOLD", False):
            lo, hi = config.HUMAN_TAP_HOLD_MS
            ms = random.randint(int(lo), int(hi))
            ex, ey = self._travel_end(x, y, config.HUMAN_TAP_TRAVEL)
            return self._input(["swipe", x, y, ex, ey, ms])
        return self._input(["tap", x, y])

    def hold(self, x, y, seconds):
        """กดค้างที่ (x,y) เป็นเวลา seconds (ผ่าน swipe + นิ้วขยับเล็กน้อย) — คืน True เมื่อสำเร็จ"""
        ms = int(seconds * 1000)
        ex, ey = self._travel_end(x, y, config.HUMAN_TAP_TRAVEL)
        return self._input(["swipe", int(x), int(y), ex, ey, ms],
                           timeout=seconds + config.ADB_CMD_TIMEOUT)

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        """ปัดจาก (x1,y1) → (x2,y2) — คืน True เมื่อสำเร็จ"""
        return self._input(["swipe", int(x1), int(y1), int(x2), int(y2), int(duration_ms)],
                           timeout=duration_ms / 1000 + config.ADB_CMD_TIMEOUT)

    def slide(self, jitter=None, hold_sec=None):
        """สไลด์ = กดค้างปุ่ม Slide (มี jitter) + นิ้วลากเลื่อนระหว่างกดค้าง
        hold_sec = ระยะกดค้าง (วินาที) — ไม่ส่งมาใช้ config.SLIDE_HOLD_SEC (ค่าตายตัวเดิม)
        คืน True เมื่อสำเร็จ"""
        j = config.JUMP_JITTER if jitter is None else jitter
        x, y = self._jit(*config.BTN_SLIDE, j)
        sec = config.SLIDE_HOLD_SEC if hold_sec is None else hold_sec
        ex, ey = self._travel_end(x, y, config.HUMAN_SLIDE_TRAVEL)
        return self._input(["swipe", x, y, ex, ey, int(sec * 1000)],
                           timeout=sec + config.ADB_CMD_TIMEOUT)
