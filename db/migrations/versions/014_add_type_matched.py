"""เพิ่ม discover_cells.type_matched — นับว่าผลที่ Google คืนมา ตรงกับ type ที่ขอกี่รายการ

ที่มา (บทเรียนราคา $4.65):
  เราส่ง type=place_of_worship ไป 82 เซลล์ ได้ผล 2,878 รายการ แต่**เป็นศาสนสถาน
  จริงแค่ 43 รายการ (1%)** ที่เหลือคือโรงแรม ร้านค้า อู่ซ่อมรถ ปั๊มน้ำมัน ATM

  สาเหตุ: place_of_worship อยู่ใน Table 2 ของเอกสาร Google = "ประเภทที่ Places
  คืนมาได้ แต่ใช้กรองการค้นหาไม่ได้" เมื่อส่งไปเป็น type Google จะ**เพิกเฉยเงียบ ๆ**
  แล้วคืนทุก establishment ในรัศมีมาให้ ไม่มี error ไม่มีคำเตือน
  ผลข้างเคียงคือชนเพดาน 60 ถึง 52 จาก 82 เซลล์ (63% สูงสุดของทุก type)

  เทียบกับ 7 type ที่อยู่ใน Table 1 (cafe, restaurant, bakery, tourist_attraction,
  museum, park, university) ซึ่งตรง 100% ทุกตัว

เก็บตัวเลขนี้ไว้ต่อเซลล์+type เพื่อ:
  1. ให้สคริปต์หยุด type ที่ถูกเพิกเฉยได้เองหลังเก็บตัวอย่างพอ (ไม่เผาเงินต่อ)
  2. ตรวจย้อนหลังได้ว่า type ไหนเชื่อผลได้ (--verify-types)
  3. กันไม่ให้ซอยเซลล์ย่อยให้ type ที่เพิกเฉย ซึ่งจะยิ่งเก็บของนอกเรื่องเพิ่ม

ทำไมเก็บที่ discover_cells ไม่ใช่ place_candidates:
  place_candidates.source_type เขียนครั้งเดียวตอน INSERT (ON CONFLICT ไม่ทับ)
  ร้านที่ถูกคืนจากหลาย type จะจำได้แค่ type แรก → นับอัตราตรงไม่ได้
  ส่วน discover_cells เป็นราย (เซลล์, type) จึงนับได้ตรงต่อคำขอที่ยิงไปจริง

Revision ID: 014
Revises: 013
Create Date: 2026-09-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # nullable = แถวเดิม 663 แถวเป็น NULL (ยิงก่อนมีการตรวจนี้) แยกจาก 0 ที่หมายถึง
    # "ตรวจแล้วไม่ตรงเลย" — ต่างกันและต้องแยกให้ออก
    op.add_column(
        "discover_cells",
        sa.Column("type_matched", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discover_cells", "type_matched")
