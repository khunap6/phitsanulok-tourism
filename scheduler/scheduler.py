"""
scheduler.py — APScheduler jobs for weekly scrape + analysis
Timezone: Asia/Bangkok
  Job 1 — weekly_discover : Mon 02:00
  Job 2 — weekly_refresh  : Mon 03:00
  Job 3 — weekly_analyze  : Mon 05:00
"""

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from db.database import AsyncSessionLocal
from nlp.pipeline import run_analysis
from scraper.scraper import run_discover, run_refresh

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Bangkok")

# ---------------------------------------------------------------------------
# Job functions
# ---------------------------------------------------------------------------

async def job_discover() -> None:
    """Discover new tourist places in Phitsanulok and save to DB."""
    logger.info("[scheduler] job_discover — started")
    async with AsyncSessionLocal() as session:
        try:
            result = await run_discover(session, headless=True, max_places=50)
            logger.info(
                "[scheduler] job_discover — done: %d places, %d new reviews",
                result["places"],
                result["reviews_new"],
            )
        except Exception as e:
            logger.error("[scheduler] job_discover — FAILED: %s", e)


async def job_refresh() -> None:
    """Re-scrape existing places (oldest scraped_at first)."""
    logger.info("[scheduler] job_refresh — started")
    async with AsyncSessionLocal() as session:
        try:
            result = await run_refresh(session, headless=True)
            logger.info(
                "[scheduler] job_refresh — done: %d places, %d new reviews",
                result["places"],
                result["reviews_new"],
            )
        except Exception as e:
            logger.error("[scheduler] job_refresh — FAILED: %s", e)


async def job_analyze() -> None:
    """Analyze all unanalyzed reviews in batches until exhausted."""
    logger.info("[scheduler] job_analyze — started")
    total = 0
    async with AsyncSessionLocal() as session:
        try:
            while True:
                result = await run_analysis(session, batch_size=20)
                total += result["analyzed"]
                if result["analyzed"] == 0:
                    break
            logger.info("[scheduler] job_analyze — done: %d reviews analyzed", total)
        except Exception as e:
            logger.error("[scheduler] job_analyze — FAILED: %s", e)


# ---------------------------------------------------------------------------
# Register jobs
# ---------------------------------------------------------------------------

scheduler.add_job(
    job_discover,
    CronTrigger(day_of_week="mon", hour=2, minute=0),
    id="weekly_discover",
    replace_existing=True,
)

scheduler.add_job(
    job_refresh,
    CronTrigger(day_of_week="mon", hour=3, minute=0),
    id="weekly_refresh",
    replace_existing=True,
)

scheduler.add_job(
    job_analyze,
    CronTrigger(day_of_week="mon", hour=5, minute=0),
    id="weekly_analyze",
    replace_existing=True,
)
