"""
admin.py — Manual trigger endpoints + job status
POST /api/admin/trigger/discover
POST /api/admin/trigger/refresh
POST /api/admin/trigger/analyze
GET  /api/admin/jobs/status
"""

import asyncio
import logging
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

# Track whether a job is already running to prevent double-trigger
_running: dict[str, bool] = {
    "discover": False,
    "refresh": False,
    "analyze": False,
}


def _make_runner(job_name: str, coro_fn):
    """Wrap a job coroutine so it clears the _running flag when done."""
    async def _run():
        _running[job_name] = True
        try:
            await coro_fn()
        finally:
            _running[job_name] = False
    return _run


@router.post("/trigger/discover")
async def trigger_discover(background_tasks: BackgroundTasks):
    if _running["discover"]:
        raise HTTPException(status_code=409, detail="discover job already running")
    from scheduler.scheduler import job_discover
    background_tasks.add_task(_make_runner("discover", job_discover))
    return {"status": "started", "job": "weekly_discover"}


@router.post("/trigger/refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    if _running["refresh"]:
        raise HTTPException(status_code=409, detail="refresh job already running")
    from scheduler.scheduler import job_refresh
    background_tasks.add_task(_make_runner("refresh", job_refresh))
    return {"status": "started", "job": "weekly_refresh"}


@router.post("/trigger/analyze")
async def trigger_analyze(background_tasks: BackgroundTasks):
    if _running["analyze"]:
        raise HTTPException(status_code=409, detail="analyze job already running")
    from scheduler.scheduler import job_analyze
    background_tasks.add_task(_make_runner("analyze", job_analyze))
    return {"status": "started", "job": "weekly_analyze"}


@router.get("/jobs/status")
async def jobs_status(db: Annotated[AsyncSession, Depends(get_db)]):
    """APScheduler next run times + latest DB job records."""
    from scheduler.scheduler import scheduler

    scheduled = []
    for job in scheduler.get_jobs():
        scheduled.append({
            "id": job.id,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "currently_running": _running.get(job.id.replace("weekly_", ""), False),
        })

    result = await db.execute(
        text("""
            SELECT id, job_type, status, places_count, reviews_count,
                   started_at, finished_at, error_msg
            FROM scrape_jobs
            ORDER BY started_at DESC NULLS LAST
            LIMIT 10
        """)
    )
    recent_jobs = [dict(row._mapping) for row in result.fetchall()]

    return {"scheduled": scheduled, "recent": recent_jobs}
