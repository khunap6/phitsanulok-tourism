"""Initial schema — places, reviews, analyzed_reviews, scrape_jobs

Revision ID: 001
Revises:
Create Date: 2026-05-28 00:00:00.000000

"""
from typing import Sequence, Union

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostGIS extension (ต้องรันก่อน create table ที่ใช้ GEOMETRY)
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # ------------------------------------------------------------------
    # places
    # ------------------------------------------------------------------
    op.create_table(
        "places",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("search_query", sa.String(255), nullable=True),
        sa.Column("overall_rating", sa.Numeric(2, 1), nullable=True),
        sa.Column(
            "location",
            geoalchemy2.types.Geometry("POINT", srid=4326),
            nullable=True,
        ),
        sa.Column("scraped_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    # Spatial index สำหรับ ST_DWithin / ST_Within queries
    # NOTE: geoalchemy2 auto-creates idx_places_location GIST index

    # ------------------------------------------------------------------
    # reviews
    # ------------------------------------------------------------------
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(32), nullable=True),
        sa.Column("review_date", sa.String(100), nullable=True),
        sa.Column(
            "scraped_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=True,
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="chk_rating"),
        sa.ForeignKeyConstraint(["place_id"], ["places.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("place_id", "text_hash", name="uq_place_text_hash"),
    )

    # ------------------------------------------------------------------
    # analyzed_reviews
    # ------------------------------------------------------------------
    op.create_table(
        "analyzed_reviews",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("sentiment", sa.String(20), nullable=True),
        sa.Column("pain_point_category", sa.String(100), nullable=True),
        sa.Column("pain_point_thai", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(10), nullable=True),
        sa.Column("keywords", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column(
            "analyzed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=True,
        ),
        sa.Column("model_used", sa.String(50), nullable=True),
        sa.ForeignKeyConstraint(["review_id"], ["reviews.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id"),
    )

    # ------------------------------------------------------------------
    # scrape_jobs
    # ------------------------------------------------------------------
    op.create_table(
        "scrape_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_type", sa.String(20), nullable=True),
        sa.Column("places_count", sa.Integer(), nullable=True),
        sa.Column("reviews_count", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("scrape_jobs")
    op.drop_table("analyzed_reviews")
    op.drop_table("reviews")
    op.drop_table("places")
