"""
backfill_review_dates.py — กู้ review_date_approx ของรีวิวที่แปลงวันที่ไม่ได้

ปัญหาที่แก้ (พบ 2026-09-26): 1,658 รีวิวมี review_date_approx เป็น NULL
→ **หายไปจากทุกหน้าที่กรองช่วงวันที่** ซึ่งหน้า Dashboard กรองเป็นค่าเริ่มต้น
รีวิวเหล่านั้นมีข้อความครบทุกอัน จึงเป็นข้อมูลที่ใช้วิเคราะห์ได้แต่มองไม่เห็น

เกิดจาก 2 บั๊กคนละที่ (แก้ต้นตอทั้งคู่แล้ว):

  บั๊ก A — scraper/date_parser.py รับแค่ "ที่แล้ว" กับ "ago"
    Google ใช้ "ที่ผ่านมา" ด้วยสำหรับรีวิวใหม่ ๆ ("2 วันที่ผ่านมา")
    → 368 รีวิวที่ review_date ถูกต้องแต่แปลงไม่ได้ (กู้ได้จาก review_date)

  บั๊ก B — scraper_core.py หยิบป้าย "มื้อที่ไป" ของ Google มาเป็นวันที่
    เงื่อนไข JS จับคำว่า "วัน" เปล่า ๆ จึงเข้าเงื่อนไขกับ "วันธรรมดา" /
    "วันเสาร์-อาทิตย์" / "วันหยุดนักขัตฤกษ์" / "อาหารกลางวัน" (มี "วัน" ข้างใน)
    และใช้ forEach โดยไม่ break ทำให้ span สุดท้ายชนะ — ป้ายเขียนทับวันที่
    → 908 รีวิวที่ review_date เป็นขยะ แต่**วันที่จริงยังอยู่ในข้อความดิบ**
      (กู้ได้จาก r.text)

  382 รีวิวกู้ไม่ได้ — ป้ายทับไปแล้วและข้อความดิบไม่มีวันที่เลย

⚠️ ต้องใช้ r.scraped_at เป็นจุดอ้างอิง ไม่ใช่วันนี้
   "3 เดือนที่แล้ว" ที่เก็บมาเมื่อ 3 เดือนก่อน = 6 เดือนก่อนถ้านับจากวันนี้
   ยิ่ง scrape นานยิ่งเพี้ยน — วัดจริงพบคลาดเคลื่อนได้ถึง 34 วัน

⚠️ ไม่แตะ review_date (ข้อความดิบ) — เก็บไว้เป็นหลักฐานว่าที่มาคืออะไร
⚠️ ไม่แตะรีวิวที่มี review_date_approx อยู่แล้ว

รัน:
  uv run python scripts/backfill_review_dates.py           # DRY-RUN
  uv run python scripts/backfill_review_dates.py --apply   # แก้จริง
"""
import argparse
import asyncio
import os
import re
import sys
from collections import Counter

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from scraper.date_parser import parse_relative_date

# รูปแบบวันที่สัมพัทธ์ที่โผล่ในข้อความดิบ — ต้องมีคำบอกอดีตเสมอ
# (ไม่งั้นจะจับ "อายุ 93 ปี" หรือ "ตั้งแต่ปี 2003" จากเนื้อรีวิว)
_RELATIVE = re.compile(
    r"(\d+|a|an)\s*(วัน|สัปดาห์|เดือน|ปี|day|week|month|year)s?\s*"
    r"(ที่แล้ว|ที่ผ่านมา|ago)",
    re.IGNORECASE,
)
# "เมื่อวานนี้" / "วันนี้" ไม่มีตัวเลขและคำบอกอดีต จับแยก
_TODAY = re.compile(r"(เมื่อวาน\S*|วันนี้|yesterday|today)", re.IGNORECASE)


def find_relative(s: str | None) -> str | None:
    """หาวลีวันที่สัมพัทธ์ตัวแรกในข้อความ — คืน None ถ้าไม่มี"""
    if not s:
        return None
    m = _RELATIVE.search(s)
    if m:
        return m.group(0)
    m = _TODAY.search(s)
    return m.group(0) if m else None


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


