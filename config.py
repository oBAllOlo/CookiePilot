"""
config.py — ศูนย์รวมค่าคงที่ทั้งหมดของบอท
=========================================
ทุกโมดูล (adb / vision / bot / app) อ้างอิงค่าจากไฟล์นี้ที่เดียว
อยากจูนพิกัดปุ่ม / ความไว (threshold) / ดีเลย์ → แก้ที่นี่ที่เดียวพอ

หมายเหตุสำคัญ: พิกัดทั้งหมดจูนมาสำหรับความละเอียด LDPlayer 1280 x 720 (DPI 240)
ถ้าจอ/เวอร์ชันเกม/ภาษาต่างไป รูป template จะไม่ตรง ต้องแคปรูปใหม่ให้ตรงชื่อเดิมในโฟลเดอร์ templates/
"""

# ============================================================
# ความละเอียดหน้าจอที่บอทถูกจูนมา (ใช้ clamp พิกัดตอนแตะ)
# ============================================================
SCREEN_W = 1280
SCREEN_H = 720

# ============================================================
# ADB / อีมูเลเตอร์
# ============================================================
# ค่า default ของ adb.exe (ถ้าหาไม่เจอจะใช้ค่านี้) — แก้ให้ตรงเครื่องคุณได้
DEFAULT_ADB = r"D:\LDPlayer\LDPlayer14\adb.exe"

# device เริ่มต้น (พอร์ตมาตรฐานของ LDPlayer ตัวแรก)
DEFAULT_DEVICE = "emulator-5554"

# timeout ต่อ 1 คำสั่ง adb (วินาที) — กัน adb ค้างเมื่อ device หลุดแล้วบอทแขวนถาวร
ADB_CMD_TIMEOUT = 10.0

# โฟลเดอร์ที่อาจมี LDPlayer ติดตั้งอยู่ (ใช้ค้นหา adb.exe อัตโนมัติ)
LDPLAYER_ROOTS = [
    r"D:\LDPlayer", r"C:\LDPlayer", r"E:\LDPlayer",
    r"C:\Program Files\LDPlayer", r"C:\Program Files (x86)\LDPlayer",
    r"D:\Program Files\LDPlayer", r"C:\ChangZhi", r"D:\ChangZhi",
]
LDPLAYER_SUBDIRS = ["LDPlayer14", "LDPlayer9", "LDPlayer64", "LDPlayer4", ""]

# ============================================================
# ความไวการจับคู่ภาพ (template matching) — 0..1 ยิ่งสูงยิ่งเข้มงวด
# ============================================================
MATCH_THRESHOLD = 0.85

# ============================================================
# ไฟล์ template (path สัมพัทธ์กับโฟลเดอร์โปรเจกต์)
# ============================================================
IMG_TARGET_ITEM   = "templates/target_item.png"    # แบนเนอร์ Double Coins บนหน้าเตรียมตัว
IMG_OK_BUTTON     = "templates/ok_button.png"       # ปุ่ม OK หน้าผลลัพธ์
IMG_RESULT        = "templates/result_screen.png"   # หน้าผลลัพธ์ (Result)
IMG_RELAY         = "templates/relay_prompt.png"    # นินจา Cookie Relay Boost
IMG_BOOST_SCREEN  = "templates/boost_screen.png"    # หน้าเตรียมตัว (Buy some Boosts)
IMG_LOBBY_PLAY    = "templates/lobby_play.png"      # ปุ่ม Play เขียวที่ล็อบบี้
IMG_FRIEND_POPUP  = "templates/friend_popup.png"
IMG_MODE_POPUP    = "templates/mode_popup.png"
IMG_SENDLIFE_POPUP = "templates/sendlife_popup.png"
IMG_MULTI_CHECK   = "templates/multi_check.png"     # เครื่องหมายถูกในหน้า Multi

# ป๊อปอัปที่ต้องปิด (กดปุ่มปิด X ที่พิกัด x)
DISMISS_POPUPS = [
    {"name": "Friend's Info", "img": IMG_FRIEND_POPUP,   "x": (1080, 68),  "th": 0.80},
    {"name": "Select a Mode", "img": IMG_MODE_POPUP,     "x": (1240, 90),  "th": 0.80},
    {"name": "Send Life",     "img": IMG_SENDLIFE_POPUP, "x": (485, 458),  "th": 0.80},
]

