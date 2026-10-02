"""
coverage_report.py — รายงานความครบถ้วนของการเก็บรีวิว (อ่านอย่างเดียว)

นิยามที่ใช้:
  เพดานที่ทำได้ต่อร้าน = LEAST(google_reviews_total, 850)
  ความครบถ้วน         = รีวิวที่เก็บได้ / เพดานที่ทำได้
  "ครบ"               = เก็บได้ >= เพดานที่ทำได้

⚠️ ทำไมต้องใช้ LEAST(..., 850) ไม่ใช่ google_reviews_total ตรง ๆ
  Google เสิร์ฟรีวิวผ่านการ scroll ได้สูงสุดราว 850 อัน/ร้าน (วัดจากร้านที่
  deep scan สำเร็จ 26 ร้าน: ต่ำสุด 433 มัธยฐาน 785 สูงสุด 890)
  วัดพระศรีฯ deep แล้วได้ 832 จาก 10,058 = 8% ซึ่ง**ไม่ใช่ความล้มเหลว**
  แต่คือเต็มเพดานแล้ว ถ้าเทียบยอดเต็มจะสรุปผิดว่าร้านใหญ่ทุกร้านพัง

⚠️ google_reviews_total ใช้ได้ทางเดียว: ตัวส่วนของ "ความครบถ้วนการเก็บ"
  **ห้ามใช้เป็นตัวส่วนของอัตรา pain point** เพราะมันนับรีวิวทั้งหมดรวมที่ไม่มี
  ข้อความ ส่วนอัตรา pain point ต้องผ่านตัวกรองชุดเดียวกันทั้งตัวตั้งและตัวส่วน
  (กฎข้อ 1) — ดู docstring ของ migration 012

⚠️ ร้านที่เกิน 100% ไม่ใช่บั๊ก มี 3 สาเหตุ
  1. เราเก็บการ์ดที่ให้ดาวเปล่าไว้ด้วย ขณะที่ user_ratings_total นับไม่ตรงกัน
     (วัดแล้ว 112 จาก 124 ร้านที่เกิน พอตัดรีวิวไม่มีข้อความออกก็ไม่เกิน)
  2. google_reviews_total เป็นค่าตอน api_fetched_at ไม่ได้อัปเดตทุกรอบ
     และ Google ลบ/ซ่อนรีวิวทีหลังได้
  3. listing แบบโรงแรมมีรีวิวจาก Tripadvisor ปนมา ซึ่งไม่ถูกนับใน user_ratings_total

รัน:
  uv run python scripts/coverage_report.py
  uv run python scripts/coverage_report.py --list-incomplete 30   # โชว์ร้านที่ขาดมากสุด
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


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def bar(frac: float, width: int = 32) -> str:
    n = max(0, min(width, round(frac * width)))
    return "#" * n + "." * (width - n)


BASE = f"""
    SELECT p.id, p.name, p.google_reviews_total AS g,
           LEAST(p.google_reviews_total, {SERVE_CEILING}) AS ceil,
           (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS sc,
           (SELECT count(*) FROM reviews r WHERE r.place_id = p.id
              AND COALESCE(r.text_clean,'') <> '') AS sct,
           p.deep_scanned_at IS NOT NULL AS deep,
           COALESCE(p.refresh_shortfalls, 0) AS sf,
           p.scraped_at IS NULL AS queued
    FROM places p
    WHERE NOT p.scrape_excluded AND p.google_reviews_total IS NOT NULL
"""


async def main(args) -> int:
    async with AsyncSessionLocal() as s:
        tot = (await s.execute(text("""
            SELECT count(*) all_pl,
                   count(*) FILTER (WHERE scrape_excluded) excl,
                   count(*) FILTER (WHERE NOT scrape_excluded
                       AND google_reviews_total IS NULL) unmeasurable
            FROM places"""))).fetchone()
        rows = (await s.execute(text(BASE))).fetchall()

        p("=" * 78)
        p("  ความครบถ้วนของการเก็บรีวิว")
        p("=" * 78)
        p(f"  ร้านในฐานทั้งหมด            {tot.all_pl:>5}")
        p(f"    - กันออกจากขอบเขต         {tot.excl:>5}  (โรงแรม/เขตปกครอง)")
        p(f"    - วัดไม่ได้               {tot.unmeasurable:>5}  (ไม่มี google_reviews_total)")
        p(f"    - วัดได้                  {len(rows):>5}  <- ฐานของตัวเลขทั้งหมดข้างล่าง")

        got = sum(x.sc for x in rows)
        exp = sum(int(x.ceil) for x in rows)
        p("")
        p(f"  ระดับรีวิว : เก็บได้ {got:,} / เพดานที่ทำได้ {exp:,} = "
          f"{got / exp * 100:.1f}%")
        p(f"               {bar(got / exp)}")
        p(f"               ยังขาดอีก {exp - got:,} รีวิว")

        # ── ระดับร้าน ──
        done = [x for x in rows if x.sc >= x.ceil]
        t90 = [x for x in rows if x.ceil > x.sc >= 0.9 * x.ceil]
        t50 = [x for x in rows if 0.9 * x.ceil > x.sc >= 0.5 * x.ceil]
        t20 = [x for x in rows if 0.5 * x.ceil > x.sc >= 0.2 * x.ceil]
        low = [x for x in rows if x.sc < 0.2 * x.ceil]
        zero = [x for x in rows if x.sc == 0]

        p("")
        p("  ระดับร้าน:")
        p(f"  {'ช่วงความครบถ้วน':<22} {'ร้าน':>5} {'%ของร้าน':>9} {'รีวิวที่ขาด':>12}")
        for label, grp in (("ครบ 100% ขึ้นไป", done), ("90-99%", t90),
                           ("50-89%", t50), ("20-49%", t20),
                           ("ต่ำกว่า 20%", low)):
            miss = sum(max(int(x.ceil) - x.sc, 0) for x in grp)
            p(f"  {label:<22} {len(grp):>5} {len(grp) / len(rows) * 100:>8.1f}% "
              f"{miss:>12,}")
        p(f"  {'(ในนั้นเก็บได้ 0 เลย)':<22} {len(zero):>5} "
          f"{len(zero) / len(rows) * 100:>8.1f}% "
          f"{sum(int(x.ceil) for x in zero):>12,}")

        n_ok = len(done) + len(t90)
        p("")
        p(f"  สรุปแบบสั้น: ครบหรือเกือบครบ (>=90%) {n_ok} ร้าน = "
          f"{n_ok / len(rows) * 100:.1f}% ของร้านที่วัดได้")
        p(f"               ยังไม่ครบ (<90%) {len(rows) - n_ok} ร้าน = "
          f"{(len(rows) - n_ok) / len(rows) * 100:.1f}%")

        # ── แยกตามขนาดร้าน ──
        p("")
        p("  แยกตามขนาดร้าน (ร้านใหญ่เก็บยากกว่าเพราะต้อง scroll มาก):")
        p(f"  {'Google มีรีวิว':<16} {'ร้าน':>5} {'ครบถ้วน':>9} {'ครบ>=90%':>10} {'ขาด':>10}")
        bands = [(0, 50, "< 50"), (50, 200, "50-199"), (200, 500, "200-499"),
                 (500, 1000, "500-999"), (1000, 10**9, "1,000+")]
        for lo, hi, label in bands:
            grp = [x for x in rows if lo <= x.g < hi]
            if not grp:
                continue
            gg = sum(x.sc for x in grp)
            ge = sum(int(x.ceil) for x in grp)
            nok = sum(1 for x in grp if x.sc >= 0.9 * x.ceil)
            p(f"  {label:<16} {len(grp):>5} {gg / ge * 100:>8.1f}% "
              f"{nok:>9} {ge - gg:>10,}")

        # ── ตัวช่วยตัดสินใจ ──
        gap50 = [x for x in rows if int(x.ceil) - x.sc >= 50]
        p("")
        p("  งานที่เหลือ:")
        p(f"    ร้านที่ขาด >= 50 รีวิว   {len(gap50):>4} ร้าน · "
          f"{sum(int(x.ceil) - x.sc for x in gap50):,} รีวิว  "
          f"-> deep_scan --targets gap")
        p(f"    ร้านที่ยังไม่เคย deep    "
          f"{sum(1 for x in rows if not x.deep):>4} ร้าน")
        p(f"    ร้านที่อยู่ในคิว refresh {sum(1 for x in rows if x.queued):>4} ร้าน")
        p(f"    ร้านที่ชนเพดาน sf>=3    {sum(1 for x in rows if x.sf >= 3):>4} ร้าน "
          f"(ระบบเลิกตามแล้ว)")

        # ── หมายเหตุเรื่องเกิน 100% ──
        over = [x for x in rows if x.sc > x.ceil]
        over_txt = [x for x in over if x.sct > x.ceil]
        p("")
        p(f"  หมายเหตุ: ร้านที่เก็บได้เกินเพดาน {len(over)} ร้าน")
        p(f"    - พอตัดรีวิวที่ไม่มีข้อความออกแล้วไม่เกิน "
          f"{len(over) - len(over_txt)} ร้าน (เราเก็บการ์ดให้ดาวเปล่าไว้ด้วย)")
        p(f"    - ตัดแล้วยังเกิน {len(over_txt)} ร้าน "
          f"(google_reviews_total เป็นค่าค้าง หรือ API จับ listing ซ้ำของร้านเดียวกัน)")

        if args.list_incomplete:
            p("")
            p("=" * 78)
            p(f"  ร้านที่ขาดมากสุด {args.list_incomplete} อันดับ")
            p("=" * 78)
            worst = sorted(rows, key=lambda x: int(x.ceil) - x.sc,
                           reverse=True)[:args.list_incomplete]
            p(f"  {'id':>5} {'Google':>7} {'เพดาน':>6} {'เก็บ':>5} {'ขาด':>6} "
              f"{'%':>5} {'deep':>5} {'sf':>3}  ชื่อร้าน")
            for x in worst:
                pct = x.sc / x.ceil * 100 if x.ceil else 0
                p(f"  {x.id:>5} {x.g:>7} {int(x.ceil):>6} {x.sc:>5} "
                  f"{int(x.ceil) - x.sc:>6} {pct:>4.0f}% "
                  f"{('Y' if x.deep else '-'):>5} {x.sf:>3}  {x.name[:34]}")

        p("=" * 78)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="รายงานความครบถ้วนของการเก็บรีวิว")
    ap.add_argument("--list-incomplete", type=int, default=0, metavar="N",
                    help="โชว์ร้านที่ขาดมากสุด N อันดับ")
    sys.exit(asyncio.run(main(ap.parse_args())))
