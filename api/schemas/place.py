from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PlaceResponse(BaseModel):
    id: int
    name: str
    overall_rating: Optional[float] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    review_count: int = 0
    high_severity_count: int = 0

    model_config = {"from_attributes": True}


class PlaceDetailResponse(PlaceResponse):
    search_query: Optional[str] = None
    scraped_at: Optional[datetime] = None


class PainPointSummaryItem(BaseModel):
    category: str
    severity: str
    count: int


class NearbyPlaceResponse(PlaceResponse):
    distance_m: float
