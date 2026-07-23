"""
backfill_text_clean.py — ทำความสะอาด text ของรีวิวทั้งหมด → เก็บใน text_clean
(ไม่แตะ text ต้นฉบับ)

รัน: uv run python scripts/backfill_text_clean.py
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from db.database import AsyncSessionLocal
from nlp.text_cleaner import clean_review_text


async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT id, text FROM reviews"))
        rows = result.fetchall()
        print(f"รีวิวทั้งหมด: {len(rows)}")

        cleaned = 0
        empty = 0
        batch = 0
        for r in rows:
            c = clean_review_text(r.text)
            if not c:
                empty += 1
            else:
                cleaned += 1
            await session.execute(
                text("UPDATE reviews SET text_clean = :c WHERE id = :id"),
                {"c": c, "id": r.id},
            )
            batch += 1
            if batch % 500 == 0:
                await session.commit()
                print(f"  ...{batch}")
        await session.commit()

        print(f"\n✅ เสร็จ")
        print(f"  มีเนื้อรีวิว: {cleaned}")
        print(f"  ว่าง (ให้ดาวอย่างเดียว): {empty}")

        # เทียบความยาวเฉลี่ย ก่อน/หลัง
        stats = await session.execute(
            text("""
                SELECT
                    ROUND(AVG(LENGTH(text)))       AS avg_before,
                    ROUND(AVG(LENGTH(text_clean)))  AS avg_after
                FROM reviews
                WHERE text_clean IS NOT NULL AND text_clean <> ''
            """)
        )
        s = stats.fetchone()
        print(f"\n  ความยาวเฉลี่ย: {s.avg_before} → {s.avg_after} ตัวอักษร (ตัด noise ออก)")


asyncio.run(main())
