"""รันครบทุกขั้นตอน: Discover → Refresh → Analyze"""
import asyncio
from dotenv import load_dotenv
load_dotenv()
from db.database import AsyncSessionLocal
from scraper.scraper import run_discover, run_refresh
from nlp.pipeline import run_analysis

MAX_PLACES = 20   # <-- ปรับจำนวนสถานที่ตรงนี้

async def main():
    print('=' * 40)
    print('STEP 1: DISCOVER')
    print('=' * 40)
    async with AsyncSessionLocal() as session:
        r = await run_discover(session, headless=True, max_places=MAX_PLACES)
        print(r)

    print('=' * 40)
    print('STEP 2: REFRESH')
    print('=' * 40)
    async with AsyncSessionLocal() as session:
        r = await run_refresh(session, headless=True)
        print(r)

    print('=' * 40)
    print('STEP 3: ANALYZE')
    print('=' * 40)
    total = 0
    async with AsyncSessionLocal() as session:
        while True:
            r = await run_analysis(session, batch_size=20)
            total += r['analyzed']
            if r['analyzed'] == 0:
                break
    print(f'วิเคราะห์รวม: {total} รีวิว')
    print('=' * 40)
    print('เสร็จสิ้น')

asyncio.run(main())
