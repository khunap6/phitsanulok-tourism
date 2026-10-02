"""เพิ่ม places.scrape_excluded — ธงกันร้านที่อยู่นอกขอบเขตงานไม่ให้เข้าคิว scrape

ทำไมต้องมีคอลัมน์นี้ ไม่ใช่ลบร้านทิ้ง:
  ขอบเขตงานวิจัยตัดโรงแรม/เชน/ห้างออกจากการเก็บรีวิว แต่ข้อมูลระดับร้าน
  (พิกัด, หมวด, คะแนน Google, จำนวนรีวิวจริง, ที่อยู่, เวลาทำการ) ยิง API
  มาครบแล้วและมีค่าในตัวเอง — ใช้เป็นตัวส่วนวัดความครอบคลุมพื้นที่ได้
  ลบร้านทิ้งจะทำให้ ON DELETE CASCADE ลบรีวิวที่เก็บมาแล้วไปด้วย กู้ไม่ได้

  ธงนี้แยก "ไม่เก็บรีวิวเพิ่ม" ออกจาก "ไม่มีข้อมูล" — ถอนกลับได้ด้วยการ
  ตั้งเป็น false ไม่มีอะไรหายไประหว่างทาง

⚠️ ทุกจุดที่สร้างคิว scrape ต้องกรอง NOT scrape_excluded ให้ครบพร้อมกัน
  โดยเฉพาะ scraper.load_places_to_refresh กับ auto_refresh.eligible_count
  ที่ต้องใช้เกณฑ์ตรงกันเป๊ะ ไม่งั้น auto_refresh จะนับว่ามีงานเหลือ
  แต่ run_refresh ไม่หยิบร้านไหนมาทำ → loop วนไม่จบ
  (กับดักเดียวกับที่คอมเมนต์ใน eligible_count เตือนไว้)

⚠️ คอลัมน์นี้ไม่ใช่ตัวกรองของสถิติ pain point
  รีวิวที่เก็บมาก่อนถูกตั้งธงยังอยู่ในฐานและยังถูกนับใน api/ ตามเดิม
  ถ้าจะตัดออกจากการวิเคราะห์ด้วยต้องเติมตัวกรองใน api/ แยกอีกชุด และต้อง
  เติมทั้งตัวตั้งและตัวส่วนพร้อมกัน (กฎข้อ 1) ไม่ใช่เติมข้างเดียว

Revision ID: 017
Revises: 016
Create Date: 2026-09-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "places",
        sa.Column("scrape_excluded", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )
    op.add_column(
        "places",
        sa.Column("scrape_excluded_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("places", "scrape_excluded_reason")
    op.drop_column("places", "scrape_excluded")
