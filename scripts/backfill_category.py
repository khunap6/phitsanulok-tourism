"""
backfill_category.py — เติม google_category ให้สถานที่ที่ยังเป็น NULL

ต่างจาก refresh_all.py ตรงที่:
  - ไม่ดึงรีวิวซ้ำ (เร็วกว่ามาก)
  - เข้าไปเฉพาะเพื่อดึง google_category เท่านั้น

รัน: uv run python scripts/backfill_category.py
     uv run python scripts/backfill_category.py --limit 10   # ทดสอบแค่ 10 แห่งก่อน
"""
import argparse
import asyncio
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from playwright.async_api import async_playwright

from db.database import AsyncSessionLocal
from scraper.scraper_core import (
    random_delay,
    wait_for_place_loaded,
)

CATEGORY_SELECTORS = [
    ".DkEaL",
    'button[jsaction*="category"]',
    '[jsaction*="pane.rating.category"]',
]


def safe_print(text_val: str) -> None:
    """print ภาษาไทยตรงๆ ถ้า terminal รองรับ ถ้าไม่รองรับ fallback เป็น ? แทนการ crash"""
    try:
        print(text_val)
    except UnicodeEncodeError:
        print(text_val.encode("ascii", errors="replace").decode("ascii"))


async def load_places_missing_category(session, limit: int | None = None) -> list[dict]:
    """หาสถานที่ที่ google_category ยังเป็น NULL"""
    query = """
        SELECT id, name, search_query
        FROM places
        WHERE google_category IS NULL
        ORDER BY id
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    result = await session.execute(text(query))
    return [
        {"id": r.id, "name": r.name, "search_query": r.search_query or r.name}
        for r in result.fetchall()
    ]


async def fetch_category(page, search_text: str) -> str | None:
    """เข้าไปหน้า Google Maps ของสถานที่ แล้วดึง google_category (ไม่ดึงรีวิว)"""
    search_url = f"https://www.google.com/maps/search/{search_text.replace(' ', '+')}"
    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    await random_delay(2.0, 3.5)

    # ถ้าเป็นหน้า list ผลลัพธ์ ให้คลิกอันแรก
    try:
        first_result = page.locator('a[href*="/maps/place/"]').first
        if await first_result.count() > 0:
            await first_result.click(timeout=5000)
            await random_delay(1.5, 2.5)
    except Exception:
        pass

    loaded = await wait_for_place_loaded(page, timeout=15000)
    if not loaded:
        return None

    await random_delay(0.5, 1.0)

    for sel in CATEGORY_SELECTORS:
        try:
            elem = await page.query_selector(sel)
            if elem:
                text_val = (await elem.inner_text()).strip()
                if text_val and len(text_val) < 60:
                    return text_val
        except Exception:
            continue

    return None


async def main(limit: int | None = None, headless: bool = True):
    async with AsyncSessionLocal() as session:
        places = await load_places_missing_category(session, limit)

        if not places:
            print("✅ ไม่มีสถานที่ที่ต้อง backfill — google_category ครบทุกแห่งแล้ว")
            return

        print(f"พบสถานที่ที่ต้อง backfill: {len(places)} แห่ง\n")

        found = 0
        still_missing = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(locale="th-TH", viewport={"width": 1280, "height": 800})
            page = await context.new_page()

            for i, place in enumerate(places):
                safe_print(f"[{i+1}/{len(places)}] {place['name']}")

                try:
                    category = await fetch_category(page, place["search_query"])
                except Exception as e:
                    print(f"  ❌ error: {e}")
                    category = None

                if category:
                    safe_print(f"  ✅ category: {category}")
                    await session.execute(
                        text("UPDATE places SET google_category = :cat WHERE id = :id"),
                        {"cat": category, "id": place["id"]},
                    )
                    await session.commit()
                    found += 1
                else:
                    print(f"  ⚠️  ยังดึงไม่ได้")
                    still_missing += 1

                if i < len(places) - 1:
                    await random_delay(3.0, 6.0)

            await browser.close()

        print(f"\n{'='*50}")
        print(f"✅ เติม category สำเร็จ: {found} แห่ง")
        print(f"⚠️  ยังดึงไม่ได้: {still_missing} แห่ง")
        print('='*50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="จำกัดจำนวนสถานที่ที่ทดสอบ")
    parser.add_argument("--visible", action="store_true", help="เปิด browser ให้เห็น (default: headless)")
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit, headless=not args.visible))
