from typing import Any, Optional

from pydantic import BaseModel


class CategoryCount(BaseModel):
    category: str
    count: int


class PlaceSeverityCount(BaseModel):
    place_name: str
    high_count: int


class InsightResponse(BaseModel):
    total_places: int
    total_reviews: int
    total_analyzed: int
    top_pain_point_categories: list[CategoryCount]
    severity_distribution: dict[str, int]
    worst_places: list[PlaceSeverityCount]


class GeoJSONGeometry(BaseModel):
    type: str
    coordinates: list[float]


class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    geometry: GeoJSONGeometry
    properties: dict[str, Any]


class GeoJSONCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[GeoJSONFeature]


class ScrapeJobResponse(BaseModel):
    id: int
    job_type: Optional[str] = None
    status: Optional[str] = None
    places_count: Optional[int] = None
    reviews_count: Optional[int] = None
    started_at: Optional[Any] = None
    finished_at: Optional[Any] = None
    error_msg: Optional[str] = None
