from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.schemas.analysis import (
    CategoryCount,
    GeoJSONCollection,
    GeoJSONFeature,
    GeoJSONGeometry,
    InsightResponse,
)

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/summary", response_model=InsightResponse)
async def insights_summary(db: Annotated[AsyncSession, Depends(get_db)]):
    counts = await db.execute(
        text("""
            SELECT
                (SELECT COUNT(*) FROM places)          AS total_places,
                (SELECT COUNT(*) FROM reviews)         AS total_reviews,
                (SELECT COUNT(*) FROM analyzed_reviews) AS total_analyzed
        """)
    )
    row = counts.fetchone()
    total_places, total_reviews, total_analyzed = (
        row.total_places, row.total_reviews, row.total_analyzed
    )

    cat_result = await db.execute(
        text("""
            SELECT pain_point_category AS category, COUNT(*) AS count
            FROM analyzed_reviews
            WHERE pain_point_category IS NOT NULL
            GROUP BY pain_point_category
            ORDER BY count DESC
            LIMIT 10
        """)
    )
    top_categories = [
        {"category": r.category, "count": r.count}
        for r in cat_result.fetchall()
    ]

    sev_result = await db.execute(
        text("""
            SELECT severity, COUNT(*) AS count
            FROM analyzed_reviews
            WHERE severity IS NOT NULL
            GROUP BY severity
        """)
    )
    severity_dist = {r.severity: r.count for r in sev_result.fetchall()}

    worst_result = await db.execute(
        text("""
            SELECT p.name AS place_name,
                   COUNT(*) FILTER (WHERE ar.severity = 'high') AS high_count
            FROM places p
            JOIN reviews r  ON r.place_id = p.id
            JOIN analyzed_reviews ar ON ar.review_id = r.id
            GROUP BY p.id, p.name
            ORDER BY high_count DESC
            LIMIT 10
        """)
    )
    worst_places = [
        {"place_name": r.place_name, "high_count": r.high_count}
        for r in worst_result.fetchall()
    ]

    return {
        "total_places": total_places,
        "total_reviews": total_reviews,
        "total_analyzed": total_analyzed,
        "top_pain_point_categories": top_categories,
        "severity_distribution": severity_dist,
        "worst_places": worst_places,
    }


@router.get("/top-places")
async def top_problematic_places(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 10,
):
    result = await db.execute(
        text("""
            SELECT p.id, p.name,
                   p.overall_rating,
                   COUNT(DISTINCT r.id)                                          AS review_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high')    AS high_count,
                   COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'medium')  AS medium_count
            FROM places p
            JOIN reviews r  ON r.place_id = p.id
            JOIN analyzed_reviews ar ON ar.review_id = r.id
            GROUP BY p.id, p.name, p.overall_rating
            ORDER BY high_count DESC, medium_count DESC
            LIMIT :lim
        """),
        {"lim": limit},
    )
    return [dict(row._mapping) for row in result.fetchall()]


@router.get("/categories", response_model=list[CategoryCount])
async def category_counts(db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        text("""
            SELECT pain_point_category AS category, COUNT(*) AS count
            FROM analyzed_reviews
            WHERE pain_point_category IS NOT NULL
            GROUP BY pain_point_category
            ORDER BY count DESC
        """)
    )
    return [{"category": r.category, "count": r.count} for r in result.fetchall()]


@router.get("/heatmap", response_model=GeoJSONCollection)
async def heatmap_geojson(db: Annotated[AsyncSession, Depends(get_db)]):
    """GeoJSON FeatureCollection — one feature per place with analysis properties."""
    result = await db.execute(
        text("""
            SELECT
                p.id, p.name,
                p.overall_rating,
                ST_X(p.location) AS lng,
                ST_Y(p.location) AS lat,
                MODE() WITHIN GROUP (ORDER BY ar.severity)           AS dominant_severity,
                ARRAY_AGG(DISTINCT ar.pain_point_category)
                    FILTER (WHERE ar.pain_point_category IS NOT NULL) AS pain_categories,
                COUNT(DISTINCT ar.id) FILTER (WHERE ar.severity = 'high') AS high_count
            FROM places p
            LEFT JOIN reviews r  ON r.place_id = p.id
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE p.location IS NOT NULL
            GROUP BY p.id, p.name, p.overall_rating, p.location
        """)
    )

    features = []
    for row in result.fetchall():
        if row.lat is None or row.lng is None:
            continue
        features.append(
            GeoJSONFeature(
                geometry=GeoJSONGeometry(
                    type="Point",
                    coordinates=[row.lng, row.lat],
                ),
                properties={
                    "id": row.id,
                    "name": row.name,
                    "rating": float(row.overall_rating) if row.overall_rating else None,
                    "dominant_severity": row.dominant_severity,
                    "pain_point_categories": row.pain_categories or [],
                    "high_count": row.high_count or 0,
                },
            )
        )

    return GeoJSONCollection(features=features)
