"""
humanizer.py — SessionPlanner (V2 Phase 1)
==========================================
ทำให้จังหวะ "ระหว่างเกม" ดูเป็นคนจริง 3 อย่าง:
  1) พักสั้นแบบคนวางมือถือ — วิ่งรวดต่อเนื่องแบบสุ่ม (config.CONTINUOUS_RUN_RANGE รอบ)
     แล้วค่อยพัก 1 ที (ยาว config.BREAK_AFTER_GAME_RANGE วิ) ไม่ใช่พักทุกรอบ
     แทรกเฉพาะรอยต่อ RESULT→REROLL เกมเห็นแค่ "เล่นจบหลายเกมแล้ววางมือถือแป๊บ"
  2) ความล้า (fatigue) — เล่นต่อเนื่องนานขึ้น จังหวะกดช้าลงทีละนิด
     (ดัน HUMAN_GAP_MU ขึ้นเรื่อย ๆ จนสุดที่ FATIGUE_MU_MAX_ADD)
  3) สุ่มพารามิเตอร์จังหวะกดชุดใหม่เป็นช่วง ๆ — เหมือนอารมณ์/ท่านั่งคนเปลี่ยน
     ระหว่างวัน สถิติแต่ละช่วงจะไม่เหมือนกัน

ใช้งาน: bot.run() สร้าง SessionPlanner ตอนเริ่ม แล้วเรียก on_game_end()
ทุกครั้งที่จบเกม — คืนจำนวนวินาทีที่ควรพักก่อนเริ่มรอบใหม่
(เริ่มบอทใหม่ = เซสชันใหม่ ความล้ารีเซ็ต)
"""
import math
import time
import random

import config

# พารามิเตอร์ที่สุ่มชุดใหม่เป็นช่วง ๆ : ชื่อ key ใน config → ระยะแกว่งรอบค่า base (±)
# ค่า base อ่านตอนสร้าง planner (หลัง settings.json ทับแล้ว) — การสุ่มทับเฉพาะใน
# หน่วยความจำ ไม่เขียนลง settings.json (ปิดโปรแกรมแล้วค่ากลับเป็นของผู้ใช้เสมอ)
REROLL_BANDS = {
    "HUMAN_GAP_MU":       0.15,
    "HUMAN_GAP_SIGMA":    0.08,
    "HUMAN_BURST_CHANCE": 0.05,
    "HUMAN_IDLE_CHANCE":  0.03,
}


def menu_pause(base):
    """หน่วงเมนูแบบคน (V2 Phase 3): คืนเวลา >= base เสมอ (base จูนไว้กับแอนิเมชันเกม —
    สั้นกว่านั้นเสี่ยงกดก่อน UI พร้อม) + ส่วนยืดสุ่ม log-normal:
    ส่วนใหญ่ +10–40%, นาน ๆ ทีเกือบเท่าตัว → ดีเลย์เมนูไม่เท่ากันเป๊ะซ้ำพันรอบอีก"""
    if not getattr(config, "MENU_HUMAN_DELAY", False):
        return base
    extra = random.lognormvariate(-1.4, 0.7)   # median ~0.25, p95 ~0.78
    return base * (1.0 + min(1.0, extra))


