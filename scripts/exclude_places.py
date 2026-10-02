"""
exclude_places.py — กันร้านที่อยู่นอกขอบเขตงานไม่ให้เข้าคิว scrape

ขอบเขตงานวิจัยเก็บรีวิวเฉพาะร้านอาหาร/คาเฟ่/แหล่งท่องเที่ยว/สวน/พิพิธภัณฑ์
**ไม่รวม** โรงแรม-ที่พัก เชนใหญ่ และห้างสรรพสินค้า เพราะปัญหาของที่พักเป็น
คนละชุดกับปัญหาการท่องเที่ยวเชิงกิน-เที่ยว (เช็คอิน/ห้องพัก/ราคาต่อคืน)
เอามารวมจะทำให้หมวดปัญหาปนกัน

ทำไมตั้งธง ไม่ลบร้านทิ้ง:
  ข้อมูลระดับร้านยิง Places API มาครบแล้ว — พิกัด, หมวด, คะแนน, จำนวนรีวิวจริง,
  ที่อยู่, เวลาทำการ ใช้เป็นตัวส่วนวัดความครอบคลุมพื้นที่ได้ (ในโซนนี้มีกี่ร้าน
  เราเก็บไปกี่ร้าน) ถ้าลบทิ้งจะเสียตัวส่วนไปด้วย

  ที่หนักกว่า: reviews.place_id เป็น ON DELETE CASCADE ลบร้าน = ลบรีวิวที่
  เก็บมาแล้วทิ้งไปด้วย กู้ไม่ได้ สคริปต์นี้จึงไม่ลบอะไรเลย

  ธงนี้ถอนกลับได้ด้วย --include ไม่มีข้อมูลหายระหว่างทาง

⚠️ ธงนี้ไม่ใช่ตัวกรองของสถิติ pain point
  รีวิวที่เก็บมาก่อนถูกตั้งธงยังอยู่ในฐานและยังถูกนับใน api/ ตามเดิม
  ถ้าจะตัดออกจากการวิเคราะห์ด้วยต้องเติมตัวกรองใน api/ แยก และต้องเติม
  ทั้งตัวตั้งและตัวส่วนพร้อมกัน (กฎข้อ 1) ไม่ใช่เติมข้างเดียว

⚠️ ใช้ google_types จาก Places API ไม่ใช่ google_category
  google_category มาจากการอ่านหน้าเว็บ ซึ่งพลาดได้ (บางร้านได้ข้อความปุ่ม UI
  มาเป็นหมวด — ดู fix_place_category.py) google_types มาจาก API ตรง ๆ

เกณฑ์ --pure-lodging:
  google_types มี 'lodging' แต่**ไม่มี** 'restaurant' และ 'cafe'
  ที่ต้องยกเว้นร้านที่มีทั้งคู่ เพราะคาเฟ่ที่มีห้องพักด้วยยังเป็นคาเฟ่จริง
  (เช่น 168 HEAVEN CAFE Resort เก็บได้ 127 รีวิว · บ้านติดดินสโลว์บาร์ 49)
  ถ้ากวาดทุกร้านที่มี lodging จะตัดคาเฟ่จริงออกไป 3 ร้าน

รัน:
  uv run python scripts/exclude_places.py --pure-lodging            # DRY-RUN
  uv run python scripts/exclude_places.py --pure-lodging --apply    # ทำจริง
  uv run python scripts/exclude_places.py --admin-areas --apply     # เขตปกครอง
  uv run python scripts/exclude_places.py --report                  # ดูว่ากันอะไรไว้
  uv run python scripts/exclude_places.py --include 664 1618        # ถอนธงคืน
  uv run python scripts/exclude_places.py --exclude 1185 953 --apply  # กันทีละ id
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal

REASON_LODGING = "ที่พัก — อยู่นอกขอบเขต (โรงแรม/เชน/ห้าง)"
REASON_ADMIN = "เขตปกครอง ไม่ใช่ร้าน — scrape ไม่ได้"
REASON_MANUAL = "อยู่นอกขอบเขต — ตัดสินด้วยคน"

# เกณฑ์ที่พักล้วน: มี lodging แต่ไม่มี restaurant/cafe
PURE_LODGING_SQL = """
    p.google_types LIKE '%lodging%'
    AND p.google_types NOT LIKE '%restaurant%'
    AND p.google_types NOT LIKE '%cafe%'
    AND NOT p.scrape_excluded
