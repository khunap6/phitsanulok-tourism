"""
filters.py — ตัวกรอง SQL ที่ใช้ร่วมกันทุก router (และรายงาน)

เหตุผลที่ต้องมีไฟล์นี้: นิยาม "หมวดที่ไม่ใช่ปัญหา" กับตัวกรองวันที่/สถานะร้าน
เคยถูก copy-paste อยู่หลายที่ (analysis.py, report_data.py) พอแก้ที่เดียว
อีกที่ไม่เปลี่ยน → ตัวเลขบนแดชบอร์ดกับในรายงาน PDF/Word ไม่ตรงกัน
ทุกที่ที่ต้องกรองต้อง import จากไฟล์นี้เท่านั้น ห้ามเขียนซ้ำ
"""
import json
from datetime import date
from pathlib import Path

# ── ชื่อหมวดที่แสดงต่อผู้ใช้ ──
#
# ⚠️ อ่านจาก shared/category_labels.json ซึ่งหน้าเว็บก็อ่านไฟล์เดียวกัน
#   ถ้าต่างคนต่างถือสำเนา วันหนึ่งแดชบอร์ดกับรายงาน PDF จะเรียกหมวดเดียวกัน
#   คนละชื่อ ซึ่งเป็นปัญหาเดิมที่ไฟล์นี้ตั้งขึ้นมาเพื่อแก้
#
# ⚠️ แปลงเฉพาะตอน "แสดงผล" เท่านั้น ห้ามแปลงก่อนเอาไปเทียบหรือจัดกลุ่ม
#   ค่าใน DB ยังเป็น key เดิม การเปลี่ยนชื่อจึงไม่แตะข้อมูล ไม่ต้องวิเคราะห์ใหม่
#   และไม่กระทบโมเดล (id2label ผูกกับเลขคลาส ไม่ใช่คำไทย)
_LABELS_FILE = Path(__file__).resolve().parent.parent / "shared" / "category_labels.json"
try:
    _SHARED = json.loads(_LABELS_FILE.read_text(encoding="utf-8"))
    CATEGORY_LABELS: dict[str, str] = _SHARED["labels"]
    # หมวดทั้งหมดที่โมเดลทำนายได้ — ลอกจาก id2label ของโมเดล
    # ใช้เป็นรายการตัวเลือกในหน้าเว็บและในพรอมป์ NLP เพื่อไม่ให้มีลิสต์เพี้ยนอีกชุด
    CATEGORY_KEYS: list[str] = _SHARED["keys"]
    # กติกาเลือกหมวดเมื่อรีวิวพูดถึงหลายเรื่อง — โมเดลเลือกได้หมวดเดียว
    # (single-label) และ DB เก็บได้ช่องเดียว จึงต้องมีกติกาว่าเลือกเรื่องไหน
    # ใส่ลงพรอมป์ด้วย เพื่อให้เส้นทาง Claude ตัดสินแบบเดียวกับโมเดลและคนตรวจ
    CATEGORY_RULES: list[str] = _SHARED.get("decision_rules", [])
except (OSError, ValueError, KeyError):
    CATEGORY_LABELS = {}
    CATEGORY_KEYS = []
    CATEGORY_RULES = []


def category_label(category: str | None) -> str | None:
    """คืนชื่อหมวดสำหรับแสดงผล — ไม่มีใน map ก็คืนค่าเดิม"""
    if category is None:
        return None
    return CATEGORY_LABELS.get(category, category)


def category_guideline_text() -> str:
    """กติกาเลือกหมวดในรูปข้อความ สำหรับพรอมป์ NLP และคู่มือผู้ตรวจ"""
    return "\n".join(r for r in CATEGORY_RULES if r.strip())


# ── นิยามของอารมณ์ (sentiment) ──
#
# ⚠️ อ่านจาก shared/sentiment_labels.json ด้วยเหตุผลเดียวกับหมวดหมู่ข้างบน
#   เดิมพรอมป์ใน nlp/sentiment.py บอกแค่ว่าตอบได้ 3 ค่า แต่ไม่ได้นิยามว่า
#   แต่ละค่าหมายถึงอะไร การตีความจึงเลื่อนได้ตามรอบที่รัน และเวลาเอาคน
#   มาประเมินเทียบ ถ้าคนใช้กติกาคนละชุดกับที่ชุดเทรนใช้ ค่า kappa จะต่ำ
#   เพราะกติกาไม่ตรงกัน ไม่ใช่เพราะโมเดลแย่ แล้วจะสรุปผลงานวิจัยผิด
#
# ⚠️ ค่าใน DB ยังเป็น 'positive'/'neutral'/'negative' เหมือนเดิม
#   ไฟล์นี้ให้แต่ "ความหมาย" กับ "ชื่อที่แสดง" ไม่ได้เปลี่ยนค่าที่เก็บ
#   จึงไม่ต้องวิเคราะห์ใหม่และไม่กระทบโมเดล
_SENTI_FILE = Path(__file__).resolve().parent.parent / "shared" / "sentiment_labels.json"
try:
    _SENTI = json.loads(_SENTI_FILE.read_text(encoding="utf-8"))
    SENTIMENT_LABELS: dict[str, str] = _SENTI["labels"]
    SENTIMENT_KEYS: list[str] = _SENTI["keys"]
    SENTIMENT_DEFS: dict[str, dict] = _SENTI["definitions"]
    SENTIMENT_RULES: list[str] = _SENTI["decision_rules"]
