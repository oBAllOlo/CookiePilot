"""
vision.py — งานด้านภาพทั้งหมด (OpenCV)
======================================
  - find()        : หา template ในหน้าจอ → (เจอไหม, จุดกึ่งกลาง, คะแนน)
  - find_in_roi() : หา template เฉพาะในกรอบที่กำหนด (เช่นเช็คเครื่องหมายถูกจุดตายตัว)
  - frame_signature() : ย่อเฟรมไว้เทียบว่า "จอนิ่ง/ค้าง" หรือไม่
  - CoinReader    : อ่านจำนวนเหรียญบนหน้า Result ด้วย template เลข 0-9
"""
from collections import namedtuple

import cv2
import numpy as np

import config
from paths import resource_path

# ผลการค้นหา template: found=เจอไหม, center=(x,y) กึ่งกลาง, score=คะแนน 0..1
Match = namedtuple("Match", ["found", "center", "score"])

# แคช template ที่โหลดแล้ว (โหลดครั้งเดียวใช้ซ้ำ)
_TEMPLATE_CACHE = {}


def load_template(path):
    """โหลด template (BGR) พร้อมแคช — ไม่เจอไฟล์จะโยน FileNotFoundError"""
    if path not in _TEMPLATE_CACHE:
        tpl = cv2.imread(resource_path(path), cv2.IMREAD_COLOR)
        if tpl is None:
            raise FileNotFoundError(f"ไม่พบไฟล์ template: {path}")
        _TEMPLATE_CACHE[path] = tpl
    return _TEMPLATE_CACHE[path]


def find(screen, template_path, threshold=config.MATCH_THRESHOLD):
    """
    หา template ในภาพ screen ด้วย matchTemplate (TM_CCOEFF_NORMED)
    คืน Match(found, center, score) — center เป็น None ถ้าไม่เจอ
    """
    if screen is None:
        return Match(False, None, 0.0)
    tpl = load_template(template_path)
    th, tw = tpl.shape[:2]

    # กันกรณี template ใหญ่กว่าหน้าจอ (จะทำให้ matchTemplate error)
    if screen.shape[0] < th or screen.shape[1] < tw:
        return Match(False, None, 0.0)

    res = cv2.matchTemplate(screen, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val >= threshold:
        center = (max_loc[0] + tw // 2, max_loc[1] + th // 2)
        return Match(True, center, max_val)
    return Match(False, None, max_val)


def find_in_roi(screen, template_path, roi, threshold=config.MATCH_THRESHOLD):
    """
    หา template เฉพาะในกรอบ roi=(x1,y1,x2,y2)
    คืน (found: bool, score: float)
    """
    if screen is None:
        return (False, 0.0)
    x1, y1, x2, y2 = roi
    sub = screen[y1:y2, x1:x2]
    tpl = load_template(template_path)
    th, tw = tpl.shape[:2]
    if sub.shape[0] < th or sub.shape[1] < tw:
        return (False, 0.0)
    res = cv2.matchTemplate(sub, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(res)
    return (max_val >= threshold, max_val)


def frame_signature(screen):
    """ย่อเฟรมเป็น grayscale 64x36 (float32) ไว้เทียบว่าจอเปลี่ยนไหม (ตรวจค้าง/ป๊อปอัป)"""
    small = cv2.resize(screen, (64, 36))
    return cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)


class CoinReader:
    """อ่านจำนวนเหรียญบนหน้า Result ด้วยการเทียบ template ตัวเลข 0-9"""

    def __init__(self, log=print):
        self.log = log
        self._digits = None   # dict: '0'..'9' -> template grayscale float32

    def _load_digits(self):
        """โหลด template เลข 0-9 (grayscale, normalize ขนาด) แบบ lazy + แคช"""
        if self._digits is None:
            self._digits = {}
            for d in "0123456789":
                t = cv2.imread(resource_path(f"{config.DIGIT_DIR}/{d}.png"), cv2.IMREAD_GRAYSCALE)
                if t is None:
                    continue
                if t.shape != (config.DIGIT_H, config.DIGIT_W):
                    t = cv2.resize(t, (config.DIGIT_W, config.DIGIT_H))
                self._digits[d] = t.astype(np.float32)
        return self._digits

    @staticmethod
    def _segment_digits(crop):
        """
        แยก glyph ตัวเลขในกรอบ:
          - แปลง grayscale + threshold แบบ INV (เลขกลายเป็นสีขาวบนพื้นดำ)
          - หา "คอลัมน์ที่มีหมึก" แล้วจับกลุ่มติดกันเป็นแต่ละหลัก
          - ตัดคอมมา/จุด (ตัวที่เตี้ยกว่า 55% ของหลักที่สูงสุด) ออก
        คืน (ภาพ threshold, boxes เรียงซ้าย→ขวา แต่ละ box = [x0,y0,x1,y1])
        """
        g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(g, 110, 255, cv2.THRESH_BINARY_INV)

        cols = th.sum(axis=0)
        groups, inrun, start = [], False, 0
        for x, v in enumerate(cols):
            if v > 0 and not inrun:
                inrun, start = True, x
            elif v == 0 and inrun:
                groups.append((start, x))
                inrun = False
        if inrun:
            groups.append((start, len(cols)))

        boxes = []
        for x0, x1 in groups:
            rows = np.where(th[:, x0:x1].sum(axis=1) > 0)[0]
            if not len(rows):
                continue
            boxes.append([x0, rows[0], x1, rows[-1] + 1])
        if not boxes:
            return th, []

        maxh = max(b[3] - b[1] for b in boxes)
        boxes = [b for b in boxes if b[3] - b[1] >= 0.55 * maxh]
        return th, sorted(boxes, key=lambda b: b[0])

    def read(self, screen):
        """อ่านเลขเหรียญจาก screen → int (หรือ None ถ้าอ่านไม่ได้)"""
        if screen is None:
            return None
        try:
            digits = self._load_digits()
            if len(digits) < 10:
                return None
            x1, y1, x2, y2 = config.COIN_ROI
            th, boxes = self._segment_digits(screen[y1:y2, x1:x2])
            if not boxes:
                return None
            out = ""
            for b in boxes:
                glyph = cv2.resize(th[b[1]:b[3], b[0]:b[2]],
                                   (config.DIGIT_W, config.DIGIT_H)).astype(np.float32)
                best_ch, best_sc = None, -1.0
                for ch, tpl in digits.items():
                    sc = cv2.matchTemplate(glyph, tpl, cv2.TM_CCOEFF_NORMED)[0][0]
                    if sc > best_sc:
                        best_ch, best_sc = ch, sc
                if best_sc < config.DIGIT_MIN_SCORE:
                    return None
                out += best_ch
            return int(out) if out else None
        except Exception as e:
            self.log(f"[coins] อ่านเลขไม่สำเร็จ: {e}")
            return None
