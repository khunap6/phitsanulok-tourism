"""
why_incomplete.py — ร้านไหนยังเก็บรีวิวไม่ครบ และ "เพราะอะไร" (อ่านอย่างเดียว)

ต่อยอดจาก coverage_report.py ที่บอกแค่ "ครบกี่ %" — ตัวนี้จัดกลุ่มสาเหตุให้
เพื่อตัดสินใจได้ว่าร้านไหนยังเก็บต่อได้ กับร้านไหนครบเท่าที่ทำได้แล้วจริง ๆ

นิยาม: เพดานที่ทำได้ = LEAST(google_reviews_total, 850) · ไม่ครบ = เก็บได้ < เพดาน

⚠️ "ไม่ครบ" ไม่ได้แปลว่า "เก็บต่อได้" ทุกกรณี
  ร้านที่ Google มีรีวิวเกิน 850 แล้วเราเก็บได้ ~800 ถือว่าเต็มเพดานแล้ว
  เพราะ Google เสิร์ฟผ่าน scroll ได้สูงสุดราว 850/ร้าน (วัดจาก deep ที่สำเร็จ
  26 ร้าน: ต่ำสุด 433 มัธยฐาน 785 สูงสุด 890) จึงต้องแยกกลุ่มนี้ออกก่อน
  ไม่งั้นจะวนไล่เก็บสิ่งที่เก็บไม่ได้

ลำดับการจัดกลุ่ม (ร้านหนึ่งได้สาเหตุเดียว — ตัวแรกที่เข้าเกณฑ์ชนะ):
  1. เก็บได้ 0 เลย            — เข้าไม่ถึงหน้ารีวิว (คนละเรื่องกับเก็บไม่ครบ)
  2. ระบบเลิกตามแล้ว          — refresh_shortfalls ชนเพดาน
  3. เต็มเพดาน scroll แล้ว     — ceil = 850 และเก็บได้ >= 90% ของเพดาน
  4. deep แล้วแต่ยังไม่ครบ     — Google เสิร์ฟให้ได้เท่านี้จริง
  5. ยังไม่เคย deep           — เกินเพดาน refresh (200) จึงต้องใช้ deep
  6. อยู่ในคิว ยังไม่ถึงตา     — scraped_at NULL
  7. อยู่ใน cooldown          — รอครบ 7-30 วัน

รัน:
  uv run python scripts/why_incomplete.py
  uv run python scripts/why_incomplete.py --list 20      # โชว์ร้านในแต่ละกลุ่ม 20 อันดับ
  uv run python scripts/why_incomplete.py --cause deep   # โชว์เฉพาะกลุ่มเดียว
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal

SERVE_CEILING = 850
REFRESH_CAP = 200          # MAX_REVIEWS_PER_PLACE ใน scraper_core
SHORTFALL_CAP = 3          # REFRESH_MAX_SHORTFALLS ใน scraper
NEAR_CEILING = 0.90        # เก็บได้เท่านี้ของเพดาน 850 = ถือว่าเต็มแล้ว

CAUSES = [
    ("zero", "เก็บได้ 0 เลย — เข้าไม่ถึงหน้ารีวิว",
     "คนละปัญหากับเก็บไม่ครบ · ดู GUIDE หัวข้อ listing แบบโรงแรม / ชื่อไม่ตรง"),
    ("gaveup", "ระบบเลิกตามแล้ว (refresh_shortfalls ชนเพดาน)",
     "ปลดล็อกด้วย requeue_shortfall.py --reset-shortfalls --apply"),
    ("maxed", "เต็มเพดาน scroll ของ Google แล้ว (~850)",
     "เก็บต่อไม่ได้อีก — ไม่ใช่ความล้มเหลว"),
    ("deep_done", "deep แล้วแต่ยังไม่ครบ",
     "Google เสิร์ฟให้ได้เท่านี้จริง — รีวิวถูกซ่อน/ลบ หรือชนเพดานย่อย"),
    ("need_deep", "ยังไม่เคย deep scan (เกินเพดาน refresh 200)",
     "deep_scan.py --targets gap  <- งานหลักที่เหลือ"),
    ("queued", "อยู่ในคิว ยังไม่ถึงตา",
     "auto_refresh.py รอบถัดไปจะหยิบเอง"),
    ("cooldown", "อยู่ใน cooldown รอครบ 7-30 วัน",
     "ไม่ต้องทำอะไร ระบบหยิบเองเมื่อครบกำหนด"),
]


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def classify(r) -> str:
    ceil = int(r.ceil)
    if r.sc == 0:
        return "zero"
    if r.sf >= SHORTFALL_CAP:
        return "gaveup"
    if ceil >= SERVE_CEILING and r.sc >= NEAR_CEILING * ceil:
        return "maxed"
    if r.deep:
        return "deep_done"
    if ceil > REFRESH_CAP:
        return "need_deep"
    if r.queued:
        return "queued"
    return "cooldown"


async def main(args) -> int:
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(text(f"""
            SELECT p.id, p.name, p.google_reviews_total AS g,
                   LEAST(p.google_reviews_total, {SERVE_CEILING}) AS ceil,
                   (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS sc,
                   COALESCE(p.refresh_shortfalls, 0) AS sf,
                   p.deep_scanned_at IS NOT NULL AS deep,
                   COALESCE(p.deep_attempts, 0) AS datt,
                   p.scraped_at IS NULL AS queued,
                   COALESCE(p.consecutive_no_change, 0) AS cnc
            FROM places p
            WHERE NOT p.scrape_excluded
              AND p.google_reviews_total IS NOT NULL
              AND (SELECT count(*) FROM reviews r WHERE r.place_id = p.id)
                  < LEAST(p.google_reviews_total, {SERVE_CEILING})
            ORDER BY LEAST(p.google_reviews_total, {SERVE_CEILING})
                     - (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) DESC
        """))).fetchall()

        total = (await s.execute(text(f"""
            SELECT count(*) n,
                   coalesce(sum(LEAST(google_reviews_total, {SERVE_CEILING})), 0) exp,
                   coalesce(sum((SELECT count(*) FROM reviews r
                                 WHERE r.place_id = p.id)), 0) got
            FROM places p WHERE NOT scrape_excluded
              AND google_reviews_total IS NOT NULL"""))).fetchone()
        unmeasurable = (await s.execute(text("""
            SELECT count(*) FROM places WHERE NOT scrape_excluded
              AND google_reviews_total IS NULL"""))).scalar()

        groups: dict[str, list] = {k: [] for k, _, _ in CAUSES}
        for r in rows:
            groups[classify(r)].append(r)

        p("=" * 80)
        p("  ร้านที่ยังเก็บรีวิวไม่ครบ — แยกตามสาเหตุ")
        p("=" * 80)
        p(f"  ร้านที่วัดได้ {total.n} ร้าน · เก็บได้ {int(total.got):,}/"
          f"{int(total.exp):,} = {total.got / total.exp * 100:.1f}%")
        p(f"  ในนั้นยังไม่ครบ {len(rows)} ร้าน "
          f"({len(rows) / total.n * 100:.1f}%) · "
          f"ขาดรวม {sum(int(x.ceil) - x.sc for x in rows):,} รีวิว")
        p(f"  (อีก {unmeasurable} ร้านวัดไม่ได้เลยเพราะไม่มี google_reviews_total)")
        p("")

        p(f"  {'สาเหตุ':<42} {'ร้าน':>5} {'รีวิวที่ขาด':>12}")
        p(f"  {'-' * 42} {'-' * 5} {'-' * 12}")
        recoverable = unrecoverable = 0
        for key, label, _ in CAUSES:
            grp = groups[key]
            if not grp:
                continue
            gap = sum(int(x.ceil) - x.sc for x in grp)
            if key in ("maxed", "deep_done"):
                unrecoverable += gap
            else:
                recoverable += gap
            p(f"  {label:<42} {len(grp):>5} {gap:>12,}")

        p("")
        p(f"  เก็บต่อได้จริง        {recoverable:>9,} รีวิว")
        p(f"  เก็บต่อไม่ได้แล้ว      {unrecoverable:>9,} รีวิว "
          f"(เต็มเพดาน Google / รีวิวถูกซ่อน-ลบ)")

        # ── รายละเอียดแต่ละกลุ่ม ──
        for key, label, advice in CAUSES:
            grp = groups[key]
            if not grp:
                continue
            if args.cause and args.cause != key:
                continue
            p("")
            p("=" * 80)
            p(f"  {label}  —  {len(grp)} ร้าน")
            p(f"  → {advice}")
            p("=" * 80)

            if key == "deep_done":
                ratios = sorted(x.sc / int(x.ceil) for x in grp)
                med = ratios[len(ratios) // 2]
                p(f"  กลุ่มนี้ deep แล้วได้เฉลี่ย {sum(ratios) / len(ratios) * 100:.0f}% "
                  f"ของเพดาน (มัธยฐาน {med * 100:.0f}%)")
                p(f"  เคยลอง deep ซ้ำ >1 ครั้ง {sum(1 for x in grp if x.datt > 1)} ร้าน")
                p("")

            n_show = args.list or 10
            p(f"  {'id':>5} {'Google':>7} {'เพดาน':>6} {'เก็บ':>5} {'ขาด':>6} "
              f"{'%':>5} {'sf':>3} {'deep':>5}  ชื่อร้าน")
            for x in grp[:n_show]:
                ceil = int(x.ceil)
                p(f"  {x.id:>5} {x.g:>7} {ceil:>6} {x.sc:>5} {ceil - x.sc:>6} "
                  f"{x.sc / ceil * 100:>4.0f}% {x.sf:>3} "
                  f"{('Y' if x.deep else '-'):>5}  {x.name[:32]}")
            if len(grp) > n_show:
                p(f"  ... และอีก {len(grp) - n_show} ร้าน "
                  f"(ใช้ --list {len(grp)} เพื่อดูทั้งหมด)")

        p("")
        p("=" * 80)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="ร้านไหนเก็บรีวิวไม่ครบ และเพราะอะไร")
    ap.add_argument("--list", type=int, default=0, metavar="N",
                    help="โชว์ร้านในแต่ละกลุ่ม N อันดับ (ค่าเริ่มต้น 10)")
    ap.add_argument("--cause", choices=[k for k, _, _ in CAUSES],
                    help="โชว์เฉพาะกลุ่มสาเหตุนี้")
    sys.exit(asyncio.run(main(ap.parse_args())))