# ============================================================
# พิกัดปุ่ม (x, y) — จูนสำหรับ 1280x720
# ============================================================
# หน้าเตรียมตัว / สุ่มบูสต์
BTN_BOX          = (540, 560)   # กล่อง Random Boost
BTN_BUY          = (925, 292)   # ปุ่มซื้อ (โหมดกดทีละครั้ง — ไม่ได้ใช้ในโหมด multi-buy)
BTN_BUY_CONFIRM  = (785, 448)
BTN_PLAY         = (955, 615)   # ปุ่ม Play เข้าเกมจากหน้าเตรียมตัว
BTN_LOBBY_PLAY   = (1012, 668)  # ปุ่ม Play ที่ล็อบบี้ (fallback ถ้าหา template ไม่เจอ)

# ปุ่ม Confirm/Open all กลางล่างของป๊อปอัปรางวัล (กด 2 จุดเผื่อตำแหน่งต่าง)
BTN_POPUP_CONFIRM     = (625, 585)
BTN_POPUP_CONFIRM_LOW = (630, 620)

# ปุ่มปิด X มุมขวาบน
BTN_CLOSE_X = (1080, 68)

# ระบบ Multi-Buy (ให้เกมสุ่มซื้อเองจนได้บูสต์ที่ติ๊ก)
BTN_MULTI       = (1097, 200)   # เปิดหน้า "Pick desired Boosts!"
BTN_MULTI_BUY   = (635, 588)    # ปุ่ม Multi-Buy
BTN_MULTI_CLOSE = (1043, 82)    # ปิดหน้า Multi
MULTI_SELECT_TARGETS = [(285, 176)]   # พิกัดบูสต์ที่ยอมรับ (Double Coins)
MULTI_CHECK_THRESHOLD = 0.70          # ความไวเช็คว่าติ๊กแล้วหรือยัง
MULTIBUY_TIMEOUT = 40.0               # วินาที รอ multi-buy จนเจอ target

# ปุ่มในเกม (ตอนวิ่ง)
BTN_JUMP  = (80, 670)    # ปุ่มกระโดด
BTN_SLIDE = (1200, 670)  # ปุ่มสไลด์
BTN_RELAY = (644, 335)   # ปุ่มรับช่วง (นินจา relay)

# ปุ่ม Confirm กลางจอ (ใช้แก้อาการค้าง/inactive)
BTN_INACTIVE_CONFIRM = (640, 490)

# ============================================================
# บูสต์ที่ต้องติ๊กก่อนเริ่มเกม
#   tap       = พิกัดที่กดเพื่อเปิดใช้บูสต์
#   check_img = template เครื่องหมายถูกเขียว
#   check_roi = กรอบ (x1,y1,x2,y2) ที่ใช้เช็คเครื่องหมายถูก
# ============================================================
BOOST_ITEMS = [
    {"name": "Potion",    "tap": (210, 430), "check_img": "templates/chk_potion.png",    "check_roi": (240, 455, 320, 515)},
    {"name": "Stopwatch", "tap": (365, 430), "check_img": "templates/chk_stopwatch.png", "check_roi": (392, 455, 472, 515)},
    {"name": "Star x2",   "tap": (515, 430), "check_img": "templates/chk_star.png",      "check_roi": (545, 455, 625, 515)},
]
CHECK_THRESHOLD = 0.75   # ความไวเช็คเครื่องหมายถูกของบูสต์

# ============================================================
# การกดในเกม (jitter = สุ่มเยื้องตำแหน่งกันดูเป็นบอท)
# ============================================================
TAP_JITTER  = 7          # รัศมีสุ่มการแตะทั่วไป (px)
JUMP_JITTER = 28         # รัศมีสุ่มตอนกดกระโดด (px)
SLIDE_HOLD_SEC = 0.35    # ระยะเวลากดค้างปุ่มสไลด์

# โหมดเดิม (ใช้เมื่อ HUMANLIKE_JUMP=False): สุ่มดีเลย์แบบ uniform ระหว่างการกด (วินาที)
JUMP_DELAY_MIN = 0.0
JUMP_DELAY_MAX = 0.75

# ตำแหน่งกดกระโดดแบบสุ่มหลายจุด (ใช้เมื่อ PREVENT_INACTIVE=True กันจอ inactive)
JUMP_TAP_POINTS = [(80, 670), (170, 650), (300, 668), (430, 648), (560, 665)]

