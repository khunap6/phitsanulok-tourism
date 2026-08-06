from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.schemas.analysis import (
    CategoryCount,
    GeoJSONCollection,
    GeoJSONFeature,
    GeoJSONGeometry,
    InsightResponse,
)

router = APIRouter(prefix="/insights", tags=["insights"])

# หมวด "ความคิดเห็นทั่วไป" ไม่ใช่ pain point จริง — ตัดออกเมื่อดูโหมด "เฉพาะปัญหา"
GENERAL_CATEGORY = "ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)"

# หมวดที่ "ไม่ใช่ปัญหา" — ไม่นับเป็น pain point ไม่ว่ากรณีใด
NON_PROBLEM_CATEGORIES = [GENERAL_CATEGORY, "อื่นๆ", "ไม่มี"]
# literal สำหรับ NOT IN (...) — ค่าเป็น constant ของเราเอง ปลอดภัยจาก injection
_NONPROBLEM_IN = ", ".join("'" + c.replace("'", "''") + "'" for c in NON_PROBLEM_CATEGORIES)

# นิยาม "pain point" = รีวิวเชิงลบ (คำบ่น) เท่านั้น — ไม่นับคำชม/ความเห็นทั่วไป
NEGATIVE_ONLY = "ar.sentiment = 'negative'"


def pain_filter(pain_only: bool, alias: str = "ar") -> str:
    """
    โหมด "เฉพาะปัญหา" (pain_only=True):
      - เอาเฉพาะรีวิว sentiment=negative (คำบ่นจริง ไม่ใช่คำชม)
      - ตัดหมวดที่ไม่ใช่ปัญหา (ความคิดเห็นทั่วไป/อื่นๆ/ไม่มี)
    โหมดปกติ (pain_only=False): ไม่กรอง (ดูทุกรีวิวทุกอารมณ์)
    """
    if not pain_only:
        return ""
    return (f"AND {alias}.sentiment = 'negative' "
            f"AND {alias}.pain_point_category NOT IN ({_NONPROBLEM_IN})")


def status_filter(status: str, alias: str = "p") -> str:
    """
    คืน SQL fragment กรองสถานะร้าน
      operational (default) = เฉพาะร้านที่เปิด
      closed                = เฉพาะร้านที่ปิด (ถาวร + ชั่วคราว)
      all                   = ทุกร้าน
    """
    if status == "closed":
        return (f"AND COALESCE({alias}.business_status,'operational') "
                f"IN ('closed_permanently','closed_temporarily')")
    if status == "all":
        return ""
    return f"AND COALESCE({alias}.business_status,'operational') = 'operational'"


@router.get("/zones")
async def zone_summary(db: Annotated[AsyncSession, Depends(get_db)]):
    """สรุป pain point แยกตามโซนพื้นที่"""
    result = await db.execute(
        text("""
            SELECT
                COALESCE(p.zone, 'other')           AS zone,
                COUNT(DISTINCT p.id)                 AS place_count,
                COUNT(DISTINCT r.id)                 AS review_count,
                COUNT(DISTINCT ar.id)                AS analyzed_count,
                -- นับระดับความรุนแรง เฉพาะรีวิวเชิงลบ (คำบ่นจริง)
                COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high'   AND ar.sentiment='negative') AS high_count,
                COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'medium' AND ar.sentiment='negative') AS medium_count,
                COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'low'    AND ar.sentiment='negative') AS low_count,
                -- ปัญหาหลัก = หมวดคำบ่นที่พบบ่อยสุด (เฉพาะรีวิวเชิงลบ + ตัดหมวดที่ไม่ใช่ปัญหา)
                MODE() WITHIN GROUP (ORDER BY ar.pain_point_category)
                    FILTER (WHERE r.text_clean <> ''
                            AND ar.sentiment = 'negative'
                            AND ar.pain_point_category IS NOT NULL
                            AND ar.pain_point_category NOT IN (""" + _NONPROBLEM_IN + """)) AS top_category
            FROM places p
            LEFT JOIN reviews r  ON r.place_id = p.id
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            GROUP BY COALESCE(p.zone, 'other')
            ORDER BY analyzed_count DESC
        """),
        {"general": GENERAL_CATEGORY},
    )
    rows = result.fetchall()

    zone_labels = {
        "naresuan":   "รอบ ม.นเรศวร",
        "rajabhat":   "รอบ ม.ราชภัฏ",
        "city_center": "ตัวเมือง",
        "other":      "อื่นๆ พิษณุโลก",
    }

    return [
        {
            "zone": r.zone,
            "label": zone_labels.get(r.zone, r.zone),
            "place_count": r.place_count,
            "review_count": r.review_count,
            "analyzed_count": r.analyzed_count,
            "high_count": r.high_count or 0,
            "medium_count": r.medium_count or 0,
            "low_count": r.low_count or 0,
            "top_category": r.top_category,
        }
        for r in rows
    ]


