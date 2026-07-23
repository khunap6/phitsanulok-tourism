"""
test_phase1_scrape.py — ทดสอบว่า scraper ใหม่ดึง opening_hours + price_level + วันที่ ได้ไหม
รัน: uv run python scripts/test_phase1_scrape.py
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright
from scraper.scraper_core import scrape_place
from scraper.date_parser import parse_to_iso

TEST_PLACES = [
    "Layers Cafe พิษณุโลก",
    "อาป๋า ทะเลเผา พิษณุโลก",
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="th-TH", viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        for name in TEST_PLACES:
            print(f"\n{'='*60}")
            result = await scrape_place(page, name)
            if not result:
                print(f"  ❌ scrape ไม่สำเร็จ: {name}")
                continue

            print(f"  ชื่อ:        {result['place_name']}")
            print(f"  หมวดหมู่:    {result.get('google_category')}")
            print(f"  เวลาเปิด:    {result.get('opening_hours')}")
            print(f"  ราคา:        {result.get('price_level')}")
            print(f"  จำนวนรีวิว:  {len(result.get('reviews', []))}")

            # ตัวอย่างวันที่ 3 รีวิวแรก
            print(f"  ตัวอย่างวันที่รีวิว:")
            for rv in result.get("reviews", [])[:3]:
                raw = rv.get("date", "")
                parsed = parse_to_iso(raw)
                print(f"    {raw!r:25} -> {parsed}")

        await browser.close()


asyncio.run(main())
