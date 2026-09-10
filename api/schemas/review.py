from datetime import date
from typing import Optional

from pydantic import BaseModel


class ReviewResponse(BaseModel):
    id: int
    place_id: int
    place_name: Optional[str] = None
    rating: Optional[int] = None
    text: str
    review_date: Optional[str] = None
    # วันที่โดยประมาณที่คำนวณตอน scrape — ใช้แสดงผลแทน review_date ซึ่งเป็น
    # ข้อความสัมพัทธ์ที่เพี้ยนขึ้นเรื่อย ๆ ตามเวลา
    review_date_approx: Optional[date] = None
    sentiment: Optional[str] = None
    pain_point_category: Optional[str] = None
    pain_point_thai: Optional[str] = None
    severity: Optional[str] = None
    keywords: Optional[list[str]] = None

    model_config = {"from_attributes": True}


class ReviewListResponse(BaseModel):
    total: int
    # รีวิวที่เข้าเงื่อนไขอื่นครบแต่ไม่มีข้อความ (ให้ดาวอย่างเดียว) — ถูกซ่อนจากรายการ
    hidden_no_text: int = 0
    page: int
    page_size: int
    items: list[ReviewResponse]
