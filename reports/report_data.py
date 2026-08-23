"""
report_data.py — รวบรวมข้อมูลสำหรับรายงานประจำเดือน

แยกส่วน "ดึงข้อมูล" ออกจาก "จัดรูปแบบ" เพื่อให้ PDF และ Word ใช้ข้อมูลชุดเดียวกัน
"""
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# หมวดที่ไม่ใช่ปัญหา — ไม่นับในรายงาน
NON_PROBLEM = ["ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)", "อื่นๆ", "ไม่มี"]
_NP_IN = ", ".join("'" + c.replace("'", "''") + "'" for c in NON_PROBLEM)

TH_MONTH = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
            "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]

ZONE_LABEL = {
    "naresuan": "รอบ ม.นเรศวร", "rajabhat": "รอบ ม.ราชภัฏ",
    "city_center": "ตัวเมือง", "other": "อื่นๆ พิษณุโลก",
}


def month_range(year: int, month: int) -> tuple[date, date]:
    """คืน (วันแรก, วันสุดท้าย) ของเดือนนั้น"""
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end


def thai_month_label(year: int, month: int) -> str:
    return f"{TH_MONTH[month - 1]} {year + 543}"


@dataclass
class ReportData:
    year: int
    month: int
    period_label: str
    generated_at: str
    # ภาพรวม
    total_places: int = 0
    reviews_in_month: int = 0
    complaints_in_month: int = 0
    praise_in_month: int = 0
    # เทียบเดือนก่อน
    prev_complaints: int = 0
    complaint_delta: int = 0
    # ตาราง
    top_problems: list[dict] = field(default_factory=list)
    severity: dict = field(default_factory=dict)
    zones: list[dict] = field(default_factory=list)
    worst_places: list[dict] = field(default_factory=list)
    highlights: list[dict] = field(default_factory=list)
    sample_reviews: list[dict] = field(default_factory=list)

    @property
    def has_data(self) -> bool:
        return self.reviews_in_month > 0


