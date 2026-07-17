"""
ทดสอบว่า selector สำหรับดึง google_category (เช่น "ร้านอาหารไทย", "คาเฟ่")
ใช้งานได้จริงกับหน้า Google Maps ปัจจุบันไหม ก่อนรัน refresh_all.py กับสถานที่ทั้งหมด

รัน: uv run python scripts/test_category_selector.py
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright

# สถานที่ที่รู้ผลอยู่แล้ว ใช้เทียบว่า selector ดึงถูกไหม
TEST_PLACES = [
    ("ร้านอรรถรส พิษณุโลก", "ร้านอาหาร (คาดหวัง)"),
    ("KITCHIN พิษณุโลก", "ร้านอาหาร (คาดหวัง)"),
    ("Layers Cafe พิษณุโลก", "คาเฟ่ (คาดหวัง)"),
]

# selector ที่จะทดสอบ (ตัวที่ใส่ใน scraper_core.py ตอนนี้ + สำรอง)
CATEGORY_SELECTORS = [
    ".DkEaL",
    'button[jsaction*="category"]',
    '[jsaction*="pane.rating.category"]',
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page(locale="th-TH")

        for place_name, expected in TEST_PLACES:
            print(f"\n{'='*60}")
            print(f"สถานที่: {place_name}")
            print(f"คาดหวัง: {expected}")
            print('='*60)

            search_url = f"https://www.google.com/maps/search/{place_name.replace(' ', '+')}"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            # ถ้าเป็นหน้า list ผลลัพธ์ ให้คลิกอันแรก
            try:
                first_result = page.locator('a[href*="/maps/place/"]').first
                if await first_result.count() > 0:
                    await first_result.click(timeout=5000)
                    await asyncio.sleep(2.5)
            except Exception:
                pass

            await asyncio.sleep(1.5)

            # ทดสอบทุก selector
            found_any = False
            for sel in CATEGORY_SELECTORS:
                try:
                    elem = await page.query_selector(sel)
                    if elem:
                        text = (await elem.inner_text()).strip()
                        if text:
                            print(f"  ✅ [{sel}] → \"{text}\"")
                            found_any = True
                        else:
                            print(f"  ⚠️  [{sel}] → เจอ element แต่ text ว่าง")
                    else:
                        print(f"  ❌ [{sel}] → ไม่เจอ element")
                except Exception as e:
                    print(f"  ❌ [{sel}] → error: {e}")

            if not found_any:
                print(f"\n  ⚠️  ไม่มี selector ไหนดึงค่าได้เลย — ต้องเปิด debug screenshot ดู HTML จริง")

            await asyncio.sleep(1.5)

        await browser.close()
        print(f"\n{'='*60}")
        print("เสร็จสิ้น — ดูผลด้านบนว่า selector ไหนดึงค่าได้ถูกต้อง")
        print('='*60)


asyncio.run(main())
