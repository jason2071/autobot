# autobot

บอท auto-click หาเป้าหมายบนหน้าจอด้วย **template/image match** (เสริม **color/pixel** detection)
แล้วคลิกอัตโนมัติ. ควบคุมผ่าน GUI ปุ่ม Start/Stop.

## ติดตั้ง

```bash
cd autobot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## สิทธิ์ macOS (จำเป็น)

System Settings → Privacy & Security:

1. **Screen Recording** — ให้ terminal (หรือ app ที่รัน Python) capture จอได้
2. **Accessibility** — ให้ส่ง mouse click ได้

ต้องเพิ่ม **Terminal.app** / **iTerm** (หรือ IDE ที่ใช้รัน) เข้าทั้ง 2 รายการ แล้วปิด-เปิด terminal ใหม่.

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
   - **Region** — `top,left,width,height` (physical px) หรือเว้นว่าง = ทั้งจอ
   - **Background click (ไม่ขยับเมาส์)** — ติ๊ก = คลิกโดยไม่ขยับ cursor จริง (ดูด้านล่าง)
   - **Start** / **Stop**

### Background click (ไม่ขยับเมาส์)
ติ๊ก **Background click** = บอทส่ง click ตรงไปยัง window ใต้จุดเป้าหมายผ่าน Quartz
`CGEventPostToPid` โดย **ไม่ขยับ cursor จริงของคุณ** — ใช้เครื่องทำอย่างอื่นไปพร้อมกันได้.

ข้อจำกัด:
- macOS เท่านั้น (ต้องมี `pyobjc-framework-Quartz`)
- เกม/แอปที่อ่าน raw HID หรือมี anti-cheat อาจ **ไม่รับ** synthetic event
- target ต้องเป็น window ปกติ (ไม่ใช่ menubar/overlay) ที่มองเห็นใต้จุดนั้น

ถ้าไม่ติ๊ก = โหมด foreground (pyautogui) ขยับ cursor จริงไปคลิก รองรับทุกแอปแต่แย่งเมาส์.

### หยุดฉุกเฉิน
- โหมด foreground: ลากเมาส์ไปมุมจอ (pyautogui FAILSAFE) หรือกด **Stop**
- โหมด background: FAILSAFE ใช้ไม่ได้ (เมาส์ไม่ขยับ) — ใช้ปุ่ม **Stop**

## Retina note

จอ Retina แคปเป็น physical pixels (2x) แต่คลิกด้วย logical points. โค้ดคำนวณ scale
อัตโนมัติใน `clicker.py` (logical_width / physical_width). พิกัด Region ที่กรอกใช้
**physical px**.

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
