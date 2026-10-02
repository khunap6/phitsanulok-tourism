"""
dedup_cross_place.py — ลบรีวิวที่ข้อความเดียวกันถูกบันทึกไว้หลายร้าน

`uq_place_text_hash` กันรีวิวซ้ำ**ในร้านเดียวกัน** แต่กันข้ามร้านไม่ได้
ถ้า scraper ดึงรีวิวของร้าน A มาใส่ร้าน B ด้วย จะได้ 2 แถวที่ระบบมองว่าถูกต้อง

พบ 2026-09-26: 102 ข้อความกระจายใน 205 แถว (0.28% ของรีวิวทั้งหมด)

สาเหตุที่พบ 2 แบบ:
  1. Google ย้าย/รวม listing — รีวิวที่เคยอยู่ listing หนึ่งไปโผล่อีก listing
     ตัวอย่างชัดสุด: Kyoto Shi Cafe (สาขาหลัก) เก็บได้ 193 รีวิว แต่ Google
     บอกว่ามี 4 — 84 อันในนั้นเป็นสำเนาของ "สาขาท่าทอง" (225/211)
  2. scraper จับหน้าผิดร้าน — ค้นชื่อร้าน A แล้ว Google Maps แสดงร้าน B

── หลักฐานที่ใช้ตัดสินว่าจะลบสำเนาไหน ──

  over = เก็บได้ - LEAST(google_reviews_total, 850)

ร้านที่ `over` เป็นบวกมาก คือร้านที่เก็บรีวิวได้เกินกว่าที่ Google บอกว่ามี
→ รีวิวส่วนเกินนั้นน่าจะเป็นของร้านอื่นที่หลุดมา จึงลบสำเนาที่อยู่ร้านนั้น

ถ้าไม่มีร้านไหน `over` เป็นบวก = ไม่มีหลักฐานว่าฝั่งไหนผิด → **ปล่อยไว้**
ไม่เดา เช่น "วงเวียนสถานีรถไฟพิษณุโลก" กับ "สถานีรถไฟพิษณุโลก" อยู่ห่างกัน
480 ม. เป็นสถานที่ใกล้กันจริง คนรีวิวอาจหมายถึงที่เดียวกัน — ตัดสินแทนไม่ได้

⚠️ ลบแถวใน reviews จะลบแถวใน analyzed_reviews ตามไปด้วย (FK CASCADE)
   สคริปต์รายงานจำนวนก่อนลบ และเหลือสำเนาไว้ 1 อันเสมอ — ข้อความไม่หายจากระบบ

⚠️ ควร backup ก่อนรัน --apply (ลบแถวย้อนกลับไม่ได้)

รัน:
  uv run python scripts/dedup_cross_place.py           # DRY-RUN
  uv run python scripts/dedup_cross_place.py --apply   # ลบจริง
"""
import argparse
import asyncio
import os
import sys
from collections import Counter

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal

SERVE_CEILING = 850
MIN_TEXT_LEN = 40   # ข้อความสั้น ("อร่อย", "ดีมาก") ซ้ำกันได้เองตามธรรมชาติ


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


async def build_plan(session) -> tuple[list[dict], list[dict]]:
    """คืน (แถวที่จะลบ, กลุ่มที่ตัดสินไม่ได้)"""
    groups = (await session.execute(text(f"""
        SELECT r.text_clean AS body,
               array_agg(r.id) AS rids,
               array_agg(r.place_id) AS pids
        FROM reviews r
        WHERE length(COALESCE(r.text_clean, '')) > {MIN_TEXT_LEN}
        GROUP BY r.text_clean
        HAVING count(DISTINCT r.place_id) > 1
    """))).fetchall()

    places = {x.id: x for x in (await session.execute(text("""
        SELECT p.id, p.name, p.google_reviews_total AS g,
               (SELECT count(*) FROM reviews rv WHERE rv.place_id = p.id) AS sc
        FROM places p
    """))).fetchall()}

    # over > 0 = เก็บได้เกินที่ Google บอก → น่าจะได้รีวิวของร้านอื่นมา
    over = {pid: (x.sc - min(x.g, SERVE_CEILING)) if x.g else None
            for pid, x in places.items()}

    drop, undecided = [], []
    for g in groups:
        cand = [(over.get(pid), pid, rid)
                for rid, pid in zip(g.rids, g.pids)]
        positive = [c for c in cand if c[0] is not None and c[0] > 0]
        if not positive:
            undecided.append({"pids": set(g.pids), "n": len(g.rids)})
            continue
        # ลบจากร้านที่ over สูงสุด (หลักฐานแรงสุดว่าได้ของคนอื่นมา)
        worst = max(positive, key=lambda c: c[0])
        drop.append({"rid": worst[2], "pid": worst[1], "over": worst[0]})
    return drop, undecided


