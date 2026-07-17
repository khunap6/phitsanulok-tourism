import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
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

LDA_RESULT_PATH = Path(__file__).parent.parent.parent / "data" / "lda_output" / "lda_result.json"


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
                COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high')   AS high_count,
                COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'medium') AS medium_count,
                COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'low')    AS low_count,
                MODE() WITHIN GROUP (ORDER BY ar.pain_point_category) AS top_category
            FROM places p
            LEFT JOIN reviews r  ON r.place_id = p.id
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            GROUP BY COALESCE(p.zone, 'other')
            ORDER BY analyzed_count DESC
        """)
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
async def zone_pain_points(zone: str, db: Annotated[AsyncSession, Depends(get_db)]):
    """Pain point categories ของโซนที่เลือก"""
    result = await db.execute(
        text("""
            SELECT ar.pain_point_category AS category, COUNT(*) AS count
            FROM analyzed_reviews ar
            JOIN reviews r  ON r.id = ar.review_id
            JOIN places p   ON p.id = r.place_id
            WHERE COALESCE(p.zone, 'other') = :zone
              AND ar.pain_point_category IS NOT NULL
            GROUP BY ar.pain_point_category
            ORDER BY count DESC
            LIMIT 10
        """),
        {"zone": zone},
    )
    return [{"category": r.category, "count": r.count} for r in result.fetchall()]


@router.get("/zones/{zone}/breakdown")
async def zone_breakdown(zone: str, db: Annotated[AsyncSession, Depends(get_db)]):
    """Pain point แยกตามประเภทสถานที่ภายในโซน (คาเฟ่ / ร้านอาหาร / สถานที่ท่องเที่ยว)"""

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

    # ดึงสถานที่ + รีวิวในโซนนี้
    places_result = await db.execute(
        text("""
            SELECT p.id, p.name, p.google_category,
                   COUNT(DISTINCT r.id)  AS review_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high')   AS high_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'medium') AS medium_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'low')    AS low_count
            FROM places p
            LEFT JOIN reviews r  ON r.place_id = p.id
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE COALESCE(p.zone, 'other') = :zone
            GROUP BY p.id, p.name, p.google_category
            ORDER BY high_count DESC
        """),
        {"zone": zone},
    )
    places = places_result.fetchall()

    # Pain points ต่อสถานที่
    pain_result = await db.execute(
        text("""
            SELECT p.name AS place_name,
                   ar.pain_point_category AS category,
                   COUNT(*) AS cnt
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places p  ON p.id = r.place_id
            WHERE COALESCE(p.zone, 'other') = :zone
              AND ar.pain_point_category IS NOT NULL
            GROUP BY p.name, ar.pain_point_category
        """),
        {"zone": zone},
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


@router.get("/lda-topics")
async def lda_topics():
    """คืนผลลัพธ์ LDA Topic Modeling จากไฟล์ที่รันไว้"""
    if not LDA_RESULT_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="ยังไม่มีผล LDA — รัน: uv run python scripts/topic_model_lda.py ก่อน"
        )
    with open(LDA_RESULT_PATH, encoding="utf-8") as f:
        return json.load(f)


@router.get("/summary", response_model=InsightResponse)
async def insights_summary(db: Annotated[AsyncSession, Depends(get_db)]):
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

    cat_result = await db.execute(
        text("""
            SELECT pain_point_category AS category, COUNT(*) AS count
            FROM analyzed_reviews
            WHERE pain_point_category IS NOT NULL
            GROUP BY pain_point_category
            ORDER BY count DESC
            LIMIT 10
        """)
    )
    top_categories = [
        {"category": r.category, "count": r.count}
        for r in cat_result.fetchall()
    ]

    sev_result = await db.execute(
        text("""
            SELECT severity, COUNT(*) AS count
            FROM analyzed_reviews
            WHERE severity IS NOT NULL
            GROUP BY severity
        """)
    )
    severity_dist = {r.severity: r.count for r in sev_result.fetchall()}

    worst_result = await db.execute(
        text("""
            SELECT p.name AS place_name,
                   COUNT(*) FILTER (WHERE ar.severity = 'high') AS high_count
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
):
    result = await db.execute(
        text("""
            SELECT p.id, p.name,
                   p.overall_rating,
                   COUNT(DISTINCT r.id)                                          AS review_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high')    AS high_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'medium')  AS medium_count
            FROM places p
            JOIN reviews r  ON r.place_id = p.id
            JOIN analyzed_reviews ar ON ar.review_id = r.id
            GROUP BY p.id, p.name, p.overall_rating
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
            SELECT pain_point_category AS category, COUNT(*) AS count
            FROM analyzed_reviews
            WHERE pain_point_category IS NOT NULL
            GROUP BY pain_point_category
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
