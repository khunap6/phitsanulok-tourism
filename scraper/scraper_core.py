"""
Google Maps Reviews Scraper for Phitsanulok Tourism
Scrapes 1-3 star reviews from tourist attractions using Playwright
"""

import asyncio
import hashlib
import json
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # โหลด PLAYWRIGHT_BROWSERS_PATH และ env อื่นๆ ก่อน Playwright ทำงาน

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout

# ใช้ล้างข้อความรีวิวก่อนคำนวณ hash (ตัดวันที่/ไอคอน/ข้อความ UI ออก)
from nlp.text_cleaner import clean_review_text


DATA_DIR = Path(__file__).parent.parent / "data"

# จำนวนรีวิวสูงสุดต่อสถานที่ (ตอน refresh — เก็บให้มากที่สุด)
MAX_REVIEWS_PER_PLACE = 200
# ตอน discover ร้านใหม่ — เก็บ "เฉพาะข้อมูลร้าน" ไม่แตะรีวิวเลย (เร็ว + เสี่ยงบล็อกน้อย)
# ชื่อ/พิกัด/หมวดหมู่/เวลาทำการ/สถานะร้าน มาจาก discover ส่วนรีวิวมาจาก refresh ทีหลัง
DISCOVER_MAX_REVIEWS = 0

# Bounding box ของจังหวัดพิษณุโลก (lat/lng)
PHITSANULOK_BBOX = {
    "lat_min": 16.35,
    "lat_max": 17.35,
    "lng_min": 100.05,  # ขอบตะวันตกของพิษณุโลก (สุโขทัยอยู่ทางซ้ายของเส้นนี้)
    "lng_max": 101.2,
}

def is_in_phitsanulok(lat: float, lng: float) -> bool:
    """Check if coordinates are within Phitsanulok province bounding box."""
    if lat is None or lng is None:
        return True  # ถ้าไม่มีพิกัด ยังเก็บไว้ก่อน
    bb = PHITSANULOK_BBOX
    return bb["lat_min"] <= lat <= bb["lat_max"] and bb["lng_min"] <= lng <= bb["lng_max"]

# Fallback list — เฉพาะสถานที่ในจังหวัดพิษณุโลกเท่านั้น
PHITSANULOK_PLACES_FALLBACK = [
    "วัดพระศรีรัตนมหาธาตุวรมหาวิหาร พิษณุโลก",
    "วัดนางพญา พิษณุโลก",
    "พระราชวังจันทน์ พิษณุโลก",
    "วัดราชบูรณะ พิษณุโลก",
    "วัดจุฬามณี พิษณุโลก",
    "วัดอรัญญิก พิษณุโลก",
    "วัดสระแก้ว พิษณุโลก",
    "วัดป่าม่วง พิษณุโลก",
    "พิพิธภัณฑ์สถานแห่งชาติพิษณุโลก",
    "บึงราชนครินทร์ พิษณุโลก",
    "ถนนคนเดินพิษณุโลก",
    "ตลาดเช้าพิษณุโลก",
    "หาดท้ายเมือง พิษณุโลก",
    "เขื่อนแควน้อย พิษณุโลก",
    "อุทยานแห่งชาติทุ่งแสลงหลวง พิษณุโลก",
    "อุทยานแห่งชาติภูหินร่องกล้า พิษณุโลก",
    "น้ำตกแก่งซอง พิษณุโลก",
    "น้ำตกชาติตระการ พิษณุโลก",
    "น้ำตกสกุโณทยาน พิษณุโลก",
    "สะพานแขวนวังนกแอ่น พิษณุโลก",
    "ศูนย์วัฒนธรรมเฉลิมราช พิษณุโลก",
]


