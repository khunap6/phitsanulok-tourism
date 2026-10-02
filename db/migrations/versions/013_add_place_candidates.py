"""ตารางพักผลจาก Places API discover (place_candidates) + log เซลล์ที่ค้นแล้ว

ทำไมผลจาก API ต้องลงตารางพัก ไม่ไหลเข้า places ตรง ๆ:
  1. รันซ้ำได้ไม่เสียเงินซ้ำ — discover_cells จำว่าเซลล์ไหนค้นแล้ว รอบถัดไปข้าม
  2. มีด่านให้คนดูก่อนอนุมัติ — ข้อมูลดิบจาก Google ไม่ไหลเข้าฐานวิทยานิพนธ์ทันที
  3. ตอบคำถามเรื่องชื่อซ้ำได้โดยยังไม่เสี่ยงอะไร (places.name เป็น UNIQUE
     ถ้า Google คืนร้านชื่อซ้ำแล้วเขียนเข้า places ตรง ๆ จะยุบเป็นแถวเดียว
     รีวิวปนกันเงียบ ๆ — ตารางพักทำให้เห็นก่อนว่ามีกี่คู่)

discover_cells มีไว้เพื่อ 3 อย่าง:
  - resume: รันใหม่แล้วข้ามเซลล์ที่ทำไปแล้ว (= ไม่จ่ายเงินซ้ำถ้าพังกลางทาง)
  - ตรวจ cap 60: Nearby Search คืนได้สูงสุด 60 ผล/คำขอ เซลล์ที่ได้ครบ 60
    แปลว่า "น่าจะถูกตัด" ต้องซอยเซลล์ย่อยลงอีก ถ้าไม่ log ไว้จะไม่รู้ว่าข้อมูลขาด
  - บัญชีค่าใช้จ่าย: นับ pages ที่ยิงจริงต่อเซลล์ เทียบกับยอดใน Billing ได้

⚠️ place_candidates.google_reviews_total เป็นจำนวนรีวิวที่ Google *มี*
   ห้ามใช้เป็นตัวส่วนของอัตราส่วนใด ๆ (เหตุผลเต็มอยู่ใน migration 012)
   ในตารางนี้ใช้เพื่อ "คัดว่าร้านไหนคุ้มเอาไป scrape" เท่านั้น

Revision ID: 013
Revises: 012
Create Date: 2026-09-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "place_candidates",
        # google_place_id เป็น PK — กันซ้ำข้ามเซลล์/ข้าม type ให้อัตโนมัติ
        # (ร้านหนึ่งมี types[] หลายค่า จึงถูกคืนซ้ำจากหลาย type ได้)
        sa.Column("google_place_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("google_types", sa.Text(), nullable=True),
        sa.Column("google_rating", sa.Numeric(2, 1), nullable=True),
        sa.Column("google_reviews_total", sa.Integer(), nullable=True),
        sa.Column("business_status", sa.String(30), nullable=True),
        # vicinity = ที่อยู่ย่อที่ Nearby Search ให้มา (ไม่ใช่ formatted_address
        # ซึ่งต้องเรียก Details แยก) พอสำหรับดูว่าอยู่แถวไหน
        sa.Column("vicinity", sa.Text(), nullable=True),
        # zone คำนวณด้วย assign_zone() ตัวเดิม — นิยามโซนไม่ถูกแก้
        # ร้านที่ห่างเกิน 2 กม. จะได้ 'other' ตามกฎเดิมอย่างถูกต้อง
        sa.Column("zone", sa.String(30), nullable=True),
        # ระยะจากศูนย์โซนที่ใกล้สุด + ชื่อโซนนั้น (แม้จะเกินรัศมีโซน)
        # สองคอลัมน์นี้คือที่มาของ "ตารางวงแหวน" ที่จะตอบว่าควรขยายรัศมีไหม
        sa.Column("nearest_zone", sa.String(30), nullable=True),
        sa.Column("dist_km", sa.Numeric(6, 3), nullable=True),
        sa.Column("source_type", sa.String(40), nullable=True),
        sa.Column("source_cell", sa.String(48), nullable=True),
        sa.Column("first_seen_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        # เจอซ้ำจากกี่ (เซลล์, type) — ร้านที่โผล่หลายที่คือร้านที่อยู่กลางพื้นที่ทับซ้อน
        sa.Column("seen_count", sa.Integer(), nullable=False, server_default="1"),
        # จับคู่กับร้านเดิมได้ไหม — เติมทันทีถ้า google_place_id ตรงกับ places
        sa.Column("matched_place_id", sa.Integer(),
                  sa.ForeignKey("places.id", ondelete="SET NULL"), nullable=True),
        # new = ร้านใหม่ที่ควรเก็บ | existing = มีใน places แล้ว | reject = ไม่เอา
        sa.Column("decision", sa.String(20), nullable=True),
    )
    op.create_index("ix_place_candidates_zone", "place_candidates", ["zone"])
    op.create_index("ix_place_candidates_decision", "place_candidates", ["decision"])
    op.create_index("ix_place_candidates_matched", "place_candidates",
                    ["matched_place_id"])

    op.create_table(
        "discover_cells",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cell_lat", sa.Float(), nullable=False),
        sa.Column("cell_lng", sa.Float(), nullable=False),
        sa.Column("cell_radius_m", sa.Integer(), nullable=False),
        sa.Column("place_type", sa.String(40), nullable=False),
        # pages = จำนวนคำขอที่ยิงจริงสำหรับเซลล์+type นี้ (1-3)
        sa.Column("pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("results", sa.Integer(), nullable=False, server_default="0"),
        # True = ได้ครบ 60 ผล → น่าจะถูกตัด ต้องซอยเซลล์ย่อย
        sa.Column("hit_cap", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(30), nullable=True),
        sa.Column("fetched_at", sa.TIMESTAMP(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("cell_lat", "cell_lng", "cell_radius_m", "place_type",
                            name="uq_discover_cell"),
    )
    op.create_index("ix_discover_cells_cap", "discover_cells", ["hit_cap"])


def downgrade() -> None:
    op.drop_index("ix_discover_cells_cap", table_name="discover_cells")
    op.drop_table("discover_cells")
    op.drop_index("ix_place_candidates_matched", table_name="place_candidates")
    op.drop_index("ix_place_candidates_decision", table_name="place_candidates")
    op.drop_index("ix_place_candidates_zone", table_name="place_candidates")
    op.drop_table("place_candidates")
