"""
fix_false_deep.py — ล้าง deep_scanned_at ของร้านที่ถูกตีว่าเสร็จทั้งที่ดึงมาได้น้อยมาก

ปัญหาที่แก้ (พบ 2026-10-01):
  เกณฑ์เดิมใน run_deep_scan คือ `collected > 0` ดึงมาได้ 10 อันจากร้านที่
  Google มี 7,028 ก็ถูกตี deep_scanned_at ว่าเสร็จถาวร

  วัดจากข้อมูลจริง — 11 จาก 158 ร้านที่ถูกตีว่า deep แล้ว ดึงมาได้ไม่ถึง 50%:
    พระพุทธชินราช              7,028 -> 14   =  2%
    พระราชวังจันทน์            1,424 -> 21   =  2%
    อุทยานแห่งชาติภูหินร่องกล้า 3,289 -> 108  = 13%
    ครัวท่าโพธิ์                 845 -> 202  = 24%
  ทุกร้านมี deep_attempts = 0 คือไม่เคยถูกนับว่าล้มเหลว

  กลไก: deep scroll ได้หน้าแรกราว 10 การ์ด แล้ว Google ไม่ส่งมาเพิ่ม
  ตัวนับ node ไม่โต -> ชน DEEP_NO_GROWTH_LIMIT -> หยุด -> collected > 0

ต้นเหตุถูกปิดแล้วใน scraper/scraper.py — เกณฑ์เปลี่ยนเป็นเทียบสัดส่วนกับเพดาน
(DEEP_MIN_RATIO) และนับ deep_attempts ให้เคสนี้ด้วย

สคริปต์นี้ล้างค่าที่ค้างอยู่

⚠️ ทำไมต้องล้าง ทั้งที่ --targets gap ก็กู้ได้อยู่แล้ว
  gap ไม่บังคับ deep_scanned_at IS NULL จึงยังเห็นร้านกลุ่มนี้ (ดีอยู่แล้ว)
  แต่เกณฑ์อีก 4 ตัว (capped / zero / shallow / all) บังคับ IS NULL
  จึงข้ามร้านกลุ่มนี้ถาวร
  และรายงาน "deep แล้ว N ร้าน" สูงกว่าความจริง ทำให้ประเมินงานที่เหลือผิด

⚠️ ไม่แตะ deep_attempts — ตัวนับต้องเริ่มจาก 0 เพื่อให้ร้านได้โอกาสใหม่
  ครบ DEEP_MAX_ATTEMPTS ครั้งตามปกติ ถ้าเติมไปด้วยจะยอมแพ้เร็วเกิน

⚠️ ไม่แตะรีวิว ไม่แตะ scraped_at — เปลี่ยนแค่สมาชิกของคิว deep

รัน:
  uv run python scripts/fix_false_deep.py            # DRY-RUN
  uv run python scripts/fix_false_deep.py --apply
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from scraper.scraper import DEEP_MIN_RATIO, SERVE_CEILING_DEEP


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


WHERE = f"""
    NOT p.scrape_excluded
    AND p.deep_scanned_at IS NOT NULL
    AND p.google_reviews_total IS NOT NULL
    AND (SELECT count(*) FROM reviews r WHERE r.place_id = p.id)
        < {DEEP_MIN_RATIO} * LEAST(p.google_reviews_total, {SERVE_CEILING_DEEP})
