"""
Google Maps Reviews Scraper for Phitsanulok Tourism
Scrapes 1-3 star reviews from tourist attractions using Playwright
"""

import asyncio
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


DATA_DIR = Path(__file__).parent.parent / "data"

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

        search_box = page.locator('#searchboxinput').first
        await search_box.click()
        await search_box.fill(query)
        await page.keyboard.press("Enter")
        await random_delay(3.0, 5.0)

        # Scroll results panel to load more places
        scroll_attempts = 0
        max_scrolls = 15
        while len(places) < max_places and scroll_attempts < max_scrolls:
            # Extract place names from search results
            items = await page.query_selector_all('[class*="hfpxzc"], [role="article"] a[href*="maps/place"]')
            for item in items:
                try:
                    aria = await item.get_attribute("aria-label")
                    if aria and aria not in places:
                        places.append(aria)
                except Exception:
                    continue

            if len(places) >= max_places:
                break

            # Scroll the results panel
            await page.evaluate("""
                const panel = document.querySelector('[role="feed"]');
                if (panel) panel.scrollBy(0, 800);
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


async def extract_reviews(page: Page, max_reviews: int = 20) -> list[dict]:
    """Extract reviews from the current place page."""
    reviews = []
    try:
        # Step 1: Click "รีวิว" tab by visible text
        clicked_reviews = False
        try:
            # Use has-text to find the tab by its visible label
            tab = page.locator('button', has_text="รีวิว").first
            if await tab.count() > 0:
                await tab.click(timeout=6000)
                await random_delay(2.0, 3.0)
                clicked_reviews = True
        except Exception:
            pass

        if not clicked_reviews:
            # Fallback: try clicking any tab-like element with review text
            try:
                await page.get_by_role("tab").filter(has_text="รีวิว").click(timeout=4000)
                await random_delay(2.0, 3.0)
                clicked_reviews = True
            except Exception:
                pass

        # Save debug screenshot after clicking reviews tab
        debug_dir = DATA_DIR / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(debug_dir / "after_reviews_tab.png"))

        # Step 2: Sort by Newest — หาจากข้อความ ไม่ใช่ index
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
                            break
                    # ถ้าหาไม่เจอ → ใช้ index 1
                    if not clicked and count > 1:
                        await options.nth(1).click(timeout=3000)
                    await random_delay(1.5, 2.5)
                except Exception:
                    pass
        except Exception:
            pass

        # Step 3: Scroll to load more reviews (เพิ่มจาก 8 → 20 รอบ)
        await scroll_reviews(page, times=20)

        # Step 4: Extract reviews via JavaScript
        # Match ONLY exact "N ดาว" patterns (e.g. "1 ดาว", "2 ดาว") to avoid
        # picking up overall-rating elements like "4.7 ดาว" or histogram bars.
        raw_reviews = await page.evaluate(f"""
            () => {{
                const results = [];
                const seen = new Set();
                // Only skip text that clearly belongs to Google Maps chrome (never in review text)
                const UI_SKIP = [
                    'ดาวน์โหลดแอป','ผลลัพธ์','ตัวกรองทั้งหมด',
                    'เขียนรีวิว','ค้นหารีวิว','บัญชี Google',
                ];

                // Only match individual-review star elements (exact "N ดาว" or "N star")
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

                        // Walk up max 7 levels to find the review card
                        let container = starEl.parentElement;
                        for (let i = 0; i < 7; i++) {{
                            if (!container) break;
                            const text = (container.innerText || '').trim();
                            // Valid review card: 40-1200 chars, no UI chrome, not seen before
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

                return results.slice(0, {max_reviews * 3});
            }}
        """)

        # Step 5: Filter and clean
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

                if len(reviews) >= max_reviews:
                    break
            except Exception:
                continue

    except Exception as e:
        print(f"  Warning: {e}")

    return reviews


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


async def scrape_place(page: Page, place_name: str) -> dict | None:
    """Search for a place and scrape its reviews."""
    print(f"\n  Searching: {place_name}")

    try:
        # Search directly via URL for more reliable loading
        search_url = f"https://www.google.com/maps/search/{place_name.replace(' ', '+')}"
        await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await random_delay(2.0, 4.0)

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

        print(f"  Found: {actual_name} | Rating: {overall_rating} | Coords: {coords}")

        # Save debug screenshot before extracting reviews
        safe_name = re.sub(r'[^\w]', '_', actual_name)[:20]
        await debug_page(page, f"before_reviews_{safe_name}")

        # Scrape reviews (เพิ่มจาก 30 → 80 รีวิวต่อสถานที่)
        reviews = await extract_reviews(page, max_reviews=80)
        print(f"  Collected {len(reviews)} reviews")

        return {
            "place_name": actual_name,
            "search_query": place_name,
            "overall_rating": overall_rating,
            "lat": coords[0] if coords else None,
            "lng": coords[1] if coords else None,
            "reviews": reviews,
            "scraped_at": datetime.now().isoformat(),
        }

    except Exception as e:
        print(f"  ❌ Error scraping {place_name}: {e}")
        return None


async def run_scraper(places: list[str] = None, headless: bool = True, max_places: int = None, auto_discover: bool = True) -> list[dict]:
    """Main scraper function."""
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

        # Auto-discover places if not provided
        if places is None:
            if auto_discover:
                places = await discover_places(page, max_places=max_places or 60)
            if not places:
                places = PHITSANULOK_PLACES_FALLBACK

        if max_places:
            places = places[:max_places]

        results = []
        for i, place in enumerate(places):
            print(f"\n[{i+1}/{len(places)}] Processing...")
            result = await scrape_place(page, place)
            if result:
                # กรองเฉพาะสถานที่ในพิษณุโลก
                if not is_in_phitsanulok(result.get("lat"), result.get("lng")):
                    print(f"  [skip] Outside Phitsanulok bbox: {result['place_name']} ({result.get('lat')}, {result.get('lng')})")
                else:
                    results.append(result)
                    save_results(results, "phitsanulok_reviews_inprogress.json")

            if i < len(places) - 1:
                delay = random.uniform(4.0, 8.0)
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
                delay = random.uniform(4.0, 8.0)
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
    Combine two review lists, deduplicating by first 80 chars of text.
    Keeps all unique reviews from both sources.
    """
    seen = {r["text"][:80] for r in existing}
    combined = list(existing)
    for r in new:
        key = r.get("text", "")[:80]
        if key and key not in seen:
            seen.add(key)
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
