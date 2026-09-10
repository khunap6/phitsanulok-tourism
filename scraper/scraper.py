"""
scraper.py — Web Scraper with PostgreSQL integration
Playwright (primary) → Selenium undetected-chromedriver (fallback)
"""

import asyncio
import hashlib
import random
import re
from datetime import datetime
from time import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ScrapeJob
from nlp.text_cleaner import clean_review_text
from scraper.date_parser import parse_relative_date
from scraper.scraper_core import (
    DEEP_REVIEW_CAP,
    DISCOVER_MAX_REVIEWS,
    MAX_REVIEWS_PER_PLACE,
    PHITSANULOK_PLACES_FALLBACK,
    is_in_phitsanulok,
    review_text_hash,
    run_scraper,
)
from scraper.zones import assign_zone, distance_to_campus_km

# deep scan: commit ระหว่างทางทุกกี่รีวิว (ร้านละหลายนาที ถ้าพังตอนท้ายจะเสียงานทั้งรอบ)
DEEP_COMMIT_EVERY_REVIEWS = 200
# deep scan: เจอบล็อกติดกันกี่ร้านถึงหยุดรอบแล้วส่งสัญญาณให้ผู้เรียกไป backoff
DEEP_BLOCK_STREAK_STOP = 2
# deep scan: ล้มเหลวแบบ "เข้าไม่ถึงหน้ารีวิว" กี่ครั้งถึงเลิกตามร้านนั้น
# (ยอมแพ้ = ไม่ตั้ง deep_scanned_at แต่ deep_attempts >= ค่านี้ → คิวรีแยกออกจาก "เก็บสำเร็จ" ได้)
DEEP_MAX_ATTEMPTS = 3


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def load_existing_places(session: AsyncSession) -> list[str]:
    """Load all place names from DB (ordered oldest scraped_at first)."""
    result = await session.execute(
        text("SELECT name FROM places ORDER BY scraped_at ASC NULLS FIRST")
    )
    return [row[0] for row in result.fetchall()]


async def load_places_to_refresh(session: AsyncSession) -> list[str]:
    """
    หาร้านที่ถึงคิว scan — ใช้ adaptive cooldown ตามประวัติการเปลี่ยนแปลง

      ร้านที่มีรีวิวใหม่ล่าสุด        → เว้น 7 วัน   (คนรีวิวบ่อย ต้องตามใกล้ชิด)
      ไม่มีรีวิวใหม่ 1 ครั้งติด       → เว้น 7 วัน
      ไม่มีรีวิวใหม่ 2 ครั้งติด       → เว้น 14 วัน
      ไม่มีรีวิวใหม่ 3 ครั้งขึ้นไป    → เว้น 30 วัน  (ร้านนิ่ง ไม่ต้องตามบ่อย)

    ร้านที่ยังไม่เคย scan (scraped_at NULL) มาก่อนเสมอ
    """
    result = await session.execute(
        text("""
            SELECT name FROM places
            WHERE scraped_at IS NULL
               OR scraped_at < NOW() - (
                    CASE
                        WHEN COALESCE(consecutive_no_change, 0) >= 3 THEN INTERVAL '30 days'
                        WHEN COALESCE(consecutive_no_change, 0) = 2  THEN INTERVAL '14 days'
                        ELSE INTERVAL '7 days'
                    END
                  )
            ORDER BY scraped_at ASC NULLS FIRST
        """)
    )
    return [row[0] for row in result.fetchall()]


async def load_known_hashes(session: AsyncSession, place_names: list[str]) -> dict[str, set[str]]:
    """
    โหลด hash ของรีวิวที่มีอยู่แล้ว แยกตามชื่อร้าน
    ใช้ให้ scraper รู้ว่า "อันไหนเคยเก็บแล้ว" → หยุด scroll ได้ทันทีที่ชนของเดิม
    """
    if not place_names:
        return {}
    result = await session.execute(
        text("""
            SELECT p.name, r.text_hash
            FROM places p JOIN reviews r ON r.place_id = p.id
            WHERE p.name = ANY(:names)
        """),
        {"names": place_names},
    )
    out: dict[str, set[str]] = {}
    for name, h in result.fetchall():
        out.setdefault(name, set()).add(h)
    return out


