"""
discover_api.py — ค้นหาร้านที่ยังไม่มีในระบบ ด้วย Google Places Nearby Search

ต่างจาก scripts/discover_by_zone.py (ของเดิม ที่ยังใช้ได้อยู่ ไม่ถูกแก้):
  ของเดิม  ค้นด้วยคำค้นภาษาไทยผ่าน Playwright -> บอกไม่ได้ว่าครบหรือยัง ทำซ้ำไม่ได้
  ตัวนี้   ค้นด้วย type + จุดศูนย์กลาง + รัศมี ผ่าน API -> ทำซ้ำได้ บอกขอบเขตได้ชัด

ผลลง **ตารางพัก place_candidates** ไม่ไหลเข้า places ตรง ๆ
(เหตุผล 3 ข้ออยู่ใน migration 013 — สรุป: รันซ้ำไม่เสียเงินซ้ำ, มีด่านให้คนดู,
 และวัดปัญหาชื่อซ้ำได้ก่อนเสี่ยง)

⚠️ "รัศมีค้นหา" ไม่ใช่ "รัศมีโซน" — ตัวนี้ไม่แตะนิยามโซนเลย
   รัศมีโซน  2.0 กม.  ใช้ใน assign_zone() -> ตรึงไว้ ทุกหน้าที่แยกตามโซนไม่เปลี่ยน
   รัศมีค้นหา 4.0 กม.  พารามิเตอร์ของสคริปต์นี้เท่านั้น ไม่มีใครอื่นอ่าน
   ร้านที่เจอในระยะ 2-4 กม. จะได้ zone='other' ตามกฎเดิมอย่างถูกต้อง
   ประโยชน์คือได้ "ตารางวงแหวน" ที่บอกว่าควรขยายรัศมีโซนไหม โดยยังไม่ต้องขยาย

รัน:
  uv run python scripts/discover_api.py                     # DRY-RUN: นับเซลล์ + ประเมินราคา (ไม่ยิง API)
  uv run python scripts/discover_api.py --report            # อ่านอย่างเดียว: สรุปผลที่เก็บมาแล้ว
  uv run python scripts/discover_api.py --run --max-requests 40   # ยิงจริงแบบจำกัด (แนะนำครั้งแรก)
  uv run python scripts/discover_api.py --run --types cafe        # เฉพาะ type เดียว (คุมงบ)
  uv run python scripts/discover_api.py --run --zones rajabhat    # เฉพาะโซนเดียว
  uv run python scripts/discover_api.py --run                     # ยิงทุกเซลล์ที่ยังไม่เคยทำ

resume ได้: เซลล์+type ที่ทำแล้วถูกบันทึกใน discover_cells รอบถัดไปข้ามให้เอง
→ ถ้าพังกลางทางหรือชนเพดาน รันซ้ำได้โดยไม่จ่ายค่าเซลล์เดิมอีก
"""
import argparse
import asyncio
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from scraper import places_api
from scraper.grid import cell_key, hex_cells, union_cells
from scraper.places_api import (COST_PER_REQUEST_USD, NEARBY_CAP, PlacesApiError,
                                nearby_search)
from scraper.scraper_core import is_in_phitsanulok
from scraper.zones import ZONES, _haversine_km, assign_zone

# type ที่ใช้ค้น — ที่มาและเหตุผลรายตัวอยู่ใน GUIDE.md section "การจัดหมวดสถานที่"
# ⚠️ ค่าใช้จ่าย = จำนวนเซลล์ × จำนวน type เพิ่ม type 1 ตัว = เพิ่มคำขอเท่าจำนวนเซลล์
#
# ⚠️⚠️ ก่อนเพิ่ม type ใหม่ ต้องเช็คก่อนว่าอยู่ใน **Table 1** ของเอกสาร Google
#   https://developers.google.com/maps/documentation/places/web-service/legacy/supported_types
#   Table 1 = ใช้กรองการค้นหาได้  |  Table 2 = คืนมาได้แต่กรองไม่ได้
#   ถ้าใส่ type จาก Table 2 Google จะ**เพิกเฉยเงียบ ๆ** ไม่มี error ไม่มีคำเตือน
#   แล้วคืนทุก establishment ในรัศมีมาให้ → ข้อมูลนอกเรื่องท่วม + ชนเพดาน 60 ทุกเซลล์
PLACE_TYPES = [
    "cafe", "restaurant", "bakery", "tourist_attraction",
    "museum", "park", "university",
]

# type ที่ Google **ไม่ยอมให้ใช้กรองการค้นหา** (Table 2) — สคริปต์ปฏิเสธถ้าถูกส่งมา
#
# `place_of_worship` เคยอยู่ใน PLACE_TYPES และเสียเงินไป ~$4.65 เพื่อเก็บโรงแรม 86
# ร้านค้า 57 อู่ซ่อมรถ 32 ปั๊มน้ำมัน 21 ATM 10 — เป็นศาสนสถานจริงแค่ 18 แห่ง
# ผลตรง 1% (43/2,878) เทียบกับ 7 type ที่เหลือซึ่งตรง 100% ทุกตัว
#
# หมายเหตุสำหรับวัดไทย: Table 1 มีแค่ church / hindu_temple / mosque / synagogue
# **ไม่มี buddhist_temple** → Nearby Search หาวัดด้วย type ไม่ได้ในทางโครงสร้าง
# ถ้าต้องการวัดเพิ่มต้องใช้ Text Search (textsearch?query=วัด) ซึ่งเป็น endpoint คนละตัว
UNSEARCHABLE_TYPES = {
    "place_of_worship", "food", "point_of_interest", "establishment",
    "health", "finance", "general_contractor", "geocode", "natural_feature",
    "political", "premise", "room", "route", "street_address", "subpremise",
    "town_square", "intersection", "locality", "post_box", "postal_code",
    "administrative_area_level_1", "administrative_area_level_2",
    "administrative_area_level_3", "sublocality",
}

