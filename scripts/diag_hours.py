"""
diag_hours.py — วินิจฉัยว่า Google Maps เก็บ "ตารางเวลาทำการทั้งสัปดาห์" + "สถานะร้าน" ไว้ตรงไหน
เพื่อเขียน extractor ให้ถูกต้อง

รัน: uv run python scripts/diag_hours.py
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright
from scraper.scraper_core import wait_for_place_loaded, random_delay

PLACES = [
    "Layers Cafe พิษณุโลก",
    "วัดพระศรีรัตนมหาธาตุวรมหาวิหาร พิษณุโลก",
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(locale="th-TH", viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()

        for name in PLACES:
            print(f"\n{'='*70}\n{name}\n{'='*70}")
            url = f"https://www.google.com/maps/search/{name.replace(' ', '+')}"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await random_delay(2.5, 4.0)
            try:
                first = page.locator('a[href*="/maps/place/"]').first
                if await first.count() > 0:
                    await first.click(timeout=5000)
                    await random_delay(2.0, 3.0)
            except Exception:
                pass
            await wait_for_place_loaded(page, timeout=15000)
            await random_delay(1.0, 1.5)

            # 1) element ที่ aria-label มีชื่อวัน (น่าจะเป็นตารางเต็ม)
            print("\n[1] aria-label ที่มีชื่อวัน (จันทร์/อังคาร/...):")
            day_labels = await page.evaluate("""
                () => {
                    const out = [];
                    const days = ['จันทร์','อังคาร','พุธ','พฤหัส','ศุกร์','เสาร์','อาทิตย์',
                                  'Monday','Tuesday','Wednesday'];
                    document.querySelectorAll('[aria-label]').forEach(el => {
                        const a = el.getAttribute('aria-label') || '';
                        if (days.some(d => a.includes(d)) && a.length < 400) {
                            out.push({tag: el.tagName, cls: el.className.substring(0,40), aria: a});
                        }
                    });
                    return out.slice(0, 8);
                }
            """)
            for d in day_labels:
                print(f"   <{d['tag']} class='{d['cls']}'> aria=\"{d['aria']}\"")
            if not day_labels:
                print("   (ไม่เจอ — ตารางอาจซ่อนอยู่ ต้องคลิกเปิด)")

            # 2) ปุ่ม/แถบเวลาทำการ (ที่เราดึงอยู่ตอนนี้)
            print("\n[2] element เวลาทำการที่ดึงอยู่ตอนนี้:")
            for sel in ['[jsaction*="openhours"]', '.t39EBf', '.OqCZI', '[aria-label*="เวลาทำการ"]', '[aria-label*="ชั่วโมง"]']:
                el = await page.query_selector(sel)
                if el:
                    aria = await el.get_attribute("aria-label")
                    txt = (await el.inner_text()).replace("\n", " ")[:120]
                    print(f"   [{sel}]")
                    print(f"       text: {txt!r}")
                    print(f"       aria: {aria!r}")

            # 3) ลองคลิกเปิดตารางเวลาทำการ แล้วอ่าน
            print("\n[3] หลังคลิกเปิดตารางเวลาทำการ:")
            clicked = False
            for sel in ['[jsaction*="openhours"]', 'button[aria-label*="เวลาทำการ"]', '.t39EBf']:
                try:
                    btn = page.locator(sel).first
                    if await btn.count() > 0:
                        await btn.click(timeout=4000)
                        await random_delay(1.0, 1.5)
                        clicked = True
                        print(f"   คลิก [{sel}] สำเร็จ")
                        break
                except Exception:
                    continue
            if clicked:
                rows = await page.evaluate("""
                    () => {
                        const out = [];
                        document.querySelectorAll('table tr').forEach(tr => {
                            const t = (tr.innerText || '').replace(/\\n/g,' ').trim();
                            if (t && t.length < 60) out.push(t);
                        });
                        return out.slice(0, 10);
                    }
                """)
                print("   ตาราง <tr>:")
                for r in rows:
                    print(f"       {r}")
                if not rows:
                    print("   (ไม่เจอ <table> — อาจใช้ div แทน)")

            # 4) สถานะร้าน (ข้อความสั้นๆ ที่บอก เปิด/ปิด)
            print("\n[4] ข้อความสถานะ (เปิดอยู่/ปิดอยู่/ปิดถาวร/ปิดชั่วคราว):")
            status_texts = await page.evaluate("""
                () => {
                    const out = [];
                    const kw = ['เปิดอยู่','ปิดอยู่','ปิดถาวร','ปิดชั่วคราว','ปิดกิจการ','ใกล้ปิด','เปิด 24'];
                    document.querySelectorAll('span,div').forEach(el => {
                        const t = (el.innerText || '').trim();
                        if (t.length < 40 && kw.some(k => t.includes(k))) out.push(t);
                    });
                    return [...new Set(out)].slice(0, 6);
                }
            """)
            for s in status_texts:
                print(f"       {s!r}")

        await browser.close()
        print("\nเสร็จ — ดูผลด้านบนว่าตารางเวลาทำการอยู่ตรงไหน")


asyncio.run(main())
