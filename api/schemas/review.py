from typing import Optional

from pydantic import BaseModel


class ReviewResponse(BaseModel):
    id: int
    place_id: int
    place_name: Optional[str] = None
    rating: Optional[int] = None
    text: str
    review_date: Optional[str] = None
    sentiment: Optional[str] = None
    pain_point_category: Optional[str] = None
    pain_point_thai: Optional[str] = None
    severity: Optional[str] = None
    keywords: Optional[list[str]] = None

    model_config = {"from_attributes": True}


class ReviewListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ReviewResponse]
