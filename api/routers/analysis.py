from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.filters import (
    GENERAL_CATEGORY,
    NON_PROBLEM_CATEGORIES,
    _NONPROBLEM_IN,
    date_filter,
    sentiment_filter,
    status_filter,
)
from api.schemas.analysis import (
    CategoryCount,
    GeoJSONCollection,
    GeoJSONFeature,
    GeoJSONGeometry,
    InsightResponse,
)

router = APIRouter(prefix="/insights", tags=["insights"])

# ตัวกรองที่ใช้ร่วมกับ router อื่น (และรายงาน) อยู่ที่ api/filters.py แหล่งเดียว
# ห้าม copy-paste มาไว้ที่นี่ — ดูเหตุผลใน docstring ของไฟล์นั้น

# นิยาม "pain point" = รีวิวเชิงลบ (คำบ่น) เท่านั้น — ไม่นับคำชม/ความเห็นทั่วไป
# ⚠️ dead code: ไม่มีที่ไหนเรียก คงไว้ที่นี่โดยเจตนา ไม่ย้ายเข้า api/filters.py
# (เอา dead code ไปไว้ในโมดูลกลางจะทำให้มันดูเหมือนของสำคัญ แล้วคนต่อไปไม่กล้าลบ)
NEGATIVE_ONLY = "ar.sentiment = 'negative'"


# ⚠️ dead code เช่นกัน — alias เดิมของ sentiment_filter ไม่มีที่ไหนเรียก
def pain_filter(pain_only: bool, alias: str = "ar") -> str:
    return sentiment_filter("complaints" if pain_only else "all", alias)


# ฐานต่ำกว่านี้ในหนึ่ง bucket → ติดธง low_confidence (อัตราแกว่งแรงเกินจะอ่าน)
LOW_CONFIDENCE_MIN = 30


def _rate(numerator: int | None, denominator: int | None) -> float | None:
    """
    สัดส่วน numerator/denominator — ตัวส่วนเป็น 0 หรือ None → คืน None ไม่ใช่ 0.0

    0% = "วัดแล้วไม่พบ" · None = "ไม่มีข้อมูลให้วัด" คนละความหมาย
    ถ้าคืน 0 เมื่อไม่มีข้อมูล กราฟจะวาดเส้นลงถึงศูนย์เหมือนปัญหาหมดไป
    ทั้งที่จริงคือเดือนนั้นไม่มีรีวิวเลย

    ⚠️ ตัวเศษกับตัวส่วนต้องมาจากคิวรีที่ผ่านชุดกรองเดียวกัน (ช่วงเวลา + สถานะร้าน
    + text_clean <> '' + มีแถวใน analyzed_reviews) ไม่งั้นจะได้ % เกิน 100
    หรือต่ำผิดปกติแบบหาสาเหตุไม่เจอ
    """
    if not denominator:
        return None
    return (numerator or 0) / denominator


@router.get("/zones")
async def zone_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    date_from: str | None = None,
    date_to: str | None = None,
    status: str = "all",
):
    """
    สรุป pain point แยกตามโซนพื้นที่ (กรองช่วงเวลาได้)

    status: default "all" = ไม่กรอง → ไม่ส่งมาก็ได้ค่าเท่าเดิมทุกตัว

    ฟิลด์เชิงสัดส่วน (ฐานเข้ม: มีข้อความ + วิเคราะห์แล้ว + ผ่าน status):
      total_with_text · negative_count · complaint_rate · severity_counts · severity_share
    ฟิลด์เดิม (review_count / analyzed_count / high_count / ...) ไม่กรอง text_clean
    จึงห้ามเอาไปเป็นตัวส่วนของสัดส่วนใหม่ (กฎ 1)
    """
    date_sql, date_params = date_filter(date_from, date_to)
    biz_filter = status_filter(status)
    # เมื่อกรองวันที่ ใช้ INNER JOIN reviews (คนไม่มี date จะหลุด) — ตามหลักการ
    join_kind = "JOIN" if date_sql else "LEFT JOIN"
    result = await db.execute(
        text(f"""
            SELECT
                COALESCE(p.zone, 'other')           AS zone,
                COUNT(DISTINCT p.id)                 AS place_count,
                COUNT(DISTINCT r.id)                 AS review_count,
                COUNT(DISTINCT ar.id)                AS analyzed_count,
                COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high'   AND ar.sentiment='negative') AS high_count,
                COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'medium' AND ar.sentiment='negative') AS medium_count,
                COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'low'    AND ar.sentiment='negative') AS low_count,
                MODE() WITHIN GROUP (ORDER BY ar.pain_point_category)
                    FILTER (WHERE r.text_clean <> ''
                            AND ar.sentiment = 'negative'
                            AND ar.pain_point_category IS NOT NULL
                            AND ar.pain_point_category NOT IN ({_NONPROBLEM_IN})) AS top_category
            FROM places p
            {join_kind} reviews r  ON r.place_id = p.id {date_sql}
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            GROUP BY COALESCE(p.zone, 'other')
            ORDER BY analyzed_count DESC
        """),
        {"general": GENERAL_CATEGORY, **date_params},
    )
    rows = result.fetchall()

    # ── ฐานเชิงสัดส่วนต่อโซน — คิวรีแยกเพื่อไม่แตะตัวเลขเดิม ──
    base_result = await db.execute(
        text(f"""
            SELECT COALESCE(p.zone, 'other') AS zone,
                   COUNT(*)                                          AS total_with_text,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'negative')  AS neg,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'negative'
                                      AND ar.severity = 'high')       AS sev_high,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'negative'
                                      AND ar.severity = 'medium')     AS sev_medium,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'negative'
                                      AND ar.severity = 'low')        AS sev_low
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places  p ON p.id = r.place_id
            WHERE r.text_clean <> ''
              {biz_filter}
              {date_sql}
            GROUP BY COALESCE(p.zone, 'other')
        """),
        date_params,
    )
    base = {b.zone: b for b in base_result.fetchall()}

    zone_labels = {
        "naresuan":   "รอบ ม.นเรศวร",
        "rajabhat":   "รอบ ม.ราชภัฏ",
        "city_center": "ตัวเมือง",
        "other":      "อื่นๆ พิษณุโลก",
    }

    out = []
    for r in rows:
        b = base.get(r.zone)
        sev = {
            "high": (b.sev_high if b else 0),
            "medium": (b.sev_medium if b else 0),
            "low": (b.sev_low if b else 0),
        }
        neg = b.neg if b else 0
        twt = b.total_with_text if b else 0
        out.append({
            # ── ฟิลด์เดิม ──
            "zone": r.zone,
            "label": zone_labels.get(r.zone, r.zone),
            "place_count": r.place_count,
            "review_count": r.review_count,
            "analyzed_count": r.analyzed_count,
            "high_count": r.high_count or 0,
            "medium_count": r.medium_count or 0,
            "low_count": r.low_count or 0,
            "top_category": r.top_category,
            # ── ฟิลด์ใหม่เชิงสัดส่วน (ฐานเข้ม) ──
            "total_with_text": twt,
            "negative_count": neg,
            "complaint_rate": _rate(neg, twt),
            "severity_counts": sev,
            "severity_share": {k: _rate(v, neg) for k, v in sev.items()},
        })
    return out


