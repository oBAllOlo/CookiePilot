# 🍪 CookiePilot — บอทเล่นเกมอัตโนมัติ (ของฉันเอง)

บอทเล่น **Cookie Run Classic** อัตโนมัติบน **LDPlayer** ผ่าน **ADB + OpenCV**
เขียนใหม่โครงสร้างสะอาด แยกโมดูลชัดเจน

> ปรับจูนพิกัดมาสำหรับความละเอียด **1280 × 720 (DPI 240)** เท่านั้น
> ถ้าจอ/เวอร์ชันเกม/ภาษาต่างไป รูป template จะไม่ตรง ต้องแคปใหม่

---

## โครงสร้างไฟล์

```
CookiePilot/
├── config.py        # ⚙️ ค่าคงที่ทั้งหมด (พิกัดปุ่ม / threshold / ดีเลย์) — แก้ที่นี่ที่เดียว
├── paths.py         # ตัวช่วยหา path (รองรับ build เป็น .exe)
├── adb.py           # ชั้นสื่อสารกับ emulator (แคปจอ / แตะ / ปัด / กดค้าง)
├── vision.py        # template matching + อ่านเลขเหรียญ (OCR)
├── bot.py           # 🤖 State Machine หลัก (REROLL → RUN → RESULT)
├── app.py           # 🖥️ หน้าต่างควบคุม (GUI)
├── templates/       # รูปที่ใช้เทียบหน้าจอ (+ dig/ = เลข 0-9 สำหรับอ่านเหรียญ)
├── requirements.txt
├── run_gui.bat      # ดับเบิลคลิกเปิด GUI (แบบรันด้วย Python)
├── build_exe.bat    # ดับเบิลคลิกเพื่อ build เป็นไฟล์ .exe
└── dist/
    └── CookiePilot.exe   # โปรแกรมไฟล์เดียว (หลัง build) — ดับเบิลคลิกเปิดได้เลย
```

---

## การทำงาน (State Machine 3 สถานะ, เลือกได้ 2 โหมด)

### โหมด 1: รีโรลเหรียญ (`coin` — โหมดเดิม)

| สถานะ | ทำอะไร |
|-------|--------|
| **1. REROLL** | นำทางไปหน้าเตรียมตัว → ใช้ **Multi-Buy** ในเกมสุ่มหา *Double Coins* → ติ๊กบูสต์ 3 อัน → กด Play |
| **2. RUN** | กดกระโดดจังหวะเลียนแบบคน (`HUMANLIKE_JUMP` — ค่าเริ่มต้น) + คอยกดปุ่ม relay (นินจา) + กันจอค้าง → จนจบด่าน |
| **3. RESULT** | หาปุ่ม OK → อ่านจำนวนเหรียญด้วย OCR → บันทึกลง `coin_logs/coins.csv` → กลับ STATE 1 |

### โหมด 2: วิ่งเก็บกล่อง (`box` — Fast Start)

| สถานะ | ทำอะไร |
|-------|--------|
| **1. PREP** | นำทางไปหน้าเตรียมตัว → **ไม่รีโรล** แต่ **ซื้อ Fast Start** (แตะไอคอน → กด Buy 1,600) → ติ๊กบูสต์ 3 อันเหมือนเดิม → กด Play |
| **2. RUN** | กดปุ่ม **"Tap to activate Fast Start Boost!"** ตอนเริ่มวิ่ง (โผล่ ~5-7 วิแรก) → จากนั้น**ไม่กดอะไรเลย** ปล่อยคุกกี้วิ่งเก็บกล่องเอง (Magnet Aura) — เจอนินจา relay ก็**ไม่กด** (ไม่เปลี่ยนไม้ 2) |
| **3. RESULT** | เหมือนโหมดเดิม |

เลือกโหมดได้ที่แถว **"โหมด:"** ใน GUI (จำค่าไว้ให้ใน `settings.json` เป็น `BOT_MODE`)
หรือรันแบบ CLI ให้ตั้ง `{"BOT_MODE": "box"}` ใน `settings.json`

