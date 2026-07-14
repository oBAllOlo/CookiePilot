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
# โหมดบอท
#   "coin" = โหมดเดิม: รีโรลหา Double Coins แล้วกดกระโดดเอง
#   "box"  = วิ่งเก็บกล่อง: ซื้อ Fast Start แล้วปล่อยคุกกี้วิ่งเอง
#            (ไม่กดกระโดด / ไม่กดนินจา relay)
#   "exp"  = เก็บ EXP: ไม่รีโรล ติ๊กเฉพาะ Star x2 (chk_star) แล้ววิ่งแบบเก็บกล่อง
#            (ไม่กดกระโดด) + กดปุ่ม activate Fast Start ตอนเริ่ม + กดนินจา relay จนจบด่าน
# ============================================================
BOT_MODE = "coin"

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
IMG_FAST_START     = "templates/fast_start_item.png" # ไอคอน Fast Start บนหน้าเตรียมตัว (โหมดเก็บกล่อง)
IMG_FAST_START_BUY = "templates/fast_start_buy.png"  # ปุ่ม Buy ในแผงซื้อ Fast Start
IMG_FAST_START_ACTIVATE = "templates/fast_start_activate.png"  # ปุ่ม "Tap to activate Fast Start Boost!" ตอนเริ่มวิ่ง
IMG_LEAGUE_POPUP   = "templates/league_popup.png"    # ป๊อปอัป "You have been entered in a League" (ทางเลือก — แคปเพิ่มเพื่อปิดแม่นขึ้น; ผู้ใช้ .exe วางไว้ใน templates\ ข้าง exe ได้เลย ไม่ต้อง build ใหม่)

# ป๊อปอัปที่ต้องปิด (กดปุ่มปิด/Confirm ที่พิกัด x) — ไฟล์ template ไหนยังไม่ได้แคป บอทจะข้ามให้เอง
DISMISS_POPUPS = [
    {"name": "Friend's Info", "img": IMG_FRIEND_POPUP,   "x": (1080, 68),  "th": 0.80},
    {"name": "Select a Mode", "img": IMG_MODE_POPUP,     "x": (1240, 90),  "th": 0.80},
    {"name": "Send Life",     "img": IMG_SENDLIFE_POPUP, "x": (485, 458),  "th": 0.80},
    {"name": "League Notice", "img": IMG_LEAGUE_POPUP,   "x": (640, 545),  "th": 0.80},
]

# ล็อบบี้: กด Play กี่ครั้งแล้วจอยังไม่ขยับ ถึงถือว่ามีป๊อปอัปแจ้งเตือน (modal) บังการแตะ
# เช่น "You have been entered in a League" — ปุ่ม Play ยังมองเห็น แต่แตะไม่ติด
NAV_PLAY_STUCK_TRIES = 2
# จุดกด Confirm กลางจอที่ไล่กดทีละจุด (สลับกับกด Play) เมื่อเจออาการข้างบน
# เรียงตามโอกาส: League Notice → Confirm กลางจอทั่วไป → ป๊อปอัปรางวัล → dialog เตี้ย
NAV_POPUP_CONFIRM_POINTS = [(640, 545), (640, 490), (625, 585), (640, 430)]

# นำทางล้มเหลว (เข้าหน้าเตรียมตัวไม่ได้) ติดกันเกินกี่ครั้งให้หยุดบอทไปเลย
# — จอที่ไม่รู้จัก (เกมเด้ง/หน้าอัปเดตสโตร์) ไม่ raise exception ตัวนับ error เดิมจับไม่ได้
#   ไม่มี watchdog นี้บอทจะวนกดจอมั่วไม่สิ้นสุด
NAV_FAIL_LIMIT = 10

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

# ============================================================
# โหมดวิ่งเก็บกล่อง (BOT_MODE="box") — ซื้อ Fast Start ก่อนเริ่มวิ่ง
# หมายเหตุจากจอจริง: แผงซื้อเปิดค้างด้านขวา (ไม่ปิดเองหลังซื้อ) และไม่บังปุ่มอื่น
# ============================================================
FAST_START_THRESHOLD   = 0.75  # ความไวหาไอคอน/ปุ่ม Buy
BTN_FAST_START         = None  # พิกัดสำรองของไอคอน Fast Start ถ้าหา template ไม่เจอ (จอจริงอยู่ ~[242, 592])
FAST_START_BUY_TIMEOUT = 6.0   # วินาที รอปุ่ม Buy โผล่หลังแตะไอคอน
FAST_START_TOAST_TIMEOUT = 8.0 # วินาที รอ toast "Purchase complete!" หายแล้วหน้าจอกลับมาปกติ
FAST_START_ACTIVATE_WINDOW = 30.0  # วินาทีแรกของการวิ่งที่คอยหาปุ่ม activate (จอจริง: โผล่ ~5-7 วิ ค้าง ~3 วิ)

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
TAP_JITTER  = 10         # รัศมีสุ่มการแตะทั่วไป (px) — V2 ขยายจาก 7
SAFE_TAP_JITTER = 6      # รัศมีสุ่มจุดเสี่ยง (ติ๊กบูสต์/เลือก Multi/ปุ่ม X เล็ก) —
                         # กดเยื้องมากแล้ว toggle ผิด/กดพลาดปุ่ม เสียหายกว่าดูเป็นหุ่น
