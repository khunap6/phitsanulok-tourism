"""
ดึงข้อมูลที่ขาด + รีวิวเพิ่มจากสถานที่เดิมใน DB

ระบบเลือกร้านที่ scrape นานสุดก่อน (คิวอัตโนมัติจาก scraped_at)
รันซ้ำด้วย --limit เท่าเดิมจะทำต่อจากที่ค้างไว้เอง ไม่ทำร้านซ้ำ

รัน:
  uv run python scripts/refresh_all.py               # ทุกร้าน (เสี่ยงโดนบล็อกถ้าเยอะ)
  uv run python scripts/refresh_all.py --limit 40    # ทีละ 40 ร้าน (แนะนำ — รันซ้ำได้)
"""
import argparse
import asyncio

from dotenv import load_dotenv
load_dotenv()

from db.database import AsyncSessionLocal
from scraper.scraper import run_refresh


async def main(limit: int | None = None):
    async with AsyncSessionLocal() as session:
        result = await run_refresh(session, headless=True, max_places=limit)
        print(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="จำนวนร้านต่อรอบ (ไม่ใส่ = ทุกร้าน)")
    args = parser.parse_args()
    asyncio.run(main(args.limit))
