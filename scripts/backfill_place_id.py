"""
backfill_place_id.py — เติม google_place_id + ฟิลด์จาก Places API ให้ร้านที่มีอยู่แล้ว

ทำไมต้องทำก่อน discover:
  ถ้าร้านเดิม 323 ร้านยังไม่มี google_place_id การจับคู่ผลจาก discover กับของเดิม
  จะเหลือแค่ "เทียบชื่อ" ซึ่งคือวิธีที่เรากำลังหนีอยู่ (ชื่อซ้ำ/สะกดต่าง/เชนหลายสาขา)
  มี place_id ก่อน → จับคู่แม่น 100% แล้วค่อยรู้ว่าอะไรใหม่จริง

⚠️ ความปลอดภัย: สคริปต์นี้ UPDATE ได้แค่ 7 คอลัมน์ที่ migration 012 เพิ่มเข้ามา
   name / location / overall_rating / opening_hours / business_status / zone /
   scraped_at / deep_* ไม่อยู่ในคำสั่ง UPDATE เลย → ทำข้อมูลเดิมเสียหายไม่ได้
   ในทางโครงสร้าง ไม่ใช่เพราะความระมัดระวัง

รัน:
  uv run python scripts/backfill_place_id.py                 # DRY-RUN: นับ + ประเมินราคา (ไม่ยิง API)
  uv run python scripts/backfill_place_id.py --report        # อ่านอย่างเดียว: ตารางจุดตรวจ 4 ข้อ
  uv run python scripts/backfill_place_id.py --limit 5       # ยิงจริง 5 ร้าน (ทดสอบก่อนเสมอ)
  uv run python scripts/backfill_place_id.py --all           # ยิงทุกร้านที่ยังไม่มี place_id
  uv run python scripts/backfill_place_id.py --all --force   # ยิงซ้ำรวมร้านที่มีแล้ว
  uv run python scripts/backfill_place_id.py --all --max-requests 100   # เพดานแข็ง

ทดสอบ --limit 5 ก่อนเสมอ เพราะมันตอบ 2 คำถามในคราวเดียวด้วยเงินไม่ถึง 10 บาท:
  1. Find Place รับ fields ชุดเต็มได้ไหม (เส้นทาง 1 คำขอ vs 2 คำขอต่อร้าน)
  2. เครดิตทดลองใช้ครอบ Places API ไหม (ดู Billing > Reports หลังรัน ~24 ชม.)
"""
import argparse
import asyncio
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from db.database import AsyncSessionLocal
from scraper import places_api
from scraper.places_api import COST_PER_REQUEST_USD, PlacesApiError, lookup_place
from scraper.zones import _haversine_km

# ระยะที่ถือว่า "API จับผิดร้าน" — เกินนี้ต้องดูรายตัว ไม่ใช่ปัดตก
COORD_DRIFT_WARN_M = 200
# หน่วงระหว่างคำขอ กัน rate limit ของ API (ค่าเดียวกับ fetch_hours_api.py)
REQUEST_DELAY_SEC = 0.15


