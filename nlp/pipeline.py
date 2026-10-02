"""
pipeline.py — NLP orchestration (A → B → C → DB)
Reads unanalyzed reviews, runs preprocessing + sentiment + topic, writes analyzed_reviews.
"""

import os
from collections import defaultdict
from time import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nlp.preprocessor import preprocess
from nlp.sentiment import analyze_wangchan, analyze_claude
from nlp.topic_model import rule_based_categorize, severity_from_rating
from nlp import wangchan_classifier

_USE_CLAUDE = bool(
    os.getenv("ANTHROPIC_API_KEY", "")
    and os.getenv("ANTHROPIC_API_KEY") != "your_anthropic_key_here"
)

# หมวดที่ไม่ใช่ปัญหา — ไม่ตั้ง severity (severity มีความหมายเฉพาะกับคำบ่น)
_NON_PROBLEM_CATS = {"ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)", "อื่นๆ", "ไม่มี"}


def _severity_for(sentiment: str, category: str, rating: int | None) -> str:
    """
    severity มีความหมายเฉพาะรีวิวเชิงลบที่เป็นปัญหาจริง
    - ไม่ใช่คำบ่น หรือเป็นหมวดที่ไม่ใช่ปัญหา → 'low' (ไม่รุนแรง)
    - คำบ่น → ประเมินจากดาว (1★=high, 2★=medium, 3-5★=low)
    """
    if sentiment != "negative" or category in _NON_PROBLEM_CATS:
        return "low"
    return severity_from_rating(rating)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _load_unanalyzed(session: AsyncSession, batch_size: int) -> list[dict]:
    """Fetch reviews without a matching analyzed_reviews row."""
    # ⚠️ ต้องใช้ r.text_clean ไม่ใช่ r.text
    #
    # r.text คือข้อความดิบจากหน้าเว็บ มีขยะปนอยู่: ชื่อคนรีวิว, "Local Guide · 536
    # รีวิว · 2,957 รูปภาพ", วันที่สัมพัทธ์ ("3 ปีที่แล้ว"), ปุ่ม "ชอบ"/"แชร์",
    # "คำตอบจากเจ้าของ" และป้ายคะแนนย่อยของ Google ("อาหาร: 5  บริการ: 5  บรรยากาศ: 5")
    #
    # บั๊กนี้เคยทำให้ (วัดเมื่อ 2026-09-26):
    #   - keywords 32% มีคำว่า "ชอบ" / 29% มีคำว่า "แชร์" / 49% มีคำว่า "ปี"
    #     ทั้งที่ไม่มีคำเหล่านั้นใน text_clean เลย
    #   - หมวด pain point เพี้ยน 5.9% — "ราคาและความคุ้มค่า" พองเกินจริง 18%,
    #     "การบริการและเจ้าหน้าที่" 11%, "การเดินทางและที่จอดรถ" 6%
    #     (เพราะป้าย "บริการ: 5" ถูกนับเป็นคำบ่นเรื่องบริการ)
    #   - รีวิวที่ให้ดาวอย่างเดียว (ไม่มีข้อความ) 3,494 แถว ถูกติดป้าย pain point
    #     จากคำในป้าย UI ทั้งที่ผู้รีวิวไม่ได้เขียนอะไรเลย
    #
    # scripts/reanalyze_all.py ใช้ text_clean ถูกต้องอยู่แล้ว — บั๊กอยู่เฉพาะ
    # เส้นทาง incremental นี้ (analyze.py / auto_refresh เรียกตัวนี้)
    #
    # ยังคงดึงรีวิวที่ text_clean ว่างมาด้วย (ไม่กรองออก) เพราะถ้าข้ามไป
    # _load_unanalyzed จะหยิบมันมาซ้ำทุกครั้งไม่จบ — จัดการที่ปลายทางแทน
    # โดยบันทึกแถวที่ pain_point_category = NULL (ดู _empty_row)
    result = await session.execute(
        text("""
            SELECT r.id, r.place_id, r.rating,
                   COALESCE(r.text_clean, '') AS text,
                   p.name AS place_name
            FROM reviews r
            JOIN places p ON p.id = r.place_id
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE ar.id IS NULL
            ORDER BY r.id
            LIMIT :lim
        """),
        {"lim": batch_size},
    )
    return [
        {
            "id": row.id,
            "place_id": row.place_id,
            "rating": row.rating,
            "text": row.text,
            "place_name": row.place_name,
        }
        for row in result.fetchall()
    ]


