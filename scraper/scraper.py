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
from scraper.scraper_core import (
    PHITSANULOK_PLACES_FALLBACK,
    is_in_phitsanulok,
    run_scraper,
)


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
    """Load places not scraped in last 7 days, oldest first (incremental logic)."""
    result = await session.execute(
        text("""
            SELECT name FROM places
            WHERE scraped_at IS NULL OR scraped_at < NOW() - INTERVAL '7 days'
            ORDER BY scraped_at ASC NULLS FIRST
        """)
    )
    return [row[0] for row in result.fetchall()]


async def save_to_db(results: list[dict], session: AsyncSession) -> tuple[int, int]:
    """
    Upsert places + insert reviews (skip duplicates via text_hash).
    Returns (places_upserted, reviews_inserted_new).
    """
    places_count = 0
    reviews_new = 0

    for result in results:
        if not result:
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

        # Upsert place — with or without coordinates
        if lat is not None and lng is not None:
            place_row = await session.execute(
                text("""
                    INSERT INTO places (name, search_query, overall_rating, location, scraped_at)
                    VALUES (:name, :search_query, :rating, ST_MakePoint(:lng, :lat), NOW())
                    ON CONFLICT (name) DO UPDATE SET
                        overall_rating = EXCLUDED.overall_rating,
                        location       = EXCLUDED.location,
                        scraped_at     = EXCLUDED.scraped_at
                    RETURNING id
                """),
                {
                    "name": result["place_name"],
                    "search_query": result.get("search_query"),
                    "rating": rating,
                    "lng": lng,
                    "lat": lat,
                },
            )
        else:
            place_row = await session.execute(
                text("""
                    INSERT INTO places (name, search_query, overall_rating, scraped_at)
                    VALUES (:name, :search_query, :rating, NOW())
                    ON CONFLICT (name) DO UPDATE SET
                        overall_rating = EXCLUDED.overall_rating,
                        scraped_at     = EXCLUDED.scraped_at
                    RETURNING id
                """),
                {
                    "name": result["place_name"],
                    "search_query": result.get("search_query"),
                    "rating": rating,
                },
            )

        place_id = place_row.scalar_one()
        places_count += 1

        # Insert reviews — skip duplicates via (place_id, text_hash)
        for review in result.get("reviews", []):
            text_content = (review.get("text") or "").strip()
            if len(text_content) < 5:
                continue

            text_hash = hashlib.md5(text_content.encode("utf-8")).hexdigest()

            rv = await session.execute(
                text("""
                    INSERT INTO reviews (place_id, rating, text, text_hash, review_date)
                    VALUES (:place_id, :rating, :text, :text_hash, :review_date)
                    ON CONFLICT (place_id, text_hash) DO NOTHING
                """),
                {
                    "place_id": place_id,
                    "rating": review.get("rating"),
                    "text": text_content[:1000],
                    "text_hash": text_hash,
                    "review_date": review.get("date"),
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
            )
        except Exception as e:
            last_exc = e
            print(f"[scraper] Playwright attempt {attempt}/3 failed: {e}")
            if attempt < 3:
                await asyncio.sleep(5 * attempt)

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

        results = await _run_with_fallback(
            places=None,
            headless=headless,
            max_places=max_places,
            auto_discover=True,
        )

        # Only save truly new places
        new_results = [r for r in results if r and r.get("place_name") not in existing]
        places_count, reviews_new = await save_to_db(new_results, session)
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

        results = await _run_with_fallback(
            places=place_names,
            headless=headless,
            max_places=max_places,
            auto_discover=False,
        )

        places_count, reviews_new = await save_to_db(results, session)
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
        print(f"[refresh] Done — {places_count} places, {reviews_new} new reviews ({duration}s)")
        return {"places": places_count, "reviews_new": reviews_new, "duration_sec": duration}

    except Exception as e:
        await session.execute(
            text("UPDATE scrape_jobs SET status='failed', error_msg=:msg, finished_at=NOW() WHERE id=:id"),
            {"msg": str(e)[:500], "id": job_id},
        )
        await session.commit()
        raise