JUMP_JITTER = 36         # รัศมีสุ่มตอนกดกระโดด (px) — V2 ขยายจาก 28 ให้จุดกดกระจายกว้างขึ้น
SLIDE_HOLD_SEC = 0.35    # ระยะกดค้างสไลด์แบบตายตัว (fallback เมื่อไม่ส่งค่า hold มาเอง)

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

# สไลด์ (กดค้างปุ่ม Slide ลอดสิ่งกีดขวางเตี้ย) — สุ่มแทรกแทนการกระโดดเป็นบางจังหวะ
# V2: เปิดแล้ว — ระยะกดค้างสุ่มทุกครั้ง (ค่าตายตัว 0.35s เดิมคือลายเซ็นหุ่นชัด ๆ)
# ถ้าเหรียญเฉลี่ย/รอบใน coin_logs/coins.csv ตกเกิน ~10% ให้ลด HUMAN_SLIDE_CHANCE ลงครึ่งหนึ่ง
HUMAN_SLIDE_CHANCE = 0.06          # โอกาสที่จังหวะนี้เป็นสไลด์แทนกระโดด
HUMAN_SLIDE_HOLD   = (0.25, 0.60)  # ระยะกดค้างปกติ (วินาที สุ่มในช่วง)
HUMAN_SLIDE_LONG_CHANCE = 0.15     # โอกาสที่การสไลด์ครั้งนั้นเป็น "สไลด์ยาว"
HUMAN_SLIDE_LONG_RANGE  = (0.8, 1.2)   # ระยะกดค้างของสไลด์ยาว (วินาที)

# คอมโบ jump→slide (คนเล่นจริงชอบกดกระโดดแล้วสไลด์ต่อทันที)
HUMAN_COMBO_CHANCE = 0.04
HUMAN_COMBO_GAP    = (0.15, 0.35)  # เว้นระหว่างกระโดดกับสไลด์ (วินาที)

# --- จงใจพลาดแบบคนจริง (V2) ---
# กดหลุดปุ่ม (fumble): นิ้วลื่น แตะเยื้องไกลจนเกมไม่รับ = เสียจังหวะไปเฉย ๆ
HUMAN_FUMBLE_CHANCE = 0.015
HUMAN_FUMBLE_DIST   = (50, 120)    # ระยะที่หลุดจากปุ่ม (px สุ่มในช่วง)
# เผลอ/หลุดโฟกัส (lapse): หน่วง gap ยาวพิเศษเกินช่วงปกติ
HUMAN_LAPSE_CHANCE  = 0.03
HUMAN_LAPSE_RANGE   = (1.5, 2.5)   # วินาที
# นินจา relay: เป็น sprite วิ่งเคลื่อนที่ — ต้องกดไว (tap ดิบตรงตำแหน่งที่เจอ) ไม่หน่วง
# poll ถี่กว่า RESULT_CHECK_INTERVAL เพราะนินจาโผล่แวบเดียว ต้องจับให้ทันก่อนวิ่งพ้น
RELAY_POLL_INTERVAL = 0.12         # วินาที — รอบ loop ตอนวิ่ง (ยิ่งถี่ ยิ่งกดนินจาทัน)

# ฐานนิ้ว (anchor) ต่อเซสชัน: สุ่มเลื่อนจุดกระโดดตั้งต้นทั้งเซสชัน ±(ช่วงนี้) px
# ทำงานผ่าน SessionPlanner (สุ่มตอนเริ่ม + ทุกครั้งที่ reroll พารามิเตอร์)
SESSION_ANCHOR_BIAS = (15, 25)

# --- V2 Phase 3: จังหวะเมนู/นำทางแบบคน (นอกด่าน) ---
# ดีเลย์เมนูเดิมตายตัวเป๊ะระดับ ms ซ้ำวันละหลายร้อยรอบ = fingerprint มาโครชัดที่สุด
# menu_pause ยืดจากค่า base เสมอ (ไม่หด — ค่า base จูนไว้กับแอนิเมชันเกมแล้ว)
MENU_HUMAN_DELAY = True
PLAY_PRESS_DELAY = (0.5, 1.5)      # หน่วงก่อนกด Play เริ่มเกม (คนขยับนิ้วไปหาปุ่ม)
READ_RESULT_RANGE = (1.5, 4.0)     # หยุดดูคะแนน/เหรียญก่อนกด OK หน้า Result
READ_RESULT_LONG_CHANCE = 0.10     # นาน ๆ ทีดูนานเป็นพิเศษ
READ_RESULT_LONG_RANGE  = (5.0, 8.0)