async def _save_analyzed(session: AsyncSession, rows: list[dict]) -> int:
    """Insert analyzed results; skip existing via ON CONFLICT DO NOTHING."""
    inserted = 0
    for row in rows:
        rv = await session.execute(
            text("""
                INSERT INTO analyzed_reviews
                    (review_id, sentiment, pain_point_category, pain_point_thai,
                     severity, keywords, model_used)
                VALUES
                    (:review_id, :sentiment, :category, :pain_point_thai,
                     :severity, :keywords, :model_used)
                ON CONFLICT (review_id) DO NOTHING
            """),
            {
                "review_id": row["review_id"],
                "sentiment": row["sentiment"],
                "category": row["pain_point_category"],
                "pain_point_thai": row["pain_point_thai"],
                "severity": row["severity"],
                "keywords": row["keywords"],
                "model_used": row["model_used"],
            },
        )
        if rv.rowcount > 0:
            inserted += 1
    await session.flush()
    return inserted


# ---------------------------------------------------------------------------
# Single-review analysis (rule-based + optional WangchanBERTa)
# ---------------------------------------------------------------------------

def _sentiment_from_rating(rating: int | None) -> str:
    """ประเมิน sentiment จากดาว (ใช้เมื่อไม่มีโมเดล)"""
    if rating is None:
        return "neutral"
    if rating >= 4:
        return "positive"
    if rating == 3:
        return "neutral"
    return "negative"  # 1-2 ดาว


def _empty_row(review: dict) -> dict:
    """
    แถวสำหรับรีวิวที่ให้ดาวอย่างเดียว (ไม่มีข้อความหลังล้าง)

    ต้องบันทึกแถวไว้ ไม่ใช่ข้ามไป เพราะ _load_unanalyzed หยิบ "รีวิวที่ยังไม่มีแถว
    ใน analyzed_reviews" ถ้าข้ามจะถูกหยิบมาซ้ำทุกครั้งไม่จบ

    pain_point_category = NULL โดยเจตนา — ไม่มีข้อความก็ไม่มีทางรู้ว่าติเรื่องอะไร
    เดิมโค้ดใส่หมวดให้จากคำในป้าย UI ที่ติดมากับข้อความดิบ ("บริการ: 5" -> หมวดบริการ)
    ทำให้ 3,494 แถวมีหมวดทั้งที่ผู้รีวิวไม่ได้เขียนอะไร

    sentiment ยังประเมินจากดาวได้ เพราะดาวเป็นข้อมูลจริงที่ผู้รีวิวให้มา
    """
    rating = review.get("rating")
    return {
        "review_id": review["id"],
        "sentiment": _sentiment_from_rating(rating),
        "pain_point_category": None,
        "pain_point_thai": None,
        "severity": severity_from_rating(rating),
        "keywords": [],
        "model_used": "rating-only",
    }


def _analyze_rule_based(review: dict) -> dict:
    """Fallback: rule-based category + severity from rating."""
    _, tokens = preprocess(review["text"])
    categories = rule_based_categorize(review["text"])
    rating = review.get("rating")
    return {
        "review_id": review["id"],
        "sentiment": _sentiment_from_rating(rating),
        "pain_point_category": categories[0],
        "pain_point_thai": review["text"][:60] + ("..." if len(review["text"]) > 60 else ""),
        "severity": severity_from_rating(rating),
        "keywords": tokens[:10],
        "model_used": "rule-based",
    }


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

