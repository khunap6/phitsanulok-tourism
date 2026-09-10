from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.filters import date_filter, sentiment_filter, status_filter
from api.schemas.review import ReviewListResponse, ReviewResponse

router = APIRouter(tags=["reviews"])

# ⚠️ ใช้ r.text_clean ไม่ใช่ r.text
# r.text คือข้อความดิบจากหน้าเว็บ มีชื่อคนรีวิว/"Local Guide · 57 รีวิว · 237 รูปภาพ"/
# วันที่สัมพัทธ์ปนอยู่ ถ้าเอามาแสดงตรง ๆ รีวิวที่ให้ดาวอย่างเดียวจะโผล่มาเป็นข้อมูลคนรีวิว
#
# ส่ง review_date_approx มาด้วย (คง review_date เดิมไว้ไม่ลบ) เพราะ review_date เป็น
# ข้อความสัมพัทธ์ ณ เวลาที่ scrape — "3 ปีที่แล้ว" ที่เก็บมาเมื่อ 2 ปีก่อน วันนี้คือ 5 ปี
# ยิ่งนานยิ่งผิด ส่วน approx เป็นวันที่จริงที่คำนวณไว้ตอน scrape จึงนิ่ง
_REVIEW_SELECT = """
    SELECT
        r.id, r.place_id, p.name AS place_name,
        r.rating, r.text_clean AS text, r.review_date, r.review_date_approx,
        ar.sentiment, ar.pain_point_category,
        ar.pain_point_thai, ar.severity, ar.keywords
    FROM reviews r
    JOIN places p ON p.id = r.place_id
    LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
"""

# เรียงแบบเดียวกับ category_reviews() ใน analysis.py — รุนแรงก่อน แล้วใหม่ก่อน
# (เดิมใช้ ORDER BY r.id DESC ซึ่งคือ "ลำดับที่บันทึกลง DB" ทำให้หน้าแรกเป็นร้านที่
#  scrape ล่าสุดร้านเดียวยกแผง — วัดจริงแล้วได้ 1 ร้านใน 30 แถวแรก)
_REVIEW_ORDER = """
    ORDER BY
        CASE ar.severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
        r.review_date_approx DESC NULLS LAST,
        r.id DESC
"""

# ที่ไหนแสดงข้อความรีวิว ที่นั่นต้องมีข้อความ — ใช้เกณฑ์เดียวกันทุก endpoint
_HAS_TEXT = "COALESCE(r.text_clean,'') <> ''"


@router.get("/places/{place_id}/reviews", response_model=list[ReviewResponse],
            deprecated=True)
