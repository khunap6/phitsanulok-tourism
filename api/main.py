"""
main.py — FastAPI application entry point
Run: uvicorn api.main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import admin, analysis, places, reviews, stats

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from scheduler.scheduler import scheduler
    scheduler.start()
    logger.info("APScheduler started — 3 weekly jobs scheduled")
    yield
    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")


app = FastAPI(
    title="Phitsanulok Tourism Pain Point API",
    description="วิเคราะห์ Pain Point การท่องเที่ยวพิษณุโลก — Naresuan University",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",   # fallback React dev server
        "http://localhost:8000",   # same-origin (Swagger UI)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(places.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")
app.include_router(stats.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.get("/", tags=["root"])
async def root():
    return {
        "message": "Phitsanulok Tourism API",
        "docs": "/docs",
        "health": "/api/health",
    }
