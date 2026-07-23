"""ดึงตัวอย่างรีวิว 'อื่นๆ' ที่สะอาดแล้ว (เชิงลบ/กลาง) เพื่อหาหมวดใหม่"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from db.database import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT r.text_clean, ar.sentiment, r.rating,
                       p.google_category
                FROM analyzed_reviews ar
                JOIN reviews r ON r.id = ar.review_id
                JOIN places p ON p.id = r.place_id
                WHERE ar.pain_point_category = 'อื่นๆ'
                  AND r.text_clean <> ''
                  AND LENGTH(r.text_clean) BETWEEN 30 AND 250
                  AND (ar.sentiment IN ('negative','neutral') OR r.rating <= 3)
                ORDER BY RANDOM()
                LIMIT 60
            """)
        )
        for i, row in enumerate(result.fetchall(), 1):
            cat = row.google_category or "-"
            print(f"{i}. [{row.rating}★|{row.sentiment}|{cat}] {row.text_clean}")


asyncio.run(main())