SEARCH_RADIUS_KM = 4.0     # รัศมีค้นหา (ไม่ใช่รัศมีโซน)
CELL_RADIUS_KM = 1.0       # รัศมีเซลล์ย่อย — เล็กลง = ชนเพดาน 60 น้อยลง แต่แพงขึ้น
REQUEST_DELAY_SEC = 0.2

# ── ตัวเฝ้าระวัง type ที่ถูกเพิกเฉย (กันเหตุการณ์ place_of_worship ซ้ำ) ──
# เก็บตัวอย่างให้ถึงเกณฑ์ก่อนตัดสิน เพราะเซลล์แรก ๆ อาจได้ 0 ผล (อัตราคำนวณไม่ได้)
TYPE_HONOR_MIN_SAMPLE = 20   # ต้องมีผลรวมอย่างน้อยเท่านี้ก่อนตัดสิน
TYPE_HONOR_MIN_RATIO = 0.5   # ต่ำกว่านี้ = Google ไม่เคารพ type → หยุด type นั้น


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


# ---------------------------------------------------------------------------
# เซลล์
# ---------------------------------------------------------------------------

def build_cells(zone_keys: list[str], radius_km: float,
                cell_km: float) -> list[tuple[float, float]]:
    """สร้างเซลล์แบบยูเนียนของทุกโซน แล้วตัดเซลล์ทับซ้อนออก"""
    centers = [(ZONES[z]["center_lat"], ZONES[z]["center_lng"]) for z in zone_keys]
    return union_cells(centers, radius_km, cell_km)


def nearest_zone_info(lat, lng) -> tuple[str | None, float | None]:
    """โซนที่ใกล้สุด + ระยะ (กม.) — คืนได้แม้อยู่นอกรัศมีทุกโซน"""
    if lat is None or lng is None:
        return None, None
    best_k, best_d = None, float("inf")
    for k, z in ZONES.items():
        d = _haversine_km(lat, lng, z["center_lat"], z["center_lng"])
        if d < best_d:
            best_k, best_d = k, d
    return best_k, round(best_d, 3)


# ---------------------------------------------------------------------------
# บันทึกผล
# ---------------------------------------------------------------------------

# ⚠️ ต้อง CAST(:pid AS varchar(64)) ทุกที่ที่ใช้ ไม่ใช่ :pid เปล่า
# เพราะพารามิเตอร์ตัวเดียวถูกใช้ 3 ตำแหน่ง (ค่าที่ INSERT + 2 subquery)
# asyncpg จะ deduce ชนิดไม่ตรงกันแล้วโยน AmbiguousParameterError
# ("inconsistent types deduced for parameter $1: text versus character varying")
_UPSERT_CANDIDATE = text("""
    INSERT INTO place_candidates (
        google_place_id, name, lat, lng, google_types, google_rating,
        google_reviews_total, business_status, vicinity, zone,
        nearest_zone, dist_km, source_type, source_cell, matched_place_id, decision
    ) VALUES (
        CAST(:pid AS varchar(64)), :name, :lat, :lng, :types, :rating,
        :total, :status, :vicinity, :zone,
        :nzone, :dist, :stype, :scell,
        (SELECT id FROM places
          WHERE google_place_id = CAST(:pid AS varchar(64))),
        CASE WHEN EXISTS (SELECT 1 FROM places
                           WHERE google_place_id = CAST(:pid AS varchar(64)))
             THEN 'existing' ELSE 'new' END
    )
    ON CONFLICT (google_place_id) DO UPDATE SET
        -- เจอซ้ำจากเซลล์/type อื่น: อัปเดตค่าที่อาจเปลี่ยน + นับว่าเจอกี่ครั้ง
        -- ไม่ทับ source_type/source_cell/first_seen_at เพราะอยากรู้ว่า "เจอครั้งแรกจากไหน"
        name                 = EXCLUDED.name,
        google_rating        = EXCLUDED.google_rating,
        google_reviews_total = EXCLUDED.google_reviews_total,
        business_status      = EXCLUDED.business_status,
        last_seen_at         = NOW(),
        seen_count           = place_candidates.seen_count + 1
""")

_LOG_CELL = text("""
    INSERT INTO discover_cells (cell_lat, cell_lng, cell_radius_m, place_type,
                                pages, results, hit_cap, status, type_matched)
    VALUES (:lat, :lng, :rm, :type, :pages, :results, :cap, :status, :matched)
    ON CONFLICT (cell_lat, cell_lng, cell_radius_m, place_type) DO UPDATE SET
        pages = EXCLUDED.pages, results = EXCLUDED.results,
        hit_cap = EXCLUDED.hit_cap, status = EXCLUDED.status,
        type_matched = EXCLUDED.type_matched, fetched_at = NOW()
""")


def count_type_matches(items: list[dict], place_type: str) -> int:
    """
    ผลที่ Google คืนมา มี type ที่เราขอในตัวมันเองกี่รายการ

    ใช้จับกรณี Google เพิกเฉยพารามิเตอร์ type (type จาก Table 2) ซึ่งไม่มี error
    บอก — สังเกตได้ทางเดียวคือดูว่าของที่ได้มาเป็นประเภทที่ขอจริงไหม
    """
    return sum(1 for it in items
               if place_type in (it.get("types") or "").split(","))


