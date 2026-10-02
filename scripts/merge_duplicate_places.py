"""
merge_duplicate_places.py — รวมแถวร้านซ้ำที่เกิดจาก promote + refresh ชื่อไม่ตรงกัน

ปัญหาที่แก้ (พบ 2026-09-26 · 26 คู่):

  promote_candidates.py สร้างแถวใน places ด้วย **ชื่อจาก Google Places API**
  แล้ว auto_refresh ไป scrape ร้านนั้น Google Maps แสดง**ชื่อที่ขึ้นบนหน้าเว็บ**
  ซึ่งมักเป็นภาษาไทยขณะที่ API ให้ชื่ออังกฤษ

  save_to_db upsert ด้วย `ON CONFLICT (name)` — ชื่อไม่ตรงจึง **INSERT แถวใหม่**

      id=3084  Google 791 รีวิว | Pang Ki Khao Man Kai      (จาก API, 0 รีวิว)
      id=3705  เก็บ  200 รีวิว | พังกี่ข้าวมันไก่           (จาก scrape)

  ผลเสีย 3 อย่าง:
    1. นับร้านเกินจริง (792 ควรเป็น 766)
    2. ตัวเลขความครบถ้วนเพี้ยน — แถว API มีเฉลยแต่ 0 รีวิว (0%)
       ส่วนแถวที่มีรีวิวไม่มีเฉลย (วัดไม่ได้) ทั้งที่ของจริงคือ 200/791 = 25%
    3. คิว refresh เปื้อน — แถว API ค้าง scraped_at = NULL ตลอดไป
       เพราะ refresh สร้างแถวใหม่ทุกครั้งไม่มาเติมแถวเดิม = วน scrape ไม่รู้จบ

⚠️ เก็บแถวที่ "มีรีวิว" ไว้ ไม่ใช่แถวจาก API
   เพราะชื่อของมันคือชื่อที่ Google Maps แสดงจริง → refresh รอบหน้าจะ match
   แถวเดิมและไม่สร้างใหม่อีก ถ้าเก็บแถว API ไว้ปัญหาจะเกิดซ้ำทุกรอบ scrape

   ย้าย google_place_id + ฟิลด์ API ทั้ง 6 ไปใส่แถวที่เก็บ แล้วลบแถว API

⚠️ reviews.place_id เป็น ON DELETE CASCADE
   ลบแถว places = ลบรีวิวของแถวนั้นด้วย สคริปต์จึง **ยืนยันว่ามี 0 รีวิว
   ทันทีก่อนลบทุกครั้ง** ไม่เชื่อค่าที่อ่านมาตอนแรก

⚠️ snapshot_places.place_id ก็ CASCADE — ประวัติ snapshot ของแถวที่ลบจะหายด้วย
   (แถวที่ลบมี 0 รีวิว จึงไม่มีสถิติที่มีความหมายอยู่แล้ว สคริปต์รายงานให้ดู)

⚠️ place_candidates.matched_place_id เป็น ON DELETE SET NULL
   สคริปต์ชี้ค่านั้นไปที่แถวที่เก็บไว้ก่อนลบ เพื่อไม่ให้ตามรอยขาด

รัน:
  uv run python scripts/merge_duplicate_places.py           # DRY-RUN: ดูคู่ที่จะรวม
  uv run python scripts/merge_duplicate_places.py --apply   # รวมจริง
  uv run python scripts/merge_duplicate_places.py --max-distance 60 --apply
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from scraper.zones import _haversine_km

# ระยะที่ถือว่า "พิกัดเดียวกัน" — คู่ที่พบจริงทั้ง 26 คู่ห่างกัน 0 ม.
# ตั้ง 40 ม. เผื่อพิกัดคลาดเคลื่อน แต่ไม่กว้างจนรวมร้านข้างเคียงผิด
MAX_DISTANCE_M = 40


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


async def find_pairs(session, max_m: float) -> list[dict]:
    """
    หาคู่ (แถวที่เก็บไว้, แถวที่จะลบ)

    ลายเซ็นที่ชัดเจน — ต้องครบทุกข้อ:
      - อยู่ห่างกันไม่เกิน max_m
      - แถวหนึ่งมี google_place_id และ **0 รีวิว** (แถวจาก API ที่ยังไม่ถูก scrape)
      - อีกแถว **มีรีวิว** และ **ไม่มี** google_place_id (แถวที่ scraper สร้าง)

    เงื่อนไข "ไม่มี google_place_id" สำคัญ — ถ้าทั้งสองแถวมี place_id คนละตัว
    แปลว่า Google ถือว่าเป็นคนละสถานที่ ไม่ควรรวม (เช่น 2 สาขาในตึกเดียวกัน)
    """
    rows = (await session.execute(text("""
        SELECT p.id, p.name, p.google_place_id AS gpid,
               p.google_reviews_total AS g, p.google_types, p.google_rating AS rt,
               p.formatted_address AS addr, p.api_fetched_at AS fetched,
               p.discovered_by AS src, p.scraped_at AS scraped,
               ST_Y(p.location::geometry) AS lat, ST_X(p.location::geometry) AS lng,
               (SELECT count(*) FROM reviews rv WHERE rv.place_id = p.id) AS sc
        FROM places p WHERE p.location IS NOT NULL ORDER BY p.id
    """))).fetchall()

    api_empty = [x for x in rows if x.gpid and x.sc == 0]
    scraped_rows = [x for x in rows if x.sc > 0 and x.gpid is None]

    pairs = []
    used_keep = set()
    for a in api_empty:
        best = None
        for b in scraped_rows:
            if b.id in used_keep:
                continue
            d = _haversine_km(a.lat, a.lng, b.lat, b.lng) * 1000
            if d > max_m:
                continue
            # ถ้ามีหลายแถวในรัศมี เลือกที่ใกล้สุด แล้วตัดสินด้วยจำนวนรีวิวที่ใกล้เคียงเฉลย
            score = (d, abs((a.g or 0) - b.sc))
            if best is None or score < best[0]:
                best = (score, b, d)
        if best:
            _, b, d = best
            used_keep.add(b.id)
            pairs.append({"drop": a, "keep": b, "dist": d})
    return pairs


_MOVE_API_FIELDS = text("""
    UPDATE places SET
        google_place_id      = :gpid,
        google_types         = COALESCE(:types, google_types),
        formatted_address    = COALESCE(:addr, formatted_address),
        google_rating        = COALESCE(:rt, google_rating),
        google_reviews_total = COALESCE(:g, google_reviews_total),
        api_fetched_at       = COALESCE(:fetched, api_fetched_at),
        discovered_by        = COALESCE(discovered_by, 'scrape')
    WHERE id = :keep_id
