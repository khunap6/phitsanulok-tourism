from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.schemas.review import ReviewListResponse, ReviewResponse

router = APIRouter(tags=["reviews"])

_REVIEW_SELECT = """
    SELECT
        r.id, r.place_id, p.name AS place_name,
        r.rating, r.text, r.review_date,
        ar.sentiment, ar.pain_point_category,
        ar.pain_point_thai, ar.severity, ar.keywords
    FROM reviews r
    JOIN places p ON p.id = r.place_id
    LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
"""


@router.get("/places/{place_id}/reviews", response_model=list[ReviewResponse])
async def reviews_for_place(
    place_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    severity: Optional[str] = Query(None, description="high | medium | low"),
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    filters = "WHERE r.place_id = :pid"
    params: dict = {"pid": place_id, "lim": limit, "off": offset}

    if severity:
        filters += " AND ar.severity = :sev"
        params["sev"] = severity
    if category:
        filters += " AND ar.pain_point_category = :cat"
        params["cat"] = category

    result = await db.execute(
        text(f"{_REVIEW_SELECT} {filters} ORDER BY r.id DESC LIMIT :lim OFFSET :off"),
        params,
    )
    return [dict(row._mapping) for row in result.fetchall()]


@router.get("/reviews", response_model=ReviewListResponse)
async def list_reviews(
    db: Annotated[AsyncSession, Depends(get_db)],
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    offset = (page - 1) * page_size
    filters = "WHERE 1=1"
    params: dict = {"lim": page_size, "off": offset}

    if category:
        filters += " AND ar.pain_point_category = :cat"
        params["cat"] = category
    if severity:
        filters += " AND ar.severity = :sev"
        params["sev"] = severity

    count_result = await db.execute(
        text(f"""
            SELECT COUNT(*)
            FROM reviews r
            LEFT JOIN analyzed_reviews ar ON ar.review_id = r.id
            {filters}
        """),
        params,
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(f"{_REVIEW_SELECT} {filters} ORDER BY r.id DESC LIMIT :lim OFFSET :off"),
        params,
    )
    items = [dict(row._mapping) for row in result.fetchall()]

    return {"total": total, "page": page, "page_size": page_size, "items": items}