# --- V2 โหมดเก็บกล่อง (box) — ตอบสนองแบบคนใน flow ซื้อ Fast Start ---
# ใช้เฉพาะหน้าเตรียมตัว (ไม่มีจับเวลา) — ปุ่ม activate ตอนวิ่ง "ไม่หน่วง" กดทันทีเสมอ
# เพราะปุ่มค้างแค่ ~3 วิ พลาดคือเสียบูสต์ทั้งด่าน
BOX_REACT_RANGE = (0.3, 0.9)        # หน่วงก่อนแตะไอคอน Fast Start / ปุ่ม Buy (วินาที)

# --- V2 Phase 4: micro-movement ระดับ touch ---
# นิ้วคนจริงไม่เคยนิ่งสนิท 0px ระหว่างสัมผัส — เดิม swipe จุดเดิม→จุดเดิมเป๊ะ
HUMAN_TOUCH_TRAVEL = True
HUMAN_TAP_TRAVEL   = (1, 4)        # px ที่นิ้วขยับระหว่างแตะ/กดค้าง
HUMAN_SLIDE_TRAVEL = (8, 20)       # px ที่นิ้วลากเลื่อนระหว่างกดค้างสไลด์

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
HUMAN_DRIFT_STEP = 4.5    # ระยะเลื่อนเฉลี่ยต่อการกด (px) — V2 ขยายจาก 3.0
HUMAN_DRIFT_PULL = 0.15   # แรงดึงกลับเข้าจุดตั้งต้น (0..1) กันนิ้วลอยหนี
HUMAN_DRIFT_MAX  = 32.0   # ระยะห่างสูงสุดจากจุดตั้งต้น (px) — V2 ขยายจาก 18

# ============================================================
# Session Planner (V2 Phase 1) — พักสั้นตอนจบเกม + ความล้า + สุ่มจังหวะใหม่เป็นช่วง ๆ
#   พักแทรกเฉพาะรอยต่อ "จบเกม → เริ่มรอบใหม่" เท่านั้น (ไม่หยุดกลางด่าน)
#   ไม่ยุ่งกับ logic รีโรล Double Coins ทุกกรณี
# ============================================================
SESSION_PLANNER = True             # เปิด/ปิดทั้งระบบ (False = พฤติกรรม V1 เดิม)
BREAK_AFTER_GAME_RANGE = (0, 20)   # ความยาวการพักแต่ละครั้ง — สุ่ม uniform ในช่วงนี้ (วินาที)
# ไม่พักทุกรอบ — วิ่งรวดต่อเนื่องแบบสุ่มจำนวนรอบในช่วงนี้ก่อน ค่อยพัก 1 ที แล้วสุ่มใหม่
#   เช่น (0,5): บางทีพักทุกรอบ (สุ่มได้ 0) บางทีวิ่งรวด 5 รอบค่อยพัก
CONTINUOUS_RUN_RANGE = (0, 5)      # จำนวนรอบวิ่งต่อเนื่อง (ไม่พัก) ก่อนพักครั้งถัดไป — สุ่ม int ในช่วงนี้

# ความล้า: ยิ่งเล่นต่อเนื่องนาน จังหวะกดยิ่งช้าลงเล็กน้อย (ดัน HUMAN_GAP_MU ขึ้นทีละนิด)
# รีเซ็ตเมื่อเริ่มบอทใหม่ (1 การกดเริ่ม = 1 เซสชัน)
FATIGUE_ENABLED = True
FATIGUE_FULL_HOURS = 6.0           # เล่นต่อเนื่องกี่ชั่วโมงถึง "ล้าเต็มที่"
FATIGUE_MU_MAX_ADD = 0.20          # MU เพิ่มสูงสุดเมื่อล้าเต็มที่ (gap กลาง 0.35s → ~0.43s)

# สุ่มพารามิเตอร์จังหวะกด (MU/SIGMA/burst/idle) ชุดใหม่เป็นช่วง ๆ
# — เหมือนอารมณ์/ท่านั่งคนเปลี่ยนระหว่างวัน สถิติแต่ละช่วงไม่เหมือนกัน
# ทับเฉพาะในหน่วยความจำ ไม่เขียนลง settings.json
SESSION_REROLL_PARAMS = True
PARAM_REROLL_EVERY_MIN = (60, 150)  # ทุกกี่นาที (สุ่มในช่วง) ถึงสุ่มชุดใหม่

