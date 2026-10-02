"""
requeue_shortfall.py — ส่งร้านที่เก็บรีวิวได้น้อยผิดปกติกลับเข้าคิว refresh

ปัญหาที่แก้ (เกิดจริง 25-26 ก.ย. 2026):
  Google จำกัดอัตราแบบ**เงียบ** — ไม่ขึ้น CAPTCHA ไม่ขึ้นหน้า sorry แค่เสิร์ฟรีวิว
  ให้น้อยลงจนเกือบศูนย์ ตัวตรวจจับบล็อกดูแค่ CAPTCHA/sorry-page จึงไม่ทำงาน

  ผลคือร้านที่เก็บได้แค่ 5 รีวิว (ทั้งที่ Google มี 3,937) ถูกตี scraped_at = NOW()
  และเพิ่ม consecutive_no_change → ระบบถือว่าเสร็จแล้วและตั้ง cooldown 7-30 วัน
  ร้านพวกนี้จะไม่ถูกหยิบมาทำอีกเลยจนพ้น cooldown

  ลายเซ็นของปัญหา: 93 ร้านเก็บได้เป๊ะ 5 · 40 ร้านเป๊ะ 10 — การกระจายแบบนี้
  ไม่เกิดเองตามธรรมชาติ เป็น scraper หยุดที่จุดเดียวกันซ้ำ ๆ

สคริปต์นี้ทำ 3 อย่างกับร้านที่เข้าเกณฑ์:
  scraped_at            -> NULL   ให้กลับไปอยู่หัวคิว refresh (NULLS FIRST)
  consecutive_no_change -> 0      ล้าง cooldown ที่ตั้งผิด
  refresh_shortfalls    -> +1     นับไว้กันวน scrape ร้านเดิมไม่รู้จบ

⚠️ ไม่ลบรีวิวที่เก็บได้แล้ว — รีวิว 5 อันนั้นยังอยู่ครบ การ scrape รอบใหม่จะ
   เพิ่มทับด้วย ON CONFLICT (place_id, text_hash) ไม่เกิดรายการซ้ำ

⚠️ ต้องมี google_reviews_total จึงจะเช็คได้
   ร้านที่ไม่มีเฉลย (Places API หาไม่เจอ) จะถูกข้าม เพราะไม่รู้ว่าควรได้เท่าไร

เพดานที่ใช้เทียบคือ LEAST(google_reviews_total, 850) ไม่ใช่ google_reviews_total
   เพราะ Google เสิร์ฟผ่านการ scroll ได้สูงสุดราว 850 อัน/ร้าน (วัดจากร้านที่
   deep สำเร็จ 26 ร้าน: ต่ำสุด 433 มัธยฐาน 785 สูงสุด 890) วัดพระศรีฯ deep แล้ว
   ได้ 832 จาก 10,058 = 8% ซึ่ง**ไม่ใช่ความล้มเหลว** ถ้าเทียบกับ 10,058 ตรง ๆ
   จะเข้าใจผิดว่าร้านใหญ่ล้มเหลวทั้งหมด

รัน:
  uv run python scripts/requeue_shortfall.py                  # DRY-RUN: ดูว่าจะแตะร้านไหน
  uv run python scripts/requeue_shortfall.py --apply          # ทำจริง
  uv run python scripts/requeue_shortfall.py --min-coverage 0.3 --apply
  uv run python scripts/requeue_shortfall.py --max-shortfalls 3 --apply
  uv run python scripts/requeue_shortfall.py --reset-shortfalls          # ดูก่อน
  uv run python scripts/requeue_shortfall.py --reset-shortfalls --apply  # ล้างตัวนับ
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal

# เพดานที่ Google เสิร์ฟให้ต่อร้าน (วัดจากร้านที่ deep สำเร็จจริง)
SERVE_CEILING = 850
# เก็บได้ต่ำกว่าสัดส่วนนี้ของเพดาน = ผิดปกติ ไม่ใช่ "ร้านนี้มีแค่นี้"
# 0.20 มาจากข้อมูลจริง: ชั่วโมงที่ทำงานปกติได้ 86-91% ชั่วโมงที่พังได้ 13-31%
# ตั้งไว้ต่ำ (20%) เพื่อแตะเฉพาะเคสที่ชัดเจน ไม่กวาดร้านที่เก็บได้พอสมควรแล้ว
MIN_COVERAGE = 0.20
# ร้านที่รีวิวน้อยอยู่แล้วไม่ต้องเช็ค — 5 จาก 20 ไม่ใช่สัญญาณอะไร
MIN_GOOGLE_REVIEWS = 50
# ส่งกลับเข้าคิวได้ไม่เกินกี่ครั้ง — เกินนี้ยอมรับว่าเก็บได้เท่านั้นจริง
MAX_SHORTFALLS = 2


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def where_sql(min_cov: float, min_g: int, max_sf: int) -> str:
    """
    เงื่อนไข "ร้านที่ควรส่งกลับเข้าคิว"

    ต้องเคย scrape แล้ว (scraped_at IS NOT NULL) — ร้านที่ยังไม่เคย scrape
    อยู่ในคิวอยู่แล้ว ไม่ต้องแตะ
    """
    return f"""
        p.scraped_at IS NOT NULL
        AND NOT p.scrape_excluded
        AND p.google_reviews_total IS NOT NULL
        AND p.google_reviews_total >= {int(min_g)}
        AND COALESCE(p.refresh_shortfalls, 0) < {int(max_sf)}
        AND (SELECT count(*) FROM reviews r WHERE r.place_id = p.id)
            < {float(min_cov)} * LEAST(p.google_reviews_total, {SERVE_CEILING})
    """


async def report(session, min_cov, min_g, max_sf, apply: bool) -> None:
    w = where_sql(min_cov, min_g, max_sf)

    rows = (await session.execute(text(f"""
        SELECT p.id, p.name, p.google_reviews_total AS g,
               (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS sc,
               LEAST(p.google_reviews_total, {SERVE_CEILING}) AS ceil,
               p.consecutive_no_change AS cnc,
               COALESCE(p.refresh_shortfalls, 0) AS sf,
               p.deep_scanned_at IS NOT NULL AS deep,
               p.scraped_at
        FROM places p
        WHERE {w}
        ORDER BY LEAST(p.google_reviews_total, {SERVE_CEILING})
                 - (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) DESC
    """))).fetchall()

    p("=" * 78)
    p(f"  {'ทำจริง' if apply else 'DRY-RUN'} — ส่งร้านที่เก็บรีวิวได้น้อยผิดปกติกลับเข้าคิว")
    p("=" * 78)
    p(f"\n  เกณฑ์: เก็บได้ < {min_cov * 100:.0f}% ของ LEAST(google, {SERVE_CEILING})")
    p(f"         และ Google มี >= {min_g} รีวิว")
    p(f"         และ refresh_shortfalls < {max_sf} (กันวนไม่รู้จบ)")

    if not rows:
        p(f"\n  ✅ ไม่มีร้านเข้าเกณฑ์ — ไม่มีอะไรต้องทำ")
        p("=" * 78)
        return

    lost = sum(r.ceil - r.sc for r in rows)
    cooled = sum(1 for r in rows if (r.cnc or 0) >= 1)
    p(f"\n  พบ {len(rows)} ร้าน | รีวิวที่ควรได้แต่ยังไม่ได้ ~{lost:,} อัน")
    p(f"  ในนั้นติด cooldown อยู่ {cooled} ร้าน (จะไม่ถูกหยิบอีก 7-30 วันถ้าไม่แก้)")

    p(f"\n  {'ขาด':>6}{'เก็บได้':>8}{'เพดาน':>7}{'Google':>8}{'%':>5}"
      f"{'sf':>4}  {'scrape เมื่อ':<17} ชื่อ")
    for r in rows[:30]:
        pct = r.sc / r.ceil * 100 if r.ceil else 0
        p(f"  {r.ceil - r.sc:>6}{r.sc:>8}{r.ceil:>7}{r.g:>8}{pct:>4.0f}%{r.sf:>4}"
          f"  {str(r.scraped_at)[:16]:<17} {r.name[:32]}")
    if len(rows) > 30:
        p(f"  ... และอีก {len(rows) - 30} ร้าน")

    # ร้านที่ถูกข้ามเพราะนับครบแล้ว — บอกให้รู้ว่ามีอยู่ ไม่ใช่หายไปเงียบ
    skipped = (await session.execute(text(f"""
        SELECT count(*) n FROM places p
        WHERE p.scraped_at IS NOT NULL AND NOT p.scrape_excluded
          AND p.google_reviews_total >= {int(min_g)}
          AND COALESCE(p.refresh_shortfalls, 0) >= {int(max_sf)}
          AND (SELECT count(*) FROM reviews r WHERE r.place_id = p.id)
              < {float(min_cov)} * LEAST(p.google_reviews_total, {SERVE_CEILING})
    """))).scalar()
    if skipped:
        p(f"\n  ข้าม {skipped} ร้านที่ส่งกลับเข้าคิวครบ {max_sf} ครั้งแล้ว")
        p(f"    (Google น่าจะเสิร์ฟให้ได้เท่านั้นจริง — รีวิวถูกซ่อนหรือลบไป)")
        p(f"    ถ้าอยากลองอีก: --max-shortfalls {max_sf + 1}")

    if not apply:
        p(f"\n  ยังไม่ได้แก้อะไร — เติม --apply เพื่อทำจริง")
        p(f"\n  สิ่งที่จะทำ:")
        p(f"    scraped_at            -> NULL  (กลับไปหัวคิว refresh)")
        p(f"    consecutive_no_change -> 0     (ล้าง cooldown ที่ตั้งผิด)")
        p(f"    refresh_shortfalls    -> +1    (นับกันวนซ้ำ)")
        p(f"    รีวิว {sum(r.sc for r in rows):,} อันที่เก็บได้แล้ว **ไม่ถูกลบ**")
        p("=" * 78)
        return

    ids = [r.id for r in rows]
    await session.execute(text("""
        UPDATE places SET
            scraped_at            = NULL,
            consecutive_no_change = 0,
            refresh_shortfalls    = COALESCE(refresh_shortfalls, 0) + 1
        WHERE id = ANY(:ids)
    """), {"ids": ids})
    await session.commit()

    after = (await session.execute(text("""
        SELECT count(*) FILTER (WHERE scraped_at IS NULL) queued,
               count(*) total FROM places"""))).fetchone()
    rev = (await session.execute(text("SELECT count(*) FROM reviews"))).scalar()

    p(f"\n  ✅ ส่งกลับเข้าคิวแล้ว {len(ids)} ร้าน")
    p(f"  คิว refresh ตอนนี้ {after.queued} ร้าน จากทั้งหมด {after.total}")
    p(f"  รีวิวในระบบ {rev:,} อัน (ไม่ถูกลบ)")
    p(f"\n  ⚠️ ก่อนรัน auto_refresh ต่อ: ปัญหาเดิมคือ Google จำกัดอัตราแบบเงียบ")
    p(f"     ถ้ายังใช้ IP เดิมและรันต่อทันที จะพังแบบเดิมอีก")
    p(f"     แนะนำเปลี่ยน IP (mobile hotspot / VPN) และลด --limit ลง")
    p(f"\n  auto_refresh มีตัวตัดวงจรแล้ว (ดู GUIDE) จะหยุดเองถ้าเก็บได้ต่ำผิดปกติ")
    p("=" * 78)


async def reset_shortfalls(session, min_cov, min_g, apply: bool) -> None:
    """ล้าง refresh_shortfalls ให้ร้านที่ชนเพดานแล้ว เพื่อให้ลองซ้ำได้อีก

    ทำไมต้องมี: ตัวนับนี้ออกแบบให้ "ยอมแพ้" หลังลองครบ ซึ่งถูกต้องเมื่อสาเหตุคือ
    Google เสิร์ฟให้ได้เท่านั้นจริง แต่สาเหตุอีกแบบคือ Google เสิร์ฟหน้าร้าน
    แบบ**ไม่มีส่วนรีวิวมาให้เลย** ซึ่งเกิดแบบไม่คงที่ — ร้านเดิมรอบหน้าอาจได้ครบ
    ร้านกลุ่มนี้จะถูกกันออกถาวรทั้งที่ยังเก็บได้

    ใช้เมื่อเปลี่ยน IP แล้ว หรือย้ายไปรันช่วง 02:00-05:00 ที่โหลดน้อย
    ไม่ใช่คำสั่งที่ควรรันทุกรอบ — ถ้ารันทุกรอบตัวนับจะไร้ความหมาย

    ไม่แตะ scraped_at — ล้างแค่ตัวนับ ให้ report() รอบต่อไปตัดสินใจเองว่า
    ร้านไหนควรกลับเข้าคิว ถ้าล้างตัวนับพร้อมรีเซ็ต scraped_at ในคำสั่งเดียว
    จะข้ามเกณฑ์ความครบถ้วนไปเลย
    """
    rows = (await session.execute(text(f"""
        SELECT p.id, p.name, p.google_reviews_total AS g,
               COALESCE(p.refresh_shortfalls, 0) AS sf,
               LEAST(p.google_reviews_total, {SERVE_CEILING}) AS ceil,
               (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS sc
        FROM places p
        WHERE NOT p.scrape_excluded
          AND COALESCE(p.refresh_shortfalls, 0) > 0
          AND p.google_reviews_total IS NOT NULL
          AND p.google_reviews_total >= {int(min_g)}
          AND (SELECT count(*) FROM reviews r WHERE r.place_id = p.id)
              < {float(min_cov)} * LEAST(p.google_reviews_total, {SERVE_CEILING})
        ORDER BY COALESCE(p.refresh_shortfalls, 0) DESC,
                 LEAST(p.google_reviews_total, {SERVE_CEILING})
                 - (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) DESC
    """))).fetchall()

    p("=" * 78)
    p(f"  {'ทำจริง' if apply else 'DRY-RUN'} — ล้างตัวนับ refresh_shortfalls")
    p("=" * 78)
    if not rows:
        p("  ไม่มีร้านที่มีตัวนับค้างและยังเก็บไม่ครบ")
        p("=" * 78)
        return

    gap = sum(int(r.ceil) - r.sc for r in rows)
    p(f"  ร้านที่มีตัวนับค้าง {len(rows)} ร้าน · ช่องว่างรวม {gap:,} รีวิว")
    p()
    p(f"  {'id':>5} {'sf':>3} {'Google':>7} {'เก็บ':>6} {'ขาด':>6}  ชื่อร้าน")
    for r in rows[:30]:
        p(f"  {r.id:>5} {r.sf:>3} {str(r.g):>7} {r.sc:>6} "
          f"{int(r.ceil) - r.sc:>6}  {r.name[:38]}")
    if len(rows) > 30:
        p(f"  ... และอีก {len(rows) - 30} ร้าน")

    if not apply:
        p()
        p("  ยังไม่ได้แก้อะไร — เติม --apply เพื่อทำจริง")
        p("  สิ่งที่จะทำ: refresh_shortfalls -> 0 (ไม่แตะ scraped_at ไม่แตะรีวิว)")
        p("  หลังล้างแล้วรัน requeue_shortfall --apply ต่อ เพื่อส่งกลับเข้าคิว")
        p("=" * 78)
        return

    await session.execute(text("""
        UPDATE places SET refresh_shortfalls = 0 WHERE id = ANY(:ids)
    """), {"ids": [r.id for r in rows]})
    await session.commit()

    p()
    p(f"  ✅ ล้างตัวนับแล้ว {len(rows)} ร้าน")
    p(f"  ขั้นต่อไป: uv run python scripts/requeue_shortfall.py --apply")
    p(f"  ⚠️ ถ้ายังใช้ IP เดิมและรันต่อทันที จะพังแบบเดิมอีก")
    p("=" * 78)


async def run(args):
    async with AsyncSessionLocal() as session:
        if args.reset_shortfalls:
            await reset_shortfalls(session, args.min_coverage,
                                   args.min_reviews, args.apply)
            return
        await report(session, args.min_coverage, args.min_reviews,
                     args.max_shortfalls, args.apply)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="ส่งร้านที่เก็บรีวิวได้น้อยผิดปกติกลับเข้าคิว refresh")
    ap.add_argument("--apply", action="store_true",
                    help="ทำจริง (ไม่ใส่ = DRY-RUN ดูเฉย ๆ)")
    ap.add_argument("--min-coverage", type=float, default=MIN_COVERAGE,
                    help=f"เก็บได้ต่ำกว่าสัดส่วนนี้ของเพดาน = ผิดปกติ "
                         f"(ค่าเริ่มต้น {MIN_COVERAGE})")
    ap.add_argument("--min-reviews", type=int, default=MIN_GOOGLE_REVIEWS,
                    help=f"เช็คเฉพาะร้านที่ Google มีรีวิวตั้งแต่นี้ขึ้นไป "
                         f"(ค่าเริ่มต้น {MIN_GOOGLE_REVIEWS})")
    ap.add_argument("--max-shortfalls", type=int, default=MAX_SHORTFALLS,
                    help=f"ส่งกลับเข้าคิวได้ไม่เกินกี่ครั้ง "
                         f"(ค่าเริ่มต้น {MAX_SHORTFALLS})")
    ap.add_argument("--reset-shortfalls", action="store_true",
                    help="ล้างตัวนับ refresh_shortfalls ให้ร้านที่ชนเพดาน "
                         "เพื่อให้ลองซ้ำได้ (ใช้หลังเปลี่ยน IP/ย้ายช่วงเวลา)")
    asyncio.run(run(ap.parse_args()))
