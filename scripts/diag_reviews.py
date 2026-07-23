"""
diag_reviews.py — วินิจฉัยว่าทำไม extract_reviews ได้ 0 อัน
บอกว่าเป็น rate-limit (ไม่มี content) หรือ code bug (content มีแต่ดึงไม่เจอ)
รัน: uv run python scripts/diag_reviews.py
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright
from scraper.scraper_core import wait_for_place_loaded, random_delay, scroll_reviews

PLACE = "Layers Cafe พิษณุโลก"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="th-TH", viewport={"width": 1280, "height": 800})
        page = await context.new_page()

        url = f"https://www.google.com/maps/search/{PLACE.replace(' ', '+')}"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await random_delay(2.0, 4.0)

        try:
            first = page.locator('a[href*="/maps/place/"]').first
            if await first.count() > 0:
                await first.click(timeout=5000)
                await random_delay(2.0, 3.0)
        except Exception:
            pass

        await wait_for_place_loaded(page, timeout=20000)
        await random_delay(1.0, 2.0)

        print("=== ก่อนคลิกแท็บรีวิว ===")
        # นับปุ่มที่มีข้อความ "รีวิว"
        review_btns = await page.locator('button', has_text="รีวิว").count()
        print(f"ปุ่ม 'รีวิว' ที่เจอ: {review_btns}")

        # ลอง print ชื่อปุ่มทั้งหมดในหน้า (แท็บ)
        tabs = await page.evaluate("""
            () => Array.from(document.querySelectorAll('button[role="tab"], button'))
                     .map(b => (b.innerText||'').trim())
                     .filter(t => t && t.length < 25)
                     .slice(0, 25)
        """)
        print(f"ปุ่ม/แท็บในหน้า: {tabs}")

        # คลิกแท็บรีวิว
        clicked = False
        try:
            tab = page.locator('button', has_text="รีวิว").first
            if await tab.count() > 0:
                await tab.click(timeout=6000)
                await random_delay(2.5, 3.5)
                clicked = True
        except Exception as e:
            print(f"คลิกแท็บรีวิวไม่ได้: {e}")
        print(f"คลิกแท็บรีวิว: {clicked}")

        await scroll_reviews(page, times=8)

        print("\n=== หลังคลิก + scroll ===")
        # นับ star element ที่ใช้จับรีวิว
        star_count = await page.evaluate("""
            () => {
                const all = document.querySelectorAll('[aria-label]');
                let n = 0;
                all.forEach(el => {
                    const lbl = el.getAttribute('aria-label') || '';
                    if (/^[1-5]\\s*(ดาว|star)/.test(lbl)) n++;
                });
                return n;
            }
        """)
        print(f"star element (N ดาว/star): {star_count}")

        # นับ review feed
        feed = await page.evaluate("""
            () => {
                const f = document.querySelector('[role="feed"]');
                return f ? f.children.length : -1;
            }
        """)
        print(f"[role=feed] children: {feed}")

        # หาข้อความบ่งชี้ rate-limit / captcha
        body_sample = await page.evaluate("() => (document.body.innerText||'').substring(0, 400)")
        print(f"\n=== ตัวอย่าง body text (400 ตัวอักษรแรก) ===\n{body_sample}")

        # screenshot
        await page.screenshot(path="data/diag_reviews.png")
        print("\n📸 บันทึก screenshot -> data/diag_reviews.png")

        await browser.close()


asyncio.run(main())