# ============================================================
# จังหวะกระโดดแบบเลียนแบบคน (human-like timing)
#   คนไม่กดสม่ำเสมอ — ปกติ react เป็นช่วง (log-normal: สั้นบ่อย ยาวนานๆ ที),
#   บางทีกดรัวติดกัน (double/triple jump), บางทีเว้นยาว (วิ่งเก็บของไม่มีอุปสรรค)
# ============================================================
HUMANLIKE_JUMP = True      # True = จังหวะเลียนแบบคน / False = กลับไปใช้ uniform เดิม

# ดีเลย์ปกติระหว่างการกด — สุ่มแบบ log-normal (median ≈ exp(MU) วินาที)
HUMAN_GAP_MU    = -1.05    # exp(-1.05) ≈ 0.35s เป็นค่ากลาง
HUMAN_GAP_SIGMA = 0.45     # ยิ่งมากยิ่งกระจาย (มีทั้งสั้นมาก/ยาวมาก)
HUMAN_GAP_MIN   = 0.12     # หน่วงต่ำสุด (กันกดถี่เกินมนุษย์)
HUMAN_GAP_MAX   = 1.40     # หน่วงสูงสุดของการกดปกติ

# เบิร์สต์รัว (double/triple jump) — บางครั้งกดติดกันเร็ว ๆ
HUMAN_BURST_CHANCE = 0.18       # โอกาสที่การกดครั้งนี้จะเป็นเบิร์สต์
HUMAN_BURST_TAPS   = (2, 3)     # จำนวนแตะในเบิร์สต์ (สุ่มในช่วงนี้)
HUMAN_BURST_GAP    = (0.09, 0.18)  # ระยะห่างระหว่างแตะในเบิร์สต์ (วินาที)

# ช่วงเงียบยาว (วิ่งเก็บของ/ไม่มีอุปสรรค) — นาน ๆ ที
HUMAN_IDLE_CHANCE = 0.08        # โอกาสหยุดยาวหลังกดเสร็จ
HUMAN_IDLE_RANGE  = (1.0, 3.0)  # ช่วงเวลาหยุดยาว (วินาที)

# --- ระดับ "นิ้วคน" (ทำให้การแตะแต่ละครั้งไม่เหมือนหุ่นเป๊ะ) ---
# เวลาสัมผัสนิ้ว (contact time): คนจิ้มจอ ~40–110ms ไม่ใช่แตะ 0 วิ
HUMAN_TAP_HOLD    = True         # True = ใส่เวลาสัมผัสนิ้วแทนการแตะ 0 วิ
HUMAN_TAP_HOLD_MS = (40, 110)    # ช่วงเวลาสัมผัสต่อการแตะ (มิลลิวินาที)

# ตำแหน่งการแตะ: gaussian = กระจุกกลางจุดเหมือนคนเล็ง (แทน uniform สี่เหลี่ยม)
HUMAN_GAUSS_JITTER = True

# นิ้วเลื่อนช้า ๆ (คนไม่จิ้มจุดเป๊ะเดิมทุกครั้ง) — จุดฐานกระโดดค่อย ๆ ดริฟต์
#   ใช้เฉพาะโหมดจุดกระโดดเดียว (PREVENT_INACTIVE=False)
HUMAN_DRIFT      = True
HUMAN_DRIFT_STEP = 3.0    # ระยะเลื่อนเฉลี่ยต่อการกด (px)
HUMAN_DRIFT_PULL = 0.15   # แรงดึงกลับเข้าจุดตั้งต้น (0..1) กันนิ้วลอยหนี
HUMAN_DRIFT_MAX  = 18.0   # ระยะห่างสูงสุดจากจุดตั้งต้น (px)

# ============================================================
# ความไวเฉพาะจุด
# ============================================================
RELAY_THRESHOLD  = 0.70   # เจอนินจา relay

# ============================================================
# ดีเลย์ / timeout (วินาที)
# ============================================================
DELAY_AFTER_REROLL   = 2.0
DELAY_AFTER_PLAY     = 3.0
LOOP_SLEEP           = 0.3
RESULT_CHECK_INTERVAL = 0.5    # ความถี่ตรวจหน้า Result ตอนวิ่ง
RUN_STATE_TIMEOUT    = 300.0   # กันค้างในด่านเกินเวลานี้ → บังคับไปหน้า Result

