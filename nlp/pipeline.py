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

_USE_CLAUDE = bool(
    os.getenv("ANTHROPIC_API_KEY", "")
    and os.getenv("ANTHROPIC_API_KEY") != "your_anthropic_key_here"
)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _load_unanalyzed(session: AsyncSession, batch_size: int) -> list[dict]:
    """Fetch reviews without a matching analyzed_reviews row."""
    result = await session.execute(
        text("""
            SELECT r.id, r.place_id, r.rating, r.text,
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
    reviews = await _load_unanalyzed(session, batch_size)

    if not reviews:
        return {"analyzed": 0, "duration_sec": 0.0}

    analyzed_rows: list[dict] = []

    # -----------------------------------------------------------------------
    # Strategy A: WangchanBERTa sentiment + rule-based categories
    # -----------------------------------------------------------------------
    wangchan_ok = False
    try:
        texts = [preprocess(r["text"])[0] for r in reviews]
        sentiments = analyze_wangchan(texts)
        wangchan_ok = True
    except Exception:
        sentiments = ["neutral"] * len(reviews)

    if wangchan_ok:
        for review, sentiment in zip(reviews, sentiments):
            _, tokens = preprocess(review["text"])
            categories = rule_based_categorize(review["text"])
            analyzed_rows.append({
                "review_id": review["id"],
                "sentiment": sentiment,
                "pain_point_category": categories[0],
                "pain_point_thai": review["text"][:60] + ("..." if len(review["text"]) > 60 else ""),
                "severity": severity_from_rating(review.get("rating")),
                "keywords": tokens[:10],
                "model_used": "wangchanberta+rule-based",
            })
        print(f"[nlp] WangchanBERTa analyzed {len(analyzed_rows)} reviews")

    # -----------------------------------------------------------------------
    # Strategy B: Claude API (used when WangchanBERTa unavailable + API key set)
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

        print(f"[nlp] Claude analyzed {len(analyzed_rows)} reviews")

    # -----------------------------------------------------------------------
    # Strategy C: Pure rule-based (no model, no API key)
    # -----------------------------------------------------------------------
    else:
        for review in reviews:
            analyzed_rows.append(_analyze_rule_based(review))
        print(f"[nlp] Rule-based analyzed {len(analyzed_rows)} reviews")

    inserted = await _save_analyzed(session, analyzed_rows)
    await session.commit()

    duration = round(time() - t0, 1)
    print(f"[nlp] Done — {inserted} new rows in analyzed_reviews ({duration}s)")
    return {"analyzed": inserted, "duration_sec": duration}