@router.get("/zones/{zone}/pain-points")
async def zone_pain_points(
    zone: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    view_mode: str = "complaints",
    status: str = "operational",
    date_from: str | None = None,
    date_to: str | None = None,
):
    """
    Pain point categories ของโซน (view_mode: complaints/praise/all)

    คืน object ไม่ใช่ list เพราะต้องส่ง "ตัวส่วน" มาด้วย — ตัวเลข % บนหน้าเว็บ
    ต้องมี n ควบคู่เสมอ และตัวเศษ/ตัวส่วนต้องมาจากชุดกรองเดียวกัน (กฎ 1)
    ถ้าให้ UI ไปหยิบตัวส่วนจาก /insights/zones (ซึ่งไม่รู้ status ของแผงนี้)
    พอผู้ใช้สลับสถานะร้าน ตัวเศษจะเปลี่ยนแต่ตัวส่วนไม่เปลี่ยน → % ผิดเงียบ ๆ

    {
      items: [{category, count, share_of_negative, rate_of_all}],
      total_with_text, sentiment_counts, complaint_rate,
      severity_counts, severity_share
    }
    """
    general_filter = sentiment_filter(view_mode)
    biz_filter = status_filter(status)
    date_sql, date_params = date_filter(date_from, date_to)

    # ── ฐานของโซนนี้ ใช้ตัวกรองชุดเดียวกับคิวรีหมวด (ต่างแค่ไม่กรอง sentiment/หมวด) ──
    base_result = await db.execute(
        text(f"""
            SELECT COUNT(*)                                         AS total_with_text,
                   COUNT(*) FILTER (WHERE ar.sentiment='negative')  AS neg,
                   COUNT(*) FILTER (WHERE ar.sentiment='positive')  AS pos,
                   COUNT(*) FILTER (WHERE ar.sentiment='neutral')   AS neu,
                   COUNT(*) FILTER (WHERE ar.sentiment='negative'
                                      AND ar.severity='high')       AS sev_high,
                   COUNT(*) FILTER (WHERE ar.sentiment='negative'
                                      AND ar.severity='medium')     AS sev_medium,
                   COUNT(*) FILTER (WHERE ar.sentiment='negative'
                                      AND ar.severity='low')        AS sev_low
            FROM analyzed_reviews ar
            JOIN reviews r  ON r.id = ar.review_id
            JOIN places p   ON p.id = r.place_id
            WHERE COALESCE(p.zone, 'other') = :zone
              AND r.text_clean <> ''
              {biz_filter}
              {date_sql}
        """),
        {"zone": zone, **date_params},
    )
    b = base_result.fetchone()

    result = await db.execute(
        text(f"""
            SELECT ar.pain_point_category AS category, COUNT(*) AS count
            FROM analyzed_reviews ar
            JOIN reviews r  ON r.id = ar.review_id
            JOIN places p   ON p.id = r.place_id
            WHERE COALESCE(p.zone, 'other') = :zone
              AND ar.pain_point_category IS NOT NULL
              AND r.text_clean <> ''
              {general_filter}
              {biz_filter}
              {date_sql}
            GROUP BY ar.pain_point_category
            ORDER BY count DESC
            LIMIT 10
        """),
        {"zone": zone, "general": GENERAL_CATEGORY, **date_params},
    )
    # share_of_negative มีความหมายเฉพาะโหมด complaints (เหมือน /insights/summary)
    share_base = b.neg if view_mode == "complaints" else None
    sev = {"high": b.sev_high, "medium": b.sev_medium, "low": b.sev_low}
    return {
        "items": [
            {
                "category": r.category,
                "count": r.count,
                "share_of_negative": _rate(r.count, share_base),
                "rate_of_all": _rate(r.count, b.total_with_text),
            }
            for r in result.fetchall()
        ],
        "total_with_text": b.total_with_text,
        "sentiment_counts": {"negative": b.neg, "positive": b.pos, "neutral": b.neu},
        "complaint_rate": _rate(b.neg, b.total_with_text),
        "severity_counts": sev,
        "severity_share": {k: _rate(v, b.neg) for k, v in sev.items()},
    }


