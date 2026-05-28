from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.schemas.analysis import ScrapeJobResponse

router = APIRouter(tags=["system"])


@router.get("/health")
async def health_check(db: Annotated[AsyncSession, Depends(get_db)]):
    try:
        await db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"
    return {"status": "ok", "db": db_status}


@router.get("/jobs", response_model=list[ScrapeJobResponse])
async def list_scrape_jobs(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 20,
):
    result = await db.execute(
        text("""
            SELECT id, job_type, status, places_count, reviews_count,
                   started_at, finished_at, error_msg
            FROM scrape_jobs
            ORDER BY started_at DESC NULLS LAST
            LIMIT :lim
        """),
        {"lim": limit},
    )
    return [dict(row._mapping) for row in result.fetchall()]


@router.get("/map/geojson")
async def map_geojson(db: Annotated[AsyncSession, Depends(get_db)]):
    """Full GeoJSON FeatureCollection of all places for map rendering."""
    result = await db.execute(
        text("""
            SELECT
                p.id, p.name, p.overall_rating,
                ST_X(p.location) AS lng,
                ST_Y(p.location) AS lat,
                COUNT(DISTINCT r.id)                                         AS review_count,
                COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high')   AS high_count,
                MODE() WITHIN GROUP (ORDER BY ar.severity)                   AS dominant_severity,
                ARRAY_AGG(DISTINCT ar.pain_point_category)
                    FILTER (WHERE ar.pain_point_category IS NOT NULL)        AS pain_categories
            FROM places p
            LEFT JOIN reviews r  ON r.place_id = p.id
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE p.location IS NOT NULL
            GROUP BY p.id, p.name, p.overall_rating, p.location
        """)
    )
    features = []
    for row in result.fetchall():
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row.lng, row.lat],
            },
            "properties": {
                "id": row.id,
                "name": row.name,
                "rating": float(row.overall_rating) if row.overall_rating else None,
                "review_count": row.review_count,
                "high_count": row.high_count or 0,
                "dominant_severity": row.dominant_severity,
                "pain_point_categories": row.pain_categories or [],
            },
        })
    return {"type": "FeatureCollection", "features": features}
