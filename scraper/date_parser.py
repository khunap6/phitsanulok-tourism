"""
date_parser.py — แปลงข้อความวันที่รีวิวแบบ relative ของ Google Maps
                 เช่น "3 เดือนที่แล้ว", "a year ago" → วันที่โดยประมาณ (date)

ใช้เวลาปัจจุบัน (หรือเวลาที่ scrape) เป็นจุดอ้างอิง

ข้อจำกัด: ค่าที่ได้เป็น "โดยประมาณ" เพราะ Google บอกแบบหยาบ เช่น
  - "3 สัปดาห์ที่แล้ว" → แม่นระดับ ±ไม่กี่วัน
  - "2 ปีที่แล้ว"      → หยาบระดับ ±หลายเดือน
ควรระบุข้อจำกัดนี้ในงานวิจัย
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

# หน่วยเวลา → จำนวนวันโดยประมาณ
_UNIT_DAYS = {
    "วัน": 1,
    "day": 1,
    "สัปดาห์": 7,
    "week": 7,
    "เดือน": 30,
    "month": 30,
    "ปี": 365,
    "year": 365,
}

# คำบอกจำนวน "หนึ่ง" ในภาษาอังกฤษ (Google ใช้ "a month ago", "an hour ago")
_ARTICLE_ONE = {"a", "an", "หนึ่ง", ""}

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def parse_relative_date(
    text: str | None,
    reference: datetime | date | None = None,
) -> date | None:
    """
    แปลงข้อความ relative date → date object โดยประมาณ

    คืน None ถ้าแปลงไม่ได้ (เช่น ข้อความว่าง หรือรูปแบบไม่รู้จัก)

    ตัวอย่าง:
        "3 เดือนที่แล้ว"      → today - 90 วัน
        "a week ago"          → today - 7 วัน
        "เมื่อวานนี้"          → today - 1 วัน
        "2 ปีที่แล้ว"         → today - 730 วัน
    """
    if not text:
        return None

    if reference is None:
        reference = datetime.now()
    if isinstance(reference, datetime):
        ref_date = reference.date()
    else:
        ref_date = reference

    t = text.strip().lower().translate(_THAI_DIGITS)

    # กรณีพิเศษ: วันนี้ / เมื่อวาน
    if "วันนี้" in t or "today" in t:
        return ref_date
    if "เมื่อวาน" in t or "yesterday" in t:
        return ref_date - timedelta(days=1)

    # ต้องเป็นวลี relative-past จริงๆ (มี "ที่แล้ว" หรือ "ago")
    # ป้องกัน false positive จากข้อความรีวิวที่มีคำว่า ปี/เดือน
    # เช่น "อายุ 93 ปี", "กินมาตั้งแต่ปี 2003"
    if "ที่แล้ว" not in t and "ago" not in t:
        return None

    # หาหน่วยเวลา (เดือน/สัปดาห์/ปี/วัน หรือ month/week/year/day)
    unit_days = None
    for unit, days in _UNIT_DAYS.items():
        if unit in t:
            unit_days = days
            break

    if unit_days is None:
        return None

    # หาจำนวน (ตัวเลข)
    num_match = re.search(r"(\d+)", t)
    if num_match:
        amount = int(num_match.group(1))
    else:
        # ไม่มีตัวเลข → "a month ago", "เดือนที่แล้ว" = 1
        amount = 1

    # sanity cap: Google Maps ไม่แสดงวันที่ย้อนเกินขอบเขตนี้
    # (เกินกว่านี้ = ดึงข้อความผิด)
    _MAX_AMOUNT = {1: 60, 7: 8, 30: 24, 365: 20}  # วัน/สัปดาห์/เดือน/ปี
    if amount > _MAX_AMOUNT.get(unit_days, 100):
        return None

    return ref_date - timedelta(days=amount * unit_days)


def parse_to_iso(text: str | None, reference: datetime | date | None = None) -> str | None:
    """เหมือน parse_relative_date แต่คืนเป็น ISO string 'YYYY-MM-DD' หรือ None"""
    d = parse_relative_date(text, reference)
    return d.isoformat() if d else None
