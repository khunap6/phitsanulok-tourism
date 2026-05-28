"""ค้นหาสถานที่ใหม่ 50 แห่ง (~1 ชั่วโมง)"""
import asyncio
from dotenv import load_dotenv
load_dotenv()
from db.database import AsyncSessionLocal
from scraper.scraper import run_discover

async def main():
    async with AsyncSessionLocal() as session:
        result = await run_discover(session, headless=True, max_places=50)
        print(result)

asyncio.run(main())