async def run(apply: bool, limit) -> None:
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(text(f"""
            SELECT id, review_date AS rd, text AS raw, scraped_at
            FROM reviews
            WHERE review_date_approx IS NULL
            ORDER BY id
            {f'LIMIT {int(limit)}' if limit else ''}
        """))).fetchall()

        p("=" * 78)
        p(f"  {'ทำจริง' if apply else 'DRY-RUN'} — กู้ review_date_approx")
        p("=" * 78)
        p(f"\n  รีวิวที่ไม่มี review_date_approx: {len(rows):,} อัน")

        if not rows:
            p("\n  ✅ ทุกรีวิวมีวันที่แล้ว")
            p("=" * 78)
            return

        plan = []
        src_count = Counter()
        hopeless = []
        for x in rows:
            # ลอง review_date ก่อน (ตรงประเด็นที่สุด) แล้วค่อยหาในข้อความดิบ
            phrase = find_relative(x.rd)
            source = "review_date"
            if not phrase:
                phrase = find_relative(x.raw)
                source = "ข้อความดิบ"
            if not phrase:
                hopeless.append(x)
                continue

            # ⚠️ อ้างอิง scraped_at ไม่ใช่วันนี้ — ดูเหตุผลหัวไฟล์
            d = parse_relative_date(phrase, x.scraped_at)
            if d is None:
                hopeless.append(x)
                continue
            plan.append({"id": x.id, "d": d, "phrase": phrase,
                         "source": source, "rd": x.rd,
                         "scraped": x.scraped_at})
            src_count[source] += 1

        p(f"\n  กู้ได้ {len(plan):,} อัน")
        for src, n in src_count.most_common():
            p(f"    จาก {src:<14}{n:>6,}")
        p(f"  กู้ไม่ได้ {len(hopeless):,} อัน (ไม่มีวันที่ทั้งใน review_date และข้อความดิบ)")

        if plan:
            years = Counter(q["d"].year for q in plan)
            p(f"\n  ปีของวันที่ที่กู้ได้ (ค.ศ.):")
            for y in sorted(years):
                p(f"    {y}  {years[y]:>6,}")

            p(f"\n  ตัวอย่าง 5 อัน:")
            for q in plan[:5]:
                p(f"    id={q['id']}  scrape {str(q['scraped'])[:10]}")
                p(f"      review_date เดิม : {q['rd']!r}")
                p(f"      วลีที่ใช้ ({q['source']}) : {q['phrase']!r}")
                p(f"      -> review_date_approx = {q['d']}")

        if hopeless:
            c = Counter((x.rd or "(NULL)") for x in hopeless)
            p(f"\n  กลุ่มที่กู้ไม่ได้ (review_date ที่พบ):")
            for v, n in c.most_common(6):
                p(f"    {n:>5}  {v!r}")

        if not apply:
            p(f"\n  ยังไม่แก้อะไร — เติม --apply เพื่อทำจริง")
            p(f"\n  สิ่งที่จะทำ: ตั้ง review_date_approx ให้ {len(plan):,} อัน")
            p(f"    ไม่แตะ review_date (เก็บไว้เป็นหลักฐานที่มา)")
            p(f"    ไม่แตะรีวิวที่มีวันที่อยู่แล้ว")
            p("=" * 78)
            return

        for q in plan:
            await s.execute(
                text("UPDATE reviews SET review_date_approx = :d WHERE id = :i"),
                {"d": q["d"], "i": q["id"]})
        await s.commit()
        p(f"\n  ✅ กู้แล้ว {len(plan):,} อัน")

        left = (await s.execute(text(
            "SELECT count(*) FROM reviews WHERE review_date_approx IS NULL"))).scalar()
        tot = (await s.execute(text("SELECT count(*) FROM reviews"))).scalar()
        wt = (await s.execute(text("""
            SELECT count(*) FROM reviews
            WHERE review_date_approx IS NULL
              AND COALESCE(text_clean,'') <> ''"""))).scalar()
        p(f"  เหลือไม่มีวันที่ {left:,} จาก {tot:,} อัน ({left / tot * 100:.1f}%)")
        p(f"    ในนั้นมีข้อความ {wt:,} อัน — ยังมองไม่เห็นเมื่อกรองช่วงวันที่")
        p(f"\n  ขั้นต่อไป: uv run python scripts/take_snapshot.py --label dates-fixed")
        p("=" * 78)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="กู้ review_date_approx ที่แปลงไม่ได้")
    ap.add_argument("--apply", action="store_true", help="แก้จริง (ไม่ใส่ = DRY-RUN)")
    ap.add_argument("--limit", type=int, default=None, help="จำกัดจำนวน (ทดสอบ)")
    a = ap.parse_args()
    asyncio.run(run(a.apply, a.limit))