async def done_cells(session, radius_m: int) -> set[tuple[float, float, str]]:
    """เซลล์+type ที่ยิงสำเร็จแล้ว (ใช้ resume — ไม่จ่ายเงินซ้ำ)"""
    rows = (await session.execute(text("""
        SELECT cell_lat, cell_lng, place_type FROM discover_cells
        WHERE cell_radius_m = :rm AND status IN ('OK', 'ZERO_RESULTS')
    """), {"rm": radius_m})).fetchall()
    return {(round(r.cell_lat, 6), round(r.cell_lng, 6), r.place_type) for r in rows}


async def save_results(session, items: list[dict], stype: str, ckey: str) -> int:
    """เขียนผลลงตารางพัก คืนจำนวนที่อยู่ในพิษณุโลก (ที่เก็บจริง)"""
    kept = 0
    for it in items:
        if not it.get("place_id"):
            continue
        # ใช้ bbox ตัวเดียวกับ save_to_db — กันร้านนอกจังหวัดหลุดเข้ามา
        if not is_in_phitsanulok(it.get("lat"), it.get("lng")):
            continue
        nz, dist = nearest_zone_info(it.get("lat"), it.get("lng"))
        await session.execute(_UPSERT_CANDIDATE, {
            "pid": it["place_id"], "name": it.get("name") or "(ไม่มีชื่อ)",
            "lat": it.get("lat"), "lng": it.get("lng"),
            "types": it.get("types"), "rating": it.get("rating"),
            "total": it.get("user_ratings_total"),
            "status": it.get("business_status"), "vicinity": it.get("vicinity"),
            "zone": assign_zone(it.get("lat"), it.get("lng")),
            "nzone": nz, "dist": dist, "stype": stype, "scell": ckey,
        })
        kept += 1
    return kept


# ---------------------------------------------------------------------------
# รายงาน
# ---------------------------------------------------------------------------

async def verify_types(session) -> None:
    """
    ตรวจย้อนหลังว่า Google เคารพพารามิเตอร์ type ของแต่ละ type ไหม (ไม่ยิง API)

    อ่านจาก discover_cells.type_matched — ถ้า % ต่ำ = type นั้นอยู่ใน Table 2
    Google เพิกเฉยแล้วคืนทุกอย่างในรัศมี ผลที่เก็บมาจึงเป็นของนอกเรื่อง
    """
    p("=" * 72)
    p("  Google เคารพพารามิเตอร์ type ไหม")
    p("  (ผลที่คืนมา มี type ที่เราขอในตัวมันเองกี่ %)")
    p("=" * 72)
    # ⚠️ ตัวส่วนต้องเป็น "ผลจากเซลล์ที่ตรวจแล้ว" เท่านั้น
    # ถ้าใช้ sum(results) ทั้งหมด แถวเก่าที่ type_matched เป็น NULL จะถูกนับเป็น
    # ตัวส่วนโดยมีตัวเศษ 0 → ทุก type จะถูก flag ว่าเป็นของนอกเรื่องทั้งหมด (ผิด)
    # กฎเดียวกับ Rule 1 ของโปรเจกต์: ตัวเศษกับตัวส่วนต้องผ่านตัวกรองชุดเดียวกัน
    rows = (await session.execute(text("""
        SELECT place_type, count(*) cells,
               coalesce(sum(results),0) res,
               coalesce(sum(results) FILTER (WHERE type_matched IS NOT NULL),0)
                   AS checked_res,
               coalesce(sum(type_matched),0) matched,
               count(*) FILTER (WHERE type_matched IS NULL) unchecked,
               count(*) FILTER (WHERE hit_cap) capped
        FROM discover_cells GROUP BY 1 ORDER BY 2 DESC
    """))).fetchall()
    if not rows:
        p("\n  ยังไม่มีข้อมูล — รัน --run ก่อน")
        return

    p(f"\n  {'type':<20}{'เซลล์':>6}{'ผล':>7}{'ตรวจแล้ว':>9}{'%ตรง':>7}"
      f"{'ชนเพดาน':>9}  สรุป")
    bad = []
    for x in rows:
        # Table 2 ตัดสินได้จากเอกสาร ไม่ต้องรอข้อมูล
        if x.place_type in UNSEARCHABLE_TYPES:
            verdict, pct = "⛔ Table 2 — ใช้กรองไม่ได้", "-"
            bad.append(x)
        elif not x.checked_res:
            verdict, pct = ("ยิงก่อนมีการตรวจ — ตัดสินไม่ได้"
                            if x.unchecked else "ไม่มีผล ตัดสินไม่ได้"), "-"
        else:
            ratio = x.matched / x.checked_res
            pct = f"{ratio * 100:.0f}%"
            if ratio >= 0.9:
                verdict = "✅ เชื่อผลได้"
            elif ratio >= TYPE_HONOR_MIN_RATIO:
                verdict = "⚠️ ตรวจรายตัวก่อนใช้"
            else:
                verdict = "⛔ น่าจะถูกเพิกเฉย — เช็ค Table 1/2"
                bad.append(x)
        p(f"  {x.place_type:<20}{x.cells:>6}{x.res:>7}{x.checked_res:>9}{pct:>7}"
          f"{x.capped:>9}  {verdict}")
    if bad:
        p(f"\n  ⚠️ ข้อมูลจาก type ข้างล่างนี้เป็นของนอกเรื่อง ไม่ควรนับรวมในผลวิเคราะห์:")
        for x in bad:
            n = (await session.execute(text("""
                SELECT count(*) FROM place_candidates
                WHERE source_type = :t AND decision = 'new'
            """), {"t": x.place_type})).scalar()
            p(f"     {x.place_type:<20} มีร้านในตารางพัก {n} ร้านที่มาจาก type นี้")
        p(f"\n     กรองออกด้วย:  WHERE source_type NOT IN (...)")
        p(f"     หรือติดธง:    UPDATE place_candidates SET decision='reject' ...")
    p("\n" + "=" * 72)


