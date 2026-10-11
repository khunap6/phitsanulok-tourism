"""
reset_deep_attempts.py — คืนสิทธิ์ให้ร้านที่ถูก "ยอมแพ้" ด้วยเหตุที่ไม่ใช่ความผิดของร้าน

ปัญหาที่แก้ (วัด 2026-10-03):
  Google เสิร์ฟหน้าร้านได้ 3 แบบ สุ่มตามช่วงเวลา ไม่ใช่ตามร้าน
    A ไม่มีแท็บรีวิวเลย (มีแค่ ภาพรวม/เกี่ยวกับ ข้างคะแนนไม่มีจำนวนรีวิว) -> ได้ 0
    B มีแท็บ แต่ฟีดจำกัดจบที่ปุ่ม "ดูรีวิวเพิ่มเติม (N)"                 -> ได้ 5
    C มีแท็บ ฟีดปกติ เลื่อนได้เรื่อย ๆ                                   -> ได้ครบ

  หลักฐานว่าเป็นเรื่องช่วงเวลา ไม่ใช่เรื่องร้าน:
    - place_id เดิมไม่เปลี่ยนตัวอักษรเดียว ได้แท็บ 3/3 ตอน 02:1x แล้ว 0/1 ตอน 02:58
    - น้ำตกแก่งซองที่มีรีวิวใน DB แล้ว 782 อัน ก็เจอหน้าแบบ A เหมือนกัน
    - ค้นด้วยชื่อสั้น/ชื่อยาว/place_id ให้หน้าเดียวกันทุกพิกเซล (checksum ตรงกัน)

  แต่ run_deep_scan เดิมนับทุกความล้มเหลวเป็น deep_attempts รวมหน้า A และ B
  ครบ DEEP_MAX_ATTEMPTS แล้วถอดร้านออกจากคิวถาวร ร้านที่เก็บได้จริงจึงถูกฝัง
  ตัวอย่างที่ชัดที่สุด: แพตามสั่งนั่งชิว ถูกยอมแพ้ที่ 3/3 ทั้งที่รอบทดสอบ
  ในช่วงหน้าปกติดึงได้ 532 จาก 544 รีวิว

ต้นเหตุถูกปิดแล้ว (scraper/scraper_core.py + scraper/scraper.py):
  1. detect_limited_view() ตรวจหน้าแบบ A และ B แล้วติดธง _limited_view
  2. run_deep_scan ข้ามการนับ deep_attempts เมื่อมีธงนั้น
  3. DEEP_LIMITED_STREAK_STOP หยุดรอบเมื่อเจอหน้าจำกัดติดกัน 3 ร้าน

สคริปต์นี้ล้างค่าที่ค้างมาจากกติกาเก่า

⚠️ ไม่แตะ deep_scanned_at — ร้านกลุ่มนี้เป็น NULL อยู่แล้ว ถ้าไปตีค่าให้
  จะกลายเป็น "เสร็จแล้ว" แล้วหลุดจากทุกคิวแทน

⚖️ สิ่งที่แลกไป: ร้านที่เข้าไม่ถึงจริง ๆ จะถูกหยิบมาลองใหม่อีก
  รับได้เพราะ DEEP_LIMITED_STREAK_STOP คุมไม่ให้รอบหนึ่งเสียเวลาเกิน 3 ร้าน
  และถ้าพังด้วยเหตุอื่นจริง ตัวนับจะกลับมาเพิ่มเองตามปกติ

ใช้งาน
  uv run python scripts/reset_deep_attempts.py            # DRY-RUN
  uv run python scripts/reset_deep_attempts.py --apply
  uv run python scripts/reset_deep_attempts.py --ids 5531 --apply
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from scraper.scraper import DEEP_MAX_ATTEMPTS, SERVE_CEILING_DEEP

# ปลดร้านที่เก็บได้ต่ำกว่าสัดส่วนนี้ — ไม่ใช่ DEEP_MIN_RATIO (0.5)
#
# ⚠️ ทำไมต้องเป็นคนละเลขกับ DEEP_MIN_RATIO (วัดเมื่อ 2026-10-08)
#   DEEP_MIN_RATIO ตอบคำถาม "รอบนี้ถือว่าสำเร็จไหม"
#   เลขนี้ตอบคำถามคนละข้อ: "ยังคุ้มที่จะให้โอกาสใหม่ไหม"
#
#   ใช้ 0.5 แล้วพลาดร้านที่ยังขาดเยอะจริงแต่เกิน 50% ไปแล้ว:
#     พระราชวังจันทน์            596/850  ขาด 254  (70.1%)
#     ล่องแพแก่งไฮ ผู้ใหญ่ฮิปปี้  183/341  ขาด 158  (53.7%)
#   สองร้านนี้ attempts = 3 จึงหลุดจากคิว gap ถาวร รวม 412 รีวิวที่เข้าไม่ถึง
#
#   0.8 ปลดสองร้านนั้น และไม่ไปกวนอีก 5 ร้านที่เก็บได้ 87-94% แล้ว
#   (ข้าวต้มอนันต์ 87.3% · ร้านอาหารตั้งหลัก 87.8% · ฟ้าไทยฟาร์ม 92.5%
#    ก๋วยเตี๋ยวจูงนาง 92.3% · ครัวแอบแดก 94.1%) ซึ่งเหลือขาดรวมแค่ 377 รีวิว
#   และแต่ละรอบ deep ใช้เวลา 1-3 นาที จึงไม่คุ้มที่จะวนกลับไปหาร้านเกือบครบ
RESET_BELOW_RATIO = 0.8


def p(msg=""):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


# ร้านที่ "ยอมแพ้แล้ว" และยังเก็บได้ต่ำกว่าเกณฑ์
# ใช้ตัวกรองชุดเดียวกับ run_deep_scan ตอนตัดสิน enough เพื่อให้ตัวเลขตรงกัน
#
# ⚠️ ต้อง CAST(:ratio AS double precision) ห้ามเขียน :ratio เปล่า
#   asyncpg อนุมานชนิดของ placeholder จากบริบท — ใน :ratio * LEAST(int, int)
#   มันตีเป็น integer แล้ว 0.5 กลายเป็น 0 เงื่อนไขเป็น count < 0 ซึ่งเท็จทุกแถว
#   วัดได้จริง: ฝังเลข 0.5 ลงใน SQL -> 6 แถว / ผูกเป็น param -> 0 แถว
#   เป็นบั๊กเงียบ ไม่ error ไม่เตือน จึงต้องระบุชนิดเองทุกครั้งที่คูณด้วยทศนิยม
SELECT_SQL = """
    SELECT p.id, p.name, p.google_reviews_total AS g,
           COALESCE(p.deep_attempts, 0) AS da,
           (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS sc
    FROM places p
    WHERE NOT p.scrape_excluded
      AND p.google_reviews_total IS NOT NULL
      AND COALESCE(p.deep_attempts, 0) >= :maxa
      AND (SELECT count(*) FROM reviews r WHERE r.place_id = p.id)
          < CAST(:ratio AS double precision)
            * LEAST(p.google_reviews_total, :ceil)
      {id_filter}
    ORDER BY LEAST(p.google_reviews_total, :ceil)
           - (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) DESC
"""


async def run(apply: bool, ids: list[int] | None):
    id_filter = ""
    params = {
        "maxa": DEEP_MAX_ATTEMPTS,
        "ratio": RESET_BELOW_RATIO,
        "ceil": SERVE_CEILING_DEEP,
    }
    if ids:
        id_filter = "AND p.id = ANY(:ids)"
        params["ids"] = ids

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text(SELECT_SQL.format(id_filter=id_filter)), params
        )).fetchall()

        if not rows:
            p("ไม่มีร้านที่เข้าเกณฑ์ — ไม่ต้องรีเซ็ตอะไร")
            return

        p(f"{'id':>6}  {'ชื่อ':<36} {'Google':>7} {'เก็บได้':>8} {'ขาด':>7} {'attempts':>9}")
        p("-" * 82)
        total_gap = 0
        for r in rows:
            gap = min(r.g, SERVE_CEILING_DEEP) - r.sc
            total_gap += gap
            p(f"{r.id:>6}  {r.name[:36]:<36} {r.g:>7} {r.sc:>8} {gap:>7} "
              f"{r.da:>9}")
        p("-" * 82)
        p(f"รวม {len(rows)} ร้าน | รีวิวที่ยังขาด {total_gap}")
        p("")
        p(f"จะตั้ง deep_attempts = 0 ให้ {len(rows)} ร้านนี้ "
          f"(deep_scanned_at คง NULL ไว้ตามเดิม)")

        if not apply:
            p("")
            p("นี่คือ DRY-RUN — ยังไม่เขียนอะไรลงฐานข้อมูล")
            p("ลงมือจริงด้วย: uv run python scripts/reset_deep_attempts.py --apply")
            return

        target_ids = [r.id for r in rows]
        await session.execute(
            text("UPDATE places SET deep_attempts = 0 WHERE id = ANY(:ids)"),
            {"ids": target_ids},
        )
        await session.commit()

        # ยืนยันผลจากฐานข้อมูลจริง ไม่ใช่เชื่อว่า UPDATE สำเร็จ
        left = (await session.execute(
            text("SELECT count(*) FROM places WHERE id = ANY(:ids) "
                 "AND COALESCE(deep_attempts, 0) > 0"),
            {"ids": target_ids},
        )).scalar()
        p("")
        p(f"✅ รีเซ็ตแล้ว {len(target_ids)} ร้าน | ยังเหลือค่า > 0 อยู่ {left} ร้าน")
        p("   ร้านพวกนี้กลับเข้าคิว gap แล้ว — รันต่อด้วย")
        p("   uv run python scripts/deep_scan.py --targets gap --limit 10 --wait 20")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="คืนสิทธิ์ร้านที่ถูกยอมแพ้เพราะ Google เสิร์ฟหน้าแบบจำกัด")
    ap.add_argument("--apply", action="store_true",
                    help="เขียนลงฐานข้อมูลจริง (ไม่ใส่ = DRY-RUN)")
    ap.add_argument("--ids", type=int, nargs="+", default=None, metavar="ID",
                    help="จำกัดเฉพาะ id ที่ระบุ")
    args = ap.parse_args()
    asyncio.run(run(apply=args.apply, ids=args.ids))
