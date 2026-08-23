"""
dedup_reviews.py — ล้างรีวิวซ้ำ + คำนวณ text_hash ใหม่ตามสูตรที่แก้แล้ว

ที่มาของปัญหา:
  text_hash เดิมคำนวณจาก "ข้อความดิบ" ซึ่งมีวันที่แบบสัมพัทธ์ติดมาด้วย
  ("7 เดือนที่แล้ว") พอ scrape รอบใหม่วันที่เลื่อนเป็น "8 เดือนที่แล้ว"
  → hash เปลี่ยน → ระบบนึกว่าเป็นรีวิวใหม่ แล้วบันทึกซ้ำ

สคริปต์นี้ทำ 2 อย่าง:
  1. ลบแถวซ้ำ (เก็บแถวที่วิเคราะห์แล้วไว้ก่อน ไม่งั้นเก็บแถวเก่าสุด)
  2. คำนวณ text_hash ใหม่จาก text_clean → ครั้งต่อไปจะกันซ้ำได้จริง

รัน:
  uv run python scripts/dedup_reviews.py            # ดูก่อนว่าจะลบเท่าไหร่ (ไม่ลบจริง)
  uv run python scripts/dedup_reviews.py --apply    # ลบจริง
"""
import argparse
import asyncio

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal

# ข้อความที่ใช้เทียบว่าซ้ำกันไหม — ใช้ text_clean ถ้ามี ไม่งั้นใช้ข้อความดิบ
# (ต้องตรงกับ review_text_hash() ใน scraper_core.py)
EFFECTIVE_TEXT = "COALESCE(NULLIF(r.text_clean, ''), TRIM(r.text))"


def safe_print(t: str) -> None:
    try:
        print(t)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"))


async def survey(session) -> dict:
    r = await session.execute(
        text(f"""
            SELECT
              (SELECT COUNT(*) FROM reviews)          AS total_reviews,
              (SELECT COUNT(*) FROM analyzed_reviews) AS total_analyzed,
              COALESCE(SUM(c - 1), 0)                 AS extra_rows,
              COUNT(*)                                AS dup_groups
            FROM (
              SELECT r.place_id, {EFFECTIVE_TEXT} AS eff, COUNT(*) AS c
              FROM reviews r
              GROUP BY r.place_id, {EFFECTIVE_TEXT}
              HAVING COUNT(*) > 1
            ) t
        """)
    )
    x = r.fetchone()
    # จำนวน analyzed ที่จะหายไปด้วย (แถวซ้ำที่มีผลวิเคราะห์ และไม่ใช่ตัวที่เก็บไว้)
    r2 = await session.execute(
        text(f"""
            WITH ranked AS (
              SELECT r.id,
                     ROW_NUMBER() OVER (
                       PARTITION BY r.place_id, {EFFECTIVE_TEXT}
                       ORDER BY (ar.id IS NOT NULL) DESC, r.id ASC
                     ) AS rn,
                     (ar.id IS NOT NULL) AS has_analysis
              FROM reviews r
              LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            )
            SELECT COUNT(*) FILTER (WHERE has_analysis) AS analyzed_lost
            FROM ranked WHERE rn > 1
        """)
    )
    return {
        "total_reviews": x.total_reviews,
        "total_analyzed": x.total_analyzed,
        "dup_groups": x.dup_groups,
        "extra_rows": x.extra_rows,
        "analyzed_lost": r2.scalar() or 0,
    }


async def dedup(session) -> int:
    """ลบแถวซ้ำ — เก็บแถวที่มีผลวิเคราะห์ไว้ก่อน ไม่งั้นเก็บ id น้อยสุด (เก่าสุด)"""
    r = await session.execute(
        text(f"""
            WITH ranked AS (
              SELECT r.id,
                     ROW_NUMBER() OVER (
                       PARTITION BY r.place_id, {EFFECTIVE_TEXT}
                       ORDER BY (ar.id IS NOT NULL) DESC, r.id ASC
                     ) AS rn
              FROM reviews r
              LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            )
            DELETE FROM reviews
            WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
        """)
    )
    return r.rowcount