@router.get("/zones/{zone}/breakdown")
async def zone_breakdown(
    zone: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    view_mode: str = "complaints",
    status: str = "operational",
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Pain point แยกตามประเภทสถานที่ภายในโซน (view_mode: complaints/praise/all)"""

    # แผนที่ Google category → ประเภทที่ใช้ในระบบ
    _GOOGLE_CATEGORY_MAP = {
        'คาเฟ่': 'คาเฟ่', 'ร้านกาแฟ': 'คาเฟ่', 'coffee shop': 'คาเฟ่', 'cafe': 'คาเฟ่',
        'ร้านขนม': 'คาเฟ่', 'bakery': 'คาเฟ่', 'เบเกอรี่': 'คาเฟ่', 'ร้านเบเกอรี่': 'คาเฟ่',
        'ร้านอาหาร': 'ร้านอาหาร', 'restaurant': 'ร้านอาหาร', 'ร้านอาหารไทย': 'ร้านอาหาร',
        'thai restaurant': 'ร้านอาหาร', 'ร้านก๋วยเตี๋ยว': 'ร้านอาหาร', 'noodle shop': 'ร้านอาหาร',
        'ร้านอาหารตามสั่ง': 'ร้านอาหาร', 'buffet restaurant': 'ร้านอาหาร',
        'วัด': 'สถานที่ท่องเที่ยว', 'buddhist temple': 'สถานที่ท่องเที่ยว', 'temple': 'สถานที่ท่องเที่ยว',
        'สถานที่ท่องเที่ยว': 'สถานที่ท่องเที่ยว', 'tourist attraction': 'สถานที่ท่องเที่ยว',
        'พิพิธภัณฑ์': 'สถานที่ท่องเที่ยว', 'museum': 'สถานที่ท่องเที่ยว',
        'อุทยานแห่งชาติ': 'สถานที่ท่องเที่ยว', 'national park': 'สถานที่ท่องเที่ยว',
        'สวนสาธารณะ': 'สถานที่ท่องเที่ยว', 'park': 'สถานที่ท่องเที่ยว',
        'น้ำตก': 'สถานที่ท่องเที่ยว', 'waterfall': 'สถานที่ท่องเที่ยว',
        'ตลาด': 'สถานที่ท่องเที่ยว', 'market': 'สถานที่ท่องเที่ยว',
    }

    def detect_place_type(name: str, google_category: str | None) -> str:
        # ลำดับที่ 1: ใช้ category จริงจาก Google ถ้ามี (แม่นยำกว่า)
        if google_category:
            gc = google_category.strip().lower()
            if gc in _GOOGLE_CATEGORY_MAP:
                return _GOOGLE_CATEGORY_MAP[gc]
            for key, mapped in _GOOGLE_CATEGORY_MAP.items():
                if key in gc:
                    return mapped

        # ลำดับที่ 2: เดาจากชื่อสถานที่ (fallback สำหรับข้อมูลเก่าที่ไม่มี google_category)
        n = name.lower()
        if any(k in n for k in ['cafe', 'coffee', 'คาเฟ่', 'คาเฟ', 'กาแฟ', 'ชา', 'bakery', 'บาเกอรี']):
            return 'คาเฟ่'
        if any(k in n for k in ['ร้านอาหาร', 'อาหาร', 'restaurant', 'ข้าว', 'ก๋วยเตี๋ยว', 'บุฟเฟ่', 'ชาบู', 'แกง']):
            return 'ร้านอาหาร'
        if any(k in n for k in ['วัด', 'อุทยาน', 'พิพิธภัณฑ์', 'น้ำตก', 'เขื่อน', 'สวน', 'ถนนคนเดิน',
                                  'ตลาด', 'บึง', 'หาด', 'พระราชวัง', 'museum', 'park', 'street art']):
            return 'สถานที่ท่องเที่ยว'
        return 'ทั่วไป'

    # ดึงสถานที่ + รีวิวในโซนนี้ (กรองตามสถานะร้าน + ช่วงเวลา)
    biz_filter = status_filter(status)
    date_sql, date_params = date_filter(date_from, date_to)
    # เมื่อกรองวันที่ ใช้ INNER JOIN เพื่อตัดรีวิวไม่มี date
    join_kind = "JOIN" if date_sql else "LEFT JOIN"
    places_result = await db.execute(
        text(f"""
            SELECT p.id, p.name, p.google_category,
                   COUNT(DISTINCT r.id)  AS review_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high'   AND ar.sentiment='negative') AS high_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'medium' AND ar.sentiment='negative') AS medium_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'low'    AND ar.sentiment='negative') AS low_count
            FROM places p
            {join_kind} reviews r  ON r.place_id = p.id {date_sql}
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE COALESCE(p.zone, 'other') = :zone
              {biz_filter}
            GROUP BY p.id, p.name, p.google_category
            ORDER BY high_count DESC
        """),
        {"zone": zone, **date_params},
    )
    places = places_result.fetchall()

    # Pain points ต่อสถานที่
    general_filter = sentiment_filter(view_mode)
    pain_result = await db.execute(
        text(f"""
            SELECT p.name AS place_name,
                   ar.pain_point_category AS category,
                   COUNT(*) AS cnt
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places p  ON p.id = r.place_id
            WHERE COALESCE(p.zone, 'other') = :zone
              AND ar.pain_point_category IS NOT NULL
              AND r.text_clean <> ''
              {general_filter}
              {biz_filter}
              {date_sql}
            GROUP BY p.name, ar.pain_point_category
        """),
        {"zone": zone, "general": GENERAL_CATEGORY, **date_params},
    )
    pain_rows = pain_result.fetchall()

    # จัด pain points ตาม place
    pain_by_place: dict[str, dict[str, int]] = {}
    for row in pain_rows:
        if row.place_name not in pain_by_place:
            pain_by_place[row.place_name] = {}
        pain_by_place[row.place_name][row.category] = row.cnt

    # จัดกลุ่มตามประเภทสถานที่
    type_groups: dict[str, dict] = {}
    for p in places:
        ptype = detect_place_type(p.name, p.google_category)
        if ptype not in type_groups:
            type_groups[ptype] = {
                "type": ptype,
                "places": [],
                "pain_point_totals": {},
                "high_total": 0,
                "medium_total": 0,
                "low_total": 0,
            }
        g = type_groups[ptype]
        g["places"].append({"name": p.name, "high_count": p.high_count or 0})
        g["high_total"] += p.high_count or 0
        g["medium_total"] += p.medium_count or 0
        g["low_total"] += p.low_count or 0
        for cat, cnt in pain_by_place.get(p.name, {}).items():
            g["pain_point_totals"][cat] = g["pain_point_totals"].get(cat, 0) + cnt

    # แปลงเป็น list เรียงตาม high_total
    type_order = ["คาเฟ่", "ร้านอาหาร", "สถานที่ท่องเที่ยว", "ทั่วไป"]
    result_list = []
    for ptype in type_order:
        if ptype not in type_groups:
            continue
        g = type_groups[ptype]
        top_pain = sorted(g["pain_point_totals"].items(), key=lambda x: x[1], reverse=True)[:5]
        result_list.append({
            "type": ptype,
            "place_count": len(g["places"]),
            "high_total": g["high_total"],
            "medium_total": g["medium_total"],
            "low_total": g["low_total"],
            "top_places": sorted(g["places"], key=lambda x: x["high_count"], reverse=True)[:5],
            "top_pain_points": [{"category": c, "count": n} for c, n in top_pain],
        })

    return result_list


@router.get("/category-places")
async def category_places(
    category: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    zone: str | None = None,
    status: str = "operational",
    view_mode: str = "complaints",
    date_from: str | None = None,
    date_to: str | None = None,
):
    """ร้านในหมวดนี้ (view_mode: complaints=ร้านที่ถูกบ่น / praise=ร้านที่ถูกชม / all=ทั้งหมด)"""
    filters = ["ar.pain_point_category = :category", "r.text_clean <> ''"]
    # กรอง sentiment ตาม view_mode (complaints=negative, praise=positive, all=ไม่กรอง)
    if view_mode == "complaints":
        filters.append("ar.sentiment = 'negative'")
    elif view_mode == "praise":
        filters.append("ar.sentiment = 'positive'")
    params: dict = {"category": category}
    if zone:
        filters.append("COALESCE(p.zone, 'other') = :zone")
        params["zone"] = zone
    where = " AND ".join(filters)
    biz_filter = status_filter(status)
    date_sql, date_params = date_filter(date_from, date_to)
    params.update(date_params)

    result = await db.execute(
        text(f"""
            SELECT p.id AS place_id, p.name AS place_name,
                   COALESCE(p.zone, 'other') AS zone,
                   COALESCE(p.business_status, 'operational') AS business_status,
                   COUNT(*) AS total,
                   -- ระดับความรุนแรง (ใช้ในโหมด complaints)
                   COUNT(*) FILTER (WHERE ar.severity = 'high')   AS high,
                   COUNT(*) FILTER (WHERE ar.severity = 'medium') AS medium,
                   COUNT(*) FILTER (WHERE ar.severity = 'low')    AS low,
                   -- ประเภทความรู้สึก (ใช้ในโหมด all ที่รีวิวปนกันทุกแบบ)
                   COUNT(*) FILTER (WHERE ar.sentiment = 'negative') AS neg,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'positive') AS pos,
                   COUNT(*) FILTER (WHERE ar.sentiment NOT IN ('negative','positive')
                                       OR ar.sentiment IS NULL)      AS neu
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places p  ON p.id = r.place_id
            WHERE {where}
              {biz_filter}
              {date_sql}
            GROUP BY p.id, p.name, p.zone, p.business_status
            ORDER BY total DESC
            LIMIT 50
        """),
        params,
    )
    return [dict(row._mapping) for row in result.fetchall()]


@router.get("/category-reviews")
async def category_reviews(
    category: str,
    place_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    severity: str | None = None,
    sentiment: str | None = None,
    view_mode: str = "complaints",
    date_from: str | None = None,
    date_to: str | None = None,
):
    """
    รีวิวจริงของร้าน+หมวด
      view_mode : complaints=คำบ่น / praise=คำชม / all=ทั้งหมด
      severity  : กรองระดับความรุนแรง (ใช้ในโหมด complaints)
      sentiment : กรองประเภทความรู้สึก (ใช้ในโหมด all)
    """
    filters = [
        "ar.pain_point_category = :category",
        "r.place_id = :place_id",
        "r.text_clean <> ''",
    ]
    if view_mode == "complaints":
        filters.append("ar.sentiment = 'negative'")
    elif view_mode == "praise":
        filters.append("ar.sentiment = 'positive'")
    params: dict = {"category": category, "place_id": place_id}
    if severity:
        filters.append("ar.severity = :severity")
        params["severity"] = severity
    if sentiment == "neutral":
        # "กลางๆ" = ไม่ใช่ทั้งลบและบวก (รวม neutral/mixed/NULL)
        filters.append("(ar.sentiment NOT IN ('negative','positive') OR ar.sentiment IS NULL)")
    elif sentiment in ("negative", "positive"):
        filters.append("ar.sentiment = :sentiment")
        params["sentiment"] = sentiment
    date_sql, date_params = date_filter(date_from, date_to)
    if date_sql:
        # date_filter คืน "AND ..." — เอา "AND " ออก แล้ว append เข้า filters
        filters.append(date_sql.removeprefix("AND ").strip())
        params.update(date_params)
    where = " AND ".join(filters)

    result = await db.execute(
        text(f"""
            SELECT r.text_clean AS text, r.rating, ar.severity, ar.sentiment,
                   r.review_date_approx AS date
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            WHERE {where}
            ORDER BY
                CASE ar.severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                r.review_date_approx DESC NULLS LAST
            LIMIT 30
        """),
        params,
    )
    return [
        {
            "text": r.text,
            "rating": r.rating,
            "severity": r.severity,
            "sentiment": r.sentiment,
            "date": r.date.isoformat() if r.date else None,
        }
        for r in result.fetchall()
    ]


@router.get("/summary", response_model=InsightResponse)
async def insights_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    view_mode: str = "complaints",
    status: str = "operational",
    date_from: str | None = None,
    date_to: str | None = None,
):
    """สรุปภาพรวม + top categories + severity + worst places (view_mode: complaints/praise/all)"""
    date_sql, date_params = date_filter(date_from, date_to)

    # นับรีวิว/วิเคราะห์ตามช่วงเวลาที่เลือก (places = ทั้งหมด — ไม่แปรตามเวลา)
    counts = await db.execute(
        text(f"""
            SELECT
                (SELECT COUNT(*) FROM places) AS total_places,
                (SELECT COUNT(*) FROM reviews r WHERE TRUE {date_sql}) AS total_reviews,
                (SELECT COUNT(*) FROM analyzed_reviews ar
                    JOIN reviews r ON r.id = ar.review_id
                    WHERE TRUE {date_sql}) AS total_analyzed
        """),
        date_params,
    )
    row = counts.fetchone()
    total_places, total_reviews, total_analyzed = (
        row.total_places, row.total_reviews, row.total_analyzed
    )

    general_filter = sentiment_filter(view_mode)
    biz_filter = status_filter(status)

    # ── ฐานเดียวของทุกตัวชี้วัดเชิงสัดส่วน (กฎ 1) ────────────────────────────
    # ประชากร = รีวิวในช่วงที่เลือก ที่มีข้อความ + มีแถวใน analyzed_reviews
    #           + ผ่าน status_filter  → ใช้เป็นตัวส่วนทุกตัวในบล็อกนี้
    # ต่างจาก total_reviews/total_analyzed (ฟิลด์เดิม) ที่ไม่กรอง text_clean/status
    # จึงห้ามเอาฟิลด์เดิมมาเป็นตัวส่วนของสัดส่วนใหม่
    base_result = await db.execute(
        text(f"""
            SELECT
                COUNT(*)                                                    AS total_with_text,
                COUNT(*) FILTER (WHERE ar.sentiment = 'negative')           AS neg,
                COUNT(*) FILTER (WHERE ar.sentiment = 'positive')           AS pos,
                COUNT(*) FILTER (WHERE ar.sentiment = 'neutral')            AS neu,
                COUNT(*) FILTER (WHERE ar.sentiment = 'negative'
                                   AND ar.severity = 'high')                AS sev_high,
                COUNT(*) FILTER (WHERE ar.sentiment = 'negative'
                                   AND ar.severity = 'medium')              AS sev_medium,
                COUNT(*) FILTER (WHERE ar.sentiment = 'negative'
                                   AND ar.severity = 'low')                 AS sev_low
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places  p ON p.id = r.place_id
            WHERE r.text_clean <> ''
              {biz_filter}
              {date_sql}
        """),
        date_params,
    )
    b = base_result.fetchone()
    total_with_text = b.total_with_text
    sentiment_counts = {"negative": b.neg, "positive": b.pos, "neutral": b.neu}
    # severity มีความหมายเฉพาะรีวิวเชิงลบ → ตัวส่วนของ severity_share คือคำบ่นทั้งหมด
    severity_counts = {"high": b.sev_high, "medium": b.sev_medium, "low": b.sev_low}
    severity_share = {k: _rate(v, b.neg) for k, v in severity_counts.items()}

    cat_result = await db.execute(
        text(f"""
            SELECT ar.pain_point_category AS category, COUNT(*) AS count
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places p  ON p.id = r.place_id
            WHERE ar.pain_point_category IS NOT NULL
              AND r.text_clean <> ''
              {general_filter}
              {biz_filter}
              {date_sql}
            GROUP BY ar.pain_point_category
            ORDER BY count DESC
            LIMIT 10
        """),
        {"general": GENERAL_CATEGORY, **date_params},
    )
    # share_of_negative มีความหมายเฉพาะโหมด complaints เพราะตัวเศษเป็นรีวิวเชิงลบ
    # โหมด praise ตัวเศษเป็นรีวิวเชิงบวก / โหมด all รวมทุกอารมณ์ → หารด้วยคำบ่น
    # จะได้ค่าไร้ความหมายและเกิน 100% ได้ จึงคืน None (ชื่อฟิลด์ต้องไม่โกหก)
    _share_base = b.neg if view_mode == "complaints" else None
    top_categories = [
        {
            "category": r.category,
            "count": r.count,
            "share_of_negative": _rate(r.count, _share_base),
            "rate_of_all": _rate(r.count, total_with_text),
        }
        for r in cat_result.fetchall()
    ]

    # การกระจายระดับความรุนแรง — เฉพาะรีวิวเชิงลบ + ในช่วงเวลาที่เลือก
    sev_result = await db.execute(
        text(f"""
            SELECT ar.severity, COUNT(*) AS count
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            WHERE ar.severity IS NOT NULL AND ar.sentiment = 'negative'
              {date_sql}
            GROUP BY ar.severity
        """),
        date_params,
    )
    severity_dist = {r.severity: r.count for r in sev_result.fetchall()}

    worst_result = await db.execute(
        text(f"""
            SELECT p.name AS place_name,
                   COUNT(*) FILTER (WHERE ar.severity = 'high' AND ar.sentiment='negative') AS high_count
            FROM places p
            JOIN reviews r  ON r.place_id = p.id
            JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE TRUE {date_sql}
            GROUP BY p.id, p.name
            ORDER BY high_count DESC
            LIMIT 10
        """),
        date_params,
    )
    worst_places = [
        {"place_name": r.place_name, "high_count": r.high_count}
        for r in worst_result.fetchall()
    ]

    return {
        # ── ฟิลด์เดิม (กฎ 3: ห้ามลบ ห้ามเปลี่ยนชนิด ห้ามเปลี่ยนค่า) ──
        "total_places": total_places,
        "total_reviews": total_reviews,
        "total_analyzed": total_analyzed,
        "top_pain_point_categories": top_categories,
        "severity_distribution": severity_dist,
        "worst_places": worst_places,
        # ── ฟิลด์ใหม่เชิงสัดส่วน ทั้งหมดคิดจากฐาน total_with_text ──
        "total_with_text": total_with_text,
        "sentiment_counts": sentiment_counts,
        "complaint_rate": _rate(b.neg, total_with_text),
        # severity_counts คือ severity บนฐานเดียวกับ severity_share
        # (ต่างจาก severity_distribution ที่ไม่กรอง text_clean/status —
        #  ห้ามเอา % ใหม่ไปแสดงคู่กับจำนวนเดิม เพราะคนละประชากร)
        "severity_counts": severity_counts,
        "severity_share": severity_share,
    }


# นิพจน์ตัวเศษ/ตัวส่วนของ high_rate — ต้องกรอง text_clean ทั้งสองฝั่ง (กฎ 1)
# วัดจริง: 46 จาก 775 ของ high+negative เป็นรีวิวที่ให้ดาวอย่างเดียว (ไม่มีข้อความ)
# ถ้าใช้ high_count เดิมเป็นตัวเศษคู่กับตัวส่วนที่กรอง text_clean จะเป่าอัตราให้สูงเกินจริง
_HIGH_WITH_TEXT = ("COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high' "
                   "AND ar.sentiment = 'negative' AND r.text_clean <> '')")
_REVIEWS_WITH_TEXT = "COUNT(DISTINCT r.id) FILTER (WHERE r.text_clean <> '')"


@router.get("/top-places")
async def top_problematic_places(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 10,
    status: str = "operational",
    date_from: str | None = None,
    date_to: str | None = None,
    sort: str = "count",
    min_reviews: int = 30,
):
    """
    ร้านที่มีปัญหามากสุด — เรียงได้ 2 แบบ

    sort='count' (default) → เรียงตาม high_count เหมือนเดิมทุกประการ
                             ร้านที่มีรีวิวเยอะจะได้เปรียบเสมอ (ยอดดิบ)
    sort='rate'            → เรียงตาม high_rate เฉพาะร้านที่มีรีวิว (ที่มีข้อความ)
                             ตั้งแต่ min_reviews ขึ้นไป — 3 รีวิว บ่น 2 = 67%
                             ไม่ใช่ข้อมูล แต่เป็นเสียงรบกวน

    ฟิลด์ใหม่ (ฟิลด์เดิมไม่แตะ ตามกฎ 3):
      review_count_with_text = ตัวส่วนของ high_rate (review_count เดิมไม่กรอง
                               text_clean จึงใช้เป็นตัวส่วนไม่ได้)
      high_count_with_text   = ตัวเศษของ high_rate
      high_rate              = high_count_with_text / review_count_with_text
    """
    biz_filter = status_filter(status)
    date_sql, date_params = date_filter(date_from, date_to)
    params: dict = {"lim": limit, **date_params}

    if sort == "rate":
        having = f"HAVING {_REVIEWS_WITH_TEXT} >= :min_reviews"
        order = (f"ORDER BY {_HIGH_WITH_TEXT}::float / NULLIF({_REVIEWS_WITH_TEXT}, 0) "
                 f"DESC NULLS LAST, high_count DESC")
        params["min_reviews"] = min_reviews
    else:
        # ของเดิมเป๊ะ — ไม่ส่ง sort/min_reviews มา ต้องได้ผลเท่าเดิมทุกค่า
        having = ""
        order = "ORDER BY high_count DESC, medium_count DESC"

    result = await db.execute(
        text(f"""
            SELECT p.id, p.name,
                   p.overall_rating,
                   COALESCE(p.business_status, 'operational') AS business_status,
                   COUNT(DISTINCT r.id)                                          AS review_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high'   AND ar.sentiment='negative') AS high_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'medium' AND ar.sentiment='negative') AS medium_count,
                   {_REVIEWS_WITH_TEXT} AS review_count_with_text,
                   {_HIGH_WITH_TEXT}    AS high_count_with_text
            FROM places p
            JOIN reviews r  ON r.place_id = p.id
            JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE TRUE
              {biz_filter}
              {date_sql}
            GROUP BY p.id, p.name, p.overall_rating, p.business_status
            {having}
            {order}
            LIMIT :lim
        """),
        params,
    )
    rows = []
    for row in result.fetchall():
        d = dict(row._mapping)
        d["high_rate"] = _rate(d["high_count_with_text"], d["review_count_with_text"])
        rows.append(d)
    return rows


@router.get("/positive-highlights")
async def positive_highlights(
    db: Annotated[AsyncSession, Depends(get_db)],
    zone: str | None = None,
    limit: int = 5,
    status: str = "operational",
    date_from: str | None = None,
    date_to: str | None = None,
):
    """จุดเด่น = หมวดที่มีคำชม (positive) มากที่สุด (กรองช่วงเวลาได้)"""
    filters = [
        "ar.sentiment = 'positive'",
        "r.text_clean <> ''",
        "ar.pain_point_category IS NOT NULL",
        f"ar.pain_point_category NOT IN ({_NONPROBLEM_IN})",
    ]
    params: dict = {"lim": limit}
    if zone:
        filters.append("COALESCE(p.zone, 'other') = :zone")
        params["zone"] = zone
    date_sql, date_params = date_filter(date_from, date_to)
    if date_sql:
        filters.append(date_sql.removeprefix("AND ").strip())
        params.update(date_params)
    where = " AND ".join(filters)
    biz_filter = status_filter(status)

    result = await db.execute(
        text(f"""
            SELECT ar.pain_point_category AS category, COUNT(*) AS count
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places p  ON p.id = r.place_id
            WHERE {where}
              {biz_filter}
            GROUP BY ar.pain_point_category
            ORDER BY count DESC
            LIMIT :lim
        """),
        params,
    )
    return [{"category": r.category, "count": r.count} for r in result.fetchall()]


@router.get("/snapshots")
async def list_snapshots(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 20,
):
    """รายการ snapshot สถิติที่เก็บไว้ (ใหม่ → เก่า)"""
    result = await db.execute(
        text("""
            SELECT id, taken_at, period_label, total_places, total_reviews, total_analyzed, note
            FROM stat_snapshots
            ORDER BY taken_at DESC
            LIMIT :lim
        """),
        {"lim": limit},
    )
    return [
        {
            "id": r.id,
            "taken_at": r.taken_at.isoformat() if r.taken_at else None,
            "period_label": r.period_label,
            "total_places": r.total_places,
            "total_reviews": r.total_reviews,
            "total_analyzed": r.total_analyzed,
            "note": r.note,
        }
        for r in result.fetchall()
    ]


@router.get("/snapshot-compare")
async def compare_snapshots(
    db: Annotated[AsyncSession, Depends(get_db)],
    from_id: int | None = None,
    to_id: int | None = None,
    zone: str | None = None,
    min_delta: int = 1,
):
    """
    เทียบ snapshot 2 ช่วง → บอกว่าปัญหาหมวดไหนเพิ่มขึ้น และ "เพิ่มแบบไหน"

    spread = 'concentrated' → เพิ่มกระจุกที่ร้านเดียว (ปัญหาเฉพาะร้าน)
             'widespread'   → เพิ่มกระจายหลายร้าน  (ปัญหาเชิงพื้นที่/ภาพรวม)

    ไม่ระบุ from_id/to_id → ใช้ snapshot ล่าสุด 2 อันอัตโนมัติ
    """
    # เลือก snapshot อัตโนมัติถ้าไม่ระบุ
    if from_id is None or to_id is None:
        r = await db.execute(
            text("SELECT id FROM stat_snapshots ORDER BY taken_at DESC LIMIT 2")
        )
        ids = [x[0] for x in r.fetchall()]
        if len(ids) < 2:
            return {"error": "ต้องมี snapshot อย่างน้อย 2 ครั้งถึงจะเทียบได้",
                    "snapshots_available": len(ids), "categories": []}
        to_id, from_id = ids[0], ids[1]

    meta = await db.execute(
        text("""SELECT id, taken_at, period_label FROM stat_snapshots WHERE id IN (:a, :b)"""),
        {"a": from_id, "b": to_id},
    )
    info = {
        x.id: {"id": x.id, "label": x.period_label,
               "taken_at": x.taken_at.isoformat() if x.taken_at else None}
        for x in meta.fetchall()
    }

    # ── 1) ผลต่างระดับหมวด ──
    zone_cond = "zone = :zone" if zone else "zone IS NULL"
    params: dict = {"from": from_id, "to": to_id}
    if zone:
        params["zone"] = zone

    cat_rows = await db.execute(
        text(f"""
            SELECT COALESCE(a.category, b.category)     AS category,
                   COALESCE(b.complaint_count, 0)       AS before_count,
                   COALESCE(a.complaint_count, 0)       AS after_count,
                   COALESCE(a.high_count, 0)            AS after_high
            FROM      (SELECT category, complaint_count, high_count FROM snapshot_categories
                       WHERE snapshot_id = :to   AND {zone_cond}) a
            FULL JOIN (SELECT category, complaint_count FROM snapshot_categories
                       WHERE snapshot_id = :from AND {zone_cond}) b
              ON a.category = b.category
            WHERE COALESCE(a.category, b.category) NOT IN ({_NONPROBLEM_IN})
        """),
        params,
    )

    # ── 2) ผลต่างระดับร้าน (ใช้ตัดสินว่ากระจุกหรือกระจาย) ──
    place_rows = await db.execute(
        text("""
            SELECT COALESCE(a.category, b.category) AS category,
                   p.name AS place_name,
                   COALESCE(a.complaint_count, 0) - COALESCE(b.complaint_count, 0) AS delta
            FROM      (SELECT place_id, category, complaint_count FROM snapshot_places
                       WHERE snapshot_id = :to) a
            FULL JOIN (SELECT place_id, category, complaint_count FROM snapshot_places
                       WHERE snapshot_id = :from) b
              ON a.place_id = b.place_id AND a.category = b.category
            JOIN places p ON p.id = COALESCE(a.place_id, b.place_id)
            WHERE COALESCE(a.complaint_count, 0) > COALESCE(b.complaint_count, 0)
        """),
        {"from": from_id, "to": to_id},
    )

    # จัดกลุ่มผลต่างรายร้านตามหมวด
    by_cat: dict[str, list[dict]] = {}
    for r in place_rows.fetchall():
        by_cat.setdefault(r.category, []).append({"place_name": r.place_name, "delta": r.delta})

    out = []
    for r in cat_rows.fetchall():
        delta = r.after_count - r.before_count
        if delta < min_delta:
            continue
        places = sorted(by_cat.get(r.category, []), key=lambda x: x["delta"], reverse=True)
        total_place_delta = sum(p["delta"] for p in places) or 1
        top = places[0] if places else None
        # "กระจุกตัว" = ปัญหามาจากร้านเดียวจริงๆ
        #   - มีร้านเดียวที่เพิ่ม → กระจุกแน่นอน
        #   - หลายร้านเพิ่ม แต่ร้านนำกินสัดส่วน ≥60% → ยังถือว่ากระจุก
        # (ไม่ใช้ ≥50% เฉยๆ เพราะกรณี 2 ร้าน ร้านละ 1 จะถูกตัดสินผิดว่ากระจุก)
        if len(places) == 1:
            concentrated = True
        elif top and total_place_delta > 0:
            concentrated = top["delta"] / total_place_delta >= 0.6
        else:
            concentrated = False
        out.append({
            "category": r.category,
            "before": r.before_count,
            "after": r.after_count,
            "delta": delta,
            "pct_change": round(delta / r.before_count * 100, 1) if r.before_count else None,
            "high_count": r.after_high,
            "spread": "concentrated" if concentrated else "widespread",
            "places_increased": len(places),
            "top_places": places[:3],
        })

    out.sort(key=lambda x: x["delta"], reverse=True)
    return {
        "from": info.get(from_id),
        "to": info.get(to_id),
        "zone": zone,
        "categories": out,
    }


@router.get("/trending")
async def trending_problems(
    db: Annotated[AsyncSession, Depends(get_db)],
    period: str = "month",
    buckets: int = 6,
    top: int = 5,
    zone: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str = "all",
):
    """
    Top N ปัญหาแยกตามช่วงเวลา (สัปดาห์/เดือน) — นับจาก "วันที่เขียนรีวิว"

    ต่างจาก snapshot ตรงที่อันนี้ดูว่า *นักท่องเที่ยวบ่นเรื่องอะไรในช่วงนั้น*
    ส่วน snapshot ดูว่า *เราเก็บข้อมูลเพิ่มได้เท่าไหร่*

    ช่วงเวลาที่ใช้ (2 โหมด):
      ไม่ส่ง date → ย้อนหลัง N bucket จากปัจจุบัน และ "ตัดช่วงปัจจุบันที่ยังไม่จบ"
                    ออกเสมอ เพราะข้อมูลยังไม่ครบ จะทำให้แท่งสุดท้ายต่ำผิดปกติ
                    และดูเหมือนปัญหาลดฮวบ (พฤติกรรมเดิมทุกประการ)
      ส่ง date     → แบ่ง bucket ภายในช่วงที่ผู้ใช้เลือก และ "ไม่ตัด" ช่วงปัจจุบัน
                    เพราะผู้ใช้กำหนดขอบเขตเองแล้ว การตัดท้ายจะกลายเป็นซ่อนข้อมูล

    status: default "all" = ไม่กรอง → ไม่ส่งมาก็ได้ counts เท่าเดิมทุกค่า
      frontend ส่ง status ของหน้ามาเพื่อให้ฐานตรงกับการ์ด KPI (กฎ 1)

    ตัวเลขเชิงสัดส่วนต่อ bucket (ตัวส่วนต่างกัน ตอบคำถามคนละข้อ):
      rates  = counts / bucket_total   → "เดือนนั้นคนกี่ % บ่นเรื่องนี้"
                                          รวมทุกหมวดได้ประมาณ complaint_rate ไม่ใช่ 100%
      shares = counts / bucket_negative → "ในบรรดาคำบ่นเดือนนั้น เรื่องนี้กินสัดส่วนเท่าไหร่"
                                          รวมได้ ~100% (ขาดไปคือหมวดที่ถูกตัด)
      ตัวแรกบอก "ปัญหาหนักขึ้นไหม" ตัวหลังบอก "องค์ประกอบของปัญหาเปลี่ยนไปไหม"

    low_confidence = bucket_total < LOW_CONFIDENCE_MIN → ตัวเลขอัตราไม่น่าเชื่อถือ
    """
    unit = "week" if period == "week" else "month"
    params: dict = {"top": top}
    zone_sql = ""
    if zone:
        zone_sql = "AND COALESCE(p.zone,'other') = :zone"
        params["zone"] = zone

    status_sql = status_filter(status, "p")
    date_sql, date_params = date_filter(date_from, date_to, "r")
    if date_sql:
        window_sql = date_sql
        params.update(date_params)
    else:
        window_sql = (
            f"AND r.review_date_approx <  DATE_TRUNC('{unit}', NOW()) "
            f"AND r.review_date_approx >= DATE_TRUNC('{unit}', NOW()) "
            f"- :buckets * INTERVAL '1 {unit}'"
        )
        params["buckets"] = buckets

    # 1) หา top N หมวดในช่วงที่สนใจ (ใช้เป็นแถวของตาราง)
    top_rows = await db.execute(
        text(f"""
            SELECT ar.pain_point_category AS category, COUNT(*) AS total
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places  p ON p.id = r.place_id
            WHERE ar.sentiment = 'negative'
              AND r.text_clean <> ''
              AND r.review_date_approx IS NOT NULL
              {window_sql}
              AND ar.pain_point_category NOT IN ({_NONPROBLEM_IN})
              {zone_sql}
              {status_sql}
            GROUP BY ar.pain_point_category
            ORDER BY total DESC
            LIMIT :top
        """),
        params,
    )
    top_categories = [r.category for r in top_rows.fetchall()]
    if not top_categories:
        return {"period": unit, "categories": [], "buckets": []}

    # 2) นับแต่ละหมวดแยกตามช่วงเวลา
    params["cats"] = top_categories
    cell_rows = await db.execute(
        text(f"""
            SELECT DATE_TRUNC('{unit}', r.review_date_approx)::date AS bucket,
                   ar.pain_point_category AS category,
                   COUNT(*) AS count
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places  p ON p.id = r.place_id
            WHERE ar.sentiment = 'negative'
              AND r.text_clean <> ''
              AND r.review_date_approx IS NOT NULL
              {window_sql}
              AND ar.pain_point_category = ANY(:cats)
              {zone_sql}
              {status_sql}
            GROUP BY 1, 2
            ORDER BY 1
        """),
        params,
    )

    grid: dict[str, dict[str, int]] = {}
    for r in cell_rows.fetchall():
        key = r.bucket.isoformat()
        grid.setdefault(key, {})[r.category] = r.count

    # ── ตัวส่วนของแต่ละ bucket ──────────────────────────────────────────────
    # ใช้ชุดกรองเดียวกับคิวรี counts ทุกมิติที่ใช้ร่วมกัน (window / text_clean /
    # review_date_approx NOT NULL / zone / status / JOIN analyzed_reviews)
    # ต่างกันเฉพาะที่ "ไม่กรอง sentiment และ category" เพราะเป็นตัวส่วนโดยเจตนา
    denom_rows = await db.execute(
        text(f"""
            SELECT DATE_TRUNC('{unit}', r.review_date_approx)::date AS bucket,
                   COUNT(*)                                          AS bucket_total,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'negative') AS bucket_negative
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places  p ON p.id = r.place_id
            WHERE r.text_clean <> ''
              AND r.review_date_approx IS NOT NULL
              {window_sql}
              {zone_sql}
              {status_sql}
            GROUP BY 1
        """),
        params,
    )
    denom = {r.bucket.isoformat(): (r.bucket_total, r.bucket_negative)
             for r in denom_rows.fetchall()}

    bucket_list = sorted(grid.keys())
    buckets = []
    for b in bucket_list:
        counts = {c: grid[b].get(c, 0) for c in top_categories}
        b_total, b_neg = denom.get(b, (0, 0))
        buckets.append({
            "bucket": b,
            "counts": counts,
            "total": sum(counts.values()),
            "bucket_total": b_total,
            "bucket_negative": b_neg,
            "rates": {c: _rate(n, b_total) for c, n in counts.items()},
            "shares": {c: _rate(n, b_neg) for c, n in counts.items()},
            "low_confidence": b_total < LOW_CONFIDENCE_MIN,
        })

    return {
        "period": unit,
        "categories": top_categories,
        "low_confidence_min": LOW_CONFIDENCE_MIN,
        "buckets": buckets,
    }


@router.get("/alerts")
async def problem_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    min_delta: int = 2,
):
    """
    รายการแจ้งเตือน (สำหรับไอคอนกระดิ่ง) — สร้างจากการเทียบ snapshot ล่าสุด 2 ครั้ง

    ประเภทแจ้งเตือน:
      new_category → หมวดปัญหาที่ไม่เคยมีมาก่อน (ปัญหาใหม่เกิดขึ้น)
      spike        → ปัญหาเพิ่มกระจุกที่ร้านเดียว (ร้านนั้นมีเรื่อง)
      increase     → ปัญหาเพิ่มกระจายหลายร้าน (ปัญหาเชิงพื้นที่)
    """
    r = await db.execute(text("SELECT id FROM stat_snapshots ORDER BY taken_at DESC LIMIT 2"))
    ids = [x[0] for x in r.fetchall()]
    if len(ids) < 2:
        return {"unread_count": 0, "alerts": [],
                "message": "ต้องมี snapshot อย่างน้อย 2 ครั้งถึงจะเทียบได้"}
    to_id, from_id = ids[0], ids[1]

    cmp_data = await compare_snapshots(db, from_id=from_id, to_id=to_id, min_delta=min_delta)

    alerts = []
    for c in cmp_data.get("categories", []):
        is_new = c["before"] == 0 and c["after"] > 0
        concentrated = c["spread"] == "concentrated"
        top = c["top_places"][0] if c["top_places"] else None

        if is_new:
            a_type, level = "new_category", "high"
            title = f"ปัญหาใหม่: {c['category']}"
            detail = f"เพิ่งพบครั้งแรก {c['after']} คอมเมนต์"
        elif concentrated and top:
            a_type = "spike"
            level = "high" if c["delta"] >= 5 else "medium"
            title = f"{c['category']} เพิ่มขึ้น {c['delta']} คอมเมนต์"
            detail = f"กระจุกที่ร้านเดียว — {top['place_name']} (+{top['delta']})"
        else:
            a_type = "increase"
            level = "medium" if c["delta"] >= 5 else "low"
            title = f"{c['category']} เพิ่มขึ้น {c['delta']} คอมเมนต์"
            detail = f"กระจายใน {c['places_increased']} ร้าน — เป็นปัญหาภาพรวม"

        alerts.append({
            "id": f"{a_type}:{c['category']}",
            "type": a_type,
            "level": level,
            "title": title,
            "detail": detail,
            "category": c["category"],
            "delta": c["delta"],
            "pct_change": c["pct_change"],
            "spread": c["spread"],
            "places_increased": c["places_increased"],
            "top_places": c["top_places"],
        })

    order = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda a: (order[a["level"]], -a["delta"]))
    return {
        "unread_count": len(alerts),
        "from": cmp_data.get("from"),
        "to": cmp_data.get("to"),
        "alerts": alerts,
    }


@router.get("/categories", response_model=list[CategoryCount])
async def category_counts(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        text("""
            SELECT ar.pain_point_category AS category, COUNT(*) AS count
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            WHERE ar.pain_point_category IS NOT NULL
              AND r.text_clean <> ''          -- ตัดรีวิวที่ให้ดาวอย่างเดียว
            GROUP BY ar.pain_point_category
            ORDER BY count DESC
        """)
    )
    return [{"category": r.category, "count": r.count} for r in result.fetchall()]


@router.get("/heatmap", response_model=GeoJSONCollection)
async def heatmap_geojson(db: Annotated[AsyncSession, Depends(get_db)]):
    """GeoJSON FeatureCollection — one feature per place with analysis properties."""
    result = await db.execute(
        text("""
            SELECT
                p.id, p.name,
                p.overall_rating,
                ST_X(p.location) AS lng,
                ST_Y(p.location) AS lat,
                MODE() WITHIN GROUP (ORDER BY ar.severity)           AS dominant_severity,
                ARRAY_AGG(DISTINCT ar.pain_point_category)
                    FILTER (WHERE ar.pain_point_category IS NOT NULL) AS pain_categories,
                COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high') AS high_count
            FROM places p
            LEFT JOIN reviews r  ON r.place_id = p.id
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE p.location IS NOT NULL
            GROUP BY p.id, p.name, p.overall_rating, p.location
        """)
    )

    features = []
    for row in result.fetchall():
        if row.lat is None or row.lng is None:
            continue
        features.append(
            GeoJSONFeature(
                geometry=GeoJSONGeometry(
                    type="Point",
                    coordinates=[row.lng, row.lat],
                ),
                properties={
                    "id": row.id,
                    "name": row.name,
                    "rating": float(row.overall_rating) if row.overall_rating else None,
                    "dominant_severity": row.dominant_severity,
                    "pain_point_categories": row.pain_categories or [],
                    "high_count": row.high_count or 0,
                },
            )
        )

    return GeoJSONCollection(features=features)
