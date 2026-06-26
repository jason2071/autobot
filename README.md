# autobot

บอท auto-click หาเป้าหมายบนหน้าจอด้วย **template/image match** (เสริม **color/pixel** detection)
แล้วคลิกอัตโนมัติ. ควบคุมผ่าน GUI ปุ่ม Start/Stop. รองรับ **macOS + Windows**.

## ติดตั้ง

macOS / Linux:
```bash
cd autobot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):
```powershell
cd autobot
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`requirements.txt` ลง dependency ตาม OS เอง (Quartz บน macOS, pywin32 บน Windows).

## สิทธิ์ระบบ

**macOS** — System Settings → Privacy & Security:

1. **Screen Recording** — ให้ terminal (หรือ app ที่รัน Python) capture จอได้
2. **Accessibility** — ให้ส่ง mouse click ได้

เพิ่ม **Terminal.app** / **iTerm** (หรือ IDE ที่ใช้รัน) เข้าทั้ง 2 รายการ แล้วปิด-เปิด terminal ใหม่.

**Windows** — ปกติไม่ต้องตั้งสิทธิ์. แต่ถ้า target app รันแบบ Administrator
ต้องรัน Python แบบ Administrator ด้วย (ไม่งั้นส่ง click ไม่เข้า).

## ใช้งาน

1. แคปรูปปุ่ม/ไอเทมที่จะให้หา เซฟเป็น `.png` (crop ให้พอดี ไม่มีพื้นหลังเยอะ) ใส่ใน `templates/`
2. รัน:
   ```bash
   python main.py
   ```
3. ในหน้าต่าง:
   - **เลือก template…** → เลือกไฟล์ (เลือกหลายไฟล์ได้)
   - **Threshold** — ความแม่น (0.8 เริ่มต้น; สูง = เข้มงวด)
   - **Interval (ms)** — เว้นช่วงสแกน
   - **Click mode** — `first` คลิกจุดแรก / `all` คลิกทุกจุดที่เจอ
   - **Target** — เลือกขอบเขตที่จะสแกน/คลิก (ดูด้านล่าง)
   - **Background click (ไม่ขยับเมาส์)** — ติ๊ก = คลิกโดยไม่ขยับ cursor จริง (ดูด้านล่าง)
   - **Start** / **Stop**

### Target — เกมไม่เต็มจอ
ไม่ต้องสแกนทั้งจอ เลือกขอบเขตได้ 3 แบบ:
- **ทั้งจอ** (default) — สแกนทุกพิกเซล
- **เลือก window** — กด **🔄 refresh** แล้วเลือก window ของเกม/แอปจาก dropdown →
  ระบบเติม region = ขอบเขต window นั้นให้อัตโนมัติ. ถ้าย้าย/ปรับขนาด window แล้ว
  กด refresh + เลือกใหม่
- **◰ ตีกรอบพื้นที่** — ลากเมาส์วาดกรอบบนหน้าจอเอง (Esc ยกเลิก)

ทั้งสองแบบเติมลงช่อง **region** (`top,left,width,height` physical px) ซึ่งแก้มือได้.
ว่าง = ทั้งจอ. พิกัด Retina ถูกคูณ scale ให้อัตโนมัติ.

### Background click (ไม่ขยับเมาส์)
ติ๊ก **Background click** = บอทส่ง click ตรงไปยัง window ใต้จุดเป้าหมาย โดย
**ไม่ขยับ cursor จริงของคุณ** — ใช้เครื่องทำอย่างอื่นไปพร้อมกันได้.

- macOS: Quartz `CGEventPostToPid`
- Windows: Win32 `PostMessage` (WM_LBUTTONDOWN/UP) ไปยัง window ใต้จุด

ข้อจำกัด:
- เกม/แอปที่อ่าน raw HID หรือมี anti-cheat อาจ **ไม่รับ** synthetic event
- target ต้องเป็น window ปกติที่มองเห็นใต้จุดนั้น

ถ้าไม่ติ๊ก = โหมด foreground (pyautogui) ขยับ cursor จริงไปคลิก รองรับทุกแอปแต่แย่งเมาส์.

### หยุดฉุกเฉิน
- โหมด foreground: ลากเมาส์ไปมุมจอ (pyautogui FAILSAFE) หรือกด **Stop**
- โหมด background: FAILSAFE ใช้ไม่ได้ (เมาส์ไม่ขยับ) — ใช้ปุ่ม **Stop**

## Retina note

จอ Retina แคปเป็น physical pixels (2x) แต่คลิกด้วย logical points. โค้ดคำนวณ scale
อัตโนมัติใน `clicker.py` (logical_width / physical_width). พิกัด Region ที่กรอกใช้
**physical px**.

## Makefile (mac/Linux, หรือ Git Bash/WSL บน Windows)

```bash
make install   # สร้าง venv + ลง deps
make run        # เปิด GUI
make test       # smoke test
make detect IMG=shot.png TPL=btn.png   # ทดสอบ template match
make clean      # ลบ venv + __pycache__
make help       # ดูคำสั่งทั้งหมด
```

## ทดสอบ detector (ไม่ต้องคลิกจริง)

```bash
python -m src.detector screenshot.png template.png
```
พิมพ์ตำแหน่ง + score ที่เจอ.

## โครงสร้าง

```
src/capture.py   — ScreenCapture (mss)
src/detector.py  — match_template() + find_color()
src/clicker.py   — Clicker (Retina scaling + rate limit + failsafe)
src/bot.py       — BotEngine (loop บน thread, start/stop)
src/gui.py       — tkinter App
main.py          — entry
```

## ข้อจำกัด / TODO
- ยังไม่มี drag-select region UI (กรอกพิกัดเอง)
- ยังไม่รองรับ multi-monitor switching, OCR
- color mode ยังตั้งค่าผ่าน `BotConfig` เท่านั้น (ยังไม่มีช่องใน GUI)
