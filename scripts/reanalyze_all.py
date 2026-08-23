"""
reanalyze_all.py — วิเคราะห์รีวิวทั้งหมดใหม่ด้วย WangchanBERTa ที่ fine-tune เอง

ทำไม:
  ก่อนหน้านี้ 54% ของข้อมูลวิเคราะห์ด้วย rule-based (ดูแค่ดาว/จับคำ)
  ตอนนี้มีโมเดล WangchanBERTa ที่ฝึกเองแล้ว (อารมณ์ F1 0.71, หมวดหมู่ F1 0.60)
  → วิเคราะห์ใหม่ทั้งระบบให้สม่ำเสมอด้วยโมเดลเดียว

ปลอดภัย:
  - claude_category / claude_sentiment (ผลของ Claude) ไม่ถูกแตะ — เก็บไว้เทียบใน thesis
  - แนะนำ backup ก่อนรัน (สคริปต์เตือนให้)

รัน:
  uv run python scripts/reanalyze_all.py            # ดูก่อนว่าจะทำกี่รีวิว (ไม่แตะข้อมูล)
  uv run python scripts/reanalyze_all.py --apply    # วิเคราะห์ใหม่จริง
"""
import argparse
import asyncio
import time

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from nlp import wangchan_classifier
from nlp.pipeline import _severity_for
from nlp.preprocessor import preprocess

BATCH = 256   # GPU รับได้สบาย


def safe_print(t: str) -> None:
    try:
        print(t, flush=True)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"), flush=True)


async def load_all(session) -> list[dict]:
    """ทุกรีวิวที่มีเนื้อความ (ให้ดาวอย่างเดียวข้าม — โมเดลจัดหมวดไม่ได้)"""
    r = await session.execute(
        text("""
            SELECT r.id, r.rating, r.text_clean AS text
            FROM reviews r
            WHERE r.text_clean <> ''
            ORDER BY r.id
        """)
    )
    return [{"id": x.id, "rating": x.rating, "text": x.text} for x in r.fetchall()]


async def main(apply: bool) -> None:
    if not wangchan_classifier.is_available():
        safe_print("❌ โมเดล WangchanBERTa ยังไม่พร้อม — ฝึกก่อนด้วย nlp/train/train.py")
        return

    async with AsyncSessionLocal() as session:
        reviews = await load_all(session)
        safe_print(f"รีวิวที่จะวิเคราะห์ใหม่: {len(reviews):,} (เฉพาะที่มีเนื้อความ)")

        if not apply:
            safe_print("\n⚠️  โหมดดูอย่างเดียว — ยังไม่แตะข้อมูล")
            safe_print("   ⚠️  ควร backup ก่อน! ดูคำสั่งใน run_commands.ps1 (BACKUP)")
            safe_print("   วิเคราะห์จริง: uv run python scripts/reanalyze_all.py --apply")
            return

        t0 = time.time()
        done = 0
        for i in range(0, len(reviews), BATCH):
            batch = reviews[i:i + BATCH]
            results = wangchan_classifier.classify([r["text"] for r in batch])

            for review, res in zip(batch, results):
                _, tokens = preprocess(review["text"])
                sen, cat = res["sentiment"], res["category"]
                # upsert — เก็บ claude_* เดิมไว้ (COALESCE ไม่เขียนทับด้วย NULL)
                await session.execute(
                    text("""
                        INSERT INTO analyzed_reviews
                            (review_id, sentiment, pain_point_category, pain_point_thai,
                             severity, keywords, model_used)
                        VALUES
                            (:rid, :sen, :cat, :thai, :sev, :kw, :model)
                        ON CONFLICT (review_id) DO UPDATE SET
                            sentiment = EXCLUDED.sentiment,
                            pain_point_category = EXCLUDED.pain_point_category,
                            pain_point_thai = EXCLUDED.pain_point_thai,
                            severity = EXCLUDED.severity,
                            keywords = EXCLUDED.keywords,
                            model_used = EXCLUDED.model_used
                    """),
                    {
                        "rid": review["id"], "sen": sen, "cat": cat,
                        "thai": review["text"][:200],
                        "sev": _severity_for(sen, cat, review["rating"]),
                        "kw": tokens[:10],
                        "model": "wangchanberta-finetuned",
                    },
                )
            await session.commit()
            done += len(batch)
            rate = done / (time.time() - t0)
            eta = (len(reviews) - done) / rate if rate else 0
            safe_print(f"  [{done:,}/{len(reviews):,}] {rate:.0f} รีวิว/วิ | เหลือ ~{eta / 60:.1f} นาที")

        dur = time.time() - t0
        safe_print(f"\n✅ วิเคราะห์ใหม่ {done:,} รีวิว ใน {dur / 60:.1f} นาที ({done / dur:.0f} รีวิว/วิ)")
        safe_print("   claude_category / claude_sentiment (ผล Claude) ถูกเก็บไว้เทียบ ไม่ถูกแตะ")
        safe_print("   ➜ ขั้นต่อไป: อัปเดต snapshot + สร้างรายงานใหม่")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="วิเคราะห์ใหม่จริง")
    a = ap.parse_args()
    asyncio.run(main(a.apply))
