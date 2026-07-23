"""
text_cleaner.py — ทำความสะอาดข้อความรีวิวจาก Google Maps
ตัด noise ที่ scraper เก็บมาปน: ไอคอน, ปุ่ม ชอบ/แชร์, ชื่อคนรีวิว,
Local Guide, วันที่, rating fragment (อาหาร: 5) ฯลฯ

เก็บเฉพาะ "เนื้อรีวิวจริง"
"""
from __future__ import annotations

import re

# Private Use Area (U+E000-U+F8FF) — ไอคอน Material ของ Google (ดาว/ชอบ/แชร์)
_PUA = re.compile("[" + chr(0xE000) + "-" + chr(0xF8FF) + "]")

# บรรทัดที่เป็น UI ล้วนๆ → ตัดทิ้ง
_DROP_EXACT = {"ชอบ", "แชร์", "เพิ่มเติม", "ใหม่", "แนะนำการแก้ไข", "ตอบกลับ"}

# บรรทัดที่ขึ้นต้นด้วยคำพวกนี้ = metadata → ตัดทิ้ง
_DROP_PREFIX = (
    "Local Guide",
    "ประเภทการสั่ง",
    "รับประทานที่ร้าน",
    "ซื้อกลับบ้าน",
    "บริการเดลิเวอรี",
    "ราคาต่อคน",
    "ประเภทสถานที่",
    "บริการ:",
    "อาหาร:",
    "บรรยากาศ:",
    "ราคา:",
    "ความคุ้มค่า",
    "แนะนำสำหรับ",
    "ที่จอดรถ:",
    "ไปที่นี่ใน",
    "เยี่ยมชมเมื่อ",
    "ประเภทอาหาร",
    "มื้ออาหาร",
)

# บรรทัด metadata คนรีวิว เช่น "5 รีวิว · 118 รูปภาพ", "1 รีวิว"
_META_LINE = re.compile(r"^·?\s*\d[\d,]*\s*รีวิว(\s*·.*)?$")

# บรรทัดวันที่ (relative date) → ตัดทิ้ง (anchored เพื่อไม่โดนเนื้อรีวิวจริง)
# รองรับ prefix "แก้ไขเมื่อ(วันที่)" / "เยี่ยมชมเมื่อ"
_DATE_LINE = re.compile(
    r"^\s*(?:(?:แก้ไขเมื่อ|เยี่ยมชมเมื่อ)\s*(?:วันที่)?\s*)?(?:(?:\d+|a|an)\s*)?"
    r"(?:วินาที|นาที|ชั่วโมง|วัน|สัปดาห์|เดือน|ปี|"
    r"second|minute|hour|day|week|month|year)s?"
    r"\s*(?:ที่แล้ว|ago)?\s*$",
    re.IGNORECASE,
)

# marker ที่บอกว่า "จบเนื้อรีวิวจริงแล้ว" — ตัดข้อความตั้งแต่ตรงนี้ทิ้ง
# (คำตอบจากเจ้าของร้าน, footer แปลภาษา Google)
_CUT_MARKERS = ("คำตอบจากเจ้าของ", "แปลโดย Google", "Response from the owner")
_TODAY_YESTERDAY = re.compile(
    r"^\s*(วันนี้|เมื่อวาน(?:นี้)?|today|yesterday)\s*$", re.IGNORECASE
)


def clean_review_text(raw: str | None) -> str:
    """
    ทำความสะอาดข้อความรีวิว คืนเฉพาะเนื้อรีวิวจริง
    ถ้าไม่มีเนื้อรีวิว (รีวิวที่ให้ดาวอย่างเดียว) → คืน ''
    """
    if not raw:
        return ""

    lines = raw.split("\n")
    kept: list[str] = []

    for i, line in enumerate(lines):
        s = _PUA.sub("", line).strip()
        if not s:
            continue

        if s in _DROP_EXACT:
            continue

        if any(s.startswith(p) for p in _DROP_PREFIX):
            continue

        if _DATE_LINE.match(s) or _TODAY_YESTERDAY.match(s):
            continue

        # บรรทัด metadata "N รีวิว · N รูปภาพ"
        if _META_LINE.match(s):
            continue

        # ตัวเลขล้วน / +N (จำนวนรูป, จำนวนไลก์)
        if re.fullmatch(r"\+?\d+", s):
            continue

        # ตัดชื่อคนรีวิว (บรรทัดก่อนหน้า "Local Guide" หรือก่อน "· N รีวิว")
        nxt = _PUA.sub("", lines[i + 1]).strip() if i + 1 < len(lines) else ""
        if nxt.startswith("Local Guide") or re.match(r"^·?\s*\d+\s*รีวิว", nxt):
            continue

        kept.append(s)

    text = " ".join(kept)
    # ตัดข้อความตั้งแต่ marker จบรีวิว (คำตอบเจ้าของ / footer แปล Google)
    for marker in _CUT_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    # ตัด "… เพิ่มเติม" / "เพิ่มเติม" / timestamp วิดีโอ (0:10) ท้ายข้อความ
    text = re.sub(r"(?:[…\.]{1,3}\s*)?เพิ่มเติม\s*(?:\d+:\d+)?\s*$", "", text).strip()
    text = re.sub(r"\s*\d+:\d+\s*$", "", text).strip()
    text = re.sub(r"[…\.]{1,3}\s*$", "", text).strip()
    # ยุบช่องว่างซ้ำ
    text = re.sub(r"\s{2,}", " ", text)
    return text
