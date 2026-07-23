"""
inspect_raw_text.py — ดูโครงสร้างจริงของ text (รวม \n) เพื่อออกแบบตัวทำความสะอาด
รัน: uv run python scripts/inspect_raw_text.py
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from db.database import AsyncSessionLocal


async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text("""
                SELECT r.id, r.text
                FROM analyzed_reviews ar
                JOIN reviews r ON r.id = ar.review_id
                WHERE ar.pain_point_category = 'อื่นๆ'
                  AND LENGTH(r.text) > 60
                ORDER BY RANDOM()
                LIMIT 12
            """)
        )
        for row in result.fetchall():
            print(f"\n{'='*65}")
            print(f"ID {row.id}")
            print(f"{'='*65}")
            # แสดง repr เพื่อเห็น \n และ noise ชัดๆ
            print(repr(row.text))


asyncio.run(main())
