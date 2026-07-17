"""Add google_category column to places

Revision ID: 003
Revises: 002
Create Date: 2026-07-10
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "places",
        sa.Column("google_category", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("places", "google_category")