@router.get("/zones/{zone}/pain-points")
async def zone_pain_points(
    zone: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    pain_only: bool = False,
    status: str = "operational",
):
    """Pain point categories ของโซน (status=operational/closed/all)"""
    general_filter = pain_filter(pain_only)
    biz_filter = status_filter(status)
    result = await db.execute(
        text(f"""
            SELECT ar.pain_point_category AS category, COUNT(*) AS count
            FROM analyzed_reviews ar
            JOIN reviews r  ON r.id = ar.review_id
            JOIN places p   ON p.id = r.place_id
            WHERE COALESCE(p.zone, 'other') = :zone
              AND ar.pain_point_category IS NOT NULL
              AND r.text_clean <> ''          -- ตัดรีวิวที่ให้ดาวอย่างเดียว
              {general_filter}
              {biz_filter}
            GROUP BY ar.pain_point_category
            ORDER BY count DESC
            LIMIT 10
        """),
        {"zone": zone, "general": GENERAL_CATEGORY},
    )
    return [{"category": r.category, "count": r.count} for r in result.fetchall()]


@router.get("/zones/{zone}/breakdown")
async def zone_breakdown(
    zone: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    pain_only: bool = False,
    status: str = "operational",
):
    """Pain point แยกตามประเภทสถานที่ภายในโซน (status=operational/closed/all)"""

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

    # ดึงสถานที่ + รีวิวในโซนนี้ (กรองตามสถานะร้าน)
    biz_filter = status_filter(status)
    places_result = await db.execute(
        text(f"""
            SELECT p.id, p.name, p.google_category,
                   COUNT(DISTINCT r.id)  AS review_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high'   AND ar.sentiment='negative') AS high_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'medium' AND ar.sentiment='negative') AS medium_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'low'    AND ar.sentiment='negative') AS low_count
            FROM places p
            LEFT JOIN reviews r  ON r.place_id = p.id
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE COALESCE(p.zone, 'other') = :zone
              {biz_filter}
            GROUP BY p.id, p.name, p.google_category
            ORDER BY high_count DESC
        """),
        {"zone": zone},
    )
    places = places_result.fetchall()

    # Pain points ต่อสถานที่
    general_filter = pain_filter(pain_only)
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
              AND r.text_clean <> ''          -- ตัดรีวิวที่ให้ดาวอย่างเดียว
              {general_filter}
              {biz_filter}
            GROUP BY p.name, ar.pain_point_category
        """),
        {"zone": zone, "general": GENERAL_CATEGORY},
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
):
    """
    ร้านที่มี pain point หมวดนี้ พร้อมจำนวนแยกตามระดับ + สถานะร้าน
    เรียงตามจำนวนรวมมากสุด — frontend ใช้ sort ตามระดับที่เลือก
    """
    # เฉพาะรีวิวเชิงลบ = ร้านที่มี "ปัญหา" หมวดนี้จริง (ไม่ใช่ร้านที่ถูกชมเรื่องนี้)
    filters = ["ar.pain_point_category = :category", "r.text_clean <> ''", NEGATIVE_ONLY]
    params: dict = {"category": category}
    if zone:
        filters.append("COALESCE(p.zone, 'other') = :zone")
        params["zone"] = zone
    where = " AND ".join(filters)
    biz_filter = status_filter(status)

    result = await db.execute(
        text(f"""
            SELECT p.id AS place_id, p.name AS place_name,
                   COALESCE(p.zone, 'other') AS zone,
                   COALESCE(p.business_status, 'operational') AS business_status,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE ar.severity = 'high')   AS high,
                   COUNT(*) FILTER (WHERE ar.severity = 'medium') AS medium,
                   COUNT(*) FILTER (WHERE ar.severity = 'low')    AS low
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places p  ON p.id = r.place_id
            WHERE {where}
              {biz_filter}
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
):
    """รีวิวจริงของร้านหนึ่ง ในหมวดที่เลือก (กรอง severity ได้)"""
    filters = [
        "ar.pain_point_category = :category",
        "r.place_id = :place_id",
        "r.text_clean <> ''",
        NEGATIVE_ONLY,          # เฉพาะรีวิวคำบ่น (ไม่โชว์คำชม)
    ]
    params: dict = {"category": category, "place_id": place_id}
    if severity:
        filters.append("ar.severity = :severity")
        params["severity"] = severity
    where = " AND ".join(filters)

    result = await db.execute(
        text(f"""
            SELECT r.text_clean AS text, r.rating, ar.severity,
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
            "date": r.date.isoformat() if r.date else None,
        }
        for r in result.fetchall()
    ]


@router.get("/summary", response_model=InsightResponse)
async def insights_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    pain_only: bool = False,
    status: str = "operational",
):
    counts = await db.execute(
        text("""
            SELECT
                (SELECT COUNT(*) FROM places)          AS total_places,
                (SELECT COUNT(*) FROM reviews)         AS total_reviews,
                (SELECT COUNT(*) FROM analyzed_reviews) AS total_analyzed
        """)
    )
    row = counts.fetchone()
    total_places, total_reviews, total_analyzed = (
        row.total_places, row.total_reviews, row.total_analyzed
    )

    general_filter = pain_filter(pain_only)
    biz_filter = status_filter(status)
    cat_result = await db.execute(
        text(f"""
            SELECT ar.pain_point_category AS category, COUNT(*) AS count
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places p  ON p.id = r.place_id
            WHERE ar.pain_point_category IS NOT NULL
              AND r.text_clean <> ''          -- ตัดรีวิวที่ให้ดาวอย่างเดียว
              {general_filter}
              {biz_filter}
            GROUP BY ar.pain_point_category
            ORDER BY count DESC
            LIMIT 10
        """),
        {"general": GENERAL_CATEGORY},
    )
    top_categories = [
        {"category": r.category, "count": r.count}
        for r in cat_result.fetchall()
    ]

    # การกระจายระดับความรุนแรง — เฉพาะรีวิวเชิงลบ (คำบ่นจริง)
    sev_result = await db.execute(
        text("""
            SELECT severity, COUNT(*) AS count
            FROM analyzed_reviews
            WHERE severity IS NOT NULL AND sentiment = 'negative'
            GROUP BY severity
        """)
    )
    severity_dist = {r.severity: r.count for r in sev_result.fetchall()}

    worst_result = await db.execute(
        text("""
            SELECT p.name AS place_name,
                   COUNT(*) FILTER (WHERE ar.severity = 'high' AND ar.sentiment='negative') AS high_count
            FROM places p
            JOIN reviews r  ON r.place_id = p.id
            JOIN analyzed_reviews ar ON ar.review_id = r.id
            GROUP BY p.id, p.name
            ORDER BY high_count DESC
            LIMIT 10
        """)
    )
    worst_places = [
        {"place_name": r.place_name, "high_count": r.high_count}
        for r in worst_result.fetchall()
    ]

    return {
        "total_places": total_places,
        "total_reviews": total_reviews,
        "total_analyzed": total_analyzed,
        "top_pain_point_categories": top_categories,
        "severity_distribution": severity_dist,
        "worst_places": worst_places,
    }


@router.get("/top-places")
async def top_problematic_places(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 10,
    status: str = "operational",
):
    biz_filter = status_filter(status)
    result = await db.execute(
        text(f"""
            SELECT p.id, p.name,
                   p.overall_rating,
                   COALESCE(p.business_status, 'operational') AS business_status,
                   COUNT(DISTINCT r.id)                                          AS review_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high'   AND ar.sentiment='negative') AS high_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'medium' AND ar.sentiment='negative') AS medium_count
            FROM places p
            JOIN reviews r  ON r.place_id = p.id
            JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE TRUE
              {biz_filter}
            GROUP BY p.id, p.name, p.overall_rating, p.business_status
            ORDER BY high_count DESC, medium_count DESC
            LIMIT :lim
        """),
        {"lim": limit},
    )
    return [dict(row._mapping) for row in result.fetchall()]


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