except (OSError, ValueError, KeyError):
    SENTIMENT_LABELS = {}
    SENTIMENT_KEYS = ["positive", "neutral", "negative"]
    SENTIMENT_DEFS = {}
    SENTIMENT_RULES = []


def sentiment_label(sentiment: str | None) -> str | None:
    """คืนชื่ออารมณ์สำหรับแสดงผล — ไม่มีใน map ก็คืนค่าเดิม"""
    if sentiment is None:
        return None
    return SENTIMENT_LABELS.get(sentiment, sentiment)


def sentiment_guideline_text() -> str:
    """
    นิยาม sentiment ในรูปข้อความ สำหรับแปะลงพรอมป์ NLP และคู่มือคนติดป้าย

    ใช้ที่เดียวกับที่คนอ่าน เพื่อให้โมเดลกับคนตัดสินด้วยกติกาชุดเดียวกัน
    ถ้าโหลดไฟล์ไม่ได้จะคืนค่าว่าง ผู้เรียกต้องรับมือได้เอง
    """
    if not SENTIMENT_DEFS:
        return ""
    out = []
    for key in SENTIMENT_KEYS:
        d = SENTIMENT_DEFS.get(key)
        if not d:
            continue
        out.append(f'- "{key}" ({SENTIMENT_LABELS.get(key, key)}): {d["นิยาม"]}')
        for case in d.get("เข้าข่าย", []):
            out.append(f"    • {case}")
    if SENTIMENT_RULES:
        out.append("")
        out.append("ลำดับการตัดสิน:")
        out.extend(f"  {r}" for r in SENTIMENT_RULES)
    return "\n".join(out)


# หมวด "ความคิดเห็นทั่วไป" ไม่ใช่ pain point จริง — ตัดออกเมื่อดูโหมด "เฉพาะปัญหา"
GENERAL_CATEGORY = "ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)"

# หมวดที่ "ไม่ใช่ปัญหา" — ไม่นับเป็น pain point ไม่ว่ากรณีใด
NON_PROBLEM_CATEGORIES = [GENERAL_CATEGORY, "อื่นๆ", "ไม่มี"]
# literal สำหรับ NOT IN (...) — ค่าเป็น constant ของเราเอง ปลอดภัยจาก injection
_NONPROBLEM_IN = ", ".join("'" + c.replace("'", "''") + "'" for c in NON_PROBLEM_CATEGORIES)


def _parse_iso_date(s: str | None):
    """แปลง 'YYYY-MM-DD' → date; asyncpg ไม่รับ str ต้องเป็น date จริง"""
    if not s:
        return None
    try:
        y, m, d = s.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return None


def date_filter(date_from: str | None, date_to: str | None, alias: str = "r") -> tuple[str, dict]:
    """
    คืน (SQL fragment, dict params) กรองรีวิวตามช่วงเวลา
      date_from / date_to = 'YYYY-MM-DD' หรือ None
    - ถ้าไม่ส่งทั้งคู่ = ไม่กรอง (ทำงานเหมือนเดิม)
    - รีวิวที่ไม่มี review_date_approx จะถูกตัดออกเมื่อกรอง (ตามหลักการ)
    """
    conds = []
    params: dict = {}
    df = _parse_iso_date(date_from)
    dt = _parse_iso_date(date_to)
    if df:
        conds.append(f"{alias}.review_date_approx >= :date_from")
        params["date_from"] = df
    if dt:
        conds.append(f"{alias}.review_date_approx <= :date_to")
        params["date_to"] = dt
    return ("AND " + " AND ".join(conds) if conds else ""), params


def sentiment_filter(view_mode: str, alias: str = "ar") -> str:
    """
    โหมดมุมมอง (3 ทาง):
      'complaints' → รีวิวเชิงลบ (คำบ่นจริง) + ตัดหมวดที่ไม่ใช่ปัญหา
      'praise'     → รีวิวเชิงบวก (คำชม)   + ตัดหมวดที่ไม่ใช่ปัญหา
      'all' หรืออื่น → ไม่กรอง (ดูทุกรีวิวทุกอารมณ์ทุกหมวด)
    ตัด "ความคิดเห็นทั่วไป/อื่นๆ/ไม่มี" ทั้งในโหมด complaints+praise
    เพื่อให้เห็นหมวดที่มีสาระ (ปัญหา/จุดแข็ง)
    """
    if view_mode == "complaints":
        return (f"AND {alias}.sentiment = 'negative' "
                f"AND {alias}.pain_point_category NOT IN ({_NONPROBLEM_IN})")
    if view_mode == "praise":
        return (f"AND {alias}.sentiment = 'positive' "
                f"AND {alias}.pain_point_category NOT IN ({_NONPROBLEM_IN})")
    return ""


def status_filter(status: str, alias: str = "p") -> str:
    """
    คืน SQL fragment กรองสถานะร้าน
      operational (default ของ endpoint ที่ใช้) = เฉพาะร้านที่เปิด
      closed                = เฉพาะร้านที่ปิด (ถาวร + ชั่วคราว)
      all                   = ทุกร้าน

    หมายเหตุ: ค่า default ของแต่ละ endpoint เป็นเรื่องของ endpoint นั้น
    ไม่ใช่ของฟังก์ชันนี้ — /map/geojson ใช้ 'all' เพื่อคงพฤติกรรมเดิม
    """
    if status == "closed":
        return (f"AND COALESCE({alias}.business_status,'operational') "
                f"IN ('closed_permanently','closed_temporarily')")
    if status == "all":
        return ""
    return f"AND COALESCE({alias}.business_status,'operational') = 'operational'"
