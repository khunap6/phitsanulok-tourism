"""
fix_stuck_queue.py — ล้างค่า consecutive_no_change ที่พองผิดของร้านที่ติดวนลูปหัวคิว

ปัญหาที่แก้ (พบ 2026-09-27):
  ร้านที่ scrape_place คืน None (หน้าเว็บโหลดไม่ขึ้น) หรือที่หน้าเว็บมีชื่อคนละชื่อ
  กับที่คิวขอไป จะไม่ถูก save_to_db แตะเลย → scraped_at คง NULL → ค้างหัวคิว
  ตลอดไป (ORDER BY scraped_at ASC NULLS FIRST)

  แต่ update_scan_stats เดิมรับ place_names ทั้งชุดที่ขอไป ไม่ใช่เฉพาะที่บันทึก
  สำเร็จ จึงบวก consecutive_no_change ให้ร้านกลุ่มนี้ทุกรอบ → พุ่งถึง 43
  ทั้งที่ไม่เคย scrape สำเร็จแม้ครั้งเดียว

  วัดความเสียหาย: 18 ร้านกินสล็อตทุกรอบ ปิดกั้นรีวิว 3,932 อัน และทำให้
  12 รอบติดกันได้รีวิวใหม่ 0 อัน (งาน scrape_jobs id 231-242)

ต้นเหตุถูกปิดแล้วใน scraper/scraper.py 3 จุด:
  1. update_scan_stats รับเฉพาะร้านที่บันทึกสำเร็จจริง
  2. แถวที่ขอไปแต่ผลลัพธ์ไป landed แถวอื่น → ตี scraped_at ให้ (ออกจากคิว)
  3. ร้านที่ไม่คืนผลลัพธ์เลย → นับ refresh_shortfalls เพื่อให้เพดานทำงาน

สคริปต์นี้ล้างค่าที่ค้างอยู่

⚠️ ทำไมต้องล้าง cnc ไม่ใช่ปล่อยไว้
  cnc >= 3 = cooldown 30 วัน ถ้าปล่อย 43 ไว้ ร้านพวกนี้พอ scrape สำเร็จครั้งแรก
  จะถูกเว้น 30 วันทันที ทั้งที่เพิ่งเริ่มเก็บและยังไม่ครบ
  ค่า 13-43 ไม่ได้สะท้อนอะไรจริง เพราะนับจากรอบที่ไม่เคยสำเร็จ

⚠️ ไม่แตะ scraped_at — ต้องคง NULL ไว้ให้ร้านพวกนี้ถูกหยิบมาทำต่อ
  ตอนนี้ปลอดภัยแล้วเพราะตัวนับ refresh_shortfalls จะจับได้ถ้ายังพังอยู่
  และเลิกตามเองหลังครบ REFRESH_MAX_SHORTFALLS ครั้ง

⚠️ ไม่แตะ refresh_shortfalls — ประวัติความล้มเหลวที่แท้จริงต้องเก็บไว้
  ถ้าจะล้างด้วยให้ใช้ requeue_shortfall.py --reset-shortfalls แยก

รัน:
  uv run python scripts/fix_stuck_queue.py            # DRY-RUN
  uv run python scripts/fix_stuck_queue.py --apply    # ทำจริง
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal

# ลายเซ็นของร้านที่ติดลูป: ยังไม่เคยบันทึกสำเร็จ (scraped_at NULL)
# แต่ถูกนับว่า "ไม่มีรีวิวใหม่" มาแล้วหลายรอบ — สองอย่างนี้เกิดพร้อมกันไม่ได้
# ถ้าระบบทำงานถูก
MIN_CNC = 3


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


WHERE = f"""
    NOT p.scrape_excluded
    AND p.scraped_at IS NULL
    AND COALESCE(p.consecutive_no_change, 0) >= {MIN_CNC}
