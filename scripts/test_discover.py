"""ทดสอบว่า discover_places หาสถานที่เจอไหม และ selector ใดใช้ได้"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright

QUERIES = [
    "สถานที่ท่องเที่ยว พิษณุโลก",
    "คาเฟ่ พิษณุโลก",
]

SELECTORS = [
    '[class*="hfpxzc"]',
    'a[href*="/maps/place/"]',
    '[role="article"] a',
    '[jsaction*="mouseover"] a[aria-label]',
]

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        for query in QUERIES:
            print(f"\n{'='*50}")
            print(f"Query: {query}")
            print('='*50)

            await page.goto("https://www.google.com/maps", wait_until="domcontentloaded")
            await asyncio.sleep(3)

            # ปิด consent dialog ถ้ามี
            for consent_sel in [
                'button[aria-label*="Accept"]',
                'button[aria-label*="ยอมรับ"]',
                'form[action*="consent"] button',
                'button:has-text("Accept all")',
                'button:has-text("Reject all")',
            ]:
                try:
                    btn = page.locator(consent_sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await asyncio.sleep(1.5)
                        print("  ✅ ปิด consent dialog")
                        break
                except Exception:
                    continue

            # หา search box
            box = None
            for sel in ['#searchboxinput', 'input[name="q"]', '[aria-label*="ค้นหา"]', 'input[type="text"]']:
                try:
                    loc = page.locator(sel).first
                    if await loc.is_visible(timeout=3000):
                        box = loc
                        print(f"  ✅ Search box: [{sel}]")
                        break
                except Exception:
                    continue

            if box is None:
                print("  ❌ หา search box ไม่เจอเลย!")
                continue

            await box.fill(query)
            await page.keyboard.press("Enter")
            await asyncio.sleep(4)

            # ทดสอบทุก selector
            best_sel = None
            best_count = 0
            for sel in SELECTORS:
                items = await page.query_selector_all(sel)
                print(f"  Selector [{sel}]: {len(items)} items")
                if len(items) > best_count:
                    best_count = len(items)
                    best_sel = sel

            # แสดง aria-label ของ 5 รายการแรกจาก selector ที่ดีที่สุด
            if best_sel:
                print(f"\n  Best selector: [{best_sel}] → {best_count} items")
                items = await page.query_selector_all(best_sel)
                print("  ตัวอย่าง 5 รายการแรก:")
                found = 0
                for item in items:
                    if found >= 5:
                        break
                    aria = await item.get_attribute("aria-label")
                    if not aria:
                        aria = await item.evaluate(
                            "el => el.closest('[aria-label]')?.getAttribute('aria-label')"
                        )
                    if aria and len(aria) > 3:
                        print(f"    - {aria}")
                        found += 1
            else:
                print("  ❌ ไม่เจอ selector ใดเลย — อาจโดน bot detection")

            await asyncio.sleep(2)

        await browser.close()
        print("\nเสร็จสิ้น — ปิด browser แล้ว")

asyncio.run(main())
