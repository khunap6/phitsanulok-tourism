"""aspects.py — endpoint ชั้นใหม่ที่อ่านจากตาราง review_aspects

ต่างจาก router เดิมอย่างไร
  analysis.py อ่าน analyzed_reviews ซึ่งมี 1 แถว/รีวิว = 1 หมวด
  ไฟล์นี้อ่าน review_aspects ซึ่งมีหลายแถว/รีวิว แถวละหมวดพร้อมอารมณ์ของหมวดนั้น

⚠️ สองหน่วยนับที่ต้องแยกให้ขาด
  "จำนวนรีวิว"        1 รีวิวนับครั้งเดียว — รวมได้ 100% ใช้ overall_sentiment
  "การกล่าวถึง"       1 รีวิวนับได้หลายครั้ง — รวมเกิน 100% ใช้ review_aspects
  ทุก response ของไฟล์นี้ต้องบอกชัดว่าตัวเลขเป็นหน่วยไหน และตัวส่วนคืออะไร
  ไม่งั้นคนอ่านจะเอาสองหน่วยมาเทียบกันแล้วสรุปผิด

⚠️ กฎข้อ 1 ยังใช้เหมือนเดิม
  ตัวตั้งกับตัวส่วนต้องผ่านตัวกรองชุดเดียวกัน ที่นี่จึงคำนวณตัวส่วน
  จาก CTE ชุดเดียวกับตัวตั้งเสมอ ไม่ไปนับแยกคิวรี

⚠️ ตัดรีวิวที่ไม่มีข้อความออกทุกคิวรี (text_clean <> '')
  รีวิวที่ให้ดาวอย่างเดียวไม่ได้แสดงความเห็นเรื่องใดเลย
  ถ้านับรวมจะทำให้ทุกสัดส่วนเพี้ยน (บั๊กเดิมที่เคยพอง 6,021 แถว)
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.filters import (
    CATEGORIES_V2,
    LOW_DATA_THRESHOLD,
    NON_PROBLEM_CATEGORY_IDS,
    aspect_filter,
    category_v2_name,
    date_filter,
    overall_sentiment_filter,
    scope_filter,
    status_filter,
)
from api.schemas.aspects import (
    AspectOverview,
    AspectReviewItem,
    CategorySummaryItem,
    CategorySummaryResponse,
)

router = APIRouter(prefix="/aspects", tags=["aspects"])

# CTE ของ "รีวิวที่เข้าเงื่อนไข" — ทุก endpoint ในไฟล์นี้ใช้ตัวเดียวกัน
# เพื่อให้ตัวตั้งกับตัวส่วนผ่านตัวกรองชุดเดียวกันเสมอ (กฎ 1)
_BASE = """
    SELECT r.id AS review_id, ar.overall_sentiment
      FROM reviews r
      JOIN places p ON p.id = r.place_id
      JOIN analyzed_reviews ar ON ar.review_id = r.id
     WHERE r.text_clean <> ''
       {zone} {biz} {date}