"""


async def report(session, apply: bool) -> None:
    rows = (await session.execute(text(f"""
        SELECT p.id, p.name, p.google_reviews_total AS g,
               p.consecutive_no_change AS cnc,
               COALESCE(p.refresh_shortfalls, 0) AS sf,
               p.discovered_by AS db,
               (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS sc,
               LEAST(p.google_reviews_total, 850) AS ceil
        FROM places p
        WHERE {WHERE}
        ORDER BY p.google_reviews_total DESC NULLS LAST
    """))).fetchall()

    p("=" * 80)
    p(f"  {'ทำจริง' if apply else 'DRY-RUN'} — ล้าง consecutive_no_change ที่พองผิด")
    p("=" * 80)

    if not rows:
        p("  ไม่พบร้านที่ติดลูป (scraped_at NULL + cnc >= 3)")
        p("  = ต้นเหตุถูกปิดแล้วและไม่มีค่าค้าง")
        p("=" * 80)
        return

    gap = sum(int(x.ceil or 0) - x.sc for x in rows)
    p(f"  พบ {len(rows)} ร้าน · ปิดกั้นรีวิวไว้ {gap:,} อัน")
    p(f"  cnc อยู่ระหว่าง {min(x.cnc for x in rows)}-{max(x.cnc for x in rows)} "
      f"ทั้งที่ยังไม่เคยบันทึกสำเร็จแม้ครั้งเดียว")
    p("")
    p(f"  {'id':>5} {'Google':>7} {'เก็บ':>5} {'cnc':>4} {'sf':>3} {'ที่มา':<6}  ชื่อร้าน")
    for x in rows:
        p(f"  {x.id:>5} {str(x.g or '-'):>7} {x.sc:>5} {x.cnc:>4} {x.sf:>3} "
          f"{(x.db or '-'):<6}  {x.name[:38]}")

    if not apply:
        p("")
        p("  ยังไม่ได้แก้อะไร — เติม --apply เพื่อทำจริง")
        p("  สิ่งที่จะทำ:")
        p("    consecutive_no_change -> 0   (ล้างค่าที่นับจากรอบที่ไม่เคยสำเร็จ)")
        p("    scraped_at            คงเดิม (NULL — ให้ถูกหยิบมาทำต่อ)")
        p("    refresh_shortfalls    คงเดิม (เก็บประวัติความล้มเหลวจริงไว้)")
        p("    ไม่แตะรีวิว ไม่ลบร้าน")
        p("=" * 80)
        return

    await session.execute(text("""
        UPDATE places SET consecutive_no_change = 0
        WHERE id = ANY(:ids)
    """), {"ids": [x.id for x in rows]})
    await session.commit()

    left = (await session.execute(text(f"""
        SELECT count(*) FROM places p WHERE {WHERE}"""))).scalar()
    q = (await session.execute(text("""
        SELECT count(*) FILTER (WHERE scraped_at IS NULL) queued,
               count(*) total FROM places WHERE NOT scrape_excluded"""))).fetchone()
    rev = (await session.execute(text("SELECT count(*) FROM reviews"))).scalar()

    p("")
    p(f"  ✅ ล้าง consecutive_no_change แล้ว {len(rows)} ร้าน")
    p(f"  เหลือร้านที่เข้าลายเซ็นติดลูป {left} ร้าน")
    p(f"  หัวคิวตอนนี้ {q.queued} จาก {q.total} ร้าน · รีวิว {rev:,} อัน (ไม่ถูกแตะ)")
    p("")
    p("  ขั้นต่อไป: รัน auto_refresh ด้วย limit ต่ำ")
    p("    uv run python scripts/auto_refresh.py --limit 15 --wait 25")
    p("  ร้านที่ยังพังอยู่จะถูกนับ refresh_shortfalls แล้วเลิกตามเองหลัง 3 ครั้ง")
    p("=" * 80)


async def run(args) -> int:
    async with AsyncSessionLocal() as session:
        await report(session, args.apply)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="ล้าง consecutive_no_change ที่พองผิดของร้านที่ติดวนลูปหัวคิว")
    ap.add_argument("--apply", action="store_true",
                    help="ทำจริง (ไม่ใส่ = DRY-RUN ดูเฉย ๆ)")
    sys.exit(asyncio.run(run(ap.parse_args())))