# ============================================================
# กันจอค้าง (inactive) — เปรียบเทียบว่าเฟรมนิ่งเกินไปไหม
# ============================================================
PREVENT_INACTIVE = False   # True = เปิดโหมดกันจอค้าง (กดจุดสุ่ม + กด Confirm เมื่อจอนิ่ง)
FREEZE_SECS = 8.0          # จอนิ่งเกินกี่วินาทีถือว่าค้าง
FREEZE_DIFF = 3.0          # ค่าความต่างเฉลี่ยของเฟรมที่ถือว่า "นิ่ง"

# ============================================================
# อ่านจำนวนเหรียญบนหน้า Result (OCR ด้วย template เลข 0-9)
# ============================================================
COIN_ROI = (945, 383, 1118, 430)   # กรอบตัวเลขเหรียญ (x1,y1,x2,y2)
DIGIT_DIR = "templates/dig"         # โฟลเดอร์ template เลข 0-9
DIGIT_W, DIGIT_H = 24, 36           # ขนาดมาตรฐานที่ normalize glyph ก่อนเทียบ
DIGIT_MIN_SCORE = 0.30              # คะแนนต่ำสุดที่ยอมรับต่อ 1 หลัก
COIN_CSV = "coin_logs/coins.csv"    # ไฟล์บันทึกเหรียญ

# ============================================================
# เวอร์ชันแอป
# ============================================================
APP_NAME = "CookiePilot"
APP_VERSION = "1.0"

# ============================================================
# override ค่าจากไฟล์ settings.json (วางข้าง .exe / ข้างสคริปต์)
#   - มีไฟล์ → ค่าใน JSON ทับค่า default ด้านบน (เฉพาะชื่อ key ที่มีอยู่จริง)
#   - ไม่มีไฟล์ → ใช้ค่า default ทั้งหมด (ไม่บังคับต้องสร้าง)
#   - แก้ค่าแล้วเปิดโปรแกรมใหม่พอ ไม่ต้อง build .exe ใหม่
#   ตัวอย่าง: { "DEFAULT_DEVICE": "emulator-5556", "MATCH_THRESHOLD": 0.8,
#              "BTN_JUMP": [80, 670] }   ← พิกัด (tuple) ใส่เป็น list ได้เลย
# ============================================================
import json as _json
import os as _os

from paths import data_path as _data_path

SETTINGS_FILE = _data_path("settings.json")
SETTINGS_ERROR = None      # ข้อความ error ถ้าไฟล์เสีย (GUI/CLI เอาไปแจ้งผู้ใช้)
SETTINGS_APPLIED = []      # รายชื่อ key ที่ถูก override ตอนโหลด


def _apply_settings(data):
    """ทับค่าคงที่ในโมดูลนี้ด้วย dict (เฉพาะ key ตัวพิมพ์ใหญ่ที่มีอยู่แล้ว)
    ค่า default ที่เป็น tuple จะแปลง list จาก JSON กลับเป็น tuple ให้
    คืนรายชื่อ key ที่ทับสำเร็จ"""
    applied = []
    g = globals()
    for k, v in data.items():
        if not (isinstance(k, str) and k.isupper() and k in g):
            continue
        if isinstance(g[k], tuple) and isinstance(v, list):
            v = tuple(v)
        g[k] = v
        applied.append(k)
    return applied


def load_settings(path=None):
    """โหลด settings.json มาทับค่า default — คืนรายชื่อ key ที่ถูกทับ"""
    global SETTINGS_ERROR, SETTINGS_APPLIED
    p = path or SETTINGS_FILE
    if not _os.path.exists(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = _json.load(f)
        if not isinstance(data, dict):
            raise ValueError('รูปแบบต้องเป็น JSON object เช่น {"KEY": value}')
        SETTINGS_APPLIED = _apply_settings(data)
        return SETTINGS_APPLIED
    except Exception as e:
        SETTINGS_ERROR = f"อ่าน settings.json ไม่สำเร็จ ({e}) → ใช้ค่า default แทน"
        return []


def save_settings(updates, path=None):
    """บันทึกค่าลง settings.json (merge กับของเดิมในไฟล์) + ทับค่าในโมดูลทันที
    คืน True ถ้าเขียนไฟล์สำเร็จ"""
    p = path or SETTINGS_FILE
    data = {}
    try:
        if _os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                old = _json.load(f)
            if isinstance(old, dict):
                data = old
    except Exception:
        pass  # ไฟล์เดิมเสีย → เขียนทับใหม่
    data.update(updates)
    try:
        with open(p, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        return False
    _apply_settings(updates)
    return True


load_settings()