async def rehash(session) -> int:
    """คำนวณ text_hash ใหม่ให้ตรงกับสูตรใหม่ (md5 ของข้อความที่ล้างแล้ว)"""
    r = await session.execute(
        text("""
            UPDATE reviews r
            SET text_hash = MD5(COALESCE(NULLIF(r.text_clean, ''), TRIM(r.text)))
            WHERE r.text_hash IS DISTINCT FROM
                  MD5(COALESCE(NULLIF(r.text_clean, ''), TRIM(r.text)))
        """)
    )
    return r.rowcount


async def verify(session) -> dict:
    r = await session.execute(
        text(f"""
            SELECT COUNT(*) FROM (
              SELECT 1 FROM reviews r
              GROUP BY r.place_id, {EFFECTIVE_TEXT}
              HAVING COUNT(*) > 1
            ) t
        """)
    )
    dup_left = r.scalar()
    r2 = await session.execute(
        text("""
            SELECT COUNT(*) FROM reviews r
            WHERE r.text_hash IS DISTINCT FROM
                  MD5(COALESCE(NULLIF(r.text_clean, ''), TRIM(r.text)))
        """)
    )
    return {"dup_left": dup_left, "hash_mismatch": r2.scalar()}


async def main(apply: bool) -> None:
    async with AsyncSessionLocal() as session:
        before = await survey(session)
        safe_print("=" * 62)
        safe_print("สำรวจข้อมูลก่อนล้าง")
        safe_print("=" * 62)
        safe_print(f"  รีวิวทั้งหมด        : {before['total_reviews']:,}")
        safe_print(f"  วิเคราะห์แล้ว       : {before['total_analyzed']:,}")
        safe_print(f"  กลุ่มที่ซ้ำกัน      : {before['dup_groups']:,} กลุ่ม")
        safe_print(f"  แถวเกินที่จะลบ      : {before['extra_rows']:,} แถว "
                   f"({before['extra_rows'] / max(before['total_reviews'], 1) * 100:.1f}%)")
        safe_print(f"  ผลวิเคราะห์ที่หายไป : {before['analyzed_lost']:,} "
                   f"(เก็บแถวที่วิเคราะห์แล้วไว้ก่อนแล้ว)")

        if not apply:
            safe_print("\n⚠️  โหมดดูอย่างเดียว — ยังไม่ลบอะไร")
            safe_print("   ถ้าต้องการลบจริง: uv run python scripts/dedup_reviews.py --apply")
            return

        safe_print("\nกำลังลบแถวซ้ำ...")
        deleted = await dedup(session)
        safe_print(f"  ลบแล้ว {deleted:,} แถว")

        safe_print("กำลังคำนวณ text_hash ใหม่...")
        updated = await rehash(session)
        safe_print(f"  อัปเดต {updated:,} แถว")

        await session.commit()

        after = await survey(session)
        chk = await verify(session)
        safe_print("\n" + "=" * 62)
        safe_print("ผลลัพธ์")
        safe_print("=" * 62)
        safe_print(f"  รีวิวคงเหลือ    : {after['total_reviews']:,} "
                   f"(ลดลง {before['total_reviews'] - after['total_reviews']:,})")
        safe_print(f"  วิเคราะห์แล้ว   : {after['total_analyzed']:,} "
                   f"(ลดลง {before['total_analyzed'] - after['total_analyzed']:,})")
        safe_print(f"  กลุ่มซ้ำที่เหลือ: {chk['dup_left']:,} "
                   f"{'✅' if chk['dup_left'] == 0 else '⚠️'}")
        safe_print(f"  hash ไม่ตรงสูตร : {chk['hash_mismatch']:,} "
                   f"{'✅' if chk['hash_mismatch'] == 0 else '⚠️'}")
        safe_print("\n✅ เสร็จ — ครั้งต่อไปที่ scrape จะไม่เกิดรีวิวซ้ำอีก")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="ลบจริง (ไม่ใส่ = ดูอย่างเดียว)")
    a = ap.parse_args()
    asyncio.run(main(a.apply))
