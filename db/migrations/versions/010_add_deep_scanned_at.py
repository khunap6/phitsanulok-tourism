"""Add deep_scanned_at to places (deep scan bookkeeping)

บอกว่าร้านนี้ผ่าน "deep scan" (เก็บรีวิวแบบไม่จำกัดจำนวน) ไปแล้วเมื่อไร
NULL = ยังไม่เคยทำ → scripts/deep_scan.py จะหยิบมาทำ
ตั้งค่าเมื่อ scrape ร้านนั้นสำเร็จจริงเท่านั้น (ดู run_deep_scan)

Revision ID: 010
Revises: 009
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "places",
        sa.Column("deep_scanned_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("places", "deep_scanned_at")