"""


def _base_sql(zone: str | None, status: str, date_from, date_to):
    # ⚠️ ต่อตัวกรองขอบเขตงานวิจัยเข้าไปด้วยเสมอ ดู api/filters.scope_filter
    biz = status_filter(status, "p") + scope_filter("in", "p")
    date_sql, params = date_filter(date_from, date_to, "r")
    zone_sql = ""
    if zone:
        zone_sql = "AND COALESCE(p.zone, 'other') = :zone"
        params["zone"] = zone
    return _BASE.format(zone=zone_sql, biz=biz, date=date_sql), params


@router.get("/summary", response_model=CategorySummaryResponse)
async def category_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    zone: str | None = None,
    status: str = "operational",
    date_from: str | None = None,
    date_to: str | None = None,
):
    """สรุปรายหมวด — กี่รีวิวพูดถึงหมวดนี้ และพูดถึงด้วยอารมณ์ไหน

    n_reviews   = จำนวน "รีวิว" ที่พูดถึงหมวดนี้ (1 รีวิวนับครั้งเดียวต่อหมวด)
    share       = n_reviews / จำนวนรีวิวทั้งหมดในช่วงที่เลือก
                  ⚠️ ผลรวม share ของทุกหมวด "เกิน 100%" เพราะ 1 รีวิวอยู่ได้หลายหมวด
                  นี่คือพฤติกรรมที่ถูกต้อง ไม่ใช่บั๊ก
    low_data    = n_reviews < เกณฑ์ใน shared/categories.json (ตอนนี้ 10)
                  แสดงผลได้แต่ไม่ควรนำไปสรุปเชิงสถิติ
    """
    base, params = _base_sql(zone, status, date_from, date_to)
    rows = (await db.execute(text(f"""
        WITH base AS ({base}), tot AS (SELECT count(*) AS n FROM base)
        SELECT ra.category_id,
               count(*)                                                    AS n_reviews,
               count(*) FILTER (WHERE ra.aspect_sentiment = 'positive')    AS n_pos,
               count(*) FILTER (WHERE ra.aspect_sentiment = 'neutral')     AS n_neu,
               count(*) FILTER (WHERE ra.aspect_sentiment = 'negative')    AS n_neg,
               count(*) FILTER (WHERE ra.is_primary)                       AS n_primary,
               count(*) FILTER (WHERE ra.is_primary
                                  AND ra.aspect_sentiment = 'positive')     AS np_pos,
               count(*) FILTER (WHERE ra.is_primary
                                  AND ra.aspect_sentiment = 'neutral')      AS np_neu,
               count(*) FILTER (WHERE ra.is_primary
                                  AND ra.aspect_sentiment = 'negative')     AS np_neg,
               (SELECT n FROM tot)                                         AS total
          FROM review_aspects ra
          JOIN base b ON b.review_id = ra.review_id
         GROUP BY ra.category_id
         ORDER BY n_reviews DESC
    """), params)).fetchall()

    total = rows[0].total if rows else 0
    items = []
    for r in rows:
        items.append(CategorySummaryItem(
            category_id=r.category_id,
            category_name=category_v2_name(r.category_id) or str(r.category_id),
            n_reviews=r.n_reviews,
            n_positive=r.n_pos,
            n_neutral=r.n_neu,
            n_negative=r.n_neg,
            share_of_reviews=(r.n_reviews / total) if total else 0.0,
            negative_rate=(r.n_neg / r.n_reviews) if r.n_reviews else 0.0,
            n_primary=r.n_primary,
            share_as_primary=(r.n_primary / total) if total else 0.0,
            np_positive=r.np_pos, np_neutral=r.np_neu, np_negative=r.np_neg,
            low_data=r.n_reviews < LOW_DATA_THRESHOLD,
            is_non_problem=r.category_id in NON_PROBLEM_CATEGORY_IDS,
        ))
    return CategorySummaryResponse(
        items=items,
        total_reviews=total,
        total_mentions=sum(i.n_reviews for i in items),
        total_primary=sum(i.n_primary for i in items),
        low_data_threshold=LOW_DATA_THRESHOLD,
        denominator_note=(
            "share_of_reviews หารด้วยจำนวนรีวิวทั้งหมดในช่วงที่เลือก "
            "ไม่ใช่หารด้วยผลรวมของทุกหมวด — 1 รีวิวพูดถึงได้หลายหมวด "
            "ผลรวมรายหมวดจึงมากกว่าจำนวนรีวิวทั้งหมด"),
    )


@router.get("/overview", response_model=AspectOverview)
async def overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    zone: str | None = None,
    status: str = "operational",
    date_from: str | None = None,
    date_to: str | None = None,
):
    """ตัวเลขภาพรวมสองหน่วย ให้หน้าเว็บเอาไปติดป้ายแยกกันได้

    ระดับรีวิว  : positive/neutral/negative รวมได้ 100% (ใช้ overall_sentiment)
    ระดับการกล่าวถึง : รวมเกิน 100% (ใช้ review_aspects)
    """
    base, params = _base_sql(zone, status, date_from, date_to)
    r = (await db.execute(text(f"""
        WITH base AS ({base})
        SELECT count(*)                                                  AS n_reviews,
               count(*) FILTER (WHERE overall_sentiment = 'positive')    AS n_pos,
               count(*) FILTER (WHERE overall_sentiment = 'neutral')     AS n_neu,
               count(*) FILTER (WHERE overall_sentiment = 'negative')    AS n_neg,
               (SELECT count(*) FROM review_aspects ra
                 JOIN base b2 ON b2.review_id = ra.review_id)            AS n_mentions,
               (SELECT count(*) FROM review_aspects ra
                 JOIN base b3 ON b3.review_id = ra.review_id
                WHERE ra.aspect_sentiment = 'negative')                  AS n_mention_neg
          FROM base
    """), params)).fetchone()
    n = r.n_reviews or 0
    return AspectOverview(
        total_reviews=n,
        reviews_positive=r.n_pos, reviews_neutral=r.n_neu,
        reviews_negative=r.n_neg,
        complaint_rate=(r.n_neg / n) if n else 0.0,
        total_mentions=r.n_mentions,
        mentions_negative=r.n_mention_neg,
        mentions_per_review=(r.n_mentions / n) if n else 0.0,
        unit_note=("ตัวเลขระดับรีวิวรวมได้ 100% ส่วนตัวเลขระดับการกล่าวถึง "
                   "รวมเกิน 100% เพราะ 1 รีวิวพูดถึงได้หลายหมวด "
                   "ห้ามนำสองหน่วยมาเทียบกันตรง ๆ"),
    )


@router.get("/reviews", response_model=list[AspectReviewItem])
async def aspect_reviews(
    db: Annotated[AsyncSession, Depends(get_db)],
    category_id: int | None = None,
    aspect_sentiment: str | None = Query(None, pattern="^(positive|neutral|negative)$"),
    view_mode: str = "all",
    zone: str | None = None,
    status: str = "operational",
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(30, ge=1, le=200),
):
    """รีวิวที่พูดถึงหมวดหนึ่งด้วยอารมณ์หนึ่ง — ใช้ตอนคลิกแท่งกราฟเพื่อกรอง

    ⚠️ คืนได้สูงสุด limit รายการ (default 30) หน้าเว็บต้องบอกผู้ใช้ว่า
      นี่คือตัวอย่าง ไม่ใช่ทั้งหมด ไม่งั้นจะเข้าใจว่ามีแค่นี้
    """
    base, params = _base_sql(zone, status, date_from, date_to)
    where = aspect_filter(view_mode, "ra")
    if category_id is not None:
        where += " AND ra.category_id = :cid"
        params["cid"] = category_id
    if aspect_sentiment:
        where += " AND ra.aspect_sentiment = :asp"
        params["asp"] = aspect_sentiment
    params["lim"] = limit
    rows = (await db.execute(text(f"""
        WITH base AS ({base})
        SELECT r.id            AS review_id,
               r.text_clean    AS text,
               r.rating,
               r.review_date        AS review_date_text,
               r.review_date_approx AS review_date,
               p.name          AS place_name,
               ra.category_id,
               ra.aspect_sentiment,
               ra.is_primary,
               b.overall_sentiment
          FROM review_aspects ra
          JOIN base b    ON b.review_id = ra.review_id
          JOIN reviews r ON r.id = ra.review_id
          JOIN places p  ON p.id = r.place_id
         WHERE TRUE {where}
         ORDER BY r.review_date_approx DESC NULLS LAST, r.id DESC
         LIMIT :lim
    """), params)).fetchall()
    return [AspectReviewItem(
        review_id=r.review_id, text=r.text, rating=r.rating,
        review_date=r.review_date, review_date_text=r.review_date_text,
        place_name=r.place_name,
        category_id=r.category_id,
        category_name=category_v2_name(r.category_id) or str(r.category_id),
        aspect_sentiment=r.aspect_sentiment, is_primary=r.is_primary,
        overall_sentiment=r.overall_sentiment,
    ) for r in rows]


@router.get("/categories")
async def list_categories():
    """รายชื่อหมวด v2 ทั้งหมด — ให้หน้าเว็บทำดรอปดาวน์โดยไม่ต้องถือสำเนา"""
    return {
        "categories": CATEGORIES_V2,
        "non_problem_ids": NON_PROBLEM_CATEGORY_IDS,
        "low_data_threshold": LOW_DATA_THRESHOLD,
    }