class SessionPlanner:
    def __init__(self, log=print):
        self.log = log
        self.session_start = time.time()
        self.base = {}
        for k in REROLL_BANDS:
            try:
                self.base[k] = float(getattr(config, k))
            except Exception:
                # ค่าใน settings.json ผิดรูปแบบ (เช่นใส่ string) — ตัดออกจากการสุ่ม
                # ดีกว่าปล่อยให้เธรดกระโดดพังทั้งเซสชัน
                self.log(f"[human] ค่า {k} ไม่ใช่ตัวเลข → ข้ามการสุ่มค่านี้")
        self.offset = {k: 0.0 for k in self.base}
        # ฐานนิ้ว (anchor) จุดกระโดด — จำค่าตั้งต้นไว้ก่อนเลื่อน (เลื่อนเฉพาะในหน่วยความจำ)
        try:
            self.base_jump = (float(config.BTN_JUMP[0]), float(config.BTN_JUMP[1]))
        except Exception:
            self.base_jump = None
            self.log("[human] BTN_JUMP ผิดรูปแบบ → ข้ามการเลื่อนฐานนิ้ว")
        self._roll_anchor()
        self.next_reroll = self._schedule_next_reroll()
        self.free_runs = self._roll_free_runs()   # วิ่งต่อเนื่องอีกกี่รอบก่อนพักครั้งถัดไป

    # ------------------------------------------------------------
    def _schedule_next_reroll(self):
        lo, hi = config.PARAM_REROLL_EVERY_MIN
        return time.time() + random.uniform(float(lo), float(hi)) * 60.0

    def _roll_free_runs(self):
        """สุ่มจำนวนรอบที่จะวิ่งรวดต่อเนื่อง (ไม่พัก) ก่อนพักครั้งถัดไป"""
        lo, hi = getattr(config, "CONTINUOUS_RUN_RANGE", (0, 0))
        return random.randint(int(lo), int(hi))

    def fatigue_frac(self):
        """สัดส่วนความล้า 0..1 (0 = สดชื่น, 1 = ล้าเต็มที่) — GUI ใช้โชว์ด้วย"""
        if not config.FATIGUE_ENABLED:
            return 0.0
        hours = (time.time() - self.session_start) / 3600.0
        return min(1.0, hours / max(0.1, float(config.FATIGUE_FULL_HOURS)))

    def _fatigue_add(self):
        """MU ที่เพิ่มจากความล้า (0 → FATIGUE_MU_MAX_ADD ตามชั่วโมงที่เล่นต่อเนื่อง)"""
        return float(config.FATIGUE_MU_MAX_ADD) * self.fatigue_frac()

    def _apply(self):
        """เขียนค่า base + offset (+ fatigue เฉพาะ MU) ทับลง config ในหน่วยความจำ"""
        for k, base in self.base.items():
            v = base + self.offset[k]
            if k == "HUMAN_GAP_MU":
                v += self._fatigue_add()
            elif k.endswith("_CHANCE"):
                v = min(1.0, max(0.0, v))   # โอกาสต้องอยู่ใน 0..1
            elif k == "HUMAN_GAP_SIGMA":
                v = max(0.05, v)            # sigma ติดลบ/ศูนย์ทำ lognormvariate พัง
            setattr(config, k, v)

    def _roll_anchor(self):
        """สุ่มเลื่อนฐานนิ้วจุดกระโดด (BTN_JUMP) จากค่าตั้งต้น — คนแต่ละช่วงวันวางนิ้วไม่ตรงเดิม
        heatmap จุดกดรายวันจะไม่เป็นวงกลมสมมาตรรอบจุดเดียว"""
        if not self.base_jump or not getattr(config, "SESSION_ANCHOR_BIAS", None):
            return
        lo, hi = config.SESSION_ANCHOR_BIAS
        d = random.uniform(float(lo), float(hi))
        a = random.uniform(0, 2 * math.pi)
        x = self.base_jump[0] + d * math.cos(a)
        y = self.base_jump[1] + d * math.sin(a)
        # clamp กันหลุดขอบจอ (เผื่อผู้ใช้ตั้ง BTN_JUMP ชิดขอบ + bias ใหญ่)
        x = min(config.SCREEN_W - 10, max(10, x))
        y = min(config.SCREEN_H - 10, max(10, y))
        config.BTN_JUMP = (int(x), int(y))
        self.log(f"[human] เลื่อนฐานนิ้วกระโดด → {config.BTN_JUMP} "
                 f"(ตั้งต้น {int(self.base_jump[0])},{int(self.base_jump[1])})")

    def _reroll(self):
        for k, band in REROLL_BANDS.items():
            if k in self.offset:
                self.offset[k] = random.uniform(-band, band)
        self._roll_anchor()
        gap_med = 2.718281828 ** (self.base.get("HUMAN_GAP_MU", -1.05)
                                  + self.offset.get("HUMAN_GAP_MU", 0.0)
                                  + self._fatigue_add())
        self.log(f"[human] สุ่มจังหวะกดชุดใหม่ (gap กลาง ≈ {gap_med:.2f}s, "
                 f"burst {getattr(config, 'HUMAN_BURST_CHANCE', 0):.2f} → "
                 f"{min(1.0, max(0.0, self.base.get('HUMAN_BURST_CHANCE', 0) + self.offset.get('HUMAN_BURST_CHANCE', 0.0))):.2f})")

    # ------------------------------------------------------------
    def on_game_end(self):
        """เรียกทุกครั้งที่จบเกม (RESULT→REROLL) — คืนวินาทีที่ควรพักก่อนรอบถัดไป"""
        if config.SESSION_REROLL_PARAMS and time.time() >= self.next_reroll:
            self._reroll()
            self.next_reroll = self._schedule_next_reroll()
        self._apply()   # อัปเดต fatigue ทุกรอบ (และ offset ล่าสุด)

        # วิ่งต่อเนื่อง: ยังไม่ครบสตรีค → ไม่พัก (คืน 0) แล้วนับถอยหลัง
        if self.free_runs > 0:
            self.free_runs -= 1
            self.log(f"[พัก] วิ่งต่อเนื่อง — เหลืออีก {self.free_runs} รอบก่อนพัก")
            return 0.0
        # ครบสตรีคแล้ว → พัก 1 ที แล้วสุ่มสตรีคใหม่
        self.free_runs = self._roll_free_runs()
        lo, hi = config.BREAK_AFTER_GAME_RANGE
        return random.uniform(float(lo), float(hi))
