from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.schemas.place import (
    NearbyPlaceResponse,
    PainPointSummaryItem,
    PlaceDetailResponse,
    PlaceResponse,
)

router = APIRouter(tags=["places"])

_PLACE_SELECT = """
    SELECT
        p.id, p.name, p.search_query, p.overall_rating, p.scraped_at,
        ST_X(p.location) AS lng,
        ST_Y(p.location) AS lat,
        COUNT(DISTINCT r.id)                                             AS review_count,
        COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high')       AS high_severity_count
    FROM places p
    LEFT JOIN reviews r  ON r.place_id = p.id
    LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
"""


@router.get("/places", response_model=list[PlaceResponse])
async def list_places(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    result = await db.execute(
        text(
            _PLACE_SELECT
            + " GROUP BY p.id ORDER BY p.name LIMIT :lim OFFSET :off"
        ),
        {"lim": limit, "off": offset},
    )
    return [dict(row._mapping) for row in result.fetchall()]


# NOTE: /places/nearby must be declared BEFORE /places/{id}
@router.get("/places/nearby", response_model=list[NearbyPlaceResponse])
async def nearby_places(
    db: Annotated[AsyncSession, Depends(get_db)],
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    radius: float = Query(5000, description="Radius in metres", ge=100, le=100_000),
    limit: int = Query(20, ge=1, le=100),
):
    result = await db.execute(
        text("""
            SELECT
                p.id, p.name, p.overall_rating,
                ST_X(p.location) AS lng,
                ST_Y(p.location) AS lat,
                ST_Distance(p.location::geography,
                            ST_MakePoint(:lng, :lat)::geography) AS distance_m,
                COUNT(DISTINCT r.id)                                           AS review_count,
                COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high')     AS high_severity_count
            FROM places p
            LEFT JOIN reviews r  ON r.place_id = p.id
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE p.location IS NOT NULL
              AND ST_DWithin(p.location::geography,
                             ST_MakePoint(:lng, :lat)::geography, :radius)
            GROUP BY p.id
            ORDER BY distance_m
            LIMIT :lim
        """),
        {"lat": lat, "lng": lng, "radius": radius, "lim": limit},
    )
    return [dict(row._mapping) for row in result.fetchall()]


@router.get("/places/{place_id}", response_model=PlaceDetailResponse)
async def get_place(
    place_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        text(
            _PLACE_SELECT
            + " WHERE p.id = :id GROUP BY p.id"
        ),
        {"id": place_id},
    )
    row = result.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return dict(row._mapping)


@router.get("/places/{place_id}/pain-points", response_model=list[PainPointSummaryItem])
async def place_pain_points(
    place_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(
        text("""
            SELECT ar.pain_point_category AS category,
                   ar.severity,
                   COUNT(*) AS count
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            WHERE r.place_id = :pid
            GROUP BY ar.pain_point_category, ar.severity
            ORDER BY count DESC
        """),
        {"pid": place_id},
    )
    return [dict(row._mapping) for row in result.fetchall()]