"""


async def report(session, apply: bool) -> None:
    rows = (await session.execute(text(f"""
        SELECT p.id, p.name, p.google_reviews_total AS g,
               LEAST(p.google_reviews_total, {SERVE_CEILING_DEEP}) AS ceil,
               (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS sc,
               COALESCE(p.deep_attempts, 0) AS datt,
               p.deep_scanned_at AS da
        FROM places p
        WHERE {WHERE}
        ORDER BY LEAST(p.google_reviews_total, {SERVE_CEILING_DEEP})
                 - (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) DESC
    """))).fetchall()

    total_deep = (await session.execute(text("""
        SELECT count(*) FROM places
        WHERE NOT scrape_excluded AND deep_scanned_at IS NOT NULL"""))).scalar()

    p("=" * 80)
    p(f"  {'ทำจริง' if apply else 'DRY-RUN'} — ล้าง deep_scanned_at ที่ถูกตีผิด")
    p("=" * 80)
    p(f"  เกณฑ์: ดึงมาได้น้อยกว่า {DEEP_MIN_RATIO * 100:.0f}% ของเพดาน "
      f"LEAST(google_reviews_total, {SERVE_CEILING_DEEP})")
    p("")

    if not rows:
        p(f"  ไม่พบร้านที่ถูกตีผิด (จาก {total_deep} ร้านที่ deep แล้ว)")
        p("  = เกณฑ์ใหม่ทำงานแล้วและไม่มีค่าค้าง")
        p("=" * 80)
        return

    gap = sum(int(x.ceil) - x.sc for x in rows)
    p(f"  พบ {len(rows)} จาก {total_deep} ร้านที่ถูกตีว่า deep แล้ว "
      f"({len(rows) / total_deep * 100:.1f}%)")
    p(f"  ปิดกั้นรีวิวไว้ {gap:,} อัน")
    p("")
    p(f"  {'id':>5} {'Google':>7} {'เพดาน':>6} {'เก็บ':>5} {'ขาด':>6} {'%':>5} "
      f"{'attempts':>8}  ชื่อร้าน")
    for x in rows:
        ceil = int(x.ceil)
        p(f"  {x.id:>5} {x.g:>7} {ceil:>6} {x.sc:>5} {ceil - x.sc:>6} "
          f"{x.sc / ceil * 100:>4.0f}% {x.datt:>8}  {x.name[:32]}")

    if not apply:
        p("")
        p("  ยังไม่ได้แก้อะไร — เติม --apply เพื่อทำจริง")
        p("  สิ่งที่จะทำ:")
        p("    deep_scanned_at -> NULL  (กลับเข้าคิว deep ทุกเกณฑ์ ไม่ใช่แค่ gap)")
        p("    deep_attempts   คงเดิม   (ให้โอกาสใหม่ครบจำนวน)")
        p("    ไม่แตะรีวิว ไม่แตะ scraped_at")
        p("=" * 80)
        return

    await session.execute(text("""
        UPDATE places SET deep_scanned_at = NULL WHERE id = ANY(:ids)
    """), {"ids": [x.id for x in rows]})
    await session.commit()

    left = (await session.execute(text(f"""
        SELECT count(*) FROM places p WHERE {WHERE}"""))).scalar()
    after = (await session.execute(text("""
        SELECT count(*) FILTER (WHERE deep_scanned_at IS NOT NULL) deep,
               count(*) FILTER (WHERE deep_scanned_at IS NULL) nodeep
        FROM places WHERE NOT scrape_excluded"""))).fetchone()
    rev = (await session.execute(text("SELECT count(*) FROM reviews"))).scalar()

    p("")
    p(f"  ✅ ล้าง deep_scanned_at แล้ว {len(rows)} ร้าน")
    p(f"  เหลือร้านที่เข้าเกณฑ์ตีผิด {left} ร้าน")
    p(f"  deep แล้วจริง {after.deep} ร้าน · ยังไม่ deep {after.nodeep} ร้าน")
    p(f"  รีวิว {rev:,} อัน (ไม่ถูกแตะ)")
    p("")
    p("  ขั้นต่อไป:")
    p("    uv run python scripts/deep_scan.py --targets gap --dry-run")
    p("  ร้านกลุ่มนี้จะอยู่หัวคิว และถ้ายังดึงมาได้ไม่ถึงเกณฑ์")
    p(f"  จะถูกนับ deep_attempts แล้วยอมแพ้เองหลังครบ 3 ครั้ง (ไม่วนไม่รู้จบ)")
    p("=" * 80)


async def run(args) -> int:
    async with AsyncSessionLocal() as session:
        await report(session, args.apply)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="ล้าง deep_scanned_at ของร้านที่ถูกตีว่าเสร็จทั้งที่ดึงมาได้น้อย")
    ap.add_argument("--apply", action="store_true",
                    help="ทำจริง (ไม่ใส่ = DRY-RUN ดูเฉย ๆ)")
    sys.exit(asyncio.run(run(ap.parse_args())))
