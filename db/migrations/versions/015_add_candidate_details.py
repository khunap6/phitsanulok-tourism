"""เพิ่ม formatted_address + opening_hours ใน place_candidates

ทำไมต้องเก็บในตารางพัก ไม่ใช่ยิงตอนเลื่อนเข้า places:
  งานเลื่อนร้านแยกเป็น 2 ขั้นโดยเจตนา
    --details   ยิง Places Details เก็บที่อยู่เต็ม + เวลาทำการ  [เสียเงิน มีกำหนด 31 ต.ค.]
    --promote   เขียนเข้า places                                 [ฟรี ทำเมื่อไหร่ก็ได้]

  ถ้าไม่มีที่เก็บระหว่างสองขั้น ต้องรวมเป็นคำสั่งเดียว แล้วถ้าพังกลางทางจะไม่รู้ว่า
  จ่ายค่า API ไปแล้วกี่ร้านแต่ยังไม่เข้า places — ต้องยิงซ้ำทั้งชุดเพื่อความปลอดภัย
  = จ่ายสองรอบ มีคอลัมน์พักไว้แล้วรันซ้ำได้โดยข้ามร้านที่มีข้อมูลแล้ว

Nearby Search (ที่ใช้ตอน discover) ให้ vicinity มาแล้ว (ที่อยู่ย่อ เช่น "ในเมือง,
Amphoe Mueang Phitsanulok") แต่ไม่ให้ formatted_address กับ opening_hours
ต้องเรียก Place Details แยกต่อร้าน จึงเป็นค่าใช้จ่ายที่ต้องจ่ายเฉพาะร้านที่จะเก็บจริง
(433 ร้านจากผู้สมัคร 8,147 ร้าน — ถ้ายิงทุกร้านจะเสียเงิน 19 เท่าโดยไม่ได้ใช้)

รูปแบบ opening_hours ใช้ชุดเดียวกับที่ scraper เก็บ (ผ่าน _parse_weekly_hours):
  "ทุกวัน 06:00-18:00"  หรือ  "จ 08:00-17:00 | ส 09:30-14:30"  หรือ  "ไม่ระบุ"
เพื่อให้คอลัมน์ places.opening_hours มีความหมายเดียวไม่ว่าข้อมูลมาจากทางไหน

Revision ID: 015
Revises: 014
Create Date: 2026-09-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("place_candidates",
                  sa.Column("formatted_address", sa.Text(), nullable=True))
    op.add_column("place_candidates",
                  sa.Column("opening_hours", sa.Text(), nullable=True))
    # ดึง Details มาเมื่อไร — NULL = ยังไม่เคยดึง (ใช้เป็นตัว resume ของ --details)
    op.add_column("place_candidates",
                  sa.Column("details_fetched_at", sa.TIMESTAMP(timezone=True),
                            nullable=True))


def downgrade() -> None:
    op.drop_column("place_candidates", "details_fetched_at")
    op.drop_column("place_candidates", "opening_hours")
    op.drop_column("place_candidates", "formatted_address")
