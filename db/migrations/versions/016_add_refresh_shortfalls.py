"""เพิ่ม places.refresh_shortfalls — นับครั้งที่ถูกส่งกลับเข้าคิวเพราะเก็บรีวิวได้น้อยผิดปกติ

ปัญหาที่ทำให้ต้องมีคอลัมน์นี้ (เกิดขึ้นจริง 25-26 ก.ย. 2026):
  Google จำกัดอัตราแบบ**เงียบ** — ไม่ขึ้น CAPTCHA ไม่ขึ้นหน้า sorry แค่เสิร์ฟรีวิว
  ให้น้อยลงเรื่อย ๆ จนเกือบศูนย์ ตัวตรวจจับบล็อกของเราดูแค่ CAPTCHA/sorry-page
  จึงไม่ทำงาน งาน refresh จบด้วย status='done' ทุกรอบ

  ผลคือ save_to_db ตี scraped_at = NOW() ให้ร้านที่เก็บได้แค่ 5 รีวิว
  (ทั้งที่ Google มี 3,937) และ update_scan_stats เพิ่ม consecutive_no_change
  → ระบบเข้าใจว่าร้านเสร็จแล้วและตั้ง cooldown 7-30 วัน

  วัดความเสียหาย: 131 ร้านเก็บได้ไม่ถึง 20% ของเพดาน รวม ~31,761 รีวิวที่ควรได้
  ลายเซ็นชัดเจนคือ 93 ร้านเก็บได้เป๊ะ 5 และ 40 ร้านเป๊ะ 10 — ไม่ใช่การกระจาย
  ตามธรรมชาติ แต่เป็น scraper หยุดที่จุดเดียวกันซ้ำ ๆ

ทำไมต้องนับ ไม่ใช่แค่รีเซ็ต scraped_at:
  ร้านบางแห่ง Google บอกว่ามี 500 รีวิวแต่เสิร์ฟให้จริงแค่ 50 (รีวิวถูกซ่อน/ลบ)
  ถ้ารีเซ็ตทุกครั้งที่เก็บได้ต่ำกว่าคาด ร้านกลุ่มนี้จะถูกวน scrape ไม่รู้จบ
  ตัวนับนี้ทำให้ยอมแพ้ได้หลังลองซ้ำไม่กี่ครั้ง — หลักการเดียวกับ deep_attempts
  ใน migration 011 ที่แยก "ยังอยู่ในคิว" ออกจาก "ยอมแพ้แล้ว"

  refresh_shortfalls = 0            ยังไม่เคยเก็บได้ต่ำผิดปกติ
  refresh_shortfalls < เพดาน        ส่งกลับเข้าคิวได้อีก
  refresh_shortfalls >= เพดาน       ยอมรับว่าเก็บได้เท่านี้จริง ไม่วนอีก

Revision ID: 016
Revises: 015
Create Date: 2026-09-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "places",
        sa.Column("refresh_shortfalls", sa.Integer(), nullable=False,
                  server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("places", "refresh_shortfalls")
