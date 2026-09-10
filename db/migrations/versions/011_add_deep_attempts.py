"""Add deep_attempts to places (นับครั้งที่ deep scan ล้มเหลวแบบเข้าไม่ถึงหน้ารีวิว)

แยก 3 สถานะออกจากกันให้คิวรีนับได้:
  deep_scanned_at IS NOT NULL                          → เก็บสำเร็จ
  deep_scanned_at IS NULL AND deep_attempts >= 3       → ยอมแพ้ (ไว้ตรวจซ้ำด้วย Places API)
  deep_scanned_at IS NULL AND deep_attempts <  3       → ยังอยู่ในคิว

นับเฉพาะความล้มเหลวที่เป็นความผิดของหน้าเว็บ (เข้าไม่ถึงหน้ารีวิว) เท่านั้น
ไม่นับตอนโดนบล็อก — หลักการเดียวกับที่ run_refresh ไม่อัปเดต scan stats ตอนโดนบล็อก

Revision ID: 011
Revises: 010
Create Date: 2026-09-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "places",
        sa.Column("deep_attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("places", "deep_attempts")