# ============================================================
# ความไวเฉพาะจุด
# ============================================================
RELAY_THRESHOLD  = 0.70   # เจอนินจา relay
RESULT_CONFIRM_THRESHOLD = 0.70   # ยืนยันว่า "เป็นหน้า Result จริง" ก่อนอ่านเลขเหรียญ
                                  # (หลวมกว่า MATCH_THRESHOLD — เทมเพลตเพี้ยนนิดหน่อยต้องไม่ทำ
                                  #  เหรียญหายทุกรอบ แต่ยังสูงพอคัด dialog อื่นออก)

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
COIN_ROI = (945, 383, 1130, 430)   # กรอบตัวเลขเหรียญ (x1,y1,x2,y2)
                                    # x2 ต้อง ≥1130: ค่ากว้าง ๆ (เช่น 37,533) ชิดขวาเลย 1118
                                    # ขอบเดิมตัดเลขหลักสุดท้ายครึ่งตัว ทำให้อ่านผิด/อ่านไม่ได้
XP_ROI = (945, 466, 1130, 513)      # กรอบตัวเลขแถว XP (ใต้แถว Coins ~83px ฟอนต์เดียวกัน)
                                    # โหมด exp อ่านแถวนี้แทน — ทดสอบกับภาพจริงแล้วทน ±5px
DIGIT_DIR = "templates/dig"         # โฟลเดอร์ template เลข 0-9
DIGIT_W, DIGIT_H = 24, 36           # ขนาดมาตรฐานที่ normalize glyph ก่อนเทียบ
DIGIT_MIN_SCORE = 0.30              # คะแนนต่ำสุดที่ยอมรับต่อ 1 หลัก
DIGIT_MIN_MARGIN = 0.05             # เลขที่ชนะต้องทิ้งอันดับสองอย่างน้อยเท่านี้
                                    # (กันหมึกแปลกปลอม เช่น ขอบไอคอน ถูกยัดเป็นเลขที่ "ใกล้สุด")
COIN_MAX_VALUE = 99_999             # อ่านได้เกินนี้ถือว่าอ่านผิด → ลงแถวว่าง+เซฟภาพแทน
                                    # (ค่าจริงที่เคยบันทึกสูงสุด ~34,030) — 0 = ปิดเช็ค
COIN_CSV = "coin_logs/coins.csv"    # ไฟล์บันทึกเหรียญ (สัมพัทธ์กับโฟลเดอร์ข้าง .exe/สคริปต์)

# ============================================================
# เวอร์ชันแอป / หน้าตา GUI
# ============================================================
APP_NAME = "CookiePilot"
APP_VERSION = "2.0"
UI_SCALE = 1.0    # ขนาด UI (0.9 / 1.0 / 1.15 / 1.3) — ปรับได้จากในแอป จำค่าลง settings.json

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
import time as _time
import threading as _threading

from paths import data_path as _data_path

SETTINGS_FILE = _data_path("settings.json")
# save_settings ถูกเรียกจากหลายเธรด (worker ของ "ทดสอบเชื่อมต่อ" และ "เริ่มบอท")
# — read-merge-write โดยไม่มี lock ทำให้ค่าหาย (เช่น BOT_MODE เด้งกลับ) หรือไฟล์พังได้
_SETTINGS_LOCK = _threading.Lock()
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
    with _SETTINGS_LOCK:
        data = {}
        broken = False
        try:
            if _os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    old = _json.load(f)
                if isinstance(old, dict):
                    data = old
                else:
                    broken = True
        except ValueError:
            broken = True   # เนื้อไฟล์เป็น JSON พังจริง (เช่น typo ตอนแก้มือ)
        except Exception:
            # เปิดอ่านไม่ได้ชั่วคราว (เช่นโดน AV/OneDrive ล็อกไฟล์) — ไฟล์อาจดีอยู่
            # ห้ามตีความว่าเสียแล้วเขียนทับ ไม่งั้นค่าที่จูนมือหายเกลี้ยง
            return False
        if broken:
            # ไฟล์เดิมเสีย → สำรองไว้ก่อนเขียนทับ ไม่งั้น override ที่เขียนมือหายถาวร
            # ชื่อ backup ติด timestamp — ชื่อตายตัวจะโดนไฟล์เสียครั้งถัดไปทับสำเนาเดียวที่เหลือ
            try:
                _os.replace(p, p + _time.strftime(".broken.%Y%m%d_%H%M%S.bak"))
            except Exception:
                pass
        data.update(updates)
        try:
            # เขียนลงไฟล์ชั่วคราวแล้วค่อย replace — กันไฟล์ขาดกลางคันถ้าโปรแกรมถูกปิด/พังตอนเขียน
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                _json.dump(data, f, ensure_ascii=False, indent=2)
            _os.replace(tmp, p)
        except Exception:
            return False
        _apply_settings(updates)
        return True


load_settings()
