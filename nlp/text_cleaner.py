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


# ─── ตรวจ "รีวิวที่ให้ดาวอย่างเดียว" ────────────────────────────────────────
#
# ⚠️ นี่เป็นฟังก์ชันใหม่แยกต่างหาก — ห้ามเอาตรรกะนี้ไปใส่ใน clean_review_text()
#   เพราะ review_text_hash() คำนวณจาก clean_review_text(text)
#   แก้ตัวล้าง = hash ของรีวิวที่เก็บมาแล้วทั้งหมดเปลี่ยน -> INSERT ซ้ำทั้งฐาน
#   (บั๊กเดิมที่เคยทำให้มีแถวซ้ำ 3,453 แถว)
#
# ปัญหาที่แก้ (วัดเมื่อ 2026-10-11 จากข้อสังเกตของผู้ใช้):
#   ผู้รีวิวที่ "กดดาวแล้วไม่เขียนอะไร" ยังมีการ์ดที่ประกอบด้วย
#   ชื่อผู้รีวิว / ไอคอนดาว / วันที่ / เมตา ("อาหาร: 5", "ราคาต่อคน", "฿200-300")
#   clean_review_text() ตัดไอคอนกับคำ UI ออกได้ แต่ตัดชื่อคนและค่าเมตาไม่ออก
#   เศษที่เหลือจึงถูกบันทึกเป็น "เนื้อรีวิว" แล้วไหลเข้าตัวส่วนของทุกสัดส่วน
#
#   ตัวอย่างจริง:
#     'Awadsada Boonjaroen x5  8 เดือนที่แล้ว'      -> text_clean = ชื่อคน
#     'x5 ปีที่แล้ว ราคาต่อคน ฿200-300… เพิ่มเติม'  -> text_clean = '฿200-300'
#   วัดได้ 6,020 แถว = 7.62% ของรีวิวที่ระบบถือว่า "มีข้อความ"
#   และโมเดลจัดชื่อคนเข้า "ความคิดเห็นทั่วไป" ด้วยความมั่นใจ 99%
#   (โมเดลไม่ผิด — มันได้ขยะเป็นอินพุต)
#
# หลักการตรวจ: เนื้อรีวิวจริงอยู่ "บรรทัดถัดจากวันที่" เสมอ
#   ถ้าหลังบรรทัดวันที่มีแต่ไอคอน / เมตา / คำ UI / บล็อกคำตอบจากเจ้าของ
#   แปลว่าผู้รีวิวไม่ได้เขียนอะไร
#   หาวันที่ไม่เจอ -> คืน False (แยกโครงไม่ได้ ไม่เดา)

_RO_DATE = re.compile(r"(ที่แล้ว|ที่ผ่านมา|ago)", re.I)
_RO_UNIT = re.compile(r"(วัน|สัปดาห์|เดือน|ปี|day|week|month|year)", re.I)
_RO_TODAY = re.compile(r"^(เมื่อวาน|วันนี้|yesterday|today)", re.I)
_RO_PUA_ONLY = re.compile("^[" + chr(0xE000) + "-" + chr(0xF8FF) + r"\s]+$")
# เมตาแบบ "หัวข้อ: ค่า" ที่ Google แสดงใต้ดาว
_RO_META_KV = re.compile(
    r"^(อาหาร|บริการ|บรรยากาศ|ห้องพัก|สถานที่ตั้ง|ความสะอาด|ความคุ้มค่า"
    r"|Rooms|Service|Location|Cleanliness|Value|Food|Atmosphere)\s*:")
_RO_META_HDR = re.compile(
    r"^(ประเภทอาหาร|ราคาต่อคน|ประเภทการสั่ง|ประเภทการเดินทาง|กลุ่มท่องเที่ยว"
    r"|คืนที่พัก|มื้ออาหาร|บริการที่แนะนำ|จุดเด่น|ความเห็นเกี่ยวกับ)")
_RO_META_VAL = re.compile(
    r"^(฿[\d,\-–\s]+|อาหารเช้า|อาหารกลางวัน|อาหารเย็น|อาหารมื้อสาย"
    r"|รับประทานที่ร้าน|สั่งกลับบ้าน|เดลิเวอรี|ซื้อกลับบ้าน|อื่นๆ)\s*…?$")
_RO_UI = re.compile(
    r"^(เพิ่มเติม|ดูเพิ่มเติม|ดูคำแปล|ชอบ|แชร์|ใหม่|Like|Share|More)\s*$")
_RO_OWNER = re.compile(r"^คำตอบจากเจ้าของ")


def _ro_is_date_line(t: str) -> bool:
    return bool((_RO_DATE.search(t) and _RO_UNIT.search(t)) or _RO_TODAY.match(t))


def _ro_is_noise(t: str) -> bool:
    """บรรทัดนี้ไม่ใช่เนื้อรีวิวใช่ไหม"""
    if not t:
        return True
    return bool(_RO_PUA_ONLY.match(t) or _RO_META_KV.match(t)
                or _RO_META_HDR.match(t) or _RO_META_VAL.match(t)
                or _RO_UI.match(t))


def is_rating_only(raw: str | None) -> bool:
    """True = ผู้รีวิวให้ดาวอย่างเดียว ไม่ได้เขียนข้อความ

    ใช้กับ "ข้อความดิบของการ์ด" เท่านั้น ไม่ใช่ text_clean
    (text_clean ถูกล้างจนแยกโครงไม่ได้แล้ว)

    ทดสอบแล้ว: จับของเสีย 9/9 · ไม่จับผิดรีวิวจริงที่สั้น 0/12 · รีวิวยาว 0/20
    """
    lines = [l.strip() for l in (raw or "").split("\n")]
    idx = None
    for i, l in enumerate(lines):
        if _RO_OWNER.match(l):
            break          # เจอคำตอบเจ้าของก่อนเจอวันที่ของผู้รีวิว = แยกไม่ได้
        if _ro_is_date_line(l):
            idx = i
            break
    if idx is None:
        return False       # ไม่เจอวันที่ = แยกโครงไม่ได้ ไม่เดา
    for l in lines[idx + 1:]:
        if _RO_OWNER.match(l):
            break          # ตั้งแต่ตรงนี้เป็นข้อความของเจ้าของร้าน ไม่ใช่ผู้รีวิว
        if not _ro_is_noise(l):
            return False   # เจอเนื้อรีวิวจริง
    return True
