"""ดึงรีวิวเพิ่มจากทุกสถานที่ใน DB"""
import asyncio
from dotenv import load_dotenv
load_dotenv()
from db.database import AsyncSessionLocal
from scraper.scraper import run_refresh

async def main():
    async with AsyncSessionLocal() as session:
        result = await run_refresh(session, headless=True)
        print(result)

asyncio.run(main())