async def run(apply: bool) -> None:
    async with AsyncSessionLocal() as s:
        drop, undecided = await build_plan(s)

        p("=" * 84)
        p(f"  {'ทำจริง' if apply else 'DRY-RUN'} — ลบรีวิวที่ซ้ำข้ามร้าน")
        p("=" * 84)

        if not drop and not undecided:
            p("\n  ✅ ไม่มีรีวิวซ้ำข้ามร้าน")
            p("=" * 84)
            return

        places = {x.id: x for x in (await s.execute(text("""
            SELECT p.id, p.name, p.google_reviews_total AS g,
                   (SELECT count(*) FROM reviews rv WHERE rv.place_id = p.id) AS sc
            FROM places p"""))).fetchall()}

        p(f"\n  จะลบ {len(drop)} แถว — เหลือสำเนาละ 1 อันที่ร้านที่มีหลักฐานดีกว่า")
        p(f"  ปล่อยไว้ {len(undecided)} กลุ่ม — ไม่มีร้านไหนเก็บเกิน ตัดสินไม่ได้")

        if drop:
            by = Counter(q["pid"] for q in drop)
            p(f"\n  แยกตามร้านที่จะถูกลบสำเนาออก:")
            for pid, n in by.most_common():
                x = places[pid]
                p(f"    ลบ {n:>4} แถว จาก id={pid:<5} เก็บ {x.sc:>4}/Google "
                  f"{str(x.g or '-'):>5} (เกิน {x.sc - min(x.g or 0, SERVE_CEILING):+})"
                  f"  {x.name[:36]}")

            an = (await s.execute(text("""
                SELECT count(*) FROM analyzed_reviews WHERE review_id = ANY(:ids)
            """), {"ids": [q["rid"] for q in drop]})).scalar()
            p(f"\n  ผลข้างเคียง: analyzed_reviews ที่จะหายตามไป (CASCADE) {an} แถว")

        if undecided:
            p(f"\n  กลุ่มที่ปล่อยไว้:")
            seen = set()
            for u in undecided:
                key = frozenset(u["pids"])
                if key in seen:
                    continue
                seen.add(key)
                names = " | ".join(places[i].name[:26] for i in sorted(u["pids"]))
                p(f"    {names[:74]}")

        if not apply:
            p(f"\n  ยังไม่ลบอะไร — เติม --apply เพื่อทำจริง")
            p(f"  ⚠️ ควร backup ก่อน (ลบแถวย้อนกลับไม่ได้)")
            p("=" * 84)
            return

        ids = [q["rid"] for q in drop]
        before = (await s.execute(text("SELECT count(*) FROM reviews"))).scalar()
        await s.execute(text("DELETE FROM reviews WHERE id = ANY(:ids)"), {"ids": ids})
        await s.commit()
        after = (await s.execute(text("SELECT count(*) FROM reviews"))).scalar()

        p(f"\n  ✅ ลบแล้ว {before - after} แถว (รีวิว {before:,} -> {after:,})")

        left_drop, left_und = await build_plan(s)
        p(f"  ตรวจผล — แถวที่ยังลบได้ {len(left_drop)} | ตัดสินไม่ได้ {len(left_und)}")
        # ยืนยันว่าไม่มีข้อความไหนหายไปทั้งหมด
        gone = (await s.execute(text(f"""
            SELECT count(*) FROM (
              SELECT r.text_clean FROM reviews r
              WHERE length(COALESCE(r.text_clean,'')) > {MIN_TEXT_LEN}
              GROUP BY r.text_clean HAVING count(*) >= 1) q"""))).scalar()
        p(f"  ข้อความไม่ซ้ำในระบบ {gone:,} แบบ (ทุกข้อความยังมีสำเนาเหลืออย่างน้อย 1)")
        p(f"\n  ขั้นต่อไป: uv run python scripts/take_snapshot.py --label dedup-cross-place")
        p("=" * 84)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ลบรีวิวที่ข้อความเดียวกันอยู่หลายร้าน")
    ap.add_argument("--apply", action="store_true", help="ลบจริง (ไม่ใส่ = DRY-RUN)")
    asyncio.run(run(ap.parse_args().apply))