"""

# เขตปกครอง ไม่ใช่สถานที่ — Google ไม่มีหน้ารีวิวให้ scrape ได้เลย
#
# เจอ 2 แถวหลุดเข้ามาตอน discover: 'ตำบล ท่าโพธิ์' (locality,political) และ
# 'เขาสมอแคลง' (administrative_area_level_4,political) ทั้งคู่ไม่มี
# google_reviews_total เพราะ Google ไม่นับรีวิวให้เขตปกครอง
#
# ปล่อยไว้ในคิวจะเสียเวลา scrape เปล่าและถูกตี refresh_shortfalls เพิ่มทุกรอบ
ADMIN_AREA_SQL = """
    (p.google_types LIKE '%,political%' OR p.google_types LIKE 'political%'
     OR p.google_types LIKE '%locality%'
     OR p.google_types LIKE '%administrative_area_level%')
    AND p.google_types NOT LIKE '%restaurant%'
    AND p.google_types NOT LIKE '%cafe%'
    AND p.google_types NOT LIKE '%lodging%'
    AND p.google_types NOT LIKE '%tourist_attraction%'
    AND NOT p.scrape_excluded
"""


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


async def rows_for(session, where: str) -> list:
    return (await session.execute(text(f"""
        SELECT p.id, p.name, p.zone, p.google_category AS gc,
               p.google_types AS gt, p.google_reviews_total AS g,
               p.google_place_id IS NOT NULL AS has_pid,
               p.api_fetched_at IS NOT NULL AS has_api,
               p.scraped_at IS NULL AS in_queue,
               (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS sc
        FROM places p
        WHERE {where}
        ORDER BY p.google_reviews_total DESC NULLS LAST
    """))).fetchall()


async def exclude(session, where: str, reason: str, apply: bool) -> None:
    rows = await rows_for(session, where)

    p("=" * 78)
    p(f"  {'ทำจริง' if apply else 'DRY-RUN'} — กันร้านนอกขอบเขตไม่ให้เข้าคิว scrape")
    p("=" * 78)
    if not rows:
        p("  ไม่มีร้านเข้าเกณฑ์ (อาจถูกกันไว้แล้วทั้งหมด)")
        p("=" * 78)
        return

    p(f"  เข้าเกณฑ์ {len(rows)} ร้าน · เหตุผลที่จะบันทึก: {reason}")
    p()
    p(f"  {'id':>5} {'Google':>7} {'เก็บแล้ว':>9} {'คิว':>4} {'API':>4}  ชื่อร้าน")
    for r in rows:
        api_ok = "ครบ" if (r.has_pid and r.has_api) else "ขาด"
        p(f"  {r.id:>5} {str(r.g or '-'):>7} {r.sc:>9} "
          f"{('รอ' if r.in_queue else '-'):>4} {api_ok:>4}  {r.name[:40]}")
        p(f"        หมวด={r.gc!r}  types={(r.gt or '')[:58]}")

    kept_reviews = sum(r.sc for r in rows)
    missing_api = [r.id for r in rows if not (r.has_pid and r.has_api)]

    p()
    p(f"  รีวิวที่เก็บมาแล้วในกลุ่มนี้ {kept_reviews:,} อัน — **ไม่ถูกลบ**")
    if kept_reviews:
        p(f"    และยังถูกนับในสถิติ pain point ตามเดิม (ธงนี้กรองแค่คิว scrape)")
    if missing_api:
        p(f"  ⚠️ ร้าน id {missing_api} ยังไม่มีข้อมูล API ครบ")
        p(f"     ควรยิง backfill_place_id.py ก่อนกัน ไม่งั้นจะเสียตัวส่วนวัดความครอบคลุม")

    if not apply:
        p()
        p(f"  ยังไม่ได้แก้อะไร — เติม --apply เพื่อทำจริง")
        p(f"  สิ่งที่จะทำ: scrape_excluded -> true  พร้อมบันทึกเหตุผล")
        p(f"  ถอนคืนได้ด้วย: --include {' '.join(str(r.id) for r in rows[:4])} ...")
        p("=" * 78)
        return

    ids = [r.id for r in rows]
    await session.execute(text("""
        UPDATE places
           SET scrape_excluded = true,
               scrape_excluded_reason = :reason
         WHERE id = ANY(:ids)
    """), {"ids": ids, "reason": reason})
    await session.commit()

    await summary(session, f"✅ กันไว้แล้ว {len(ids)} ร้าน")


async def include(session, ids: list[int]) -> None:
    rows = (await session.execute(text("""
        SELECT id, name, scrape_excluded_reason AS why
        FROM places WHERE id = ANY(:ids) AND scrape_excluded
    """), {"ids": ids})).fetchall()

    p("=" * 78)
    p("  ถอนธง — ให้ร้านกลับเข้าคิว scrape ได้อีก")
    p("=" * 78)
    if not rows:
        p(f"  ไม่พบร้านที่ถูกกันไว้ใน id {ids}")
        p("=" * 78)
        return
    for r in rows:
        p(f"  id={r.id:<5} {r.name[:44]:<46} (เดิม: {r.why})")

    await session.execute(text("""
        UPDATE places
           SET scrape_excluded = false,
               scrape_excluded_reason = NULL
         WHERE id = ANY(:ids)
    """), {"ids": [r.id for r in rows]})
    await session.commit()
    await summary(session, f"✅ ถอนธงแล้ว {len(rows)} ร้าน")


async def report(session) -> None:
    rows = (await session.execute(text("""
        SELECT p.id, p.name, p.scrape_excluded_reason AS why,
               p.google_reviews_total AS g,
               (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS sc
        FROM places p WHERE p.scrape_excluded
        ORDER BY p.google_reviews_total DESC NULLS LAST
    """))).fetchall()

    p("=" * 78)
    p("  ร้านที่ถูกกันไว้ตอนนี้")
    p("=" * 78)
    if not rows:
        p("  ยังไม่มีร้านถูกกัน")
    for r in rows:
        p(f"  id={r.id:<5} Google {str(r.g or '-'):>5} · เก็บแล้ว {r.sc:>4}  "
          f"{r.name[:36]:<38} {r.why or ''}")
    await summary(session)


async def summary(session, head: str | None = None) -> None:
    s = (await session.execute(text("""
        SELECT count(*) total,
               count(*) FILTER (WHERE scrape_excluded) excluded,
               count(*) FILTER (WHERE NOT scrape_excluded
                                AND scraped_at IS NULL) queued
        FROM places"""))).fetchone()
    rev = (await session.execute(text("SELECT count(*) FROM reviews"))).scalar()
    p()
    if head:
        p(f"  {head}")
    p(f"  ร้านทั้งหมด {s.total} · กันไว้ {s.excluded} · อยู่ในคิว scrape {s.queued}")
    p(f"  รีวิวในระบบ {rev:,} อัน (สคริปต์นี้ไม่ลบรีวิว)")
    p("=" * 78)


async def run(args) -> int:
    async with AsyncSessionLocal() as session:
        if args.include:
            await include(session, args.include)
        elif args.exclude:
            # กันทีละ id — ใช้กับร้านที่ตัดสินด้วยคนว่าอยู่นอกขอบเขต
            # (เช่นห้างสรรพสินค้า/เชนในห้าง ที่ google_types บอกไม่ได้)
            ids = ",".join(str(int(i)) for i in args.exclude)
            await exclude(session, f"p.id IN ({ids}) AND NOT p.scrape_excluded",
                          args.reason, args.apply)
        elif args.pure_lodging:
            await exclude(session, PURE_LODGING_SQL, REASON_LODGING, args.apply)
        elif args.admin_areas:
            await exclude(session, ADMIN_AREA_SQL, REASON_ADMIN, args.apply)
        else:
            await report(session)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="กันร้านนอกขอบเขตงานไม่ให้เข้าคิว scrape (ไม่ลบข้อมูล)")
    ap.add_argument("--pure-lodging", action="store_true",
                    help="เลือกร้านที่ google_types มี lodging แต่ไม่มี restaurant/cafe")
    ap.add_argument("--admin-areas", action="store_true",
                    help="เลือกแถวที่เป็นเขตปกครอง (locality/political) ไม่ใช่ร้าน")
    ap.add_argument("--apply", action="store_true",
                    help="ทำจริง (ไม่ใส่ = DRY-RUN ดูเฉย ๆ)")
    ap.add_argument("--include", type=int, nargs="+", metavar="ID",
                    help="ถอนธงคืนให้ร้านตาม id")
    ap.add_argument("--exclude", type=int, nargs="+", metavar="ID",
                    help="กันร้านตาม id (ใช้กับร้านที่ตัดสินด้วยคน)")
    ap.add_argument("--reason", default=REASON_MANUAL,
                    help="เหตุผลที่บันทึกคู่กับ --exclude")
    ap.add_argument("--report", action="store_true",
                    help="ดูรายการร้านที่ถูกกันไว้ (ค่าเริ่มต้นถ้าไม่ใส่โหมดอื่น)")
    sys.exit(asyncio.run(run(ap.parse_args())))