""")


async def run(apply: bool, max_m: float) -> None:
    async with AsyncSessionLocal() as s:
        pairs = await find_pairs(s, max_m)

        p("=" * 84)
        p(f"  {'ทำจริง' if apply else 'DRY-RUN'} — รวมแถวร้านซ้ำ (ห่างกันไม่เกิน {max_m:.0f} ม.)")
        p("=" * 84)

        if not pairs:
            p("\n  ✅ ไม่พบแถวซ้ำ")
            p("=" * 84)
            return

        p(f"\n  พบ {len(pairs)} คู่\n")
        p(f"  {'ห่าง':>5}  แถวที่เก็บ (มีรีวิว) <- ย้ายฟิลด์ API มาจากแถวที่ลบ")
        for q in pairs:
            k, d_ = q["keep"], q["drop"]
            p(f"  {q['dist']:>4.0f}ม  เก็บ id={k.id:<5} รีวิว {k.sc:>4} | {k.name[:44]}")
            p(f"         ลบ  id={d_.id:<5} รีวิว {d_.sc:>4} | {d_.name[:44]}")
            p(f"         ย้ายมา: Google {d_.g or '-'} รีวิว · place_id {(d_.gpid or '')[:22]}")

        # snapshot ที่จะหายไปเพราะ CASCADE
        snap = (await s.execute(text("""
            SELECT count(*) FROM snapshot_places WHERE place_id = ANY(:ids)
        """), {"ids": [q["drop"].id for q in pairs]})).scalar()
        cand = (await s.execute(text("""
            SELECT count(*) FROM place_candidates WHERE matched_place_id = ANY(:ids)
        """), {"ids": [q["drop"].id for q in pairs]})).scalar()

        p(f"\n  ผลข้างเคียง:")
        p(f"    แถวใน snapshot_places ที่จะหาย (CASCADE) : {snap}")
        p(f"    place_candidates ที่ต้องชี้ใหม่           : {cand}")
        p(f"    รีวิวที่จะหาย                            : 0 (แถวที่ลบมี 0 รีวิวทุกแถว)")

        if not apply:
            tot = (await s.execute(text("SELECT count(*) FROM places"))).scalar()
            q_now = (await s.execute(text(
                "SELECT count(*) FROM places WHERE scraped_at IS NULL"))).scalar()
            p(f"\n  ยังไม่แก้อะไร — เติม --apply เพื่อทำจริง")
            p(f"\n  หลังรวม:")
            p(f"    places         {tot} -> {tot - len(pairs)}")
            p(f"    คิว refresh    {q_now} -> {q_now - len(pairs)} (แถวซ้ำออกจากคิว)")
            p("=" * 84)
            return

        merged = skipped = 0
        for q in pairs:
            keep, drop = q["keep"], q["drop"]

            # ⚠️ ยืนยัน 0 รีวิวอีกครั้งทันทีก่อนลบ — reviews.place_id เป็น CASCADE
            # ไม่เชื่อค่าที่อ่านมาตอนแรก (ข้อมูลอาจเปลี่ยนระหว่างนั้น)
            live = (await s.execute(text(
                "SELECT count(*) FROM reviews WHERE place_id = :i"),
                {"i": drop.id})).scalar()
            if live != 0:
                p(f"  ⚠️ ข้าม id={drop.id} — มีรีวิว {live} อันแล้ว (ลบจะทำข้อมูลหาย)")
                skipped += 1
                continue

            # ⚠️ ลำดับสำคัญ — ทำผิดลำดับแล้วพังทั้งสองทาง:
            #   1. ชี้ place_candidates ไปแถวที่เก็บ **ก่อน** ลบ
            #      (FK เป็น ON DELETE SET NULL ถ้าลบก่อนจะเสียการตามรอย)
            #   2. ลบแถวที่ซ้ำ **ก่อน** ตั้ง google_place_id ให้แถวที่เก็บ
            #      เพราะ uq_places_google_place_id เป็น UNIQUE — ตั้งค่าซ้ำกับแถว
            #      ที่ยังมีอยู่จะได้ UniqueViolationError ทันที
            #   3. ทั้งหมดอยู่ใน transaction เดียว ถ้าขั้นไหนพังจะ rollback
            #      ไม่เกิดสภาพ "ลบแถวแล้วแต่ยังไม่ได้ย้าย place_id"
            await s.execute(text("""
                UPDATE place_candidates SET matched_place_id = :keep
                WHERE matched_place_id = :drop
            """), {"keep": keep.id, "drop": drop.id})
            await s.execute(text("DELETE FROM places WHERE id = :i"), {"i": drop.id})
            await s.execute(_MOVE_API_FIELDS, {
                "gpid": drop.gpid, "types": drop.google_types, "addr": drop.addr,
                "rt": drop.rt, "g": drop.g, "fetched": drop.fetched,
                "keep_id": keep.id,
            })
            await s.commit()
            merged += 1

        tot = (await s.execute(text("SELECT count(*) FROM places"))).scalar()
        q_now = (await s.execute(text(
            "SELECT count(*) FROM places WHERE scraped_at IS NULL"))).scalar()
        rev = (await s.execute(text("SELECT count(*) FROM reviews"))).scalar()
        p(f"\n  ✅ รวมแล้ว {merged} คู่" + (f" | ข้าม {skipped}" if skipped else ""))
        p(f"  places {tot} แถว | คิว refresh {q_now} ร้าน | รีวิว {rev:,} อัน")

        left = await find_pairs(s, max_m)
        p(f"  ตรวจผล — แถวซ้ำที่เหลือ: {len(left)}")
        p("=" * 84)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="รวมแถวร้านซ้ำจาก promote + refresh")
    ap.add_argument("--apply", action="store_true", help="รวมจริง (ไม่ใส่ = DRY-RUN)")
    ap.add_argument("--max-distance", type=float, default=MAX_DISTANCE_M,
                    help=f"ระยะที่ถือว่าพิกัดเดียวกัน เมตร (ค่าเริ่มต้น {MAX_DISTANCE_M})")
    a = ap.parse_args()
    asyncio.run(run(a.apply, a.max_distance))