async def run_analysis(
    session: AsyncSession,
    batch_size: int = 20,
) -> dict:
    """
    Read up to batch_size unanalyzed reviews → analyze → write to analyzed_reviews.
    Returns {"analyzed": int, "duration_sec": float}
    """
    t0 = time()
    all_reviews = await _load_unanalyzed(session, batch_size)

    if not all_reviews:
        return {"analyzed": 0, "duration_sec": 0.0}

    # แยกรีวิวที่ให้ดาวอย่างเดียวออกก่อนเข้าโมเดล — ไม่มีข้อความก็ไม่มีอะไรให้วิเคราะห์
    # และห้ามให้โมเดลเดาหมวดจากสตริงว่าง (เดิมส่ง text ดิบเข้าไปจึงได้หมวดจากขยะ)
    reviews = [r for r in all_reviews if (r["text"] or "").strip()]
    rating_only = [r for r in all_reviews if not (r["text"] or "").strip()]

    analyzed_rows: list[dict] = [_empty_row(r) for r in rating_only]
    if rating_only:
        print(f"[nlp] รีวิวให้ดาวอย่างเดียว {len(rating_only)} อัน "
              f"— บันทึกโดยไม่ระบุหมวด")

    if not reviews:
        saved = await _save_analyzed(session, analyzed_rows)
        return {"analyzed": saved, "duration_sec": round(time() - t0, 2)}

    # -----------------------------------------------------------------------
    # Strategy A: WangchanBERTa ที่ fine-tune เองแล้ว (อารมณ์ + หมวดหมู่)
    # โมเดลนี้ทำทั้ง 2 งาน แทน rule-based เดิมที่จับได้แค่ 1% ของหมวด
    # -----------------------------------------------------------------------
    wangchan_results = None
    if wangchan_classifier.is_available():
        texts = [r["text"] for r in reviews]
        try:
            wangchan_results = wangchan_classifier.classify(texts)
        except Exception as e:
            print(f"[nlp] WangchanBERTa classify ล้มเหลว: {str(e)[:80]}")
            wangchan_results = None

    if wangchan_results:
        for review, res in zip(reviews, wangchan_results):
            _, tokens = preprocess(review["text"])
            sentiment = res["sentiment"]
            category = res["category"]
            analyzed_rows.append({
                "review_id": review["id"],
                "sentiment": sentiment,
                "pain_point_category": category,
                "pain_point_thai": review["text"][:60] + ("..." if len(review["text"]) > 60 else ""),
                "severity": _severity_for(sentiment, category, review.get("rating")),
                "keywords": tokens[:10],
                "model_used": "wangchanberta-finetuned",
            })
        print(f"[nlp] WangchanBERTa (fine-tuned) analyzed {len(reviews)} reviews")

    # -----------------------------------------------------------------------
    # Strategy B: Claude API (ใช้เมื่อโมเดล WangchanBERTa ไม่พร้อม + มี API key)
    # -----------------------------------------------------------------------
    elif _USE_CLAUDE:
        by_place: dict[str, list[dict]] = defaultdict(list)
        for r in reviews:
            by_place[r["place_name"]].append(r)

        for place_name, place_reviews in by_place.items():
            for i in range(0, len(place_reviews), 5):
                batch = place_reviews[i : i + 5]
                claude_results = analyze_claude(batch, place_name)

                if claude_results:
                    for j, cr in enumerate(claude_results):
                        if j >= len(batch):
                            break
                        review = batch[j]
                        cr = cr or {}
                        # ใช้ (x or default) กัน None: ถ้า Claude คืน null field
                        # .get(key, default) จะคืน None (ไม่ใช่ default) → slice พัง
                        kw = cr.get("keywords")
                        kw = kw[:10] if isinstance(kw, list) else []
                        analyzed_rows.append({
                            "review_id": review["id"],
                            "sentiment": cr.get("sentiment") or "neutral",
                            "pain_point_category": cr.get("pain_point_category") or "อื่นๆ",
                            "pain_point_thai": (cr.get("pain_point_thai") or "")[:200],
                            "severity": cr.get("severity") or "medium",
                            "keywords": kw,
                            "model_used": "claude-haiku-4-5-20251001",
                        })
                else:
                    # Claude failed → rule-based for this batch
                    for review in batch:
                        analyzed_rows.append(_analyze_rule_based(review))

        print(f"[nlp] Claude analyzed {len(reviews)} reviews")

    # -----------------------------------------------------------------------
    # Strategy C: Pure rule-based (no model, no API key)
    # -----------------------------------------------------------------------
    else:
        for review in reviews:
            analyzed_rows.append(_analyze_rule_based(review))
        print(f"[nlp] Rule-based analyzed {len(reviews)} reviews")

    inserted = await _save_analyzed(session, analyzed_rows)
    await session.commit()

    duration = round(time() - t0, 1)
    print(f"[nlp] Done — {inserted} new rows in analyzed_reviews ({duration}s)")
    return {"analyzed": inserted, "duration_sec": duration}