async def report(session) -> None:
    tot = (await session.execute(text("""
        SELECT count(*) n,
               count(*) FILTER (WHERE decision = 'new')      AS new_,
               count(*) FILTER (WHERE decision = 'existing') AS existing_
        FROM place_candidates"""))).fetchone()

    cells = (await session.execute(text("""
        SELECT count(*) n, coalesce(sum(pages),0) pages,
               coalesce(sum(results),0) results,
               count(*) FILTER (WHERE hit_cap) AS capped
        FROM discover_cells"""))).fetchone()

    p("=" * 72)
    p("  ผล discover ที่เก็บมาแล้ว")
    p("=" * 72)
    p(f"\n[1] ต้นทุนที่ใช้ไป")
    p(f"    เซลล์+type ที่ยิงแล้ว   {cells.n:,}")
    p(f"    คำขอที่ยิงจริง          {cells.pages:,}  (~${cells.pages * COST_PER_REQUEST_USD:.2f})")
    p(f"    ผลลัพธ์ที่ได้มา         {cells.results:,} รายการ (รวมซ้ำ)")
    if cells.capped:
        p(f"    ⚠️ เซลล์ที่ชนเพดาน {NEARBY_CAP} ผล: {cells.capped} เซลล์"
          f" — ข้อมูลตรงนั้น**ขาด** ต้องซอยเซลล์ย่อย (--cell-radius 0.5)")
        rows = (await session.execute(text("""
            SELECT cell_lat, cell_lng, place_type, results FROM discover_cells
            WHERE hit_cap ORDER BY place_type LIMIT 12"""))).fetchall()
        for r in rows:
            p(f"       {r.cell_lat:.4f},{r.cell_lng:.4f}  {r.place_type:<20} {r.results}")
    else:
        p(f"    ✅ ไม่มีเซลล์ไหนชนเพดาน {NEARBY_CAP} — เชื่อได้ว่าค้นครบในเซลล์ที่ทำแล้ว")

    if not tot.n:
        p(f"\n    ยังไม่มีผลในตารางพัก — รันด้วย --run ก่อน")
        p("\n" + "=" * 72)
        return

    p(f"\n[2] ร้านที่เจอ")
    p(f"    ทั้งหมด (ไม่ซ้ำ)        {tot.n:,}")
    p(f"    มีใน places แล้ว        {tot.existing_:,}")
    p(f"    ⭐ ร้านใหม่              {tot.new_:,}")

    p(f"\n[3] ตารางวงแหวน — ร้านใหม่อยู่ห่างจากศูนย์โซนเท่าไร")
    p(f"    (ตารางนี้ตอบว่าควรขยายรัศมีโซนจาก 2 กม. ไหม)")
    rings = (await session.execute(text("""
        SELECT nearest_zone z,
               width_bucket(dist_km, 0, 4, 4) b,
               count(*) FILTER (WHERE decision = 'new')      AS new_,
               count(*) FILTER (WHERE decision = 'existing') AS old_,
               coalesce(sum(google_reviews_total) FILTER (WHERE decision='new'),0) rv
        FROM place_candidates
        WHERE dist_km IS NOT NULL
        GROUP BY 1, 2 ORDER BY 1, 2"""))).fetchall()
    p(f"\n    {'โซน':<13}{'วงแหวน':<11}{'ร้านใหม่':>9}{'มีแล้ว':>8}"
      f"{'รีวิว(Google)':>15}  สถานะ")
    for r in rings:
        lo = (r.b - 1) if r.b and r.b <= 4 else 4
        lab = f"{lo}-{lo + 1} km" if r.b and r.b <= 4 else "> 4 km"
        tag = "อยู่ในโซน" if lo < 2 else "นอกโซน (other)"
        p(f"    {(r.z or '-'):<13}{lab:<11}{r.new_:>9}{r.old_:>8}{r.rv:>15,}  {tag}")

    p(f"\n[4] ร้านใหม่แยกตาม type ที่ค้นเจอ")
    # ⚠️ ห้ามตั้ง alias ว่า "t" — SQLAlchemy 2.0 มี Row.t เป็น tuple accessor ของตัวเอง
    # ชื่อคอลัมน์จะถูกทับเงียบ ๆ แล้ว r.t คืน Row ไม่ใช่ค่าในคอลัมน์
    # (พลาดมาแล้ว: TypeError: unsupported format string passed to Row.__format__)
    # ชื่ออื่นที่ห้ามใช้ด้วยเหตุเดียวกัน: count, index, tuple
    by = (await session.execute(text("""
        SELECT source_type ptype, count(*) n,
               coalesce(sum(google_reviews_total),0) rv,
               count(*) FILTER (WHERE google_reviews_total >= 13) AS worth
        FROM place_candidates WHERE decision = 'new'
        GROUP BY 1 ORDER BY n DESC"""))).fetchall()
    p(f"    {'type':<22}{'ร้านใหม่':>9}{'รีวิว(Google)':>15}{'ผ่านเกณฑ์ >=13':>16}")
    for r in by:
        p(f"    {(r.ptype or '-'):<22}{r.n:>9}{r.rv:>15,}{r.worth:>16}")

    p(f"\n[5] ร้านใหม่ที่คุ้มเอาไป scrape (เรียงตามจำนวนรีวิวที่ Google มี)")
    top = (await session.execute(text("""
        SELECT name, zone, google_reviews_total total, google_rating rating,
               dist_km, source_type
        FROM place_candidates
        WHERE decision = 'new' AND google_reviews_total IS NOT NULL
        ORDER BY google_reviews_total DESC LIMIT 25"""))).fetchall()
    p(f"    {'รีวิว':>7}{'ดาว':>5}{'ห่าง':>7}  {'โซน':<12}{'type':<18} ชื่อ")
    for r in top:
        stars = float(r.rating) if r.rating is not None else 0.0
        dist = float(r.dist_km) if r.dist_km is not None else 0.0
        p(f"    {r.total:>7,}{stars:>5.1f}{dist:>6.1f}k  "
          f"{(r.zone or '-'):<12}{(r.source_type or '-'):<18} {r.name[:30]}")
    p("\n" + "=" * 72)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

