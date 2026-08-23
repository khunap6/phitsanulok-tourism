"""Add statistics snapshot tables

เก็บ "ภาพนิ่ง" ของสถิติ ณ เวลาหนึ่ง เพื่อให้เทียบย้อนหลังได้ว่าอะไรเปลี่ยนไป
ใช้เป็นฐานของระบบแจ้งเตือน (ปัญหาเพิ่มขึ้นภาพรวม vs เพิ่มเฉพาะร้าน)

Revision ID: 008
Revises: 007
Create Date: 2026-08-23
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. หัวข้อ snapshot (1 แถวต่อการเก็บ 1 ครั้ง) ──
    op.create_table(
        "stat_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("taken_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("period_label", sa.String(30), nullable=True),   # เช่น '2026-W34' หรือ '2026-08'
        sa.Column("total_places", sa.Integer(), nullable=True),
        sa.Column("total_reviews", sa.Integer(), nullable=True),
        sa.Column("total_analyzed", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_stat_snapshots_taken_at", "stat_snapshots", ["taken_at"])

    # ── 2. สถิติระดับหมวด (zone=NULL คือภาพรวมทั้งจังหวัด) ──
    op.create_table(
        "snapshot_categories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.Integer(),
                  sa.ForeignKey("stat_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone", sa.String(30), nullable=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("complaint_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("praise_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("high_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("medium_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("low_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_snap_cat_lookup", "snapshot_categories", ["snapshot_id", "zone", "category"])

    # ── 3. สถิติระดับร้าน × หมวด (ตอบว่า "เพิ่มภาพรวม หรือเพิ่มแค่ร้านเดียว") ──
    op.create_table(
        "snapshot_places",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.Integer(),
                  sa.ForeignKey("stat_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("place_id", sa.Integer(),
                  sa.ForeignKey("places.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("complaint_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("praise_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("high_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_snap_place_lookup", "snapshot_places", ["snapshot_id", "category"])
    op.create_index("ix_snap_place_place", "snapshot_places", ["place_id"])


def downgrade() -> None:
    op.drop_table("snapshot_places")
    op.drop_table("snapshot_categories")
    op.drop_index("ix_stat_snapshots_taken_at", table_name="stat_snapshots")
    op.drop_table("stat_snapshots")
