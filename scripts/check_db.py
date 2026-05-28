"""ดูสถานะ Database"""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()
import asyncpg

async def main():
    url = os.getenv('DATABASE_URL', '').replace('postgresql+asyncpg', 'postgresql')
    conn = await asyncpg.connect(url)
    places   = await conn.fetchval('SELECT COUNT(*) FROM places')
    reviews  = await conn.fetchval('SELECT COUNT(*) FROM reviews')
    analyzed = await conn.fetchval('SELECT COUNT(*) FROM analyzed_reviews')
    jobs     = await conn.fetchval('SELECT COUNT(*) FROM scrape_jobs')
    print('=== สถานะ Database ===')
    print(f'  สถานที่       : {places} แห่ง')
    print(f'  รีวิวทั้งหมด  : {reviews} รีวิว')
    print(f'  วิเคราะห์แล้ว : {analyzed} รีวิว')
    print(f'  Scrape jobs   : {jobs} ครั้ง')
    await conn.close()

asyncio.run(main())
