"""Add Phase 1 fields: opening_hours, price_level, distances, review_date_approx

Revision ID: 004
Revises: 003
Create Date: 2026-07-16
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # places — ข้อมูลร้านเพิ่มเติม
    op.add_column("places", sa.Column("opening_hours", sa.Text(), nullable=True))
    op.add_column("places", sa.Column("price_level", sa.String(50), nullable=True))
    op.add_column("places", sa.Column("distance_nu_km", sa.Numeric(6, 3), nullable=True))
    op.add_column("places", sa.Column("distance_psru_km", sa.Numeric(6, 3), nullable=True))

    # reviews — วันที่โดยประมาณ (แปลงจาก relative date)
    op.add_column("reviews", sa.Column("review_date_approx", sa.Date(), nullable=True))
    op.create_index("ix_reviews_date_approx", "reviews", ["review_date_approx"])


def downgrade() -> None:
    op.drop_index("ix_reviews_date_approx", table_name="reviews")
    op.drop_column("reviews", "review_date_approx")
    op.drop_column("places", "distance_psru_km")
    op.drop_column("places", "distance_nu_km")
    op.drop_column("places", "price_level")
    op.drop_column("places", "opening_hours")
