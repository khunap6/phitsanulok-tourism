"""schema ของ endpoint ชั้น aspect

⚠️ ทุก response ที่มีสัดส่วนต้องพกคำอธิบายตัวส่วนมาด้วย
  เพราะตัวเลขรายหมวดรวมกันเกิน 100% ซึ่งถูกต้องแต่ชวนเข้าใจผิด
  ถ้าไม่บอก คนอ่านจะคิดว่าคำนวณผิดหรือเอาไปเทียบกับตัวเลขระดับรีวิวตรง ๆ
"""
from datetime import date
from typing import Optional

from pydantic import BaseModel


class CategorySummaryItem(BaseModel):
    category_id: int
    category_name: str
    # จำนวน "รีวิว" ที่พูดถึงหมวดนี้ — 1 รีวิวนับครั้งเดียวต่อหมวด
    n_reviews: int
    n_positive: int
    n_neutral: int
    n_negative: int
    # หารด้วยจำนวนรีวิวทั้งหมดในช่วงที่เลือก ไม่ใช่ผลรวมของทุกหมวด
    share_of_reviews: float
    # n_negative / n_reviews — อัตราการติของหมวดนี้โดยเฉพาะ
    negative_rate: float
    # จำนวนรีวิวที่ "หมวดหลัก" คือหมวดนี้ — ผลรวมทุกหมวดเท่ากับจำนวนรีวิวพอดี
    # ใช้ทำกราฟที่ต้องรวมได้ 100% ส่วน n_reviews ใช้ทำกราฟที่รวมเกิน 100%
    n_primary: int = 0
    share_as_primary: float = 0.0
    # แยกอารมณ์ของ "หมวดหลัก" เพื่อให้กราฟโหมด 100% ซ้อนสีได้เหมือนกัน
    np_positive: int = 0
    np_neutral: int = 0
    np_negative: int = 0
    low_data: bool
    is_non_problem: bool


class CategorySummaryResponse(BaseModel):
    items: list[CategorySummaryItem]
    total_reviews: int
    total_mentions: int
    # ต้องเท่ากับ total_reviews พอดี — ถ้าไม่เท่าแปลว่ามีรีวิวที่ไม่มี is_primary
    total_primary: int = 0
    low_data_threshold: int
    denominator_note: str


class AspectOverview(BaseModel):
    # ระดับรีวิว — รวมได้ 100%
    total_reviews: int
    reviews_positive: int
    reviews_neutral: int
    reviews_negative: int
    complaint_rate: float
    # ระดับการกล่าวถึง — รวมเกิน 100%
    total_mentions: int
    mentions_negative: int
    mentions_per_review: float
    unit_note: str


class AspectReviewItem(BaseModel):
    review_id: int
    text: str
    rating: Optional[int] = None
    # ⚠️ reviews.review_date เป็น "ข้อความสัมพัทธ์" เช่น "6 ปีที่แล้ว"
    #   ส่วนวันที่จริงที่แปลงแล้วอยู่ในคอลัมน์ review_date_approx
    #   เคยพลาดมาแล้วตอนเขียน endpoint นี้ จึงแยกสองฟิลด์ให้ชัด
    review_date: Optional[date] = None          # มาจาก review_date_approx
    review_date_text: Optional[str] = None      # ข้อความดิบจาก Google
    place_name: Optional[str] = None
    category_id: int
    category_name: str
    aspect_sentiment: str
    is_primary: bool
    overall_sentiment: Optional[str] = None