async def subdivide_jobs(session, types: list[str]) -> list[tuple]:
    """
    งานสำหรับโหมด --subdivide-capped

    อ่านเซลล์ที่ hit_cap = true แล้วสร้างเซลล์ย่อยรัศมี "ครึ่งหนึ่งของเซลล์แม่"
    มาปูคลุมเซลล์แม่ให้ครบ — คืน [(cell, type, radius_m), ...]

    ทำเฉพาะคู่ (เซลล์, type) ที่ชนเพดานจริง ไม่ใช่ทุกเซลล์ × ทุก type
    เพราะเซลล์ที่ได้ 3 ผลไม่มีเหตุให้ซอย และเซลล์ที่ชนเพดานเฉพาะ restaurant
    ก็ไม่ต้องซอยให้ museum ด้วย — ต่างกัน 7 เท่าในค่าใช้จ่าย

    ข้าม type ที่ Google ไม่เคารพ (type_matched ต่ำ) เพราะซอยแล้วจะยิ่งได้
    ของนอกเรื่องเพิ่ม ไม่ได้ของที่ต้องการ

    รองรับการซอยหลายชั้น: เซลล์ย่อยที่ชนเพดานอีกจะถูกซอยต่อในการรันครั้งถัดไป
    (แต่ละแถวจำ cell_radius_m ของตัวเอง จึงหารสองจากค่าจริงไม่ใช่ค่าคงที่)
    """
    rows = (await session.execute(text("""
        SELECT cell_lat, cell_lng, cell_radius_m, place_type, results, type_matched
        FROM discover_cells
        WHERE hit_cap AND cell_radius_m > 100
        ORDER BY place_type, cell_lat, cell_lng
    """))).fetchall()

    jobs: list[tuple] = []
    groups: dict[tuple[str, int], list[tuple[float, float]]] = {}
    skipped_unsearchable: dict[str, int] = {}
    skipped_ignored: dict[str, int] = {}

    for r in rows:
        if types and r.place_type not in types:
            continue
        if r.place_type in UNSEARCHABLE_TYPES:
            skipped_unsearchable[r.place_type] = \
                skipped_unsearchable.get(r.place_type, 0) + 1
            continue
        # type_matched เป็น NULL = ยิงก่อนมีการตรวจ (ไม่ตัดออก)
        # 0 หรือน้อยมาก = Google เพิกเฉย → ซอยไปก็ได้ของนอกเรื่องเพิ่ม
        if (r.type_matched is not None and r.results
                and r.type_matched / r.results < TYPE_HONOR_MIN_RATIO):
            skipped_ignored[r.place_type] = skipped_ignored.get(r.place_type, 0) + 1
            continue

        groups.setdefault((r.place_type, r.cell_radius_m), []).append(
            (r.cell_lat, r.cell_lng))

    # ⚠️ ปูแลตทิซ "อันเดียวต่อกลุ่ม" ไม่ใช่ทีละเซลล์แม่
    # เซลล์ที่ชนเพดานมักอยู่ติดกัน (ย่านหนาแน่นเป็นผืน) ถ้าปูแลตทิซแยกทีละเซลล์แม่
    # เซลล์ย่อยจากคนละแลตทิซจะเยื้องกันจนทับซ้อนแต่ตัดซ้ำไม่ได้ — บั๊กเดียวกับที่
    # เคยเจอตอนปูเซลล์ข้ามโซน (วัดแล้ว: 375 เซลล์ -> ~150 เซลล์ เมื่อปูแลตทิซเดียว)
    # ⚠️ ต้องกันงานที่ทำไปแล้วออก ไม่งั้นโหมดนี้ **ไม่ idempotent**
    # เซลล์แม่ 1000 ม. ยังมี hit_cap = true อยู่ตลอด (เป็นบันทึกประวัติ ไม่ได้ลบ)
    # ถ้าไม่กรอง การรันซ้ำจะสร้างเซลล์ลูก 500 ม. ชุดเดิมแล้วยิงใหม่ = จ่ายซ้ำฟรี
    # กรองแล้วการรันซ้ำจะ "ขุดลึกลงอีกชั้น" เฉพาะที่ยังชนเพดาน ซึ่งเป็นพฤติกรรมที่ต้องการ
    done = {(round(r.cell_lat, 6), round(r.cell_lng, 6),
             r.cell_radius_m, r.place_type)
            for r in (await session.execute(text("""
                SELECT cell_lat, cell_lng, cell_radius_m, place_type
                FROM discover_cells WHERE status IN ('OK', 'ZERO_RESULTS')
            """))).fetchall()}

    skipped_done = 0
    for (ptype, parent_m), centers in groups.items():
        parent_km = parent_m / 1000
        child_km = parent_km / 2
        child_m = int(parent_m // 2)
        for c in union_cells(centers, parent_km, child_km):
            if (round(c[0], 6), round(c[1], 6), child_m, ptype) in done:
                skipped_done += 1
                continue
            jobs.append((c, ptype, child_m))

    if skipped_done:
        p(f"  ข้ามเซลล์ย่อยที่ยิงไปแล้วในรอบก่อน: {skipped_done} งาน "
          f"(ประหยัด ~${skipped_done * 1.5 * COST_PER_REQUEST_USD:.2f})")

    for label, d in [("อยู่ใน Table 2 ค้นหาไม่ได้", skipped_unsearchable),
                     ("Google เพิกเฉย type (วัดจาก type_matched)", skipped_ignored)]:
        if d:
            p(f"  ข้ามเซลล์ของ type ที่{label}:")
            for t, n in sorted(d.items(), key=lambda kv: -kv[1]):
                p(f"    {t:<22}{n:>4} เซลล์  (ประหยัด ~${n * 7 * 2 * COST_PER_REQUEST_USD:.2f})")

    # กันงานซ้ำ: เซลล์ย่อยจากเซลล์แม่ที่ติดกันอาจทับกันได้
    seen = set()
    uniq = []
    for c, t, rm in jobs:
        k = (round(c[0], 6), round(c[1], 6), t, rm)
        if k in seen:
            continue
        seen.add(k)
        uniq.append((c, t, rm))
    return uniq


async def run(args):
    zone_keys = args.zones or list(ZONES.keys())
    types = args.types or PLACE_TYPES
    radius_m = int(args.cell_radius * 1000)

    bad = [z for z in zone_keys if z not in ZONES]
    if bad:
        p(f"❌ โซนไม่ถูกต้อง: {bad} — ใช้ได้: {', '.join(ZONES)}")
        return

    # ปฏิเสธ type ที่ Google ใช้กรองการค้นหาไม่ได้ ก่อนเสียเงินแม้แต่คำขอเดียว
    # (บทเรียน place_of_worship: ไม่มี error จาก API เลย ต้องกันที่ฝั่งเรา)
    forbidden = [t for t in types if t in UNSEARCHABLE_TYPES]
    if forbidden:
        p(f"❌ type เหล่านี้อยู่ใน Table 2 ของ Google = ใช้กรองการค้นหาไม่ได้:")
        for t in forbidden:
            p(f"     {t}")
        p(f"   ถ้าส่งไป Google จะเพิกเฉยเงียบ ๆ แล้วคืนทุกอย่างในรัศมีมาให้")
        p(f"   (เคยเสียไป ~$4.65 กับ place_of_worship — ได้ศาสนสถานจริง 1%)")
        p(f"   ดู Table 1/Table 2: https://developers.google.com/maps/"
          f"documentation/places/web-service/legacy/supported_types")
        return

    async with AsyncSessionLocal() as session:
        if args.report:
            await report(session)
            return
        if args.verify_types:
            await verify_types(session)
            return

        if args.subdivide_capped:
            p("=" * 68)
            p("  โหมดซอยเซลล์ที่ชนเพดาน — ทำเฉพาะคู่ (เซลล์, type) ที่ข้อมูลขาดจริง")
            p("=" * 68)
            triples = await subdivide_jobs(session, args.types or [])
            if not triples:
                p("\n✅ ไม่มีเซลล์ที่ต้องซอย (หรือถูกข้ามทั้งหมด)")
                return
            by_r: dict[int, int] = {}
            for _, _, rm in triples:
                by_r[rm] = by_r.get(rm, 0) + 1
            p(f"\n  เซลล์ย่อยที่ต้องยิง {len(triples)} งาน")
            for rm, n in sorted(by_r.items(), reverse=True):
                p(f"    รัศมี {rm} ม.  {n} งาน")
            lo, hi = len(triples), len(triples) * 3
            p(f"  คำขอ {lo:,}–{hi:,} ครั้ง ≈ ${lo * COST_PER_REQUEST_USD:.2f}"
              f"–${hi * COST_PER_REQUEST_USD:.2f}")
            if not args.do_run:
                p(f"\n  DRY-RUN — เติม --run เพื่อยิงจริง")
                p("\n" + "=" * 68)
                return
            jobs = [(c, t) for c, t, _ in triples]
            radii = {(round(c[0], 6), round(c[1], 6), t): rm
                     for c, t, rm in triples}
        else:
            cells = build_cells(zone_keys, args.radius, args.cell_radius)
            already = await done_cells(session, radius_m)
            jobs = [(c, t) for c in cells for t in types
                    if (c[0], c[1], t) not in already]
            radii = None

        if not args.do_run:
            per_zone = {z: len(hex_cells(ZONES[z]["center_lat"],
                                         ZONES[z]["center_lng"],
                                         args.radius, args.cell_radius))
                        for z in zone_keys}
            p("=" * 68)
            p("  DRY-RUN — ไม่ยิง API เลย")
            p("=" * 68)
            p(f"\n  รัศมีค้นหา            {args.radius} กม.  (รัศมีโซนยังเป็น 2.0 กม. ไม่ถูกแตะ)")
            p(f"  รัศมีเซลล์            {args.cell_radius} กม.")
            p(f"  โซน                   {', '.join(zone_keys)}")
            p(f"  type                  {len(types)} ตัว: {', '.join(types)}")
            p(f"\n  เซลล์ก่อนรวม (แยกโซน)")
            for z, n in per_zone.items():
                p(f"    {z:<14} {n:>4} เซลล์")
            p(f"    {'รวมดิบ':<14} {sum(per_zone.values()):>4} เซลล์")
            p(f"    {'หลังตัดทับซ้อน':<14} {len(cells):>4} เซลล์"
              f"  (ประหยัด {sum(per_zone.values()) - len(cells)} เซลล์)")
            p(f"\n  งานที่ต้องทำ          {len(jobs):,} (เซลล์ × type)")
            if already:
                p(f"  ทำไปแล้ว (ข้าม)       {len(already):,}")
            lo = len(jobs)
            hi = len(jobs) * 3      # เซลล์ที่มีร้านเยอะยิงได้ถึง 3 หน้า
            p(f"\n  คำขอที่จะยิง          {lo:,} – {hi:,} ครั้ง")
            p(f"    (1 คำขอ = 1 หน้า 20 ผล · เซลล์ที่มีร้านเกิน 20 ต้องยิงหน้าถัดไป)")
            p(f"  ประเมินค่าใช้จ่าย     ~${lo * COST_PER_REQUEST_USD:.2f}"
              f" – ${hi * COST_PER_REQUEST_USD:.2f}")
            p(f"\n  ⚠️ ราคาเป็นการประเมิน — ยืนยันที่หน้า pricing ใน Google Cloud Console")
            p(f"  ⚠️ เครดิต Free Trial หมดอายุ 31 ต.ค. 2026 (ดู GUIDE.md)")
            p(f"\n  แนะนำครั้งแรก — จำกัดวงเงินก่อน:")
            p(f"    uv run python scripts/discover_api.py --run --max-requests 40")
            p(f"  หรือทีละ type เพื่อคุมงบ:")
            p(f"    uv run python scripts/discover_api.py --run --types cafe")
            p("\n" + "=" * 68)
            return

        if not jobs:
            p("✅ ทุกเซลล์×type ทำไปแล้ว — ดูผลด้วย --report")
            return

        try:
            places_api.require_api_key()
        except PlacesApiError as e:
            p(f"❌ {e}")
            return

        cap_note = (f" | เพดานคำขอ {args.max_requests}"
                    if args.max_requests is not None else "")
        if args.subdivide_capped:
            # โหมดนี้ไม่มี `cells` / รัศมีเดียว — งานมาจากเซลล์ที่ชนเพดาน
            # (บั๊กเดิม: แบนเนอร์อ้าง len(cells) ซึ่งตั้งค่าแค่ในเส้นทางปกติ
            #  ทดสอบไว้แต่โหมด DRY-RUN ที่ return ก่อนถึงบรรทัดนี้ จึงไม่เจอ)
            n_cells = len({(round(c[0], 6), round(c[1], 6)) for c, _ in jobs})
            n_types = len({t for _, t in jobs})
            p(f"เริ่มซอยเซลล์: {n_cells} เซลล์ย่อย × {n_types} type "
              f"= {len(jobs):,} งาน{cap_note}")
            p(f"รัศมีเซลล์ย่อย {', '.join(f'{r} ม.' for r in sorted(set(radii.values()), reverse=True))}\n")
        else:
            p(f"เริ่ม discover: {len(cells)} เซลล์ × {len(types)} type "
              f"= {len(jobs):,} งาน{cap_note}")
            p(f"รัศมีค้นหา {args.radius} กม. · เซลล์ {args.cell_radius} กม. "
              f"· โซน {', '.join(zone_keys)}\n")

        found = capped = failed = 0
        hit_cap_run = False

        # เฝ้าระวัง type ที่ Google เพิกเฉย — {type: [ผลรวม, ที่ตรง]}
        honor: dict[str, list[int]] = {}
        abandoned: dict[str, tuple[int, int]] = {}

        for i, (cell, stype) in enumerate(jobs):
            clat, clng = cell
            if (args.max_requests is not None
                    and places_api.request_count >= args.max_requests):
                p(f"\n⛔ ชนเพดานคำขอ {args.max_requests} — หยุดที่งานที่ {i + 1}/{len(jobs)}")
                p(f"   รันคำสั่งเดิมซ้ำได้เลย จะทำต่อจากจุดนี้ (resume ผ่าน discover_cells)")
                hit_cap_run = True
                break

            # type นี้ถูกพิสูจน์แล้วว่า Google เพิกเฉย → ไม่ยิงต่อ ไม่เผาเงิน
            if stype in abandoned:
                continue

            # โหมดซอยเซลล์ใช้รัศมีต่างกันได้ในรอบเดียว (เซลล์แม่ขนาดไม่เท่ากัน)
            cell_rm = (radii.get((round(clat, 6), round(clng, 6), stype), radius_m)
                       if radii else radius_m)
            ckey = cell_key(clat, clng, cell_rm)
            try:
                res = nearby_search(clat, clng, cell_rm, stype)
            except PlacesApiError as e:
                p(f"[{i + 1}/{len(jobs)}] {stype:<18} {ckey}  ❌ {e}")
                failed += 1
                continue

            matched = count_type_matches(res["results"], stype)
            h = honor.setdefault(stype, [0, 0])
            h[0] += len(res["results"])
            h[1] += matched

            kept = 0
            if res["results"]:
                kept = await save_results(session, res["results"], stype, ckey)
            await session.execute(_LOG_CELL, {
                "lat": clat, "lng": clng, "rm": cell_rm, "type": stype,
                "pages": res["pages"], "results": len(res["results"]),
                "cap": res["hit_cap"], "status": res["_status"],
                "matched": matched,
            })
            await session.commit()

            found += kept
            mark = ""
            if res["hit_cap"]:
                capped += 1
                mark = f"  ⚠️ ชนเพดาน {NEARBY_CAP} — ข้อมูลขาด ต้องซอยเซลล์"
            p(f"[{i + 1}/{len(jobs)}] {stype:<18} {ckey}  "
              f"{len(res['results']):>2} ผล ({res['pages']} หน้า) "
              f"เก็บ {kept}{mark}")

            # ตรวจว่า Google เคารพ type นี้ไหม เมื่อเก็บตัวอย่างพอแล้ว
            # ทำหลังยิงไม่ใช่ก่อน เพราะต้องมีผลจริงมาดูก่อนจะรู้ได้
            if (h[0] >= TYPE_HONOR_MIN_SAMPLE
                    and h[1] / h[0] < TYPE_HONOR_MIN_RATIO):
                abandoned[stype] = (h[1], h[0])
                remaining = sum(1 for _, t in jobs[i + 1:] if t == stype)
                p(f"\n  ⛔ หยุด type '{stype}' — Google เพิกเฉยพารามิเตอร์นี้")
                p(f"     ผลที่ได้ {h[0]} รายการ มี type '{stype}' จริงแค่ {h[1]} "
                  f"({h[1] / h[0] * 100:.0f}%)")
                p(f"     แปลว่า Google คืนทุกอย่างในรัศมีมาให้ ไม่ได้กรองตามที่ขอ")
                p(f"     ข้าม {remaining} เซลล์ที่เหลือของ type นี้ "
                  f"(ประหยัด ~${remaining * 1.5 * COST_PER_REQUEST_USD:.2f})")
                p(f"     เช็คว่า '{stype}' อยู่ใน Table 1 หรือ Table 2 ของเอกสาร Google\n")

            time.sleep(REQUEST_DELAY_SEC)

        p("\n" + "=" * 60)
        p(f"📡 คำขอที่ยิงจริง      {places_api.request_count:,}"
          + ("  (ชนเพดาน)" if hit_cap_run else ""))
        p(f"💰 ประเมินค่าใช้จ่าย    "
          f"~${places_api.request_count * COST_PER_REQUEST_USD:.2f} "
          f"(ยืนยันยอดจริงที่ Billing > Reports)")
        p(f"📥 เก็บลงตารางพัก      {found:,} รายการ (รวมที่เจอซ้ำ)")
        if failed:
            p(f"❌ เซลล์ที่พลาด        {failed}")

        if honor:
            p(f"\n🔍 Google เคารพ type ที่ขอไหม (ผลที่ได้มี type นั้นจริงกี่ %)")
            for t, (n, m) in sorted(honor.items(), key=lambda kv: -kv[1][0]):
                if not n:
                    p(f"    {t:<20} ไม่มีผล — ยังตัดสินไม่ได้")
                    continue
                ratio = m / n
                flag = "  ⛔ ถูกเพิกเฉย" if t in abandoned else (
                    "  ✅" if ratio >= 0.9 else "  ⚠️ ตรวจดู")
                p(f"    {t:<20}{m:>6}/{n:<6} = {ratio * 100:>3.0f}%{flag}")
        if abandoned:
            p(f"\n⛔ type ที่หยุดกลางทาง: {', '.join(abandoned)}")
            p(f"   เอาออกจาก PLACE_TYPES และเพิ่มใน UNSEARCHABLE_TYPES ในไฟล์นี้")
        if capped:
            p(f"\n⚠️  เซลล์ที่ชนเพดาน {NEARBY_CAP} ผล: {capped} เซลล์")
            p(f"    ข้อมูลในเซลล์เหล่านั้น**ขาด** ไม่ใช่ครบ")
            p(f"    แก้ด้วยการซอยเซลล์ย่อย: --run --cell-radius 0.5")
            p(f"    (เซลล์ 0.5 กม. เป็นชุดใหม่ จึงไม่ถูกข้ามด้วย resume)")
        p(f"\nดูผลทั้งหมด:")
        p(f"  uv run python scripts/discover_api.py --report")
        p("=" * 60)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="ค้นหาร้านใหม่ด้วย Places Nearby Search ลงตารางพัก place_candidates")
    ap.add_argument("--run", action="store_true", dest="do_run",
                    help="ยิง API จริง (ไม่ใส่ = DRY-RUN นับเซลล์เฉย ๆ)")
    ap.add_argument("--report", action="store_true",
                    help="แสดงผลที่เก็บมาแล้ว (อ่านอย่างเดียว ไม่ยิง API)")
    ap.add_argument("--verify-types", action="store_true",
                    help="ตรวจว่า Google เคารพพารามิเตอร์ type ไหม (อ่านอย่างเดียว)")
    ap.add_argument("--subdivide-capped", action="store_true",
                    help="ซอยเฉพาะเซลล์ที่ชนเพดาน 60 ให้เล็กลงครึ่งหนึ่ง "
                         "(ข้าม type ที่ Google เพิกเฉย) — ใส่ --run เพื่อยิงจริง")
    ap.add_argument("--zones", nargs="+", default=None,
                    help=f"โซนที่ค้น (เว้นว่าง = ทุกโซน): {', '.join(ZONES)}")
    ap.add_argument("--types", nargs="+", default=None,
                    help=f"type ที่ค้น (เว้นว่าง = ทั้ง {len(PLACE_TYPES)} ตัว)")
    ap.add_argument("--radius", type=float, default=SEARCH_RADIUS_KM,
                    help=f"รัศมีค้นหา กม. (ค่าเริ่มต้น {SEARCH_RADIUS_KM}) "
                         f"— ไม่ใช่รัศมีโซน")
    ap.add_argument("--cell-radius", type=float, default=CELL_RADIUS_KM,
                    help=f"รัศมีเซลล์ย่อย กม. (ค่าเริ่มต้น {CELL_RADIUS_KM})")
    ap.add_argument("--max-requests", type=int, default=None,
                    help="เพดานแข็ง: หยุดเมื่อยิงครบ N คำขอ (resume ได้)")
    asyncio.run(run(ap.parse_args()))
