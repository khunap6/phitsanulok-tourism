"""Add incremental-scan reference fields to places

เก็บ "ค่าอ้างอิง" จากการ scan ครั้งก่อน เพื่อให้ scan ครั้งต่อไปรู้ว่า
ร้านนี้เปลี่ยนแปลงหรือยัง — ไม่ต้อง scan ซ้ำทั้งหมดให้เสียเวลา

Revision ID: 007
Revises: 006
Create Date: 2026-08-18
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # จำนวนรีวิวที่เรามีตอน scan ล่าสุด (ค่าอ้างอิง)
    op.add_column("places", sa.Column("last_review_count", sa.Integer(), nullable=True))
    # scan ล่าสุดได้รีวิวใหม่กี่อัน (0 = ไม่มีอะไรเปลี่ยน)
    op.add_column("places", sa.Column("last_scan_new_reviews", sa.Integer(), nullable=True))
    # ไม่มีรีวิวใหม่ติดกันกี่ครั้ง → ใช้ยืดรอบ scan ให้ห่างขึ้น
    op.add_column(
        "places",
        sa.Column("consecutive_no_change", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("places", "consecutive_no_change")
    op.drop_column("places", "last_scan_new_reviews")
    op.drop_column("places", "last_review_count")
