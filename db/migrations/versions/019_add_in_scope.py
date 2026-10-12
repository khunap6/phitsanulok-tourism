"""เพิ่ม places.in_scope — ธงว่าสถานที่นี้อยู่ในขอบเขตของงานวิจัยไหม

⚠️ ต่างจาก scrape_excluded ที่มีอยู่แล้ว ห้ามใช้สลับกัน
  scrape_excluded = "ไม่ต้องเก็บรีวิวเพิ่ม"   ใช้ที่ชั้น scraper
  in_scope        = "นับในสถิติไหม"          ใช้ที่ชั้น api
  migration 017 เขียนไว้เองว่า scrape_excluded ไม่ใช่ตัวกรองของสถิติ
  และถ้าจะตัดออกจากการวิเคราะห์ต้องเติมตัวกรองใน api/ แยกอีกชุด — คอลัมน์นี้คือชุดนั้น

  วัดแล้ว scrape_excluded (9 แห่ง) เป็นสับเซตของ in_scope=false (42 แห่ง)
  ไม่มีแห่งไหนที่ scrape_excluded แต่ in_scope ซึ่งถูกต้อง

⚠️ ทำไมต้องมีคอลัมน์ ไม่ใช่คำนวณสดทุกครั้ง
  เกณฑ์อยู่ใน shared/scope.json และต้องใช้ google_types + google_category
  + รายการตัดสินรายแห่ง ถ้าคำนวณในคิวรีจะได้ SQL ยาวมากและซ้ำกันทุก endpoint
  เก็บเป็นคอลัมน์แล้ว refresh ด้วย scripts/apply_scope_to_db.py เมื่อเกณฑ์เปลี่ยน

⚠️ ตั้งค่าเริ่มต้นเป็น true ทุกแถว แล้วค่อยให้สคริปต์ตั้งค่าจริง
  ถ้าตั้ง false เป็นค่าเริ่มต้น แล้วสคริปต์ยังไม่รัน ตัวเลขทุกตัวจะกลายเป็น 0
  ซึ่งเป็นความเสียหายที่มองเห็นยากกว่าการยังไม่กรอง

⚠️ ไม่ลบข้อมูลใด ๆ สถานที่ที่ in_scope=false ยังอยู่ในฐานพร้อมรีวิวครบ
  ถอนกลับได้ด้วยการตั้งเป็น true ทั้งหมด

Revision ID: 019_add_in_scope
Revises: 018_multi_aspect
"""
import sqlalchemy as sa
from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("places", sa.Column(
        "in_scope", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("places", sa.Column(
        "in_scope_reason", sa.Text(), nullable=True))
    # ดัชนีบางส่วน เพราะทุกคิวรีสถิติจะกรอง in_scope เป็นเงื่อนไขแรก
    op.create_index("ix_places_in_scope", "places", ["in_scope"])


def downgrade() -> None:
    op.drop_index("ix_places_in_scope", table_name="places")
    op.drop_column("places", "in_scope_reason")
    op.drop_column("places", "in_scope")