async def reviews_for_place(
    place_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    severity: Optional[str] = Query(None, description="high | medium | low"),
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    ⚠️ DEPRECATED — ใช้ `/reviews?place_id=<id>` แทน

    ตัวนี้ไม่รู้จัก date_from / date_to / view_mode / status จึงคืนรีวิว "ทุกช่วงเวลา
    ทุกอารมณ์ ทุกสถานะร้าน" เสมอ ถ้าหน้าเว็บกรองอยู่แล้วมาเรียกตัวนี้ ตัวเลขกับ
    รายการจะไม่ตรงกันโดยไม่มีอะไรฟ้อง — และไม่มี total / hidden_no_text ให้แสดงด้วย

    `/reviews?place_id=` ใช้ตัวกรอง ลำดับ และการนับชุดเดียวกับที่ Dashboard ใช้จริง
    ทางเดินโค้ดเดียว ความหมายเดียว จุดทดสอบเดียว

    ไม่มีผู้ใช้เหลือแล้ว (UI ย้ายไป /reviews หมด, ReviewList ของหน้าโซนที่จะทำต่อ
    จะใช้ /reviews?zone= ไม่ใช่ตัวนี้) → ลบทิ้งได้ในรอบทำความสะอาดถัดไป
    """
    filters = f"WHERE r.place_id = :pid AND {_HAS_TEXT}"
    params: dict = {"pid": place_id, "lim": limit, "off": offset}

    if severity:
        filters += " AND ar.severity = :sev"
        params["sev"] = severity
    if category:
        filters += " AND ar.pain_point_category = :cat"
        params["cat"] = category

    result = await db.execute(
        text(f"{_REVIEW_SELECT} {filters} ORDER BY r.id DESC LIMIT :lim OFFSET :off"),
        params,
    )
    return [dict(row._mapping) for row in result.fetchall()]


@router.get("/reviews", response_model=ReviewListResponse)
async def list_reviews(
    db: Annotated[AsyncSession, Depends(get_db)],
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    place_id: Optional[int] = Query(None, description="กรองเฉพาะร้านเดียว"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    view_mode: str = Query("all", description="complaints | praise | all"),
    status: str = Query("all", description="operational | closed | all"),
):
    """
    รายการรีวิวแบบแบ่งหน้า — ตัวกรองชุดเดียวกับ KPI/กราฟบนหน้า Dashboard

    view_mode / status default = "all" เพื่อให้ "ไม่ส่ง = ไม่กรอง" (ตัวกรองใหม่ไม่มีผล
    ถ้าผู้เรียกไม่ได้ส่งมา) ส่วนการเปลี่ยนไปใช้ text_clean / ตัด rating-only /
    เปลี่ยนลำดับ เป็นการแก้บั๊กที่ตั้งใจให้เปลี่ยนผลลัพธ์

    hidden_no_text = จำนวนรีวิวที่เข้าเงื่อนไขอื่นครบแต่ไม่มีข้อความ (ให้ดาวอย่างเดียว)
    ส่งมาเพื่อให้หน้าเว็บบอกผู้ใช้ได้ว่าซ่อนไปกี่รายการ ไม่ใช่ทำข้อมูลหายเงียบ ๆ

    place_id = กรองเฉพาะร้านเดียว มีไว้ให้ Dashboard ใช้ endpoint เดียวทั้งโหมด
    "ทุกร้าน" และ "เลือกร้าน" — ไม่งั้นโหมดเลือกร้านจะไปใช้ /places/{id}/reviews
    ซึ่งไม่รู้จัก date/view_mode/status แล้วบรรทัดกำกับบนหน้าเว็บจะโฆษณาตัวกรอง
    ที่ไม่ได้ทำงานจริง (ผิดยิ่งกว่าไม่เขียน) และไม่มี total/hidden_no_text ให้แสดง
    """
    offset = (page - 1) * page_size

    # ตัวกรองที่ใช้ร่วมกันทั้งคิวรีนับและคิวรีดึงรายการ (ยังไม่รวมเงื่อนไข "มีข้อความ")
    conds: list[str] = []
    params: dict = {"lim": page_size, "off": offset}

    if place_id is not None:
        conds.append("r.place_id = :pid")
        params["pid"] = place_id
    if category:
        conds.append("ar.pain_point_category = :cat")
        params["cat"] = category
    if severity:
        conds.append("ar.severity = :sev")
        params["sev"] = severity

    date_sql, date_params = date_filter(date_from, date_to, "r")
    if date_sql:
        conds.append(date_sql.removeprefix("AND ").strip())
        params.update(date_params)

    view_sql = sentiment_filter(view_mode, "ar")
    if view_sql:
        conds.append(view_sql.removeprefix("AND ").strip())

    status_sql = status_filter(status, "p")
    if status_sql:
        conds.append(status_sql.removeprefix("AND ").strip())

    where_common = ("WHERE " + " AND ".join(conds)) if conds else "WHERE 1=1"

    # นับ 2 ค่าในคิวรีเดียว: ที่แสดงได้จริง กับที่ถูกซ่อนเพราะไม่มีข้อความ
    # ต้อง JOIN places เพราะตัวกรอง status อ้างถึง p (เดิมคิวรีนับ join แค่ 2 ตาราง)
    count_result = await db.execute(
        text(f"""
            SELECT
                COUNT(*) FILTER (WHERE {_HAS_TEXT})     AS total,
                COUNT(*) FILTER (WHERE NOT ({_HAS_TEXT})) AS hidden_no_text
            FROM reviews r
            JOIN places p ON p.id = r.place_id
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            {where_common}
        """),
        params,
    )
    counts = count_result.fetchone()

    result = await db.execute(
        text(f"{_REVIEW_SELECT} {where_common} AND {_HAS_TEXT} "
             f"{_REVIEW_ORDER} LIMIT :lim OFFSET :off"),
        params,
    )
    items = [dict(row._mapping) for row in result.fetchall()]

    return {
        "total": counts.total,
        "hidden_no_text": counts.hidden_no_text,
        "page": page,
        "page_size": page_size,
        "items": items,
    }
