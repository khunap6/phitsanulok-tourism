"""Add zone column to places

Revision ID: 002
Revises: 001
Create Date: 2026-07-03
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "places",
        sa.Column("zone", sa.String(30), nullable=True),
    )
    op.create_index("ix_places_zone", "places", ["zone"])


def downgrade() -> None:
    op.drop_index("ix_places_zone", table_name="places")
    op.drop_column("places", "zone")
