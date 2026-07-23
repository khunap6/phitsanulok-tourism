"""ทดสอบ text_cleaner กับข้อมูลจริงใน DB — ดู before/after"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from db.database import AsyncSessionLocal
from nlp.text_cleaner import clean_review_text


async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT r.text
                FROM analyzed_reviews ar
                JOIN reviews r ON r.id = ar.review_id
                WHERE ar.pain_point_category = 'อื่นๆ'
                  AND LENGTH(r.text) > 50
                ORDER BY RANDOM()
                LIMIT 15
            """)
        )
        empty_after = 0
        for row in result.fetchall():
            cleaned = clean_review_text(row.text)
            if not cleaned:
                empty_after += 1
            print(f"\n{'─'*60}")
            print(f"BEFORE: {row.text[:100]!r}")
            print(f"AFTER : {cleaned!r}")
        print(f"\n{'='*60}")
        print(f"ที่กลายเป็นว่างหลัง clean (รีวิวให้ดาวอย่างเดียว): {empty_after}/15")


asyncio.run(main())