async def collect(session: AsyncSession, year: int, month: int) -> ReportData:
    start, end = month_range(year, month)
    p = {"start": start, "end": end}
    # ช่วงเดือนก่อนหน้า (ไว้เทียบแนวโน้ม)
    pm_y, pm_m = (year - 1, 12) if month == 1 else (year, month - 1)
    pstart, pend = month_range(pm_y, pm_m)

    from datetime import datetime
    data = ReportData(
        year=year, month=month,
        period_label=thai_month_label(year, month),
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"),
    )

    # ── ภาพรวม ──
    r = await session.execute(
        text(f"""
            SELECT
              (SELECT COUNT(*) FROM places) AS total_places,
              COUNT(*) AS reviews,
              COUNT(*) FILTER (WHERE ar.sentiment = 'negative') AS complaints,
              COUNT(*) FILTER (WHERE ar.sentiment = 'positive') AS praise
            FROM reviews r
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE r.review_date_approx >= :start AND r.review_date_approx < :end
        """), p)
    row = r.fetchone()
    data.total_places = row.total_places
    data.reviews_in_month = row.reviews or 0
    data.complaints_in_month = row.complaints or 0
    data.praise_in_month = row.praise or 0

    r = await session.execute(
        text("""
            SELECT COUNT(*) FROM reviews r
            JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE ar.sentiment = 'negative'
              AND r.review_date_approx >= :s AND r.review_date_approx < :e
        """), {"s": pstart, "e": pend})
    data.prev_complaints = r.scalar() or 0
    data.complaint_delta = data.complaints_in_month - data.prev_complaints

    # ── Top ปัญหา + เทียบเดือนก่อน ──
    r = await session.execute(
        text(f"""
            SELECT ar.pain_point_category AS category,
                   COUNT(*) AS cnt,
                   COUNT(*) FILTER (WHERE ar.severity = 'high') AS high,
                   (SELECT COUNT(*) FROM analyzed_reviews a2
                      JOIN reviews r2 ON r2.id = a2.review_id
                     WHERE a2.pain_point_category = ar.pain_point_category
                       AND a2.sentiment = 'negative'
                       AND r2.review_date_approx >= :pstart
                       AND r2.review_date_approx < :pend) AS prev_cnt
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            WHERE ar.sentiment = 'negative' AND r.text_clean <> ''
              AND ar.pain_point_category NOT IN ({_NP_IN})
              AND r.review_date_approx >= :start AND r.review_date_approx < :end
            GROUP BY ar.pain_point_category
            ORDER BY cnt DESC LIMIT 8
        """), {**p, "pstart": pstart, "pend": pend})
    total_c = data.complaints_in_month or 1
    data.top_problems = [
        {"category": x.category, "count": x.cnt, "high": x.high,
         "pct": round(x.cnt / total_c * 100, 1),
         "prev": x.prev_cnt, "delta": x.cnt - x.prev_cnt}
        for x in r.fetchall()
    ]

    # ── ระดับความรุนแรง ──
    r = await session.execute(
        text("""
            SELECT ar.severity AS sev, COUNT(*) AS cnt
            FROM analyzed_reviews ar JOIN reviews r ON r.id = ar.review_id
            WHERE ar.sentiment = 'negative'
              AND r.review_date_approx >= :start AND r.review_date_approx < :end
            GROUP BY ar.severity
        """), p)
    data.severity = {x.sev: x.cnt for x in r.fetchall() if x.sev}

    # ── แยกโซน ──
    r = await session.execute(
        text(f"""
            SELECT COALESCE(pl.zone,'other') AS zone,
                   COUNT(*) FILTER (WHERE ar.sentiment='negative') AS complaints,
                   COUNT(*) FILTER (WHERE ar.sentiment='positive') AS praise,
                   MODE() WITHIN GROUP (ORDER BY ar.pain_point_category)
                     FILTER (WHERE ar.sentiment='negative'
                             AND ar.pain_point_category NOT IN ({_NP_IN})) AS top_cat
            FROM reviews r
            JOIN places pl ON pl.id = r.place_id
            JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE r.review_date_approx >= :start AND r.review_date_approx < :end
            GROUP BY COALESCE(pl.zone,'other')
            ORDER BY complaints DESC
        """), p)
    data.zones = [
        {"zone": ZONE_LABEL.get(x.zone, x.zone), "complaints": x.complaints,
         "praise": x.praise, "top_category": x.top_cat or "—"}
        for x in r.fetchall()
    ]

    # ── ร้านที่ถูกบ่นมากสุด ──
    r = await session.execute(
        text(f"""
            SELECT pl.name, COALESCE(pl.zone,'other') AS zone,
                   COUNT(*) AS complaints,
                   COUNT(*) FILTER (WHERE ar.severity='high') AS high,
                   MODE() WITHIN GROUP (ORDER BY ar.pain_point_category)
                     FILTER (WHERE ar.pain_point_category NOT IN ({_NP_IN})) AS top_cat
            FROM reviews r
            JOIN places pl ON pl.id = r.place_id
            JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE ar.sentiment = 'negative' AND r.text_clean <> ''
              AND r.review_date_approx >= :start AND r.review_date_approx < :end
            GROUP BY pl.id, pl.name, pl.zone
            ORDER BY complaints DESC, high DESC LIMIT 10
        """), p)
    data.worst_places = [
        {"name": x.name, "zone": ZONE_LABEL.get(x.zone, x.zone),
         "complaints": x.complaints, "high": x.high, "top_category": x.top_cat or "—"}
        for x in r.fetchall()
    ]

    # ── จุดเด่น (คำชม) ──
    r = await session.execute(
        text(f"""
            SELECT ar.pain_point_category AS category, COUNT(*) AS cnt
            FROM analyzed_reviews ar JOIN reviews r ON r.id = ar.review_id
            WHERE ar.sentiment = 'positive' AND r.text_clean <> ''
              AND ar.pain_point_category NOT IN ({_NP_IN})
              AND r.review_date_approx >= :start AND r.review_date_approx < :end
            GROUP BY ar.pain_point_category ORDER BY cnt DESC LIMIT 5
        """), p)
    data.highlights = [{"category": x.category, "count": x.cnt} for x in r.fetchall()]

    # ── ตัวอย่างรีวิวปัญหาเด่น ──
    if data.top_problems:
        # DISTINCT ON (text_clean) — กันรีวิวเดียวกันโผล่ซ้ำ
        # (ในฐานข้อมูลมีรีวิวซ้ำจากการ scrape หลายรอบ เพราะ hash เดิมรวมข้อความวันที่ไว้ด้วย)
        r = await session.execute(
            text("""
                SELECT * FROM (
                    SELECT DISTINCT ON (r.text_clean)
                           pl.name AS place, r.rating, r.text_clean AS review,
                           CASE ar.severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END AS sev_rank
                    FROM analyzed_reviews ar
                    JOIN reviews r ON r.id = ar.review_id
                    JOIN places pl ON pl.id = r.place_id
                    WHERE ar.sentiment = 'negative' AND ar.pain_point_category = :cat
                      AND r.text_clean <> ''
                      AND r.review_date_approx >= :start AND r.review_date_approx < :end
                    ORDER BY r.text_clean, sev_rank
                ) q
                ORDER BY q.sev_rank
                LIMIT 5
            """), {**p, "cat": data.top_problems[0]["category"]})
        data.sample_reviews = [
            {"place": x.place, "rating": x.rating, "text": (x.review or "")[:220]}
            for x in r.fetchall()
        ]

    return data