async def update_scan_stats(session: AsyncSession, place_names: list[str]) -> None:
    """
    บันทึกค่าอ้างอิงหลัง scan เสร็จ:
      - last_review_count      = จำนวนรีวิวที่มีตอนนี้
      - last_scan_new_reviews  = รอบนี้ได้ใหม่กี่อัน (เทียบกับค่าอ้างอิงเดิม)
      - consecutive_no_change  = ไม่มีของใหม่ติดกันกี่รอบ (+1 หรือ reset 0)
    """
    if not place_names:
        return
    await session.execute(
        text("""
            WITH cur AS (
                SELECT p.id,
                       COUNT(r.id) AS cnt
                FROM places p
                LEFT JOIN reviews r ON r.place_id = p.id
                WHERE p.name = ANY(:names)
                GROUP BY p.id
            )
            UPDATE places p SET
                last_scan_new_reviews = GREATEST(cur.cnt - COALESCE(p.last_review_count, 0), 0),
                consecutive_no_change = CASE
                    WHEN cur.cnt > COALESCE(p.last_review_count, 0) THEN 0
                    ELSE COALESCE(p.consecutive_no_change, 0) + 1
                END,
                last_review_count = cur.cnt
            FROM cur
            WHERE p.id = cur.id
        """),
        {"names": place_names},
    )
    await session.commit()