def p(msg: str = "") -> None:
    """พิมพ์แบบไม่พังบน console ที่ไม่รองรับ UTF-8 (cp874 บน Windows)"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


# ---------------------------------------------------------------------------
# โหลดเป้าหมาย
# ---------------------------------------------------------------------------

async def load_targets(session, limit: int | None, include_done: bool,
                       ids: list[int] | None = None) -> list[dict]:
    """
    ร้านที่ต้องเติม — ค่าเริ่มต้นคือที่ยังไม่มี google_place_id

    ⚠️ เลือกคำค้นให้ถูกตัว — name หรือ search_query (แก้ 2026-10-01)

      เดิมใช้ search_query ก่อน name เสมอ ด้วยเหตุผลว่า search_query คือข้อความ
      ที่ค้นเจอร้านนี้จริง **แต่เหตุผลนั้นใช้ไม่ได้เมื่อสองค่าไม่ตรงกัน**

      save_to_db upsert ด้วย ON CONFLICT (name) โดยใช้ชื่อจริงบนหน้าเว็บ
      ถ้าการค้นด้วย search_query พาไปโผล่ที่ร้านอื่น แถวใหม่จะถูกสร้างด้วย
      ชื่อของร้านที่โผล่ ส่วน search_query ยังเป็นคำค้นเดิมที่ไม่ใช่ชื่อร้านนี้

        id=3639  name 'โรงฮัก'                   search_query 'RongHuk'
        id=4438  name 'พิซซ่าฮัท สาขา พิษณุโลก'   search_query 'Pizza Hut'
        id=3512  name 'จงรัก'                     search_query 'Jong Rak'

      ค้นด้วย search_query จึงไปจับร้านอื่นหรือหาไม่เจอทุกครั้ง — วัดได้ว่า
      23 จาก 26 ร้านที่ไม่มี place_id มี name ไม่ตรงกับ search_query

      ทดสอบด้วย name แทน: เจอครบ 8/8 ร้าน และชื่อที่ API คืนตรงกับ name เป๊ะ
      (โรงฮัก 366 รีวิว · พิซซ่าฮัท 338 · สถานีรถไฟพิษณุโลก 284)

      เกณฑ์ใหม่:
        name == search_query  -> ใช้ค่าไหนก็ได้ (เหมือนเดิม)
        name <> search_query  -> ใช้ **name** เพราะเป็นชื่อที่ Google แสดงจริง
                                 สำหรับแถวนี้ ส่วน search_query เป็นคำค้นที่
                                 พาไปผิดร้าน
    """
    # ids ระบุชัด = เขียนทับได้เสมอ ไม่สนว่ามี place_id อยู่แล้วหรือไม่
    # ใช้ตอนรู้ว่า place_id เดิมชี้ผิดร้านและต้องการค่าที่ถูกจาก API
    if ids:
        where = "id = ANY(ARRAY[" + ",".join(str(int(i)) for i in ids) + "])"
    else:
        where = "TRUE" if include_done else "google_place_id IS NULL"
    q = f"""
        SELECT id, name, search_query,
               ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng
        FROM places
        WHERE {where}
        ORDER BY id
    """
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = (await session.execute(text(q))).fetchall()
    out = []
    for r in rows:
        sq = (r.search_query or "").strip()
        nm = (r.name or "").strip()
        # ชื่อจริงบนหน้าเว็บชนะเมื่อสองค่าไม่ตรงกัน
        query = nm if (nm and sq and nm != sq) else (sq or nm)
        out.append({"id": r.id, "name": r.name, "query": query,
                    "used_name": query == nm and nm != sq,
                    "lat": r.lat, "lng": r.lng})
    return out


# ---------------------------------------------------------------------------
# บันทึกผล (แตะได้แค่ 7 คอลัมน์ใหม่)
# ---------------------------------------------------------------------------

_UPDATE_SQL = text("""
    UPDATE places SET
        google_place_id      = :pid,
        google_types         = :types,
        formatted_address    = :addr,
        google_rating        = :rating,
        google_reviews_total = :total,
        api_fetched_at       = NOW(),
        discovered_by        = COALESCE(discovered_by, 'scrape')
    WHERE id = :id
