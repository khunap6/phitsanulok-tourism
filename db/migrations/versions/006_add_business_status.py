"""Add business_status to places

Revision ID: 006
Revises: 005
Create Date: 2026-07-24
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "places",
        sa.Column("business_status", sa.String(30), nullable=True, server_default="operational"),
    )


def downgrade() -> None:
    op.drop_column("places", "business_status")
