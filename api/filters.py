"""
filters.py — ตัวกรอง SQL ที่ใช้ร่วมกันทุก router (และรายงาน)

เหตุผลที่ต้องมีไฟล์นี้: นิยาม "หมวดที่ไม่ใช่ปัญหา" กับตัวกรองวันที่/สถานะร้าน
เคยถูก copy-paste อยู่หลายที่ (analysis.py, report_data.py) พอแก้ที่เดียว
อีกที่ไม่เปลี่ยน → ตัวเลขบนแดชบอร์ดกับในรายงาน PDF/Word ไม่ตรงกัน
ทุกที่ที่ต้องกรองต้อง import จากไฟล์นี้เท่านั้น ห้ามเขียนซ้ำ
"""
from datetime import date

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
