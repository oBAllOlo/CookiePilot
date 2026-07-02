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
import random
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

    def tap(self, x, y, jitter=None):
        """
        แตะที่ (x,y) + สุ่มเยื้องเล็กน้อย (jitter=None → ใช้ config.TAP_JITTER)
        ถ้า config.HUMAN_TAP_HOLD=True → ใส่ 'เวลาสัมผัสนิ้ว' สั้น ๆ (contact time)
        ผ่าน swipe จุดเดิม แทนการแตะแบบ 0 วินาที ให้เหมือนคนจิ้มจริง
        """
        j = config.TAP_JITTER if jitter is None else jitter
        x, y = self._jit(x, y, j)
        if getattr(config, "HUMAN_TAP_HOLD", False):
            lo, hi = config.HUMAN_TAP_HOLD_MS
            ms = random.randint(int(lo), int(hi))
            self._run(self._base() + ["shell", "input", "swipe",
                                      str(x), str(y), str(x), str(y), str(ms)])
        else:
            self._run(self._base() + ["shell", "input", "tap", str(x), str(y)])

    def hold(self, x, y, seconds):
        """กดค้างที่ (x,y) เป็นเวลา seconds (ทำผ่าน swipe จุดเดิม)"""
        ms = int(seconds * 1000)
        sx, sy = int(x), int(y)
        self._run(self._base() + ["shell", "input", "swipe",
                                  str(sx), str(sy), str(sx), str(sy), str(ms)],
                  timeout=seconds + config.ADB_CMD_TIMEOUT)

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        """ปัดจาก (x1,y1) → (x2,y2)"""
        self._run(self._base() + ["shell", "input", "swipe",
                                  str(int(x1)), str(int(y1)),
                                  str(int(x2)), str(int(y2)), str(int(duration_ms))],
                  timeout=duration_ms / 1000 + config.ADB_CMD_TIMEOUT)

    def slide(self, jitter=None):
        """สไลด์ = กดค้างปุ่ม Slide (มี jitter). ใช้ config.JUMP_JITTER เป็นค่า default"""
        j = config.JUMP_JITTER if jitter is None else jitter
        x, y = self._jit(*config.BTN_SLIDE, j)
        self.hold(x, y, config.SLIDE_HOLD_SEC)
