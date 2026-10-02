"""เพิ่มฟิลด์ที่มาจาก Google Places API ในตาราง places

ทั้ง 7 คอลัมน์เป็น nullable ไม่มี server_default → แถวเดิม 323 แถวเป็น NULL ทั้งหมด
และยังไม่มีโค้ดไหนอ่านค่าเหล่านี้หลัง migration นี้ (พฤติกรรมระบบไม่เปลี่ยน)

ทำไมต้องแยกคอลัมน์ใหม่ ไม่ทับของเดิม:
  overall_rating / opening_hours / business_status / google_category ที่มีอยู่
  มาจากการ scrape หน้าเว็บ ส่วนชุดนี้มาจาก API ทางการ — เก็บทั้งสองชุดไว้ทำให้
  เทียบได้ว่าที่ scrape มาเพี้ยนไหม และไม่ทำลายข้อมูลที่ใช้ในรายงานที่ออกไปแล้ว

google_place_id เป็น UNIQUE:
  Postgres ยอมให้ UNIQUE มีหลายแถวเป็น NULL ได้ จึงใส่ได้เลยตอนที่ทุกแถวยังว่าง
  ประโยชน์คือถ้า backfill เจอว่าสองแถวใน places ชี้ไปที่เดียวกันบน Google
  (= เรามีร้านซ้ำอยู่แล้วโดยไม่รู้ตัว รีวิวถูกแยกคนละแถว) INSERT จะพังให้เห็น
  แทนที่จะเงียบ — ตาราง places ใช้ name เป็นกุญแจ (UNIQUE) ซึ่งจับกรณีนี้ไม่ได้

⚠️⚠️ google_reviews_total — ห้ามใช้เป็นตัวส่วนของอัตราส่วนใด ๆ ⚠️⚠️
  มันคือจำนวนรีวิวที่ Google *มี* ไม่ใช่จำนวนที่เรา *เก็บได้*
  ตัวเศษของทุกอัตราในระบบนี้มาจากตาราง reviews ที่ผ่านตัวกรองชุดหนึ่ง
  (date + status + text_clean <> '' + มีแถวใน analyzed_reviews) การเอาตัวส่วน
  ที่ไม่ผ่านตัวกรองเดียวกันมาใช้ผิดกฎข้อ 1 ของโปรเจกต์ และทำให้ทุกเปอร์เซ็นต์
  บนหน้าเว็บ/ในรายงานต่ำกว่าความจริงแบบไม่มีอะไรฟ้อง

  ใช้ได้ทางเดียว: เป็นตัวส่วนของ "ความครบถ้วนของการเก็บข้อมูล"
      เก็บได้ / google_reviews_total = เก็บรีวิวได้กี่ % ของที่มีอยู่จริง
  ซึ่งเป็นเมตริกคนละตัวกับ pain rate และต้องเขียนกำกับให้ชัดว่าเป็นอะไร

Revision ID: 012
Revises: 011
Create Date: 2026-09-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # กุญแจถาวรจาก Google — ฟิลด์เดียวในชุดนี้ที่เก็บได้ไม่จำกัดเวลาตามเงื่อนไข Google
    op.add_column("places", sa.Column("google_place_id", sa.String(64), nullable=True))
    op.create_index(
        "uq_places_google_place_id", "places", ["google_place_id"], unique=True
    )

    # types[] จาก API เก็บเป็น CSV เช่น "cafe,bakery,food,point_of_interest"
    # ใช้แทน google_category (ข้อความไทยอิสระ 65 ค่า) — ดู GUIDE.md section Place Types
    op.add_column("places", sa.Column("google_types", sa.Text(), nullable=True))

    op.add_column("places", sa.Column("formatted_address", sa.Text(), nullable=True))

    # แยกจาก overall_rating (มาจาก scrape) — ไม่ทับกัน เทียบกันได้
    op.add_column("places", sa.Column("google_rating", sa.Numeric(2, 1), nullable=True))

    # ⚠️ อ่านคำเตือนหัวไฟล์ก่อนใช้ — ห้ามเป็นตัวส่วนของ pain rate
    op.add_column("places", sa.Column("google_reviews_total", sa.Integer(), nullable=True))

    # ดึงมาเมื่อไร — จำเป็นทั้งสำหรับบทวิธีวิจัยและเงื่อนไขการเก็บ cache ของ Google
    op.add_column(
        "places", sa.Column("api_fetched_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )

    # 'scrape' = มาจาก Playwright | 'api' = ค้นเจอด้วย Places API
    # ยังเป็น NULL จนถึงขั้น backfill/discover ที่จะเติมค่า
    op.add_column("places", sa.Column("discovered_by", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("places", "discovered_by")
    op.drop_column("places", "api_fetched_at")
    op.drop_column("places", "google_reviews_total")
    op.drop_column("places", "google_rating")
    op.drop_column("places", "formatted_address")
    op.drop_column("places", "google_types")
    op.drop_index("uq_places_google_place_id", table_name="places")
    op.drop_column("places", "google_place_id")
