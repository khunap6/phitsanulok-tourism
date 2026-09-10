from typing import Any, Optional

from pydantic import BaseModel


# ── ตัวชี้วัดเชิงสัดส่วน ────────────────────────────────────────────────────
# ฟิลด์ใหม่ทุกตัวเป็น Optional[...] = None เพื่อไม่ให้ response เดิมพัง (กฎ 3)
# ค่า None ของอัตรา = "ไม่มีข้อมูลให้วัด" ไม่ใช่ 0% (= "วัดแล้วไม่พบ") — กฎ 2
# ฝั่ง UI ต้องแสดง "—" เมื่อเป็น None และห้ามแสดง % โดยไม่มี n ควบคู่


class CategoryCount(BaseModel):
    category: str
    count: int
    # สัดส่วนในหมู่คำบ่น — มีค่าเฉพาะ view_mode='complaints'
    # (โหมดอื่นตัวเศษไม่ใช่รีวิวเชิงลบ ชื่อฟิลด์จะโกหก จึงคืน None)
    share_of_negative: Optional[float] = None
    # สัดส่วนเทียบรีวิวที่มีข้อความทั้งหมดในช่วงนั้น — ใช้ได้ทุกโหมด
    rate_of_all: Optional[float] = None


class PlaceSeverityCount(BaseModel):
    place_name: str
    high_count: int
    review_count: Optional[int] = None
    high_rate: Optional[float] = None


class SentimentCounts(BaseModel):
    negative: int = 0
    positive: int = 0
    neutral: int = 0


class InsightResponse(BaseModel):
    # ── ฟิลด์เดิม ──
    total_places: int
    total_reviews: int
    total_analyzed: int
    top_pain_point_categories: list[CategoryCount]
    severity_distribution: dict[str, int]
    worst_places: list[PlaceSeverityCount]
    # ── ฟิลด์ใหม่: ตัวส่วนหลักและสัดส่วนที่คิดจากตัวส่วนนั้น ──
    # total_with_text = รีวิวในช่วงนั้นที่ text_clean <> '' + มีแถวใน analyzed_reviews
    #                   + ผ่าน status_filter  (≠ total_reviews / total_analyzed)
    total_with_text: Optional[int] = None
    sentiment_counts: Optional[SentimentCounts] = None
    complaint_rate: Optional[float] = None
    # severity บนฐานเดียวกับ severity_share — ต่างจาก severity_distribution
    # ที่ไม่กรอง text_clean/status ห้ามจับคู่ % ใหม่กับจำนวนเดิม (คนละประชากร)
    severity_counts: Optional[dict[str, int]] = None
    severity_share: Optional[dict[str, Optional[float]]] = None


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
