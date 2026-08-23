"""Keep Claude labels as reference for model comparison

เก็บผลวิเคราะห์ของ Claude ไว้ในคอลัมน์แยก ก่อนที่ WangchanBERTa จะเขียนทับ
เพื่อให้เปรียบเทียบได้ว่าโมเดลที่เราฝึกเองทำงานต่างจาก Claude อย่างไร
— เป็นหลักฐานเชิงประจักษ์สำหรับ thesis (Knowledge Distillation evaluation)

Revision ID: 009
Revises: 008
Create Date: 2026-08-23
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ผลของ "ครู" (Claude) — เก็บไว้เทียบกับผลของ "นักเรียน" (WangchanBERTa)
    op.add_column("analyzed_reviews", sa.Column("claude_sentiment", sa.String(20), nullable=True))
    op.add_column("analyzed_reviews", sa.Column("claude_category", sa.String(100), nullable=True))
    # บอกว่าป้ายของ Claude มาจากไหน (บางแหล่งให้แค่หมวดหมู่ ไม่ได้ให้ sentiment)
    op.add_column("analyzed_reviews", sa.Column("claude_source", sa.String(40), nullable=True))
    op.create_index("ix_analyzed_claude_source", "analyzed_reviews", ["claude_source"])


def downgrade() -> None:
    op.drop_index("ix_analyzed_claude_source", table_name="analyzed_reviews")
    op.drop_column("analyzed_reviews", "claude_source")
    op.drop_column("analyzed_reviews", "claude_category")
    op.drop_column("analyzed_reviews", "claude_sentiment")
