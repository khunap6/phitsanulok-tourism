"""เพิ่มโครงสร้าง Multi-Aspect + Multi-Label — ตาราง categories, review_aspects
และคอลัมน์ระดับรีวิวชุดใหม่

ทำไมต้องเปลี่ยน (วัดไว้แล้ว):
  เดิม analyzed_reviews มี review_id เป็น unique จึงเก็บได้รีวิวละ 1 หมวด
  แต่ชุด gold บอกว่าจริง ๆ แล้ว 1.96 หมวด/รีวิว — โมเดลเดิมจึงมี recall แค่ 0.407
  และ 13.1% ของรีวิวมีหมวดที่อารมณ์ไม่เหมือนกัน การใช้อารมณ์เดียวกับทุกหมวด
  ทำให้หมวดที่ถูก "ชม" ถูกนับเป็นคำบ่น (ถูกแค่ 49.4% ในกลุ่มนั้น)

⚠️ ไม่แตะของเดิมสักคอลัมน์
  analyzed_reviews.sentiment และ .pain_point_category ยังอยู่ครบและมีค่าเหมือนเดิม
  ทุก endpoint ทุกรายงานที่อ่านสองคอลัมน์นี้จึงทำงานต่อได้ทันทีโดยไม่ต้องแก้
  คอลัมน์ใหม่ overall_sentiment / primary_category_id เป็นของชุดใหม่
  ให้โค้ดใหม่อ่าน ส่วนของเดิมถือเป็น legacy (ผู้ใช้สั่งไว้ในข้อ 5)

⚠️ snapshot เก่าห้ามแก้ย้อนหลัง (ผู้ใช้สั่งไว้ในข้อ 6)
  เพิ่ม category_version แทน แถวเก่าเป็น 'v1' (หมวด 12 ชุดเดิม)
  แถวที่เขียนใหม่หลังจากนี้เป็น 'v2' (หมวด 11 ชุดใหม่)
  ตอนอ่านค่อย map ตาม version ไม่ใช่เขียนทับของเก่า

⚠️ review_aspects.severity เป็น nullable และยังไม่บังคับกรอกในรอบนี้
  (ผู้ใช้สั่งไว้ในข้อ 8) ของเดิม analyzed_reviews.severity ยังทำงานเหมือนเดิม

⚠️ label_source แยก "ป้ายจากคน" ออกจาก "ป้ายจากโมเดล"
  gold | claude_guided | claude_silver | model | human_verified
  ชุด 300 รีวิวเป็น claude_guided ไม่ใช่ gold เพราะยังไม่มีคนตรวจ
  ถ้าเขียนว่า gold แล้วอ้างในเล่มว่าเป็น ground truth จากคน จะเป็นการรายงานผิด

Revision ID: 018
Revises: 017
Create Date: 2026-10-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ตารางหมวดหมู่ชุดใหม่ ──
    # มีไว้ให้คิวรี join เอาชื่อได้โดยไม่ต้องฝังชื่อไทยใน SQL
    # เนื้อหาเติมด้วย scripts/seed_categories.py ซึ่งอ่านจาก shared/categories.json
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("is_non_problem", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("version", sa.String(10), nullable=False, server_default="v2"),
    )

    # ── คอลัมน์ระดับรีวิวชุดใหม่ ──
    op.add_column("analyzed_reviews",
                  sa.Column("overall_sentiment", sa.String(20), nullable=True))
    op.add_column("analyzed_reviews",
                  sa.Column("primary_category_id", sa.Integer(), nullable=True))
    op.add_column("analyzed_reviews",
                  sa.Column("needs_review", sa.Boolean(), nullable=False,
                            server_default=sa.false()))
    op.add_column("analyzed_reviews",
                  sa.Column("label_source", sa.String(20), nullable=True))
    op.create_foreign_key("fk_analyzed_primary_category", "analyzed_reviews",
                          "categories", ["primary_category_id"], ["id"],
                          ondelete="SET NULL")
    op.create_index("ix_analyzed_primary_category", "analyzed_reviews",
                    ["primary_category_id"])
    op.create_index("ix_analyzed_overall_sentiment", "analyzed_reviews",
                    ["overall_sentiment"])

    # ── ตารางระดับหมวด (หัวใจของงานนี้) ──
    # PK = (review_id, category_id) ตามที่โจทย์กำหนด
    # 1 รีวิวมีได้หลายแถว แถวละ 1 หมวด พร้อมอารมณ์ของหมวดนั้น
    op.create_table(
        "review_aspects",
        sa.Column("review_id", sa.Integer(),
                  sa.ForeignKey("reviews.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("category_id", sa.Integer(),
                  sa.ForeignKey("categories.id", ondelete="RESTRICT"),
                  primary_key=True),
        sa.Column("aspect_sentiment", sa.String(20), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        # ยังไม่บังคับกรอกในรอบนี้
        sa.Column("severity", sa.String(10), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("label_source", sa.String(20), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "aspect_sentiment IN ('positive','neutral','negative')",
            name="ck_review_aspects_sentiment"),
    )
    op.create_index("ix_review_aspects_category", "review_aspects",
                    ["category_id"])
    op.create_index("ix_review_aspects_cat_sent", "review_aspects",
                    ["category_id", "aspect_sentiment"])
    # ใช้บ่อยในคิวรี "หมวดหลักของรีวิว" — index บางส่วนเล็กกว่า index เต็ม
    op.create_index("ix_review_aspects_primary", "review_aspects",
                    ["review_id"], postgresql_where=sa.text("is_primary"))

    # ── snapshot: ติดเวอร์ชันของชุดหมวด ไม่แก้ค่าเก่า ──
    for tbl in ("snapshot_categories", "snapshot_places"):
        op.add_column(tbl, sa.Column("category_version", sa.String(10),
                                     nullable=False, server_default="v1"))


def downgrade() -> None:
    for tbl in ("snapshot_places", "snapshot_categories"):
        op.drop_column(tbl, "category_version")
    op.drop_index("ix_review_aspects_primary", table_name="review_aspects")
    op.drop_index("ix_review_aspects_cat_sent", table_name="review_aspects")
    op.drop_index("ix_review_aspects_category", table_name="review_aspects")
    op.drop_table("review_aspects")
    op.drop_index("ix_analyzed_overall_sentiment", table_name="analyzed_reviews")
    op.drop_index("ix_analyzed_primary_category", table_name="analyzed_reviews")
    op.drop_constraint("fk_analyzed_primary_category", "analyzed_reviews",
                       type_="foreignkey")
    op.drop_column("analyzed_reviews", "label_source")
    op.drop_column("analyzed_reviews", "needs_review")
    op.drop_column("analyzed_reviews", "primary_category_id")
    op.drop_column("analyzed_reviews", "overall_sentiment")
    op.drop_table("categories")
