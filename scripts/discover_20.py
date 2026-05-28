"""ค้นหาสถานที่ใหม่ 20 แห่ง"""
import asyncio
from dotenv import load_dotenv
load_dotenv()
from db.database import AsyncSessionLocal
from scraper.scraper import run_discover

async def main():
    async with AsyncSessionLocal() as session:
        result = await run_discover(session, headless=True, max_places=20)
        print(result)

asyncio.run(main())