async def save_to_db(
    results: list[dict],
    session: AsyncSession,
    full_scrape: bool = True,
    saved_place_ids: list[int] | None = None,
) -> tuple[int, int]:
    """
    Upsert places + insert reviews (skip duplicates via text_hash).
    full_scrape=False (โหมด discover) → เก็บ scraped_at เป็น NULL เพื่อให้ auto_refresh
    ดึงรีวิวเต็มทีหลัง (NULLS FIRST ในคิว refresh)
    saved_place_ids: ถ้าส่ง list มา จะเติม id ที่ได้จาก RETURNING ของแถวที่บันทึกสำเร็จจริง
      (deep scan ใช้ตัวนี้ตี deep_scanned_at — ห้ามเดาจากชื่อร้านที่ส่งเข้ามา
       เพราะชื่อจริงบนหน้าเว็บอาจไม่ตรงกับชื่อที่ใช้ค้น)
    Returns (places_upserted, reviews_inserted_new).
    """
    places_count = 0
    reviews_new = 0
    # NOW() = scrape เต็มแล้ว | NULL = แค่ discover ยังต้อง refresh รีวิวต่อ
    scraped_expr = "NOW()" if full_scrape else "NULL"

    for result in results:
        if not result or result.get("_blocked"):
            continue

        lat = result.get("lat")
        lng = result.get("lng")

        if not is_in_phitsanulok(lat, lng):
            continue

        # Parse rating safely
        try:
            rating = float(str(result.get("overall_rating", "")).replace(",", "."))
        except (ValueError, TypeError):
            rating = None

        google_category = result.get("google_category")
        opening_hours = result.get("opening_hours")
        price_level = result.get("price_level")
        business_status = result.get("business_status", "operational")

        # คำนวณ zone + ระยะทางไปมหาวิทยาลัยจาก GPS
        zone = assign_zone(lat, lng)
        dist_nu, dist_psru = distance_to_campus_km(lat, lng)

        # Upsert place — with or without coordinates
        # COALESCE ป้องกันไม่ให้ refresh ที่ไม่ได้ค่ามาทับของเดิมด้วย NULL
        if lat is not None and lng is not None:
            place_row = await session.execute(
                text(f"""
                    INSERT INTO places (name, search_query, overall_rating, google_category,
                                        opening_hours, price_level, business_status, zone,
                                        distance_nu_km, distance_psru_km, location, scraped_at)
                    VALUES (:name, :search_query, :rating, :google_category,
                            :opening_hours, :price_level, :business_status, :zone,
                            :dist_nu, :dist_psru, ST_MakePoint(:lng, :lat), {scraped_expr})
                    ON CONFLICT (name) DO UPDATE SET
                        overall_rating   = EXCLUDED.overall_rating,
                        google_category  = COALESCE(EXCLUDED.google_category, places.google_category),
                        opening_hours    = COALESCE(EXCLUDED.opening_hours, places.opening_hours),
                        price_level      = COALESCE(EXCLUDED.price_level, places.price_level),
                        business_status  = EXCLUDED.business_status,
                        zone             = EXCLUDED.zone,
                        distance_nu_km   = EXCLUDED.distance_nu_km,
                        distance_psru_km = EXCLUDED.distance_psru_km,
                        location         = EXCLUDED.location,
                        scraped_at       = COALESCE(EXCLUDED.scraped_at, places.scraped_at)
                    RETURNING id
                """),
                {
                    "name": result["place_name"],
                    "search_query": result.get("search_query"),
                    "rating": rating,
                    "google_category": google_category,
                    "opening_hours": opening_hours,
                    "price_level": price_level,
                    "business_status": business_status,
                    "zone": zone,
                    "dist_nu": dist_nu,
                    "dist_psru": dist_psru,
                    "lng": lng,
                    "lat": lat,
                },
            )
        else:
            place_row = await session.execute(
                text(f"""
                    INSERT INTO places (name, search_query, overall_rating, google_category,
                                        opening_hours, price_level, business_status, scraped_at)
                    VALUES (:name, :search_query, :rating, :google_category,
                            :opening_hours, :price_level, :business_status, {scraped_expr})
                    ON CONFLICT (name) DO UPDATE SET
                        overall_rating   = EXCLUDED.overall_rating,
                        google_category  = COALESCE(EXCLUDED.google_category, places.google_category),
                        opening_hours    = COALESCE(EXCLUDED.opening_hours, places.opening_hours),
                        price_level      = COALESCE(EXCLUDED.price_level, places.price_level),
                        business_status  = EXCLUDED.business_status,
                        scraped_at       = COALESCE(EXCLUDED.scraped_at, places.scraped_at)
                    RETURNING id
                """),
                {
                    "name": result["place_name"],
                    "search_query": result.get("search_query"),
                    "rating": rating,
                    "google_category": google_category,
                    "opening_hours": opening_hours,
                    "price_level": price_level,
                    "business_status": business_status,
                },
            )

        place_id = place_row.scalar_one()
        places_count += 1
        if saved_place_ids is not None:
            saved_place_ids.append(place_id)

        # Insert reviews — skip duplicates via (place_id, text_hash)
        for review in result.get("reviews", []):
            text_content = (review.get("text") or "").strip()
            if len(text_content) < 5:
                continue

            # แปลง relative date → วันที่โดยประมาณ (ณ เวลาที่ scrape)
            review_date_approx = parse_relative_date(review.get("date"))
            # ทำความสะอาด text → เก็บใน text_clean
            text_clean = clean_review_text(text_content)
            # hash จากข้อความที่ล้างแล้ว (คงที่ทุกรอบ scrape) — ดูคำอธิบายใน review_text_hash
            text_hash = review_text_hash(text_content)

            rv = await session.execute(
                text("""
                    INSERT INTO reviews (place_id, rating, text, text_clean, text_hash, review_date, review_date_approx)
                    VALUES (:place_id, :rating, :text, :text_clean, :text_hash, :review_date, :review_date_approx)
                    ON CONFLICT (place_id, text_hash) DO NOTHING
                """),
                {
                    "place_id": place_id,
                    "rating": review.get("rating"),
                    "text": text_content[:1000],
                    "text_clean": text_clean[:1000],
                    "text_hash": text_hash,
                    "review_date": review.get("date"),
                    "review_date_approx": review_date_approx,
                },
            )
            if rv.rowcount > 0:
                reviews_new += 1

        await session.flush()

    return places_count, reviews_new


# ---------------------------------------------------------------------------
# Selenium fallback
# ---------------------------------------------------------------------------