> template ของโหมดนี้: `templates/fast_start_item.png` (ไอคอน Fast Start บนหน้าเตรียมตัว)
> และ `templates/fast_start_buy.png` (ปุ่ม Buy ในป๊อปอัปซื้อ) — ตัดมาจากภาพแคปหน้าจอ
> ถ้าบอทหาไม่เจอ (ดู score ใน log) ให้แคปใหม่จากจอจริงทับไฟล์เดิม
> หรือตั้งพิกัดสำรอง `BTN_FAST_START` เป็น `[242, 592]` (ตำแหน่งไอคอนที่วัดจากจอจริง 1280×720) ใน `settings.json`

---

## วิธีใช้ (แบบ .exe — แนะนำ)

1. เปิด LDPlayer (ตั้งจอ **1280 × 720** + เปิด **ADB debugging**) ให้อยู่ที่ **หน้าล็อบบี้** (มีปุ่ม Play เขียว)
2. ดับเบิลคลิก **`dist\CookiePilot.exe`**
   - ครั้งแรกถ้าขึ้น *"Windows protected your PC"* → กด **More info > Run anyway**
3. กด **ทดสอบเชื่อมต่อ** — ต้องขึ้น ✅ (ถ้าไม่ขึ้น กด "หาอัตโนมัติ" หรือพิมพ์ path ของ `adb.exe` เอง)
4. (ถ้าต้องการ) กรอก **จำนวนรอบ** เช่น 10 — เล่นครบจะหยุดเอง / กรอก 0 = ไม่จำกัด
5. กด **▶ เริ่มบอท** — ดูสถานะได้ใน log / กด **■ หยุดบอท** เมื่อต้องการหยุด