""")


async def apply_one(session, target: dict, data: dict) -> tuple[str, dict]:
    """
    เขียนผลลง DB คืน (ผลลัพธ์, ข้อมูลประกอบ)

    ผลลัพธ์: "ok" | "dup" (place_id ซ้ำกับร้านอื่นใน DB) | "error"

    เช็คซ้ำก่อน UPDATE ไม่ใช่รอให้ UNIQUE index เหวี่ยง exception เพราะเราอยาก
    รายงานได้ว่า "ซ้ำกับร้านชื่ออะไร" ซึ่งเป็นข้อมูลที่ต้องใช้ตัดสินใจว่าจะรื้อ
    name UNIQUE ไหม (ถ้ารอ exception จะได้แค่ชื่อ constraint)
    """
    pid = data.get("place_id")
    if not pid:
        return "error", {"reason": "API ไม่คืน place_id"}

    owner = (await session.execute(
        text("SELECT id, name FROM places WHERE google_place_id = :pid AND id <> :id"),
        {"pid": pid, "id": target["id"]},
    )).fetchone()
    if owner:
        return "dup", {"other_id": owner.id, "other_name": owner.name, "place_id": pid}

    try:
        await session.execute(_UPDATE_SQL, {
            "pid": pid,
            "types": data.get("types"),
            "addr": data.get("formatted_address"),
            "rating": data.get("rating"),
            "total": data.get("user_ratings_total"),
            "id": target["id"],
        })
        await session.commit()
    except IntegrityError as e:
        # กันเหนียว — ไม่ควรถึงตรงนี้เพราะเช็คข้างบนแล้ว
        await session.rollback()
        return "error", {"reason": f"IntegrityError: {str(e)[:120]}"}

    return "ok", {}


# ---------------------------------------------------------------------------
# ตารางจุดตรวจ 4 ข้อ (อ่านอย่างเดียว ไม่ยิง API รันซ้ำได้ตลอด)
# ---------------------------------------------------------------------------

async def report(session) -> None:
    r = (await session.execute(text("""
        SELECT
            count(*)                                            AS total,
            count(google_place_id)                              AS matched,
            count(*) - count(google_place_id)                   AS missing,
            count(formatted_address)                            AS has_addr,
            count(google_rating)                                AS has_rating,
            count(google_reviews_total)                          AS has_total,
            count(google_types)                                 AS has_types
        FROM places
    """))).fetchone()

    p("=" * 68)
    p("  จุดตรวจ backfill — ตารางนี้ตัดสินใจ 2 เรื่องที่ค้างอยู่")
    p("=" * 68)
    pct = f"  ({r.matched / r.total * 100:.0f}%)" if r.total else ""
    p(f"\n[1] จับคู่ได้ / ไม่พบ")
    p(f"    ร้านทั้งหมด            {r.total}")
    p(f"    มี google_place_id     {r.matched}{pct}")
    p(f"    ยังไม่มี               {r.missing}")
    p(f"    มีที่อยู่ {r.has_addr} | เรตติ้ง {r.has_rating} | "
      f"จำนวนรีวิว {r.has_total} | types {r.has_types}")
    if r.missing and r.matched:
        p(f"    → ถ้า 'ไม่พบ' เยอะ = ชื่อใน DB เพี้ยนจากของจริงบน Google")

    # [2] place_id ซ้ำ — UNIQUE index กันไม่ให้เกิดในตารางแล้ว ตัวที่ต้องดูคือ
    #     ร้านที่ backfill ตกไปเพราะซ้ำ (สคริปต์รายงานตอนรัน) + ชื่อที่คล้ายกันมาก
    p(f"\n[2] ร้านซ้ำใน DB")
    dup = (await session.execute(text("""
        SELECT google_place_id, count(*) c, string_agg(name, ' | ') names
        FROM places WHERE google_place_id IS NOT NULL
        GROUP BY google_place_id HAVING count(*) > 1
    """))).fetchall()
    if dup:
        p(f"    ⚠️ พบ place_id ซ้ำ {len(dup)} กลุ่ม (ไม่ควรเกิดได้ — UNIQUE index หลุด?)")
        for x in dup:
            p(f"      {x.google_place_id}  x{x.c}  {x.names[:80]}")
    else:
        p(f"    ไม่มี place_id ซ้ำในตาราง (UNIQUE index ทำงาน)")
    p(f"    → จำนวนร้านที่ backfill ข้ามเพราะซ้ำ ดูที่สรุปตอนรัน (บรรทัด 'ซ้ำ')")

    # [3] พิกัดคลาดเคลื่อน — ต้องดึงพิกัด API มาเทียบ ซึ่งเราไม่ได้เก็บ (ไม่ทับ location)
    #     จึงรายงานได้เฉพาะตอนรันจริง — ตรงนี้บอกวิธีอ่านผลแทน
    p(f"\n[3] พิกัดที่ API ให้ ห่างจากที่เราเก็บไว้")
    p(f"    ไม่เก็บลง DB (ไม่ทับคอลัมน์ location) → ดูที่สรุปตอนรัน")
    p(f"    → ถ้าเกิน {COORD_DRIFT_WARN_M} ม. เยอะ = locationbias หลวมเกิน จับผิดร้าน")

    # [4] yield — อัตราการเก็บรีวิวได้จริง ใช้ตั้งเกณฑ์คัดในขั้นถัดไป
    p(f"\n[4] ความครบถ้วนของการเก็บรีวิว (เก็บได้ / ที่ Google มี)")
    y = (await session.execute(text("""
        SELECT p.id, p.name, p.google_reviews_total AS g,
               (SELECT count(*) FROM reviews rv WHERE rv.place_id = p.id) AS scraped
        FROM places p
        WHERE p.google_reviews_total IS NOT NULL AND p.google_reviews_total > 0
    """))).fetchall()
    if not y:
        p(f"    ยังไม่มีข้อมูล — รัน --limit หรือ --all ก่อน")
    else:
        ratios = sorted(min(x.scraped / x.g, 1.0) for x in y)
        n = len(ratios)
        med = ratios[n // 2]
        tot_g = sum(x.g for x in y)
        tot_s = sum(min(x.scraped, x.g) for x in y)
        p(f"    ร้านที่วัดได้           {n}")
        p(f"    รวม: เก็บได้ {tot_s:,} / Google มี {tot_g:,} = {tot_s / tot_g * 100:.1f}%")
        p(f"    มัธยฐานรายร้าน         {med * 100:.1f}%")
        p(f"    ควอร์ไทล์             {ratios[n // 4] * 100:.0f}% / "
          f"{med * 100:.0f}% / {ratios[3 * n // 4] * 100:.0f}%")
        p(f"\n    → เกณฑ์คัดร้านใหม่: ถ้าอยากได้ ~10 รีวิวที่ใช้งานได้จริง")
        if med > 0:
            p(f"      ต้องตั้ง user_ratings_total ขั้นต่ำ ≈ {int(10 / med)} "
              f"(10 ÷ {med:.2f})")
        p(f"      ตัวเลขนี้คือคำตอบของเรื่องที่เลื่อนไว้ ไม่ใช่การเดา")
    p("\n" + "=" * 68)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

async def run(limit, include_done, do_run, do_report, max_requests, ids=None):
    async with AsyncSessionLocal() as session:
        if do_report:
            await report(session)
            return

        targets = await load_targets(session, limit, include_done, ids)
        n = len(targets)

        if not do_run:
            # DRY-RUN — ไม่ยิง API เลย
            p(f"📊 ร้านที่ยังไม่มี google_place_id: {n} แห่ง")
            p(f"   ประเมินคำขอ: {n}–{n * 2} ครั้ง "
              f"(1 ครั้ง/ร้านถ้า Find Place รับ fields เต็ม, 2 ครั้งถ้าไม่รับ)")
            p(f"   ประเมินค่าใช้จ่าย: ~${n * COST_PER_REQUEST_USD:.2f}"
              f"–${n * 2 * COST_PER_REQUEST_USD:.2f}")
            p(f"   ⚠️ ราคาเป็นการประเมินคร่าว ๆ — ยืนยันที่หน้า pricing ใน "
              f"Google Cloud Console ก่อน")
            p(f"\n   ทดสอบก่อน:  uv run python scripts/backfill_place_id.py --limit 5")
            p(f"   ยิงเต็ม:    uv run python scripts/backfill_place_id.py --all")
            p(f"   ดูจุดตรวจ:  uv run python scripts/backfill_place_id.py --report")
            return

        if n == 0:
            p("✅ ทุกร้านมี google_place_id แล้ว (ใช้ --force เพื่อยิงซ้ำ)")
            return

        try:
            places_api.require_api_key()
        except PlacesApiError as e:
            p(f"❌ {e}")
            return

        p(f"เริ่ม backfill: {n} ร้าน"
          + (f" | เพดานคำขอ {max_requests}" if max_requests else ""))
        p("")

        ok = dup = notfound = errors = 0
        drifted: list[tuple[float, str]] = []
        paths: dict[str, int] = {}
        hit_cap = False

        for i, t in enumerate(targets):
            # `is not None` ไม่ใช่ truthy-check เพราะ --max-requests 0 ต้องหมายถึง
            # "ไม่ยิงเลย" (ใช้ทดสอบว่าเพดานทำงาน โดยไม่เสียเงินและไม่เขียน DB)
            # ไม่ใช่ "ไม่จำกัด" ซึ่งเป็นสิ่งที่ `if max_requests` จะให้ผล
            if max_requests is not None and places_api.request_count >= max_requests:
                p(f"\n⛔ ชนเพดานคำขอ {max_requests} — หยุดที่ร้านที่ {i + 1}/{n}")
                hit_cap = True
                break

            tag = "  [ค้นด้วย name]" if t.get("used_name") else ""
            p(f"[{i + 1}/{n}] {t['name'][:50]}{tag}")
            try:
                data = lookup_place(t["query"], t["lat"], t["lng"])
            except PlacesApiError as e:
                p(f"  ❌ {e}")
                errors += 1
                time.sleep(REQUEST_DELAY_SEC)
                continue

            paths[data.get("_path", "?")] = paths.get(data.get("_path", "?"), 0) + 1

            if data["_status"] != "OK":
                p(f"  ⚠️  ไม่พบ ({data['_status']})")
                notfound += 1
                time.sleep(REQUEST_DELAY_SEC)
                continue

            result, info = await apply_one(session, t, data)
            if result == "dup":
                p(f"  ⚠️  place_id ซ้ำกับ: {info['other_name'][:40]} "
                  f"(id={info['other_id']}) — ข้ามไว้ ไม่เขียนทับ")
                dup += 1
            elif result == "error":
                p(f"  ❌ {info['reason']}")
                errors += 1
            else:
                ok += 1
                bits = [f"⭐{data['rating']}" if data.get("rating") else "",
                        f"{data['user_ratings_total']:,} รีวิว"
                        if data.get("user_ratings_total") else "",
                        (data.get("types") or "").split(",")[0]]
                p(f"  ✅ {' · '.join(b for b in bits if b)}")

                # ตรวจพิกัดคลาดเคลื่อน (รายงานเท่านั้น ไม่แก้ location)
                if (t["lat"] is not None and data.get("lat") is not None):
                    d_m = _haversine_km(t["lat"], t["lng"],
                                        data["lat"], data["lng"]) * 1000
                    if d_m > COORD_DRIFT_WARN_M:
                        drifted.append((d_m, t["name"]))
                        p(f"     ⚠️ พิกัดห่างจากที่เก็บไว้ {d_m:,.0f} ม.")

            time.sleep(REQUEST_DELAY_SEC)

        # ── สรุป ──
        done = ok + dup + notfound + errors
        p("\n" + "=" * 60)
        p(f"✅ เติมสำเร็จ         {ok}")
        p(f"⚠️  place_id ซ้ำ      {dup}   ← ข้อ [2] ของจุดตรวจ")
        p(f"⚠️  ไม่พบบน Google    {notfound}")
        p(f"❌ ผิดพลาด           {errors}")
        p(f"   ทำไปทั้งหมด        {done}/{n}" + ("  (ชนเพดาน)" if hit_cap else ""))
        p(f"\n📡 คำขอที่ยิงจริง     {places_api.request_count}")
        p(f"   เส้นทางที่ใช้       "
          + ", ".join(f"{k}={v}" for k, v in paths.items()))
        if places_api._find_supports_full is True:
            p(f"   → Find Place รับ fields ชุดเต็มได้ = 1 คำขอ/ร้าน (ถูกที่สุด)")
        elif places_api._find_supports_full is False:
            p(f"   → Find Place ไม่รับ fields ชุดเต็ม = ต้องใช้ 2 คำขอ/ร้าน")
        p(f"💰 ประเมินค่าใช้จ่าย   "
          f"~${places_api.request_count * COST_PER_REQUEST_USD:.2f} "
          f"(ยืนยันยอดจริงที่ Billing > Reports)")

        if drifted:
            p(f"\n⚠️  พิกัดห่างเกิน {COORD_DRIFT_WARN_M} ม.: {len(drifted)} ร้าน "
              f"← ข้อ [3] ของจุดตรวจ")
            for d_m, name in sorted(drifted, reverse=True)[:10]:
                p(f"      {d_m:>8,.0f} ม.  {name[:45]}")
            p(f"    → ตรวจรายตัวก่อนเชื่อ อาจเป็นการจับผิดร้าน")

        p("\nดูจุดตรวจครบทั้ง 4 ข้อ:")
        p("  uv run python scripts/backfill_place_id.py --report")
        p("=" * 60)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="เติม google_place_id + ฟิลด์จาก Places API ให้ร้านที่มีอยู่แล้ว")
    ap.add_argument("--limit", type=int, default=None,
                    help="จำกัดจำนวนร้าน (ยิงจริง) — ใช้ทดสอบ เช่น --limit 5")
    ap.add_argument("--all", action="store_true", dest="run_all",
                    help="ยิงทุกร้านที่ยังไม่มี google_place_id")
    ap.add_argument("--force", action="store_true",
                    help="รวมร้านที่มี place_id แล้วด้วย (ใช้คู่ --all)")
    ap.add_argument("--report", action="store_true",
                    help="แสดงตารางจุดตรวจ 4 ข้อ (อ่านอย่างเดียว ไม่ยิง API)")
    ap.add_argument("--ids", type=int, nargs="+", default=None, metavar="ID",
                    help="ยิงเฉพาะแถวตาม id (เขียนทับ place_id เดิมได้ "
                         "ใช้ตอนรู้ว่าเดิมชี้ผิดร้าน)")
    ap.add_argument("--max-requests", type=int, default=None,
                    help="เพดานแข็ง: หยุดเมื่อยิงครบ N คำขอ")
    args = ap.parse_args()

    # do_run = มี --limit หรือ --all เท่านั้น (ไม่งั้น dry-run นับเฉย ๆ)
    do_run = bool(args.limit) or args.run_all
    asyncio.run(run(ids=args.ids, limit=args.limit,
                    include_done=args.force, do_run=do_run,
                    do_report=args.report, max_requests=args.max_requests))