async def discover_places(page: Page, query: str = "สถานที่ท่องเที่ยว พิษณุโลก", max_places: int = 60) -> list[str]:
    """
    Auto-discover tourist place names from Google Maps search results.
    Returns a list of place names to scrape.
    """
    print(f"\n🔭 Auto-discovering places: '{query}'")
    places = []

    try:
        await page.goto("https://www.google.com/maps", wait_until="domcontentloaded")
        await random_delay(2.0, 3.0)

        # ปิด Cookie Consent / Terms dialog ถ้ามี
        for consent_sel in [
            'button[aria-label*="Accept"]',
            'button[aria-label*="ยอมรับ"]',
            'button[aria-label*="Agree"]',
            'form[action*="consent"] button',
            '[id*="consent"] button',
            'button:has-text("Accept all")',
            'button:has-text("ยอมรับทั้งหมด")',
            'button:has-text("I agree")',
            'button:has-text("Reject all")',
        ]:
            try:
                btn = page.locator(consent_sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await asyncio.sleep(1.5)
                    print("  ✅ ปิด consent dialog แล้ว")
                    break
            except Exception:
                continue

        # หา search box ด้วยหลาย selector
        search_box = None
        for sel in ['#searchboxinput', 'input[name="q"]', '[aria-label*="ค้นหา"]', 'input[type="text"]']:
            try:
                loc = page.locator(sel).first
                if await loc.is_visible(timeout=3000):
                    search_box = loc
                    break
            except Exception:
                continue

        if search_box is None:
            print("  ⚠️  หา search box ไม่เจอ — ข้าม query นี้")
            return places

        await search_box.click()
        await search_box.fill(query)
        await page.keyboard.press("Enter")
        await random_delay(3.0, 5.0)

        # Scroll results panel to load more places
        scroll_attempts = 0
        max_scrolls = 15
        while len(places) < max_places and scroll_attempts < max_scrolls:
            # ลอง selector หลายแบบ (Google Maps เปลี่ยน class บ่อย)
            all_items = []
            for sel in [
                '[class*="hfpxzc"]',                      # class เก่า
                'a[href*="/maps/place/"]',                 # link ตรงๆ
                '[role="article"] a',                      # article link
                '[jsaction*="mouseover"] a[aria-label]',  # jsaction pattern
            ]:
                found_sel = await page.query_selector_all(sel)
                if found_sel:
                    all_items = found_sel
                    break  # ใช้ selector แรกที่เจอ

            for item in all_items:
                try:
                    # ลองดึง aria-label จาก element เอง หรือจาก parent
                    aria = await item.get_attribute("aria-label")
                    if not aria:
                        aria = await item.evaluate("el => el.closest('[aria-label]')?.getAttribute('aria-label')")
                    if aria and aria not in places and len(aria) > 3:
                        places.append(aria)
                except Exception:
                    continue

            if len(places) >= max_places:
                break

            # Scroll the results panel — ลอง selector หลายแบบ
            scrolled = await page.evaluate("""
                () => {
                    const sels = [
                        '[role="feed"]',
                        '.m6QErb.DxyBCb',
                        '.m6QErb',
                        'div[aria-label*="ผลลัพธ์"]',
                        'div[aria-label*="Results"]',
                        '[role="main"] > div > div',
                    ];
                    for (const sel of sels) {
                        const el = document.querySelector(sel);
                        if (el && el.scrollHeight > el.clientHeight + 50) {
                            el.scrollBy(0, 800);
                            return sel;
                        }
                    }
                    // fallback: scroll ทั้งหน้า
                    window.scrollBy(0, 800);
                    return 'window';
                }
            """)
            await asyncio.sleep(2.0)
            scroll_attempts += 1

        # Deduplicate and filter out Google Maps UI text
        UI_WORDS = {"ผลลัพธ์", "แผนที่", "ภาพรวม", "รีวิว", "ใกล้เคียง", "ค้นหา", "เส้นทาง", "บันทึก"}
        places = [p for p in dict.fromkeys(places) if p not in UI_WORDS and len(p) > 3][:max_places]
        print(f"  ✅ Discovered {len(places)} places")

    except Exception as e:
        print(f"  ⚠️  Discovery failed: {e} — using fallback list")
        places = []

    return places


async def random_delay(min_sec: float = 2.0, max_sec: float = 5.0):
    """Human-like random delay between actions."""
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def scroll_reviews(page: Page, times: int = 5):
    """Scroll the reviews panel to load more reviews."""
    try:
        for _ in range(times):
            scrolled = await page.evaluate("""
                () => {
                    // ลอง selector หลายแบบ (Google Maps เปลี่ยน HTML บ่อย)
                    const selectors = [
                        '[role="feed"]',
                        '.m6QErb.DxyBCb.kA9KIf.dS8AEf',
                        '.m6QErb[aria-label]',
                        '.DxyBCb',
                        'div[tabindex="-1"] > div[aria-label]',
                    ];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.scrollHeight > el.clientHeight) {
                            el.scrollTo(0, el.scrollHeight);
                            return sel;   // คืนค่า selector ที่ใช้ได้
                        }
                    }
                    // fallback: เลื่อนหน้าทั้งหมด
                    window.scrollBy(0, 800);
                    return 'window';
                }
            """)
            await asyncio.sleep(1.5)
    except Exception:
        pass


async def extract_place_coords(page: Page) -> tuple[float, float] | None:
    """Extract lat/lng from Google Maps URL."""
    try:
        url = page.url
        # Pattern: @16.8211839,100.2658516
        match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", url)
        if match:
            return float(match.group(1)), float(match.group(2))
    except Exception:
        pass
    return None


# ── เวลาทำการทั้งสัปดาห์ ────────────────────────────────────────────────
_DAY_ORDER = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
_DAY_ABBR = {"จันทร์": "จ", "อังคาร": "อ", "พุธ": "พ", "พฤหัสบดี": "พฤ",
             "ศุกร์": "ศ", "เสาร์": "ส", "อาทิตย์": "อา"}
_HOURS_NOISE = ("รูปภาพ", "ผู้รีวิว", "ช่วงราคา", "รายงาน", "ต่อคน")
_PUA_RE = re.compile("[" + chr(0xE000) + "-" + chr(0xF8FF) + "]")
# ช่วงเวลา 1 ช่วง เช่น "9:30 ถึง 14:30" / "6:00–20:00" / "6:00-20:00"
_TIME_RANGE_RE = re.compile(r"(\d{1,2}:\d{2})\s*(?:ถึง|[-–—])\s*(\d{1,2}:\d{2})")


def _day_hours(rest: str, raw: str) -> str:
    """แปลงข้อความเวลาของ 1 วัน → สตริงสั้น รองรับหลายช่วง (เช้า+เย็น) และกรณีปิด/24 ชม."""
    if "24" in rest and ("ชั่วโมง" in raw or "ตลอด" in raw):
        return "24 ชม."
    ranges = _TIME_RANGE_RE.findall(rest)
    if ranges:
        return ", ".join(f"{a}-{b}" for a, b in ranges)
    return "ปิด"  # ไม่มีช่วงเวลา = ปิดวันนั้น (เช่น "ปิดทำการ")


def _parse_weekly_hours(raw_list: list[str]) -> str | None:
    """
    แปลง aria-label/แถวตารางของแต่ละวัน → สตริงเวลาทำการทั้งสัปดาห์
    เช่น "ทุกวัน 6:00-20:00" หรือ "จ 8:00-17:00 | ส 9:30-14:30, 17:00-2:30"
    """
    found: dict[str, str] = {}
    for raw in raw_list:
        if not raw or any(n in raw for n in _HOURS_NOISE):
            continue
        for day in _DAY_ORDER:
            if day in raw:
                rest = _PUA_RE.sub(" ", raw.split(day, 1)[1])
                found[day] = _day_hours(rest, raw)
                break

    if not found:
        return None
    times = set(found.values())
    if len(found) == 7 and len(times) == 1:
        return f"ทุกวัน {next(iter(times))}"
    return " | ".join(f"{_DAY_ABBR[d]} {found[d]}" for d in _DAY_ORDER if d in found)


async def extract_opening_hours(page: Page) -> str | None:
    """
    ดึงตารางเวลาทำการทั้งสัปดาห์จาก Google Maps (คลิกเปิดตารางก่อน แล้วอ่านทีละวัน)
    คืนสตริงเช่น "ทุกวัน 06:00-20:00" หรือ "จ 08:00-17:00 | ..." หรือ None ถ้าไม่มีข้อมูล
    """
    # 1) คลิกเปิดตารางเวลาทำการ (ปุ่มสรุป)
    for sel in ['[jsaction*="openhours"]', 'button[aria-label*="เวลาทำการ"]']:
        try:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                await btn.click(timeout=3000)
                await asyncio.sleep(0.7)
                break
        except Exception:
            continue

    # 2) อ่านเวลาแต่ละวัน — ลอง 3 แหล่งตามลำดับความน่าเชื่อถือ:
    #    (a) ปุ่ม "คัดลอกเวลาเปิดทำการ" 1 ปุ่ม/วัน
    #    (b) ตาราง <tr> ในกล่องที่กางออก
    #    (c) .t39EBf ที่รวมทุกวันไว้ คั่นด้วยอักขระ PUA (เช่น "วันเสาร์6:00–20:00วันอาทิตย์...")
    try:
        raw_list = await page.evaluate("""
            () => {
                const out = [];
                document.querySelectorAll('[aria-label*="คัดลอกเวลา"]').forEach(el => {
                    const a = el.getAttribute('aria-label') || '';
                    if (a.includes('วัน')) out.push(a);
                });
                if (out.length === 0) {
                    document.querySelectorAll('table tr').forEach(tr => {
                        const t = (tr.innerText || '').replace(/\\s+/g, ' ').trim();
                        if (t.includes('วัน') && t.length < 60) out.push(t);
                    });
                }
                if (out.length === 0) {
                    const el = document.querySelector('.t39EBf');
                    if (el) {
                        (el.innerText || '').split(/[\\ue000-\\uf8ff\\n]/).forEach(p => {
                            p = p.trim();
                            if (p.includes('วัน') && p.length < 40) out.push(p);
                        });
                    }
                }
                return out;
            }
        """)
    except Exception:
        raw_list = []

    return _parse_weekly_hours(raw_list or [])


async def extract_price_level(page: Page) -> str | None:
    """
    ดึงระดับราคาจากหน้า Google Maps (best-effort)
    คืนค่าเช่น "฿฿", "100–200 ฿", "$$"
    """
    for sel in [
        '[aria-label*="ช่วงราคา"]',
        '[aria-label*="ราคา"]',
        '[aria-label*="Price"]',
        '.mgr77e',
        'span.mgr77e',
    ]:
        try:
            elem = await page.query_selector(sel)
            if elem:
                aria = await elem.get_attribute("aria-label")
                if aria and ("฿" in aria or "$" in aria or "ราคา" in aria or "Price" in aria):
                    return aria.strip()[:50]
                txt = (await elem.inner_text()).strip()
                if txt and ("฿" in txt or "$" in txt):
                    return txt[:50]
        except Exception:
            continue

    # fallback: หา span ที่มีสัญลักษณ์ ฿ / $ ล้วนๆ
    try:
        price = await page.evaluate("""
            () => {
                const spans = document.querySelectorAll('span');
                for (const s of spans) {
                    const t = (s.innerText || '').trim();
                    if (/^[฿$]{1,4}$/.test(t)) return t;
                }
                return null;
            }
        """)
        if price:
            return price
    except Exception:
        pass
    return None


async def extract_business_status(page: Page) -> str:
    """
    ตรวจสถานะร้านจากหน้า Google Maps
    คืน 'operational' (เปิดปกติ) / 'closed_temporarily' / 'closed_permanently'
    """
    try:
        status = await page.evaluate("""
            () => {
                const els = document.querySelectorAll('span, div');
                for (const e of els) {
                    const t = (e.innerText || '').trim();
                    if (t.length > 0 && t.length < 30) {
                        if (t.includes('ปิดถาวร') || t.includes('ปิดกิจการ') ||
                            t.toLowerCase().includes('permanently closed'))
                            return 'closed_permanently';
                        if (t.includes('ปิดชั่วคราว') ||
                            t.toLowerCase().includes('temporarily closed'))
                            return 'closed_temporarily';
                    }
                }
                return 'operational';
            }
        """)
        return status or "operational"
    except Exception:
        return "operational"


async def debug_page(page: Page, label: str = "debug"):
    """Save screenshot + HTML dump for debugging."""
    debug_dir = DATA_DIR / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    try:
        await page.screenshot(path=str(debug_dir / f"{label}.png"), full_page=False)
        html = await page.content()
        with open(debug_dir / f"{label}.html", "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  [debug] Saved screenshot+html -> data/debug/{label}.*")
    except Exception as e:
        print(f"  [debug] Could not save: {e}")


# ── Incremental scan ────────────────────────────────────────────────────────
# หยุด scroll เมื่อเจอรีวิวที่มีอยู่แล้วติดกันครบจำนวนนี้ (ไม่มีของใหม่แทรก)
# เรียง "ใหม่ล่าสุด" สำเร็จ → รีวิวใหม่อยู่บนสุดแน่นอน หยุดได้เร็ว
# เรียงไม่สำเร็จ → ลำดับเป็น "เกี่ยวข้องที่สุด" ต้องเผื่อมากขึ้น
KNOWN_STOP_SORTED = 10
KNOWN_STOP_UNSORTED = 25

# ── Deep scan ───────────────────────────────────────────────────────────────────
# โหมดเก็บรีวิวให้ครบที่สุด — ไม่สนใจ known_hashes ไม่มี early-stop
# หยุดด้วยเงื่อนไข 4 ข้อเท่านั้น: นับไม่โต / ครบ scroll / หมดเวลา / เจอสัญญาณบล็อก
DEEP_MAX_SCROLLS = 400          # กันวนไม่รู้จบ
DEEP_NO_GROWTH_LIMIT = 3        # จำนวน node ไม่โตติดกันกี่รอบถือว่าจบ
DEEP_TIME_BUDGET_SEC = 600      # เพดานเวลาต่อร้าน
DEEP_BLOCK_CHECK_EVERY = 20     # เช็คสัญญาณบล็อกทุกกี่ scroll
DEEP_REVIEW_CAP = 100_000       # cap ตอนดึงรีวิวครั้งเดียวหลังจบลูป (สูงจนเสมือนไม่จำกัด)


class DeepScanBlocked(Exception):
    """
    เจอสัญญาณบล็อกระหว่าง deep scroll — ต้องโยนออกนอกสุดทันที
    (เหตุผลที่ต้องเป็น exception: extract_reviews กับ scrape_place มี except Exception
    ครอบทั้งก้อน ถ้า return ธรรมดาสัญญาณจะถูกกลืนกลายเป็น "ไม่มีรีวิว" เฉยๆ)
    """

    def __init__(self, signal: str):
        super().__init__(signal)
        self.signal = signal


class DeepReviewsUnavailable(Exception):
    """
    เข้าไม่ถึง "หน้ารีวิว" ของร้าน — ต่างจาก "ร้านนี้ไม่มีรีวิว"

    เกิดเมื่อ: กดแท็บรีวิวไม่ติดทั้ง 2 วิธี  หรือ  scroll แล้วนับการ์ดรีวิวได้ 0
    ทั้งสองกรณีคือความล้มเหลว ห้ามนับว่า scrape สำเร็จ และห้ามตี deep_scanned_at
    (ไม่งั้นร้านที่พลาดจะถูกปิดตายถาวร ไม่ถูกหยิบมาทำใหม่อีกเลย)
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def review_text_hash(text: str) -> str:
    """
    คำนวณ hash กันรีวิวซ้ำ — ต้องตรงกับที่ scraper.py ใช้ตอน INSERT
    (ไม่งั้น early-stop จะเทียบไม่เจอของเดิม)

    ⚠️ สำคัญ: ต้อง hash จาก "ข้อความที่ล้างแล้ว" (text_clean) ไม่ใช่ข้อความดิบ
    เพราะข้อความดิบจาก Google มีวันที่แบบสัมพัทธ์ติดมาด้วย เช่น "7 เดือนที่แล้ว"
    พอ scrape รอบใหม่วันที่เลื่อนเป็น "8 เดือนที่แล้ว" → hash เปลี่ยน
    → ระบบนึกว่าเป็นรีวิวใหม่ แล้วบันทึกซ้ำ (เคยทำให้มีรีวิวซ้ำ 3,453 แถว)

    รีวิวที่ให้ดาวอย่างเดียว (ล้างแล้วเหลือว่าง) → ใช้ข้อความดิบแทน
    """
    raw = (text or "").strip()
    clean = clean_review_text(raw)[:1000] if raw else ""
    base = clean if clean else raw
    return hashlib.md5(base.encode("utf-8")).hexdigest()


async def _extract_visible_reviews(page: Page, cap: int) -> list[dict]:
    """ดึงรีวิวที่โหลดอยู่ใน DOM ตอนนี้ (ไม่ scroll) — ใช้เช็คระหว่าง scroll ทีละรอบ"""
    try:
        return await page.evaluate(f"""
            () => {{
                const results = [];
                const seen = new Set();
                const UI_SKIP = [
                    'ดาวน์โหลดแอป','ผลลัพธ์','ตัวกรองทั้งหมด',
                    'เขียนรีวิว','ค้นหารีวิว','บัญชี Google',
                ];
                const allEls = document.querySelectorAll('[aria-label]');
                const starEls = Array.from(allEls).filter(el => {{
                    const lbl = el.getAttribute('aria-label') || '';
                    return /^[1-5]\\s*(ดาว|star)/.test(lbl);
                }});
                starEls.forEach(starEl => {{
                    try {{
                        const label = starEl.getAttribute('aria-label') || '';
                        const match = label.match(/^([1-5])/);
                        const rating = match ? parseInt(match[1]) : null;
                        let container = starEl.parentElement;
                        for (let i = 0; i < 7; i++) {{
                            if (!container) break;
                            const text = (container.innerText || '').trim();
                            const hasUI = UI_SKIP.some(w => text.includes(w));
                            const key = text.substring(0, 60);
                            if (text.length >= 40 && text.length <= 1200 && !hasUI && !seen.has(key)) {{
                                seen.add(key);
                                let dateText = '';
                                container.querySelectorAll('span').forEach(s => {{
                                    const t = (s.innerText || '').trim();
                                    if (/(เดือน|สัปดาห์|วัน|ปี|ago|month|week|year)/i.test(t) && t.length < 35)
                                        dateText = t;
                                }});
                                results.push({{ rating, text: text.substring(0, 600), date: dateText }});
                                break;
                            }}
                            container = container.parentElement;
                        }}
                    }} catch(e) {{}}
                }});
                return results.slice(0, {cap});
            }}
        """)
    except Exception:
        return []


async def _count_review_nodes(page: Page) -> int:
    """
    นับจำนวน "การ์ดรีวิว" ที่โหลดอยู่ใน DOM ตอนนี้ — ใช้เป็นสัญญาณว่า scroll แล้วโตขึ้นไหม

    ตั้งใจให้ถูกกว่า _extract_visible_reviews มากๆ:
      - นับอย่างเดียว ไม่สร้าง array ข้อความ ไม่ไต่ parent ไม่อ่าน innerText
      - ค่าที่ได้ไม่เท่ากับจำนวนรีวิวสุดท้าย (ยังไม่ผ่านตัวกรอง) แต่ใช้ดู "การเติบโต" ได้
    """
    try:
        return await page.evaluate(r"""
            () => {
                let n = 0;
                document.querySelectorAll('[aria-label]').forEach(el => {
                    const lbl = el.getAttribute('aria-label') || '';
                    if (/^[1-5]\s*(ดาว|star)/.test(lbl)) n++;
                });
                return n;
            }
        """) or 0
    except Exception:
        return 0


def _trailing_known_count(raw_reviews: list[dict], known_hashes: set[str]) -> int:
    """
    นับว่ารีวิว "ท้ายรายการติดกัน" กี่อันที่เรามีอยู่แล้ว
    (เรียงใหม่ล่าสุด → ของใหม่อยู่บนสุด ถ้าท้ายๆ เป็นของเดิมยาวๆ = ไม่มีอะไรใหม่ให้เก็บอีก)
    """
    count = 0
    for item in reversed(raw_reviews):
        t = (item.get("text") or "").strip()[:500].strip()
        if review_text_hash(t) in known_hashes:
            count += 1
        else:
            break
    return count


async def reviews_feed_ready(page: Page) -> bool:
    """
    เข้าถึง "feed รีวิว" ได้จริงหรือยัง — ใช้ยืนยันผลหลังกดแท็บ
    หลักการ: กดติด != เข้าถึงได้ (เคยกดโดนปุ่ม "เขียนรีวิว" แล้วได้ modal login ค้างแทน)
    """
    try:
        kids = await page.evaluate(
            "() => { const f = document.querySelector('[role=feed]'); return f ? f.children.length : 0; }"
        )
        if kids and kids > 0:
            return True
    except Exception:
        pass
    return (await _count_review_nodes(page)) > 0


async def dismiss_login_modal(page: Page) -> None:
    """ปิด modal 'ลงชื่อเข้าใช้เพื่อเขียนรีวิว' ที่บังหน้าอยู่ด้วย Escape"""
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(1.0)
    except Exception:
        pass


async def open_reviews_tab(page: Page, allow_reload: bool = True) -> bool:
    """
    เปิดแท็บ "รีวิว" ของหน้าร้าน — คืน True เฉพาะเมื่อ "เข้าถึง feed ได้จริง"

    ทำไมต้องเขียนแบบนี้ (บั๊กที่เคยทำให้ได้ 0 รีวิวเงียบๆ ทั้ง refresh/discover/deep):
      เดิมใช้ page.locator('button', has_text="รีวิว").first เป็นวิธีหลัก
      has_text ของ Playwright จับแบบ substring → "เขียนรีวิว" แมตช์ด้วย
      และ Google เปลี่ยนแท็บรีวิวไปเป็น element อื่นที่ไม่ใช่ <button> แล้ว
      เหลือ <button> ที่มีคำนี้แค่ปุ่ม "เขียนรีวิว" → กดแล้วได้ modal login ค้าง
      feed ไม่ render → นับ node ได้ 0 ทุกร้าน

    4 ชั้น: role="tab" (ปุ่มเขียนรีวิวไม่มี role นี้) → <button> ที่ไม่มีคำว่า "เขียน"
            → ปิด modal ด้วย Escape แล้วลอง role="tab" ซ้ำ → reload หน้าแล้วลองใหม่ทั้งชุด
    ทุกชั้นยืนยันด้วย reviews_feed_ready() ก่อนถือว่าสำเร็จ
    """
    # ชั้น 1 (หลัก): แท็บจริงมี role="tab"
    try:
        tab = page.get_by_role("tab").filter(has_text="รีวิว").first
        if await tab.count() > 0:
            await tab.click(timeout=6000)
            await random_delay(2.0, 3.0)
            if await reviews_feed_ready(page):
                return True
    except Exception:
        pass

    # ชั้น 2 (fallback): <button> ที่มีคำว่า "รีวิว" แต่ต้องไม่ใช่ "เขียนรีวิว"
    try:
        buttons = page.locator("button", has_text="รีวิว")
        total = await buttons.count()
        for i in range(min(total, 5)):
            btn = buttons.nth(i)
            try:
                label = ((await btn.inner_text()) or "").strip()
            except Exception:
                continue
            if "เขียน" in label:          # ตัดปุ่มเขียนรีวิวออกเสมอ ไม่ว่ากรณีใด
                continue
            try:
                await btn.click(timeout=4000)
                await random_delay(2.0, 3.0)
            except Exception:
                continue
            if await reviews_feed_ready(page):
                return True
    except Exception:
        pass

    # ชั้น 3: อาจมี modal login ค้างบังอยู่ → Escape ปิดแล้วลองแท็บอีกครั้ง
    await dismiss_login_modal(page)
    try:
        tab = page.get_by_role("tab").filter(has_text="รีวิว").first
        if await tab.count() > 0:
            await tab.click(timeout=4000)
            await random_delay(2.0, 3.0)
            if await reviews_feed_ready(page):
                return True
    except Exception:
        pass

    # ชั้น 4: บางครั้ง Google render "แผงย่อ" ที่ไม่มีแท็บรีวิวเลย (เจอบ่อยกับหน้าร้านแรก
    # ที่เปิดในบราวเซอร์ใหม่) — วัดได้จริง: โหลดสดได้ ['ภาพรวม','เกี่ยวกับ'] แต่พอ reload
    # กลายเป็น ['ภาพรวม','เมนู','รีวิว','เกี่ยวกับ'] แล้วดึงรีวิวได้ตามปกติ
    # reload ครั้งเดียวแล้วลองทั้ง 3 ชั้นใหม่ (allow_reload=False กันวนซ้ำ)
    try:
        on_place_page = "/maps/place/" in (page.url or "")
    except Exception:
        on_place_page = False      # page ที่ไม่มี .url (เช่นตัวปลอมในเทสต์) → ไม่ reload

    if allow_reload and on_place_page:
        try:
            await page.reload(wait_until="domcontentloaded")
            await random_delay(3.0, 4.0)
            await wait_for_place_loaded(page, timeout=20000)
        except Exception:
            return False
        print("  ↻ แผงร้านไม่มีแท็บรีวิว — reload แล้วลองใหม่")
        return await open_reviews_tab(page, allow_reload=False)

    return False


async def _deep_scroll_collect(page: Page) -> list[dict]:
    """
    ลูป scroll ของโหมด deep — เก็บให้ครบที่สุดโดยไม่สนใจว่ามีรีวิวไหนอยู่ใน DB แล้ว

    หยุดเมื่อ: จำนวน node ไม่โตติดกันครบ DEEP_NO_GROWTH_LIMIT / ครบ DEEP_MAX_SCROLLS
              / ใช้เวลาเกิน DEEP_TIME_BUDGET_SEC
    ระหว่างทางเช็คสัญญาณบล็อกทุก DEEP_BLOCK_CHECK_EVERY รอบ — เจอแล้ว raise ทันที
    ดึงรีวิวจริงครั้งเดียวหลังจบลูป (ระหว่างลูปใช้แค่ตัวนับ node ซึ่งถูกกว่ามาก)
    """
    t0 = time.monotonic()
    node_count = await _count_review_nodes(page)
    no_growth = 0
    scrolls = 0
    stop_reason = f"ครบเพดาน {DEEP_MAX_SCROLLS} scroll"

    for i in range(1, DEEP_MAX_SCROLLS + 1):
        elapsed = time.monotonic() - t0
        if elapsed > DEEP_TIME_BUDGET_SEC:
            print(f"  ⚠️  deep: หมดเวลา {DEEP_TIME_BUDGET_SEC}s ที่ scroll {i - 1} รอบ "
                  f"(node {node_count}) — ร้านนี้อาจยังเก็บไม่ครบ")
            stop_reason = f"หมดเวลา {DEEP_TIME_BUDGET_SEC}s"
            break

        await scroll_reviews(page, times=1)
        scrolls = i
        count = await _count_review_nodes(page)

        if count <= node_count:
            no_growth += 1
            if no_growth >= DEEP_NO_GROWTH_LIMIT:
                stop_reason = f"โหลดครบ (node ไม่โต {DEEP_NO_GROWTH_LIMIT} รอบติด)"
                break
        else:
            no_growth = 0
        node_count = max(node_count, count)

        if i % DEEP_BLOCK_CHECK_EVERY == 0:
            blocked = await detect_block_signal(page)
            if blocked:
                raise DeepScanBlocked(blocked)
            print(f"  🔎 deep: scroll {i} รอบ | node {node_count} | {elapsed:.0f}s")

    # scroll จนจบแล้วยังนับการ์ดรีวิวไม่ได้เลย = เข้าไม่ถึง feed (ไม่ใช่ "ร้านไม่มีรีวิว")
    # เคสจริงที่เจอ: แท็บรีวิวกดติด (clicked=True) แต่ feed ไม่ render — หน้ามี [aria-label] 61 ตัว
    # แต่ไม่มี star label ของรีวิวสักอัน ทั้งที่ร้านนั้นมี 211 รีวิวใน DB
    if node_count == 0:
        raise DeepReviewsUnavailable(
            f"scroll {scrolls} รอบแล้วไม่พบการ์ดรีวิวเลย (feed ไม่ render)"
        )

    reviews = await _extract_visible_reviews(page, DEEP_REVIEW_CAP)
    print(f"  🧲 deep: จบที่ scroll {scrolls} รอบ | node {node_count} "
          f"| ดึงได้ {len(reviews)} | {time.monotonic() - t0:.0f}s | {stop_reason}")
    return reviews


async def extract_reviews(
    page: Page,
    max_reviews: int = 20,
    known_hashes: set[str] | None = None,
    deep: bool = False,
) -> list[dict]:
    """
    Extract reviews from the current place page.

    known_hashes: hash ของรีวิวที่มีอยู่แล้วในฐานข้อมูลของร้านนี้
      - ว่าง/None  → scan เต็ม (ร้านใหม่ หรือ scan ครั้งแรก)
      - มีค่า      → incremental: หยุด scroll ทันทีที่ชนกำแพงรีวิวเดิม

    deep=True: โหมดเก็บให้ครบ — เพิกเฉย known_hashes ทั้งหมด ไม่มี early-stop
      และไม่ตัดที่ max_reviews (ใช้ DEEP_REVIEW_CAP แทน)
      เจอสัญญาณบล็อกระหว่าง scroll → raise DeepScanBlocked
    """
    known_hashes = known_hashes or set()
    reviews = []
    try:
        # Step 1: เปิดแท็บ "รีวิว" — ยืนยันด้วยผลลัพธ์ (เข้าถึง feed ได้จริง) ไม่ใช่แค่ "กดติด"
        clicked_reviews = await open_reviews_tab(page)

        # เข้าไม่ถึงหน้ารีวิว = ยังอยู่หน้าภาพรวม ถ้าปล่อยผ่านจะไป scroll หน้าภาพรวม
        # แล้วคืน 0 รีวิวเงียบๆ แยกไม่ออกจาก "ร้านนี้ไม่มีรีวิวจริงๆ"
        if deep and not clicked_reviews:
            raise DeepReviewsUnavailable("เปิดแท็บรีวิวไม่สำเร็จทั้ง 3 วิธี (เข้าไม่ถึง feed)")

        # debug screenshot disabled (เปิดได้เมื่อต้องการ debug)
        # debug_dir = DATA_DIR / "debug"
        # debug_dir.mkdir(parents=True, exist_ok=True)
        # await page.screenshot(path=str(debug_dir / "after_reviews_tab.png"))

        # Step 2: Sort by Newest — หาจากข้อความ ไม่ใช่ index
        # sorted_ok บอกว่าเรียง "ใหม่ล่าสุด" สำเร็จไหม → ใช้ตัดสินว่า early-stop ได้เร็วแค่ไหน
        sorted_ok = False
        try:
            sort_btn = page.locator('button', has_text="จัดเรียง").first
            if await sort_btn.count() == 0:
                sort_btn = page.locator('button[aria-label*="Sort"], button[aria-label*="จัดเรียง"]').first
            if await sort_btn.count() > 0:
                await sort_btn.click(timeout=4000)
                await random_delay(0.8, 1.5)
                try:
                    options = page.locator('[role="menuitemradio"], [role="option"]')
                    count = await options.count()
                    clicked = False
                    # หา option ที่มีข้อความ "ล่าสุด" หรือ "Newest"
                    for i in range(count):
                        opt = options.nth(i)
                        txt = (await opt.inner_text()).strip()
                        if "ล่าสุด" in txt or "newest" in txt.lower() or "recent" in txt.lower():
                            await opt.click(timeout=3000)
                            clicked = True
                            sorted_ok = True     # เรียงตามใหม่ล่าสุดสำเร็จ
                            break
                    # ถ้าหาไม่เจอ → ใช้ index 1 (มักเป็น "ใหม่ล่าสุด" แต่ไม่การันตี)
                    if not clicked and count > 1:
                        await options.nth(1).click(timeout=3000)
                    await random_delay(1.5, 2.5)
                except Exception:
                    pass
        except Exception:
            pass

        # Step 3+4: scroll ทีละรอบ + ดึงรีวิว + เช็คว่าชนกำแพงรีวิวเดิมหรือยัง
        if deep:
            # โหมด deep — ลูปแยกคนละตัว ไม่แตะ known_hashes / ไม่ตัดที่ max_reviews
            raw_reviews: list[dict] = await _deep_scroll_collect(page)
        else:
            # เดิม: scroll รวดเดียวสูงสุด 60 รอบ แล้วค่อยดึง → ช้ามากแม้ไม่มีรีวิวใหม่เลย
            # ใหม่: ดึงหลัง scroll ทุกรอบ ถ้าเจอรีวิวเดิมติดกันครบเกณฑ์ → หยุดทันที
            max_scrolls = max(2, min(60, max_reviews // 4))
            stop_threshold = KNOWN_STOP_SORTED if sorted_ok else KNOWN_STOP_UNSORTED
            cap = max_reviews * 3
            raw_reviews: list[dict] = await _extract_visible_reviews(page, cap)

            no_growth = 0
            for _ in range(max_scrolls):
                # ชนกำแพงรีวิวเดิมแล้ว = ไม่มีของใหม่ให้เก็บอีก → หยุดประหยัดเวลา
                if known_hashes and _trailing_known_count(raw_reviews, known_hashes) >= stop_threshold:
                    print(f"  ⏩ หยุดเร็ว — เจอรีวิวเดิมติดกัน {stop_threshold} อัน (ไม่มีรีวิวใหม่)")
                    break
                if len(raw_reviews) >= cap:
                    break

                before = len(raw_reviews)
                await scroll_reviews(page, times=1)
                raw_reviews = await _extract_visible_reviews(page, cap)

                # scroll แล้วไม่ได้รีวิวเพิ่ม 2 รอบติด = โหลดครบแล้ว
                if len(raw_reviews) <= before:
                    no_growth += 1
                    if no_growth >= 2:
                        break
                else:
                    no_growth = 0

        # Step 5: Filter and clean
        # โหมด deep ไม่ตัดที่ max_reviews (คงพฤติกรรมเดิมเป๊ะเมื่อ deep=False)
        limit = DEEP_REVIEW_CAP if deep else max_reviews
        seen_texts = set()
        for item in raw_reviews:
            try:
                rating = item.get("rating")
                text = item.get("text", "").strip()
                date = item.get("date", "")

                # Skip duplicates
                key = text[:60]
                if key in seen_texts:
                    continue
                seen_texts.add(key)

                # Skip if text is too short
                if len(text) < 20:
                    continue

                # Skip clear Google Maps UI fragments
                ui_patterns = [
                    "เขียนรีวิว", "ค้นหารีวิว", "ผลลัพธ์",
                    "ดาวน์โหลดแอป", "ตัวกรองทั้งหมด", "บัญชี Google",
                ]
                if any(p in text for p in ui_patterns):
                    continue

                # Skip summary lines like "(1,359)" indicating review count widgets
                import re as _re
                if _re.search(r'\(\d{3,}\)', text):
                    continue

                # Skip if text is mostly reviewer metadata with no actual review content
                # (Local Guide line alone = short, e.g. "Local Guide · 12 รีวิว")
                if "Local Guide" in text and len(text) < 60:
                    continue

                # เก็บทุกดาว (1-5) เพื่อข้อมูลมากขึ้น
                # (เดิมกรองแค่ 1-3 ดาว)

                reviews.append({
                    "rating": rating,
                    "text": text[:500],
                    "date": date,
                })

                if len(reviews) >= limit:
                    break
            except Exception:
                continue

    except (DeepScanBlocked, DeepReviewsUnavailable):
        # สัญญาณบล็อก/เข้าไม่ถึงหน้ารีวิว ต้องทะลุออกไปให้ scrape_place จัดการ
        # ห้ามให้ except Exception ข้างล่างกลืนจนกลายเป็น "ได้ 0 รีวิว" เฉยๆ
        raise
    except Exception as e:
        print(f"  Warning: {e}")

    return reviews


async def detect_block_signal(page: Page) -> str | None:
    """
    ตรวจ "สัญญาณบล็อกจริง" จากหน้าเว็บ — แม่นกว่าการเดาจาก "ไม่มีรีวิวใหม่"
    (เพราะ incremental scan ที่ทำงานถูกต้องก็ได้ 0 รีวิวใหม่เป็นปกติ)

    คืนข้อความบอกชนิดของบล็อกถ้าเจอ, None ถ้าปกติ
    """
    try:
        # 1) CAPTCHA / reCAPTCHA / "unusual traffic" — บล็อกชัดเจนที่สุด
        block_texts = [
            "unusual traffic", "การเข้าชมที่ผิดปกติ",
            "ระบบตรวจพบการรับส่งข้อมูล", "our systems have detected",
            "verify you're not a robot", "ยืนยันว่าคุณไม่ใช่หุ่นยนต์",
        ]
        body = (await page.evaluate("() => document.body ? document.body.innerText.slice(0,3000) : ''")) or ""
        low = body.lower()
        for t in block_texts:
            if t.lower() in low:
                return f"block-page ('{t}')"

        # 2) reCAPTCHA iframe
        if await page.locator('iframe[src*="recaptcha"]').count() > 0:
            return "recaptcha"

        # 3) หน้าเปล่า/สั้นผิดปกติ (โดน redirect ไป sorry page)
        url = page.url
        if "google.com/sorry" in url or "/sorry/" in url:
            return "sorry-page"
    except Exception:
        pass
    return None


async def wait_for_place_loaded(page: Page, timeout: int = 20000) -> bool:
    """Wait for Google Maps place page to fully load using multiple strategies."""
    # Strategy 1: URL changes to include /place/
    try:
        await page.wait_for_url(re.compile(r"/maps/place/|/maps/search/"), timeout=timeout)
        await asyncio.sleep(2.0)
        return True
    except Exception:
        pass

    # Strategy 2: Any of these elements appear (place panel loaded)
    selectors = [
        'h1',                          # place name heading
        '[role="main"] button',        # buttons in main panel
        '.fontHeadlineLarge',          # place name class
        '[aria-label*="รีวิว"]',       # reviews tab (Thai)
        '[aria-label*="Review"]',      # reviews tab (English)
        'button[jsaction*="review"]',  # review button
        '.DUwDvf',                     # place name div
        '[data-item-id]',              # place info items
    ]
    for sel in selectors:
        try:
            await page.wait_for_selector(sel, timeout=8000)
            await asyncio.sleep(1.5)
            return True
        except Exception:
            continue

    return False


async def scrape_place(
    page: Page,
    place_name: str,
    max_reviews: int = MAX_REVIEWS_PER_PLACE,
    known_hashes: set[str] | None = None,
    deep: bool = False,
) -> dict | None:
    """
    Search for a place and scrape its reviews. max_reviews ต่ำ = เร็ว (ใช้ตอน discover)
    known_hashes = hash รีวิวที่มีอยู่แล้วของร้านนี้ → เปิดโหมด incremental (หยุดเร็วถ้าไม่มีของใหม่)
    deep = True → เก็บให้ครบที่สุด (เพิกเฉย known_hashes) ดู extract_reviews
    """
    print(f"\n  Searching: {place_name}")

    try:
        # Search directly via URL for more reliable loading
        search_url = f"https://www.google.com/maps/search/{place_name.replace(' ', '+')}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await random_delay(2.0, 4.0)

        # B3: ตรวจสัญญาณบล็อกจริง (CAPTCHA / sorry-page) — คืน sentinel ให้ผู้เรียกจัดการ
        blocked = await detect_block_signal(page)
        if blocked:
            print(f"  🛑 เจอสัญญาณบล็อก: {blocked}")
            return {"_blocked": blocked}

        # If results list appears (multiple places), click first result
        try:
            first_result = page.locator('a[href*="/maps/place/"]').first
            if await first_result.count() > 0:
                await first_result.click(timeout=5000)
                await random_delay(2.0, 3.0)
        except Exception:
            pass

        # Wait for place panel to load
        loaded = await wait_for_place_loaded(page, timeout=20000)
        if not loaded:
            print(f"  [skip] Could not load place page: {place_name}")
            return None

        # Get place name from page
        _UI_NAMES = {"ผลลัพธ์", "แผนที่", "ภาพรวม", "รีวิว", "ใกล้เคียง", "ค้นหา", "เส้นทาง"}
        actual_name = place_name  # default = search query
        for sel in ['.fontHeadlineLarge', '.DUwDvf', 'h1']:
            try:
                elem = await page.query_selector(sel)
                if elem:
                    text = (await elem.inner_text()).strip()
                    # Accept only if it looks like a real place name
                    if text and len(text) > 3 and text not in _UI_NAMES:
                        actual_name = text
                        break
            except Exception:
                continue

        # Get coordinates from URL
        await random_delay(0.5, 1.5)
        coords = await extract_place_coords(page)

        # Get overall rating
        overall_rating = "N/A"
        for sel in ['.fontDisplayLarge', '.F7nice span', '[aria-label*="คะแนน"]', '[aria-label*="star"]']:
            try:
                elem = await page.query_selector(sel)
                if elem:
                    text = await elem.inner_text()
                    if text.strip():
                        overall_rating = text.strip()
                        break
            except Exception:
                continue

        # Get Google-assigned category (e.g. "ร้านกาแฟ", "ร้านอาหารไทย")
        google_category = None
        for sel in ['.DkEaL', 'button[jsaction*="category"]', '[jsaction*="pane.rating.category"]']:
            try:
                elem = await page.query_selector(sel)
                if elem:
                    text = (await elem.inner_text()).strip()
                    if text and len(text) < 60:
                        google_category = text
                        break
            except Exception:
                continue

        # Get opening hours + price level + สถานะร้าน (best-effort)
        opening_hours = await extract_opening_hours(page)
        price_level = await extract_price_level(page)
        business_status = await extract_business_status(page)

        print(f"  Found: {actual_name} | Rating: {overall_rating} | Category: {google_category} | Status: {business_status} | Coords: {coords}")

        # debug screenshot disabled (เปิดได้เมื่อต้องการ debug)
        # safe_name = re.sub(r'[^\w]', '_', actual_name)[:20]
        # await debug_page(page, f"before_reviews_{safe_name}")

        # Scrape reviews — ข้ามถ้า max_reviews <= 0 (โหมด discover เร็ว)
        reviews_failed: str | None = None
        if max_reviews > 0:
            try:
                reviews = await extract_reviews(
                    page, max_reviews=max_reviews, known_hashes=known_hashes, deep=deep
                )
                print(f"  Collected {len(reviews)} reviews")
            except DeepReviewsUnavailable as e:
                # ยังคืนข้อมูลร้าน (ชื่อ/พิกัด/หมวด/เวลาทำการ) ให้บันทึกได้ตามปกติ
                # แต่ติดธงไว้ว่า "รีวิวล้มเหลว" เพื่อไม่ให้ถูกนับว่า deep scan สำเร็จ
                reviews = []
                reviews_failed = e.reason
                print(f"  ⚠️  เข้าไม่ถึงหน้ารีวิว: {e.reason}")
        else:
            reviews = []
            print(f"  Skipped reviews (discover mode)")

        return {
            "place_name": actual_name,
            "search_query": place_name,
            "overall_rating": overall_rating,
            "google_category": google_category,
            "opening_hours": opening_hours,
            "price_level": price_level,
            "business_status": business_status,
            "lat": coords[0] if coords else None,
            "lng": coords[1] if coords else None,
            "reviews": reviews,
            "_reviews_failed": reviews_failed,
            "scraped_at": datetime.now().isoformat(),
        }

    except DeepScanBlocked as e:
        # เจอบล็อกระหว่าง deep scroll → คืน sentinel เดียวกับที่ตรวจตอนเปิดหน้า
        print(f"  🛑 เจอสัญญาณบล็อกระหว่าง deep scroll: {e.signal}")
        return {"_blocked": e.signal}
    except Exception as e:
        print(f"  ❌ Error scraping {place_name}: {e}")
        return None


# Query หลายประเภทที่จะค้นหาใน Google Maps
DISCOVER_QUERIES = [
    "สถานที่ท่องเที่ยว พิษณุโลก",
    "คาเฟ่ พิษณุโลก",
]


async def run_scraper(
    places: list[str] = None,
    headless: bool = True,
    max_places: int = None,
    auto_discover: bool = True,
    discover_query: str | None = None,
    max_reviews: int = MAX_REVIEWS_PER_PLACE,
    known_hashes_by_place: dict[str, set[str]] | None = None,
    deep: bool = False,
) -> list[dict]:
    """
    Main scraper function. max_reviews ต่ำ = เก็บร้านเร็ว (โหมด discover)
    known_hashes_by_place: {ชื่อร้าน: set(hash รีวิวที่มีแล้ว)} → เปิด incremental scan
    deep=True: เก็บให้ครบที่สุด (ผู้เรียกคือ run_deep_scan ซึ่งส่งมาทีละร้าน)
      - เจอบล็อกร้านแรกก็หยุดรอบทันที (ไม่รอให้ครบ 2 ร้านเหมือนโหมดปกติ
        เพราะทีละร้าน = ไม่มีร้านที่ 2 ให้นับ) แล้วคืนผลที่เก็บมาได้ติดไปด้วย
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=random.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            ]),
            viewport={"width": 1280, "height": 800},
            locale="th-TH",
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
        page = await context.new_page()

        # Auto-discover places
        if places is None:
            if auto_discover:
                queries = [discover_query] if discover_query else DISCOVER_QUERIES
                per_query = max(10, (max_places or 60) // len(queries))
                all_places: list[str] = []
                seen: set[str] = set()
                for query in queries:
                    found = await discover_places(page, query=query, max_places=per_query)
                    for p_name in found:
                        if p_name not in seen:
                            seen.add(p_name)
                            all_places.append(p_name)
                    print(f"  [{query}] → {len(found)} places (รวม {len(all_places)} ไม่ซ้ำ)")
                places = all_places
            if not places:
                places = PHITSANULOK_PLACES_FALLBACK

        if max_places:
            places = places[:max_places]

        results = []
        block_streak = 0   # นับร้านที่เจอสัญญาณบล็อกติดกัน
        for i, place in enumerate(places):
            print(f"\n[{i+1}/{len(places)}] Processing...")
            place_hashes = (known_hashes_by_place or {}).get(place)
            result = await scrape_place(
                page, place, max_reviews=max_reviews, known_hashes=place_hashes, deep=deep
            )

            # B3: เจอสัญญาณบล็อกจริง → หยุดทั้งรอบทันที ส่งสัญญาณให้ auto_refresh พัก
            if result and result.get("_blocked"):
                block_streak += 1
                # deep = ส่งมาทีละร้าน จึงต้องรายงานตั้งแต่ร้านแรก (ตัวนับ "ติดกัน 2 ร้าน"
                # ย้ายไปอยู่ที่ run_deep_scan ซึ่งเห็นภาพข้ามร้าน)
                if block_streak >= (1 if deep else 2):
                    print(f"  🛑 เจอบล็อกติดกัน {block_streak} ร้าน — หยุด scrape รอบนี้")
                    await browser.close()
                    # deep: ร้านละหลายนาที ทิ้งผลที่เก็บมาแล้วไม่คุ้ม → ส่งกลับไปบันทึกด้วย
                    return ([*results, {"_blocked": result["_blocked"]}] if deep
                            else [{"_blocked": result["_blocked"]}])
                continue
            block_streak = 0

            if result:
                # กรองเฉพาะสถานที่ในพิษณุโลก
                if not is_in_phitsanulok(result.get("lat"), result.get("lng")):
                    print(f"  [skip] Outside Phitsanulok bbox: {result['place_name']} ({result.get('lat')}, {result.get('lng')})")
                else:
                    results.append(result)
                    save_results(results, "phitsanulok_reviews_inprogress.json")

            if i < len(places) - 1:
                delay = random.uniform(8.0, 16.0)  # B1: หน่วงนานขึ้นลดโอกาสโดนบล็อก
                print(f"  ⏳ Waiting {delay:.1f}s...")
                await asyncio.sleep(delay)

        await browser.close()
        return results

    return []


async def _run_scraper_old(places: list[str] = None, headless: bool = True, max_places: int = None) -> list[dict]:
    """Legacy — kept for reference."""
    if places is None:
        places = PHITSANULOK_PLACES_FALLBACK
    if max_places:
        places = places[:max_places]

    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = await browser.new_context(
            user_agent=random.choice([
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
            ]),
            viewport={"width": 1280, "height": 800},
            locale="th-TH",
        )

        # Stealth: hide webdriver flag
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

        page = await context.new_page()

        for i, place in enumerate(places):
            print(f"\n[{i+1}/{len(places)}] Processing...")
            result = await scrape_place(page, place)
            if result:
                results.append(result)

            # Longer delay between places
            if i < len(places) - 1:
                delay = random.uniform(8.0, 16.0)  # B1: หน่วงนานขึ้นลดโอกาสโดนบล็อก
                print(f"  ⏳ Waiting {delay:.1f}s before next place...")
                await asyncio.sleep(delay)

        await browser.close()

    return results


ACCUMULATED_FILE = DATA_DIR / "phitsanulok_accumulated.json"
_UI_NAMES = {"ผลลัพธ์", "แผนที่", "ภาพรวม", "รีวิว", "ใกล้เคียง", "ค้นหา", "เส้นทาง", "บันทึก"}


def _is_valid_place(entry: dict) -> bool:
    """Return True if entry looks like a real place (not UI garbage)."""
    name = entry.get("place_name", "")
    if not name or len(name) <= 3 or name in _UI_NAMES:
        return False
    if not is_in_phitsanulok(entry.get("lat"), entry.get("lng")):
        return False
    return True


def _merge_reviews(existing: list[dict], new: list[dict]) -> list[dict]:
    """
    รวมรีวิว 2 ชุดโดยกันซ้ำด้วย "กติกาเดียวกับ DB" — md5 ของข้อความที่ล้างแล้ว

    ⚠️ เดิมใช้ text[:80] ของข้อความ "ดิบ" ซึ่งมีวันที่สัมพัทธ์ฝังอยู่ต้นข้อความ
    พอ scrape รอบใหม่วันที่เลื่อน ("4 เดือนที่แล้ว" → "5 เดือนที่แล้ว")
    80 ตัวอักษรแรกก็เปลี่ยน → มองเป็นรีวิวใหม่แล้ว append ซ้ำเข้าไปเรื่อย ๆ
    (สะสมจนไฟล์ master พองเกินจริง 7,084 รายการ ทั้งที่ DB ถูกต้องอยู่แล้ว)
    เป็นบั๊กชนิดเดียวกับที่เคยทำให้ DB มีรีวิวซ้ำ 3,453 แถว — ดู review_text_hash()
    """
    def _key(r: dict) -> str:
        t = (r.get("text") or "").strip()
        return review_text_hash(t) if t else ""

    seen = {_key(r) for r in existing}
    seen.discard("")
    combined = list(existing)
    for r in new:
        k = _key(r)
        if k and k not in seen:
            seen.add(k)
            combined.append(r)
    return combined


def save_results(results: list[dict], filename: str = None) -> Path:
    """
    Save new scrape results AND merge them into the accumulated master file.
    The timestamped file is kept as a backup; the master file grows over time.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. Save timestamped backup ───────────────────────────────────────────
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"phitsanulok_reviews_{timestamp}.json"
    backup_path = DATA_DIR / filename
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # ── 2. Load existing accumulated master ──────────────────────────────────
    master: dict[str, dict] = {}
    if ACCUMULATED_FILE.exists():
        try:
            with open(ACCUMULATED_FILE, encoding="utf-8") as f:
                for entry in json.load(f):
                    name = entry.get("place_name", "")
                    if name:
                        master[name] = entry
        except Exception as e:
            print(f"  ⚠️  Could not read accumulated file: {e}")

    # ── 3. Merge new results in ──────────────────────────────────────────────
    added, updated, skipped = 0, 0, 0
    for entry in results:
        if not _is_valid_place(entry):
            print(f"  [skip] '{entry.get('place_name','')}' — invalid/outside bbox")
            skipped += 1
            continue
        name = entry["place_name"]
        if name not in master:
            master[name] = entry
            added += 1
        else:
            # Combine reviews from both sources (don't discard old reviews)
            old_reviews = master[name].get("reviews", [])
            new_reviews = entry.get("reviews", [])
            master[name]["reviews"] = _merge_reviews(old_reviews, new_reviews)
            # Update lat/lng if new scrape found coordinates and old didn't
            if entry.get("lat") and not master[name].get("lat"):
                master[name]["lat"] = entry["lat"]
                master[name]["lng"] = entry["lng"]
            master[name]["scraped_at"] = entry["scraped_at"]
            updated += 1

    # ── 4. Save updated master ───────────────────────────────────────────────
    accumulated = list(master.values())
    with open(ACCUMULATED_FILE, "w", encoding="utf-8") as f:
        json.dump(accumulated, f, ensure_ascii=False, indent=2)

    total_reviews = sum(len(e.get("reviews", [])) for e in accumulated)
    print(f"\n✅ Accumulated: {len(accumulated)} places, {total_reviews} reviews total")
    print(f"   (+{added} new places, {updated} updated, {skipped} skipped)")
    print(f"   Master file → {ACCUMULATED_FILE}")
    return backup_path


def load_latest_results() -> list[dict] | None:
    """Load the accumulated master file (preferred) or fall back to latest timestamped file."""
    if ACCUMULATED_FILE.exists():
        with open(ACCUMULATED_FILE, encoding="utf-8") as f:
            return json.load(f)
    files = sorted(DATA_DIR.glob("phitsanulok_reviews_*.json"), reverse=True)
    if not files:
        return None
    with open(files[0], encoding="utf-8") as f:
        return json.load(f)


def load_all_results() -> list[dict] | None:
    """
    Load accumulated master file.
    Falls back to merging old timestamped files if master doesn't exist yet.
    """
    if ACCUMULATED_FILE.exists():
        with open(ACCUMULATED_FILE, encoding="utf-8") as f:
            data = json.load(f)
        total = sum(len(e.get("reviews", [])) for e in data)
        print(f"  📂 Loaded accumulated: {len(data)} places, {total} reviews")
        return data if data else None

    # First-time migration: build master from old timestamped files
    files = sorted(DATA_DIR.glob("phitsanulok_reviews_*.json"))
    if not files:
        return None

    print(f"  📂 First run: migrating {len(files)} old file(s) into accumulated master...")
    master: dict[str, dict] = {}
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                for entry in json.load(f):
                    if not _is_valid_place(entry):
                        continue
                    name = entry["place_name"]
                    if name not in master:
                        master[name] = entry
                    else:
                        master[name]["reviews"] = _merge_reviews(
                            master[name].get("reviews", []),
                            entry.get("reviews", []),
                        )
        except Exception as e:
            print(f"  ⚠️  Could not read {path.name}: {e}")

    if not master:
        return None

    accumulated = list(master.values())
    with open(ACCUMULATED_FILE, "w", encoding="utf-8") as f:
        json.dump(accumulated, f, ensure_ascii=False, indent=2)
    total = sum(len(e.get("reviews", [])) for e in accumulated)
    print(f"  ✅ Migrated → {len(accumulated)} places, {total} reviews → {ACCUMULATED_FILE}")
    return accumulated


def scrape(headless: bool = True, max_places: int = None, use_demo_data: bool = False, auto_discover: bool = True) -> list[dict]:
    """Discover new places and scrape them."""
    if use_demo_data:
        print("📦 Using demo data (no actual scraping)")
        return _generate_demo_data()

    results = asyncio.run(run_scraper(headless=headless, max_places=max_places, auto_discover=auto_discover))
    if results:
        save_results(results)
    return results


def scrape_existing(headless: bool = True, max_places: int = None) -> list[dict]:
    """
    Re-scrape places already in the accumulated master file to collect more reviews.
    Prioritises places that were scraped longest ago (oldest scraped_at first).
    New reviews are merged in — nothing is discarded.
    """
    if not ACCUMULATED_FILE.exists():
        print("⚠️  No accumulated file found — run --scrape first to collect places")
        return []

    with open(ACCUMULATED_FILE, encoding="utf-8") as f:
        existing = json.load(f)

    # Sort oldest-refreshed first so --places N always rotates through the queue
    existing_sorted = sorted(
        existing,
        key=lambda e: e.get("scraped_at", ""),  # ISO string sorts correctly
    )

    place_names = [e.get("place_name", "") for e in existing_sorted if e.get("place_name")]

    total = len(place_names)
    if max_places:
        place_names = place_names[:max_places]
        print(f"🔄 Refreshing {len(place_names)} of {total} places (oldest first)...")
    else:
        print(f"🔄 Refreshing ALL {total} places...")

    results = asyncio.run(run_scraper(headless=headless, places=place_names, auto_discover=False))
    if results:
        save_results(results)
    return results


def reset_data(keep_backups: bool = False) -> dict:
    """
    Clear all scraped and analysis data.
    - keep_backups=False  → delete everything (full reset)
    - keep_backups=True   → delete only master + analysis files, keep timestamped backups
    Returns a dict summarising what was deleted.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    deleted = []

    # Files that are always cleared
    always_clear = [
        ACCUMULATED_FILE,
        DATA_DIR / "phitsanulok_reviews_inprogress.json",
        DATA_DIR / "analysis_results_real.json",
        DATA_DIR / "analysis_results_demo.json",
        DATA_DIR / "analysis_results.json",
    ]
    for path in always_clear:
        if path.exists():
            path.unlink()
            deleted.append(path.name)

    # Timestamped backup files (only if not keeping them)
    if not keep_backups:
        for path in DATA_DIR.glob("phitsanulok_reviews_*.json"):
            path.unlink()
            deleted.append(path.name)

    # Debug screenshots
    debug_dir = DATA_DIR / "debug"
    if debug_dir.exists():
        for f in debug_dir.glob("*.png"):
            f.unlink()
            deleted.append(f"debug/{f.name}")

    return {"deleted": deleted, "count": len(deleted)}


def _generate_demo_data() -> list[dict]:
    """Generate realistic demo data for testing the pipeline without scraping."""
    demo_places = [
        {
            "place_name": "วัดพระศรีรัตนมหาธาตุวรมหาวิหาร (วัดใหญ่)",
            "search_query": "วัดพระศรีรัตนมหาธาตุวรมหาวิหาร พิษณุโลก",
            "overall_rating": "4.6",
            "lat": 16.8258,
            "lng": 100.2654,
            "reviews": [
                {"rating": 2, "text": "ที่จอดรถไม่เพียงพอมากๆ โดยเฉพาะช่วงวันหยุด ต้องเดินไกลมาก แดดร้อนมากด้วย", "date": "1 เดือนที่แล้ว"},
                {"rating": 1, "text": "มีคนขายของรุมล้อมนักท่องเที่ยว รู้สึกอึดอัดมาก ไม่สบายใจเลย บรรยากาศไม่ดี", "date": "2 สัปดาห์ที่แล้ว"},
                {"rating": 3, "text": "ห้องน้ำสกปรกมาก กลิ่นแรง ไม่มีคนทำความสะอาด ต้องปรับปรุงด่วน", "date": "3 เดือนที่แล้ว"},
                {"rating": 2, "text": "ป้ายบอกทางน้อยมาก หาทางไม่เจอ ไม่มีเจ้าหน้าที่ช่วยแนะนำ", "date": "1 เดือนที่แล้ว"},
                {"rating": 2, "text": "นักท่องเที่ยวแน่นมากจนเดินไม่ได้ ควรจำกัดจำนวนคน โดยเฉพาะวันเสาร์-อาทิตย์", "date": "2 เดือนที่แล้ว"},
                {"rating": 1, "text": "โดนคนขายของหลอกราคา ระวังด้วย ราคาไม่ตรงกับป้าย", "date": "3 สัปดาห์ที่แล้ว"},
            ],
            "scraped_at": datetime.now().isoformat(),
        },
        {
            "place_name": "อุทยานแห่งชาติทุ่งแสลงหลวง",
            "search_query": "อุทยานแห่งชาติทุ่งแสลงหลวง",
            "overall_rating": "4.4",
            "lat": 16.9801,
            "lng": 100.9012,
            "reviews": [
                {"rating": 2, "text": "ถนนเข้าอุทยานเป็นหลุมเป็นบ่อมาก รถเล็กเข้าลำบากมาก ควรซ่อมแซมด่วน", "date": "2 เดือนที่แล้ว"},
                {"rating": 3, "text": "สัญญาณโทรศัพท์ไม่มีเลย ทำให้ติดต่อฉุกเฉินไม่ได้ อันตรายมาก", "date": "1 เดือนที่แล้ว"},
                {"rating": 1, "text": "ห้องพักในอุทยานทรุดโทรมมาก เครื่องปรับอากาศพัง น้ำร้อนไม่มี แต่คิดราคาแพง", "date": "5 เดือนที่แล้ว"},
                {"rating": 2, "text": "ขยะเยอะมากตามเส้นทางเดินป่า นักท่องเที่ยวไม่ค่อยรับผิดชอบ เจ้าหน้าที่ก็น้อย", "date": "1 เดือนที่แล้ว"},
                {"rating": 3, "text": "แผนที่เดินป่าไม่ชัดเจน หลงทางเกือบ ควรมีป้ายบอกทางมากกว่านี้", "date": "3 เดือนที่แล้ว"},
            ],
            "scraped_at": datetime.now().isoformat(),
        },
        {
            "place_name": "พระราชวังจันทน์",
            "search_query": "พระราชวังจันทน์ พิษณุโลก",
            "overall_rating": "4.3",
            "lat": 16.8198,
            "lng": 100.2601,
            "reviews": [
                {"rating": 2, "text": "ไม่มีร้านอาหารหรือของกินในบริเวณใกล้เคียงเลย หิวแต่ไม่รู้จะไปกินที่ไหน", "date": "2 สัปดาห์ที่แล้ว"},
                {"rating": 3, "text": "ข้อมูลประวัติศาสตร์น้อยมาก ป้ายอธิบายสั้น ไม่รู้สึกถึงความสำคัญของสถานที่", "date": "1 เดือนที่แล้ว"},
                {"rating": 2, "text": "ปิดบางส่วนเพื่อซ่อมแซมแต่ไม่มีการแจ้งล่วงหน้า เสียเที่ยวไป", "date": "3 เดือนที่แล้ว"},
                {"rating": 1, "text": "ที่นั่งพักไม่มีเลย ร้อนมากแต่หาร่มเงาไม่ได้ ผู้สูงอายุมาเที่ยวลำบากมาก", "date": "2 เดือนที่แล้ว"},
            ],
            "scraped_at": datetime.now().isoformat(),
        },
        {
            "place_name": "ถนนคนเดินพิษณุโลก",
            "search_query": "ถนนคนเดินพิษณุโลก",
            "overall_rating": "4.1",
            "lat": 16.8234,
            "lng": 100.2672,
            "reviews": [
                {"rating": 2, "text": "ของกินราคาแพงกว่าตลาดทั่วไปมาก คุณภาพก็ไม่ได้ต่างกัน ไม่คุ้มค่า", "date": "1 เดือนที่แล้ว"},
                {"rating": 3, "text": "จอดรถหายากมาก ถนนแคบ คนเยอะ เดินลำบาก ควรทำที่จอดรถเพิ่ม", "date": "3 สัปดาห์ที่แล้ว"},
                {"rating": 2, "text": "สินค้ากับตลาดนัดอื่นไม่ต่างกัน ไม่มีความเป็นเอกลักษณ์ของพิษณุโลกเลย", "date": "2 เดือนที่แล้ว"},
                {"rating": 1, "text": "ขยะเยอะหลังปิดงาน กลิ่นเหม็น ทางเดินลื่นมาก ควรจัดการความสะอาดให้ดีกว่านี้", "date": "1 เดือนที่แล้ว"},
                {"rating": 2, "text": "ห้องน้ำสาธารณะน้อยมาก ต้องเข้าคิวรอนานมาก โดยเฉพาะผู้หญิง", "date": "2 สัปดาห์ที่แล้ว"},
            ],
            "scraped_at": datetime.now().isoformat(),
        },
        {
            "place_name": "น้ำตกแก่งซอง",
            "search_query": "น้ำตกแก่งซอง พิษณุโลก",
            "overall_rating": "4.0",
            "lat": 16.7654,
            "lng": 100.8234,
            "reviews": [
                {"rating": 2, "text": "ทางเดินลงน้ำตกชันและลื่นมาก ไม่มีราวจับ อันตรายมากสำหรับผู้สูงอายุและเด็ก", "date": "1 เดือนที่แล้ว"},
                {"rating": 1, "text": "น้ำน้อยมากช่วงหน้าแล้ง ไม่คุ้มค่าเดินทาง ควรมีข้อมูลฤดูกาลที่เหมาะสม", "date": "4 เดือนที่แล้ว"},
                {"rating": 3, "text": "ขยะพลาสติกตามลำน้ำเยอะมาก เสียความสวยงาม ควรมีมาตรการเข้มงวดกว่านี้", "date": "2 เดือนที่แล้ว"},
                {"rating": 2, "text": "ไม่มีสิ่งอำนวยความสะดวกเลย ไม่มีร้านค้า ไม่มีที่นั่ง มาแล้วต้องกลับเลย", "date": "3 เดือนที่แล้ว"},
            ],
            "scraped_at": datetime.now().isoformat(),
        },
        {
            "place_name": "พิพิธภัณฑ์สถานแห่งชาติพิษณุโลก",
            "search_query": "พิพิธภัณฑ์สถานแห่งชาติพิษณุโลก",
            "overall_rating": "4.2",
            "lat": 16.8112,
            "lng": 100.2589,
            "reviews": [
                {"rating": 2, "text": "ป้ายอธิบายโบราณวัตถุมีแต่ภาษาไทย ไม่มีภาษาอังกฤษเลย นักท่องเที่ยวต่างชาติสับสน", "date": "2 เดือนที่แล้ว"},
                {"rating": 3, "text": "แอร์เย็นเกินไปในบางส่วน แต่บางห้องร้อนมาก การควบคุมอุณหภูมิไม่สม่ำเสมอ", "date": "1 เดือนที่แล้ว"},
                {"rating": 2, "text": "ของที่ระลึกราคาแพงมาก ไม่มีของราคาย่อมเยา เหมาะสำหรับนักท่องเที่ยวทุกระดับ", "date": "3 เดือนที่แล้ว"},
                {"rating": 1, "text": "เปิดเวลาสั้นมาก และปิดวันจันทร์-อังคาร ไม่เหมาะสำหรับนักท่องเที่ยวที่มีเวลาน้อย", "date": "1 เดือนที่แล้ว"},
            ],
            "scraped_at": datetime.now().isoformat(),
        },
    ]

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    save_path = DATA_DIR / "phitsanulok_reviews_demo.json"
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(demo_places, f, ensure_ascii=False, indent=2)

    total = sum(len(p["reviews"]) for p in demo_places)
    print(f"✅ Generated demo data: {len(demo_places)} places, {total} reviews → {save_path}")
    return demo_places


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape Google Maps reviews for Phitsanulok tourism")
    parser.add_argument("--demo", action="store_true", help="Use demo data instead of scraping")
    parser.add_argument("--visible", action="store_true", help="Show browser window")
    parser.add_argument("--places", type=int, default=None, help="Number of places to scrape")
    args = parser.parse_args()

    results = scrape(
        headless=not args.visible,
        max_places=args.places,
        use_demo_data=args.demo,
    )
    print(f"\nTotal: {len(results)} places scraped")