> ไฟล์บันทึก (`coin_logs\`) จะถูกสร้างข้าง ๆ ตัว `.exe`

---

## วิธีใช้ (แบบโค้ด Python — ไว้แก้/จูน)

```bash
pip install -r requirements.txt
python app.py          # เปิด GUI  (หรือดับเบิลคลิก run_gui.bat)
python bot.py          # รันแบบ CLI ไม่มีหน้าต่าง (กด Ctrl+C เพื่อหยุด)
```

### build เป็น .exe ใหม่ (หลังแก้ config)
ดับเบิลคลิก **`build_exe.bat`** → รอสักครู่ → ได้ `dist\CookiePilot.exe` อันใหม่

---

## ปรับจูน (ทุกอย่างอยู่ใน `config.py`)

- **โหมดบอท** — `BOT_MODE` (`"coin"` = รีโรลเหรียญ / `"box"` = วิ่งเก็บกล่อง)
- **พิกัดปุ่ม** — `BTN_*` (เช่น `BTN_JUMP`, `BTN_PLAY`)
- **ความไวการจับภาพ** — `MATCH_THRESHOLD`, `RELAY_THRESHOLD`, `CHECK_THRESHOLD`, `RESULT_CONFIRM_THRESHOLD` ...
- **จังหวะกระโดด (ค่าเริ่มต้น: เลียนแบบคน)** — `HUMANLIKE_JUMP = True` ใช้ชุด `HUMAN_*`:
  ช่วงห่าง log-normal (`HUMAN_GAP_MU/SIGMA/MIN/MAX`), กดรัว double/triple jump (`HUMAN_BURST_*`),
  ช่วงเงียบยาว (`HUMAN_IDLE_*`), เวลาสัมผัสนิ้ว (`HUMAN_TAP_HOLD`, `HUMAN_TAP_HOLD_MS`),
  จุดกดดริฟต์ (`HUMAN_DRIFT_*`), การกระจายตำแหน่งแบบ gaussian (`HUMAN_GAUSS_JITTER`)
  > ⚠ `JUMP_DELAY_MIN` / `JUMP_DELAY_MAX` มีผล**เฉพาะเมื่อตั้ง** `HUMANLIKE_JUMP = false` เท่านั้น
- **สไลด์** — `HUMAN_SLIDE_CHANCE` (ค่าเริ่มต้น 0 = ปิด) สุ่มกดค้างปุ่มสไลด์แทนกระโดดเป็นบางจังหวะ ลองเริ่มที่ `0.08`
- **กันจอค้าง** — ตั้ง `PREVENT_INACTIVE = True`
- **watchdog นำทาง** — `NAV_FAIL_LIMIT` (เข้าหน้าเตรียมตัวไม่ได้ติดกันครบจำนวนนี้ บอทหยุดเองแทนที่จะวนกดมั่ว)
- **บูสต์ที่จะติ๊ก** — `BOOST_ITEMS`
- **โหมดเก็บกล่อง** — `FAST_START_THRESHOLD`, `BTN_FAST_START` (พิกัดสำรอง), `FAST_START_TOAST_TIMEOUT`
- **กรอบอ่านเหรียญ** — `COIN_ROI` + กันอ่านเลขผิด: `DIGIT_MIN_MARGIN` (เลขต้องชนะอันดับสองขาดพอ),
  `COIN_MAX_VALUE` (อ่านได้เกินเพดานถือว่าผิด → ลงแถวว่าง+เซฟภาพไว้ดูแทน)
- **ที่เก็บ log เหรียญ** — `COIN_CSV` (path สัมพัทธ์กับโฟลเดอร์ข้างตัว .exe/สคริปต์)
- **ป๊อปอัปแจ้งเตือนบังล็อบบี้** (เช่น "You have been entered in a League") — บอทตรวจจับอาการ
  "กด Play แล้วจอไม่ขยับ" แล้วไล่กด Confirm กลางจอให้เอง (`NAV_PLAY_STUCK_TRIES`,
  `NAV_POPUP_CONFIRM_POINTS`) — ถ้าอยากให้ปิดแม่นขึ้น แคปภาพ dialog ไว้ที่
  `templates/league_popup.png` (ไม่มีไฟล์นี้ก็ทำงานได้ บอทจะข้ามให้)

ถ้าเปลี่ยนความละเอียด/เวอร์ชันเกม ต้องแคป template ใหม่ใส่โฟลเดอร์ `templates/` ให้ตรงชื่อเดิม
— ผู้ใช้ `.exe` ไม่ต้อง build ใหม่: สร้างโฟลเดอร์ `templates\` ข้าง ๆ `CookiePilot.exe`
แล้ววางไฟล์ที่แคปใหม่ลงไป ไฟล์ข้าง exe จะถูกใช้ก่อน template ที่ฝังมาในตัว exe เสมอ

### แก้ค่าโดยไม่ต้อง build ใหม่ (`settings.json`)

วางไฟล์ `settings.json` ข้าง ๆ `CookiePilot.exe` (หรือข้างสคริปต์) — ค่าในไฟล์จะ**ทับ**ค่าใน `config.py` ตอนเปิดโปรแกรม แก้เสร็จแค่เปิดโปรแกรมใหม่ ไม่ต้อง build `.exe` ใหม่

```json
{
  "DEFAULT_ADB": "D:\\LDPlayer\\LDPlayer9\\adb.exe",
  "DEFAULT_DEVICE": "emulator-5556",
  "MATCH_THRESHOLD": 0.8,
  "PREVENT_INACTIVE": true,
  "BTN_JUMP": [80, 670]
}
```

- ใช้ชื่อ key ให้ตรงกับชื่อตัวแปรใน `config.py` (พิกัดที่เป็น tuple ใส่เป็น list ได้เลย)
- key ที่ไม่รู้จักจะถูกข้าม / ไฟล์ JSON เสียจะใช้ค่า default แทน (มีแจ้งใน log)
  — ไฟล์ที่เสียจะถูกสำรองเป็น `settings.json.broken.<วันเวลา>.bak` ตอนโปรแกรมเซฟค่าครั้งถัดไป (ของเดิมไม่หายถาวร)
- โปรแกรมจะสร้าง/อัปเดตไฟล์นี้ให้เองเมื่อ "ทดสอบเชื่อมต่อ" สำเร็จหรือเริ่มบอท (จำ ADB path/Device ล่าสุด — เปิดครั้งหน้าไม่ต้องกรอกใหม่)

---

## หมายเหตุ
- ใช้เพื่อการเรียนรู้/ใช้ส่วนตัวบนอุปกรณ์ของคุณเอง — การใช้บอทอาจผิดเงื่อนไขการใช้งาน (ToS) ของเกม โปรดรับผิดชอบความเสี่ยงเอง