async def _run_selenium_fallback(
    places: list[str],
    headless: bool = True,
    max_places: int | None = None,
) -> list[dict]:
    """Selenium fallback using undetected-chromedriver (same JS extraction logic)."""
    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError:
        print("[selenium] undetected_chromedriver not available — skip fallback")
        return []

    if max_places:
        places = places[:max_places]

    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=th-TH")
    options.add_argument("--disable-blink-features=AutomationControlled")

    results = []
    driver = None

    try:
        driver = uc.Chrome(options=options)
        wait = WebDriverWait(driver, 15)

        for i, place_name in enumerate(places):
            print(f"\n[selenium][{i+1}/{len(places)}] Scraping: {place_name}")
            try:
                url = f"https://www.google.com/maps/search/{place_name.replace(' ', '+')}"
                driver.get(url)
                await asyncio.sleep(3)

                # Click first result if list page
                try:
                    first = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'a[href*="/maps/place/"]'))
                    )
                    first.click()
                    await asyncio.sleep(2)
                except Exception:
                    pass

                # Extract coordinates from URL
                lat, lng = None, None
                match = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", driver.current_url)
                if match:
                    lat, lng = float(match.group(1)), float(match.group(2))

                # Extract overall rating
                overall_rating = "N/A"
                for sel in [".fontDisplayLarge", ".F7nice span"]:
                    try:
                        elem = driver.find_element(By.CSS_SELECTOR, sel)
                        if elem.text.strip():
                            overall_rating = elem.text.strip()
                            break
                    except Exception:
                        continue

                # Extract Google-assigned category
                google_category = None
                for sel in [".DkEaL"]:
                    try:
                        elem = driver.find_element(By.CSS_SELECTOR, sel)
                        if elem.text.strip():
                            google_category = elem.text.strip()
                            break
                    except Exception:
                        continue

                # Scroll reviews panel
                for _ in range(5):
                    driver.execute_script("""
                        const panel = document.querySelector('[role="feed"]');
                        if (panel) panel.scrollTo(0, panel.scrollHeight);
                    """)
                    await asyncio.sleep(1.5)

                # Extract reviews — same JS logic as scraper_core
                raw = driver.execute_script("""
                    const results = [];
                    const seen = new Set();
                    const allEls = document.querySelectorAll('[aria-label]');
                    const starEls = Array.from(allEls).filter(el => {
                        const lbl = el.getAttribute('aria-label') || '';
                        return /^[1-5]\\s*(ดาว|star)/.test(lbl);
                    });
                    starEls.forEach(starEl => {
                        const lbl = starEl.getAttribute('aria-label') || '';
                        const match = lbl.match(/^([1-5])/);
                        const rating = match ? parseInt(match[1]) : null;
                        let container = starEl.parentElement;
                        for (let i = 0; i < 7; i++) {
                            if (!container) break;
                            const txt = (container.innerText || '').trim();
                            const key = txt.substring(0, 60);
                            if (txt.length >= 40 && txt.length <= 1200 && !seen.has(key)) {
                                seen.add(key);
                                let dateText = '';
                                container.querySelectorAll('span').forEach(s => {
                                    const t = (s.innerText || '').trim();
                                    if (/(เดือน|สัปดาห์|วัน|ปี|ago|month|week|year)/i.test(t) && t.length < 35)
                                        dateText = t;
                                });
                                results.push({ rating, text: txt.substring(0, 500), date: dateText });
                                break;
                            }
                            container = container.parentElement;
                        }
                    });
                    return results.slice(0, 90);
                """) or []

                reviews = [
                    {"rating": r["rating"], "text": r["text"], "date": r["date"]}
                    for r in raw
                    if r.get("rating") and r["rating"] <= 3 and len(r.get("text", "")) >= 20
                ]

                if is_in_phitsanulok(lat, lng):
                    results.append({
                        "place_name": place_name,
                        "search_query": place_name,
                        "overall_rating": overall_rating,
                        "google_category": google_category,
                        "lat": lat,
                        "lng": lng,
                        "reviews": reviews,
                        "scraped_at": datetime.now().isoformat(),
                    })
                    print(f"  [selenium] {place_name}: {len(reviews)} reviews")

                await asyncio.sleep(random.uniform(4.0, 8.0))

            except Exception as e:
                print(f"  [selenium] Error on {place_name}: {e}")
                continue

    except Exception as e:
        print(f"[selenium] Driver init error: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return results


# ---------------------------------------------------------------------------
# Playwright with retry → Selenium fallback
# ---------------------------------------------------------------------------

async def _run_with_fallback(
    places: list[str] | None,
    headless: bool,
    max_places: int | None,
    auto_discover: bool,
    max_reviews: int = MAX_REVIEWS_PER_PLACE,
    known_hashes_by_place: dict[str, set[str]] | None = None,
    deep: bool = False,
) -> list[dict]:
    """Try Playwright up to 3 times. On repeated failure, use Selenium fallback."""
    last_exc = None
    for attempt in range(1, 4):
        try:
            return await run_scraper(
                places=places,
                headless=headless,
                max_places=max_places,
                auto_discover=auto_discover,
                max_reviews=max_reviews,
                known_hashes_by_place=known_hashes_by_place,
                deep=deep,
            )
        except Exception as e:
            last_exc = e
            print(f"[scraper] Playwright attempt {attempt}/3 failed: {e}")
            if attempt < 3:
                await asyncio.sleep(5 * attempt)

    # โหมด deep ห้ามตกไป Selenium — ตัวนั้นไม่รู้จัก deep และกรองเก็บเฉพาะรีวิว <=3 ดาว
    # ถ้าปล่อยผ่าน จะได้ผลตื้นแล้วถูกตี deep_scanned_at = ร้านนั้นไม่ถูกหยิบมาทำอีกเลย
    if deep:
        print(f"[scraper] deep: Playwright ล้ม 3 ครั้ง ({last_exc}) — ข้ามร้านนี้ "
              f"(ไม่ใช้ Selenium fallback) ไว้รอบหน้าค่อยหยิบมาทำใหม่")
        return []

    print(f"[scraper] Playwright failed 3×. Switching to Selenium fallback...")
    fallback_places = places or PHITSANULOK_PLACES_FALLBACK
    return await _run_selenium_fallback(
        places=fallback_places,
        headless=headless,
        max_places=max_places,
    )


# ---------------------------------------------------------------------------
# Public interface (used by Phase 5 APScheduler)
# ---------------------------------------------------------------------------

async def run_discover(
    session: AsyncSession,
    headless: bool = True,
    max_places: int = 50,
) -> dict:
    """
    Discover new tourist places → save to DB.
    Returns {"places": int, "reviews_new": int, "duration_sec": float}
    """
    started_at = datetime.now()
    t0 = time()

    job = ScrapeJob(job_type="discover", status="running", started_at=started_at)
    session.add(job)
    await session.flush()
    job_id = job.id

    try:
        existing = set(await load_existing_places(session))

        # A1: discover = หาร้านใหม่ + เก็บ "เฉพาะข้อมูลร้าน" (ไม่ดึงรีวิว, DISCOVER_MAX_REVIEWS=0)
        # scraped_at=NULL → auto_refresh จะมาดึงรีวิวเต็มทีหลัง (ร้านใหม่ = scan เต็ม)
        results = await _run_with_fallback(
            places=None,
            headless=headless,
            max_places=max_places,
            auto_discover=True,
            max_reviews=DISCOVER_MAX_REVIEWS,
        )

        # บันทึกทุกสถานที่ (UPSERT จัดการ duplicate เอง)
        # ไม่กรองล่วงหน้า เพราะชื่อจาก Google Maps อาจต่างจาก DB เล็กน้อย
        valid_results = [r for r in results if r]
        places_count, reviews_new = await save_to_db(valid_results, session, full_scrape=False)
        duration = round(time() - t0, 1)

        await session.execute(
            text("""
                UPDATE scrape_jobs
                SET status='done', places_count=:p, reviews_count=:r, finished_at=NOW()
                WHERE id=:id
            """),
            {"p": places_count, "r": reviews_new, "id": job_id},
        )
        await session.commit()
        print(f"[discover] Done — {places_count} places, {reviews_new} new reviews ({duration}s)")
        return {"places": places_count, "reviews_new": reviews_new, "duration_sec": duration}

    except Exception as e:
        await session.execute(
            text("UPDATE scrape_jobs SET status='failed', error_msg=:msg, finished_at=NOW() WHERE id=:id"),
            {"msg": str(e)[:500], "id": job_id},
        )
        await session.commit()
        raise


async def run_refresh(
    session: AsyncSession,
    headless: bool = True,
    max_places: int | None = None,
) -> dict:
    """
    Re-scrape existing places (oldest scraped_at first, incremental).
    Returns {"places": int, "reviews_new": int, "duration_sec": float}
    """
    started_at = datetime.now()
    t0 = time()

    job = ScrapeJob(job_type="refresh", status="running", started_at=started_at)
    session.add(job)
    await session.flush()
    job_id = job.id

    try:
        # Prefer places not updated in 7 days; fallback to all
        place_names = await load_places_to_refresh(session)
        if not place_names:
            place_names = await load_existing_places(session)

        if max_places:
            place_names = place_names[:max_places]

        if not place_names:
            await session.execute(
                text("""
                    UPDATE scrape_jobs
                    SET status='done', places_count=0, reviews_count=0, finished_at=NOW()
                    WHERE id=:id
                """),
                {"id": job_id},
            )
            await session.commit()
            return {"places": 0, "reviews_new": 0, "duration_sec": 0.0}

        # Incremental: บอก scraper ว่าแต่ละร้านมีรีวิวอะไรอยู่แล้ว
        # → หยุด scroll ทันทีที่ชนของเดิม แทนที่จะ scroll จนครบทุกครั้ง
        known_hashes = await load_known_hashes(session, place_names)
        n_known = sum(len(v) for v in known_hashes.values())
        print(f"[incremental] โหลดรีวิวเดิม {n_known:,} อัน จาก {len(known_hashes)} ร้าน "
              f"(ร้านใหม่ {len(place_names) - len(known_hashes)} ร้าน = scan เต็ม)")

        results = await _run_with_fallback(
            places=place_names,
            headless=headless,
            max_places=max_places,
            auto_discover=False,
            known_hashes_by_place=known_hashes,
        )

        # B3: ถ้า scraper เจอบล็อกจริง → คืน flag ให้ auto_refresh พักแล้วลองใหม่
        blocked_signal = next((r["_blocked"] for r in results if r and r.get("_blocked")), None)

        places_count, reviews_new = await save_to_db(results, session)
        # อัปเดตค่าอ้างอิงเฉพาะร้านที่ scrape สำเร็จจริง (ไม่นับรอบที่โดนบล็อก)
        if not blocked_signal:
            await update_scan_stats(session, place_names)
        duration = round(time() - t0, 1)

        job_status = "blocked" if blocked_signal else "done"
        await session.execute(
            text("""
                UPDATE scrape_jobs
                SET status=:st, places_count=:p, reviews_count=:r, finished_at=NOW()
                WHERE id=:id
            """),
            {"st": job_status, "p": places_count, "r": reviews_new, "id": job_id},
        )
        await session.commit()
        print(f"[refresh] Done — {places_count} places, {reviews_new} new reviews ({duration}s)")
        return {"places": places_count, "reviews_new": reviews_new,
                "duration_sec": duration, "blocked": blocked_signal}

    except Exception as e:
        await session.execute(
            text("UPDATE scrape_jobs SET status='failed', error_msg=:msg, finished_at=NOW() WHERE id=:id"),
            {"msg": str(e)[:500], "id": job_id},
        )
        await session.commit()
        raise


async def run_deep_scan(
    session: AsyncSession,
    place_names: list[str],
    headless: bool = True,
) -> dict:
    """
    Deep scan — เก็บรีวิวของร้านที่ระบุให้ครบที่สุด (ไม่ใช้ incremental early-stop)

    ต่างจาก run_refresh:
      - ไม่ส่ง known_hashes → scraper ไม่หยุดเมื่อเจอรีวิวเดิม (กันซ้ำด้วย ON CONFLICT แทน)
      - เรียก scraper ทีละร้าน เพราะร้านละหลายนาที ถ้ารวมเป็นชุดแล้วพังกลางทางจะเสียงานทั้งชุด
        และทำให้ตี deep_scanned_at ทีละร้านตอนสำเร็จจริงได้
      - commit ทุก ~200 รีวิว ไม่ใช่ทีเดียวตอนจบ
      - หน่วงระหว่างร้าน 20–40 วิ (นานกว่าโหมดปกติ เพราะ session deep หนักกว่ามาก)
      - เจอบล็อกติดกัน 2 ร้าน → หยุดรอบแล้วคืน blocked ให้ผู้เรียกไป backoff

    Returns {"places": int, "reviews_new": int, "duration_sec": float, "blocked": str|None}
    """
    started_at = datetime.now()
    t0 = time()

    job = ScrapeJob(job_type="deep", status="running", started_at=started_at)
    session.add(job)
    await session.flush()
    job_id = job.id

    places_count = 0
    reviews_new = 0
    blocked_signal: str | None = None

    try:
        pending_commit = 0
        block_streak = 0
        done_names: list[str] = []

        for i, name in enumerate(place_names):
            print(f"\n[deep {i + 1}/{len(place_names)}] {name}")

            results = await _run_with_fallback(
                places=[name],
                headless=headless,
                max_places=None,
                auto_discover=False,
                max_reviews=DEEP_REVIEW_CAP,
                deep=True,
            )

            sig = next((r["_blocked"] for r in results if r and r.get("_blocked")), None)
            # collected = จำนวนรีวิวที่ "ดึงมาจากหน้าเว็บ" (ไม่ใช่จำนวนที่ INSERT ลง DB)
            collected = sum(len(r.get("reviews", [])) for r in results if r and not r.get("_blocked"))
            # ธงจาก scrape_place: เข้าไม่ถึงหน้ารีวิว (กดแท็บไม่ติด / scroll แล้วไม่เจอการ์ดเลย)
            reviews_failed = next(
                (r["_reviews_failed"] for r in results if r and r.get("_reviews_failed")), None
            )

            # save_to_db ข้ามรายการที่เป็น _blocked / นอก bbox ให้อยู่แล้ว
            saved_ids: list[int] = []
            p_cnt, r_cnt = await save_to_db(results, session, saved_place_ids=saved_ids)
            places_count += p_cnt
            reviews_new += r_cnt
            pending_commit += r_cnt

            # เกณฑ์ "scrape สำเร็จ" ก่อนตี deep_scanned_at — ต้องครบทุกข้อ:
            #   1. มี id จาก RETURNING  (หน้าร้านโหลดขึ้น อยู่ในพื้นที่ บันทึกลง DB แล้ว)
            #   2. ไม่โดนบล็อก
            #   3. เข้าถึงหน้ารีวิวได้จริง (ไม่ใช่กดแท็บไม่ติด / feed ไม่ render)
            #   4. ดึงรีวิวมาได้อย่างน้อย 1 อัน
            # ข้อ 3-4 ทำให้ "ร้านไม่มีรีวิว" กับ "เข้าไม่ถึงหน้ารีวิว" ไม่ถูกเหมารวมกัน —
            # ทั้งคู่ไม่ถูกมาร์ค จึงถูกหยิบมาลองใหม่ได้เสมอ (เดิมเงื่อนไข existing == 0
            # จะมาร์คร้านกลุ่ม zero ที่กดแท็บไม่ติดว่าเสร็จถาวร ซึ่งคือกลุ่มที่ตั้งใจจะไปกู้)
            scraped_ok = bool(saved_ids) and not sig and not reviews_failed and collected > 0

            if scraped_ok:
                await session.execute(
                    text("UPDATE places SET deep_scanned_at = NOW() WHERE id = ANY(:ids)"),
                    {"ids": saved_ids},
                )
                done_names.extend(
                    r["place_name"] for r in results if r and not r.get("_blocked")
                )
                print(f"   ✅ ดึงมา {collected} รีวิว (ใหม่ {r_cnt}) | ตี deep_scanned_at แล้ว")
            elif not sig:
                # นับ deep_attempts เฉพาะ "เข้าไม่ถึงหน้ารีวิว" ซึ่งเป็นความผิดของหน้าเว็บ
                # ไม่นับตอนโดนบล็อก (กิ่งนี้ไม่รวมกรณี sig อยู่แล้ว) — โดนบล็อก 3 รอบติด
                # ต้องไม่ทำให้ร้านที่ไม่ผิดอะไรถูกทิ้งถาวร
                attempts = None
                if reviews_failed and saved_ids:
                    r = await session.execute(
                        text("""
                            UPDATE places SET deep_attempts = COALESCE(deep_attempts, 0) + 1
                            WHERE id = ANY(:ids) RETURNING deep_attempts
                        """),
                        {"ids": saved_ids},
                    )
                    attempts = max((row[0] for row in r.fetchall()), default=None)

                if reviews_failed:
                    why = f"เข้าไม่ถึงหน้ารีวิว ({reviews_failed})"
                elif not saved_ids:
                    why = "หน้าร้านโหลดไม่ขึ้น/นอกพื้นที่พิษณุโลก"
                else:
                    why = "เข้าหน้ารีวิวได้แต่ดึงมาได้ 0 อัน"

                if attempts is not None and attempts >= DEEP_MAX_ATTEMPTS:
                    print(f"   ⛔ ไม่นับว่าสำเร็จ — {why} | ล้มเหลวครบ {attempts}/{DEEP_MAX_ATTEMPTS} ครั้ง "
                          f"→ ยอมแพ้ ถอดออกจากคิว (deep_scanned_at ยังเป็น NULL)")
                else:
                    tail = (f" | ล้มเหลวครั้งที่ {attempts}/{DEEP_MAX_ATTEMPTS}"
                            if attempts is not None else "")
                    print(f"   ⚠️  ไม่นับว่าสำเร็จ — {why}{tail} "
                          f"→ ปล่อย deep_scanned_at เป็น NULL ไว้ทำรอบหน้า")

            if sig:
                block_streak += 1
                print(f"   🛑 เจอสัญญาณบล็อก ({sig}) — ติดกัน {block_streak} ร้าน")
                if block_streak >= DEEP_BLOCK_STREAK_STOP:
                    blocked_signal = sig
                    print(f"   หยุดรอบนี้ (บล็อกติดกัน {block_streak} ร้าน)")
                    break
            else:
                block_streak = 0

            if pending_commit >= DEEP_COMMIT_EVERY_REVIEWS:
                await session.commit()
                print(f"   💾 commit ระหว่างทาง (สะสม {pending_commit} รีวิว)")
                pending_commit = 0

            if i < len(place_names) - 1:
                delay = random.uniform(20.0, 40.0)
                print(f"   ⏳ พัก {delay:.0f} วิ ก่อนร้านถัดไป")
                await asyncio.sleep(delay)

        await session.commit()

        # อัปเดตค่าอ้างอิงเฉพาะร้านที่ scrape สำเร็จจริง (ชื่อจริงจากหน้าเว็บ)
        if done_names:
            await update_scan_stats(session, done_names)

        duration = round(time() - t0, 1)
        job_status = "blocked" if blocked_signal else "done"
        await session.execute(
            text("""
                UPDATE scrape_jobs
                SET status=:st, places_count=:p, reviews_count=:r, finished_at=NOW()
                WHERE id=:id
            """),
            {"st": job_status, "p": places_count, "r": reviews_new, "id": job_id},
        )
        await session.commit()
        print(f"[deep] Done — {places_count} places, {reviews_new} new reviews ({duration}s)")
        return {"places": places_count, "reviews_new": reviews_new,
                "duration_sec": duration, "blocked": blocked_signal}

    except Exception as e:
        await session.rollback()
        await session.execute(
            text("UPDATE scrape_jobs SET status='failed', error_msg=:msg, finished_at=NOW() WHERE id=:id"),
            {"msg": str(e)[:500], "id": job_id},
        )
        await session.commit()
        raise
