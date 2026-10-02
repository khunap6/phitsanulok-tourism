"""
verify_coords.py — ตรวจพิกัดทุกร้านเทียบกับ Places API และซ่อมที่เพี้ยน

ปัญหาที่ตรวจ (พบ 2026-10-01):
  extract_place_coords() เดิมอ่าน `@lat,lng` จาก URL ซึ่งเป็น**จุดกลางหน้าจอ
  แผนที่** ไม่ใช่พิกัดร้าน พอ Google เปิดหน้าแบบซูมออก จุดกลางหน้าจอห่างจาก
  ร้านได้เป็นร้อยกิโลเมตร

    /maps/place/<ชื่อ>/@16.7494649,97.8843155,8z/data=...!3d16.7494649!4d100.1914444
                       └── จุดกลางหน้าจอ ──┘          └─ พิกัดร้านจริง ─┘

  ละติจูดมักตรง (แผงข้อมูลเบียดแผนที่ในแนวนอน) จึงดูเหมือนพิกัดถูก
  ตรวจด้วยตาเปล่าจับไม่ได้

  ต้นเหตุถูกปิดแล้ว — extract_place_coords() เอา !3d!4d ก่อนเสมอ
  สคริปต์นี้ซ่อมพิกัดที่เก็บผิดไปแล้ว

แหล่งความจริง 2 ทาง เรียงตามต้นทุน:
  1. place_candidates.lat/lng — มาจาก Nearby Search ของ Places API **ฟรี**
     (ตารางนี้เก็บพิกัดจาก API ไว้แล้วตอน discover)
  2. place_details(place_id)  — ยิง API 1 คำขอ/ร้าน ใช้กับร้านที่ไม่มี candidate

ร้านที่ไม่มี google_place_id เทียบไม่ได้เลย — รายงานแยกไว้

⚠️ การซ่อมพิกัดทำให้ zone และ distance_nu_km / distance_psru_km เปลี่ยนตาม
  เพราะทั้งสองคำนวณจาก location คำนวณใหม่**เฉพาะร้านที่ซ่อม** ไม่แตะร้านอื่น
  และไม่แตะนิยาม ZONES — ต่างจากการรัน assign_zones.py ทั้งระบบ

⚠️ ไม่แตะรีวิว — การซ่อมพิกัดไม่กระทบ reviews เลย

รัน:
  uv run python scripts/verify_coords.py                  # ตรวจด้วยข้อมูลฟรีเท่านั้น
  uv run python scripts/verify_coords.py --use-api        # ยิง API เติมส่วนที่ขาด
  uv run python scripts/verify_coords.py --use-api --apply   # ตรวจแล้วซ่อม
  uv run python scripts/verify_coords.py --list 60        # โชว์รายการยาวขึ้น
"""
import argparse
import asyncio
import math
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from scraper.places_api import COST_PER_REQUEST_USD, PlacesApiError, place_details
from scraper.zones import assign_zone, distance_to_campus_km

# ห่างเกินเท่านี้ถือว่าพิกัดเพี้ยน ต้องซ่อม
# 100 ม. เผื่อความคลาดปกติระหว่างจุดที่ Google ปักหมุดกับจุดที่ API คืน
DRIFT_FIX_M = 100.0
REQUEST_DELAY_SEC = 0.15


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def _hav_m(lat1, lng1, lat2, lng2) -> float:
    R = 6371000.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def load_rows(session):
    """ทุกร้าน พร้อมพิกัดอ้างอิงจาก place_candidates ถ้ามี"""
    return (await session.execute(text("""
        SELECT p.id, p.name, p.zone, p.google_place_id AS gpid,
               ST_Y(p.location::geometry) AS lat,
               ST_X(p.location::geometry) AS lng,
               (SELECT pc.lat FROM place_candidates pc
                 WHERE pc.matched_place_id = p.id AND pc.lat IS NOT NULL
                 LIMIT 1) AS ref_lat,
               (SELECT pc.lng FROM place_candidates pc
                 WHERE pc.matched_place_id = p.id AND pc.lat IS NOT NULL
                 LIMIT 1) AS ref_lng,
               (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS sc
        FROM places p
        ORDER BY p.id
    """))).fetchall()


async def main(args) -> int:
    async with AsyncSessionLocal() as s:
        rows = await load_rows(s)

        # ── จัดกลุ่มตามแหล่งความจริงที่มี ──
        have_ref = []        # เทียบได้ฟรี
        need_api = []        # ต้องยิง API
        cannot = []          # ไม่มี place_id เทียบไม่ได้
        for r in rows:
            if r.lat is None:
                cannot.append((r, "ไม่มีพิกัดในฐาน"))
            elif r.ref_lat is not None:
                have_ref.append((r, float(r.ref_lat), float(r.ref_lng), "candidates"))
            elif r.gpid:
                need_api.append(r)
            else:
                cannot.append((r, "ไม่มี google_place_id"))

        p("=" * 82)
        p("  ตรวจพิกัดทุกร้านเทียบกับ Places API")
        p("=" * 82)
        p(f"  ร้านทั้งหมด {len(rows)}")
        p(f"    เทียบได้ฟรี (place_candidates)     {len(have_ref):>4}")
        p(f"    ต้องยิง API (place_details)        {len(need_api):>4}"
          f"  = ~${len(need_api) * COST_PER_REQUEST_USD:.2f}")
        p(f"    เทียบไม่ได้                        {len(cannot):>4}")

        # ── ยิง API เติมส่วนที่ขาด ──
        api_used = 0
        if need_api and args.use_api:
            p("")
            p(f"  ยิง place_details {len(need_api)} คำขอ...")
            errs = 0
            for i, r in enumerate(need_api, 1):
                try:
                    d = place_details(r.gpid)
                    api_used += 1
                except PlacesApiError as e:
                    errs += 1
                    p(f"    [{i}/{len(need_api)}] ❌ {str(e)[:60]}")
                    time.sleep(REQUEST_DELAY_SEC)
                    continue
                if d.get("_status") == "OK" and d.get("lat") is not None:
                    have_ref.append((r, float(d["lat"]), float(d["lng"]), "details"))
                else:
                    cannot.append((r, f"API ตอบ {d.get('_status')}"))
                if i % 20 == 0:
                    p(f"    [{i}/{len(need_api)}] ...")
                time.sleep(REQUEST_DELAY_SEC)
            p(f"  ยิงไปจริง {api_used} คำขอ = ${api_used * COST_PER_REQUEST_USD:.2f}"
              + (f" · ผิดพลาด {errs}" if errs else ""))
        elif need_api:
            p("")
            p(f"  ⚠️ ข้าม {len(need_api)} ร้านที่ต้องยิง API — เติม --use-api เพื่อตรวจให้ครบ")

        # ── คำนวณระยะคลาด ──
        checked = []
        for r, rlat, rlng, src in have_ref:
            d = _hav_m(float(r.lat), float(r.lng), rlat, rlng)
            checked.append((d, r, rlat, rlng, src))
        checked.sort(reverse=True, key=lambda x: x[0])

        bands = [(0, 50), (50, 100), (100, 500), (500, 2000),
                 (2000, 10000), (10000, 10 ** 9)]
        labels = ["0-50 ม. (ปกติ)", "50-100 ม.", "100-500 ม.",
                  "500 ม.-2 กม.", "2-10 กม.", "เกิน 10 กม."]
        p("")
        p(f"  ตรวจได้จริง {len(checked)} ร้าน — การกระจายระยะคลาด:")
        p(f"  {'ช่วง':<20} {'ร้าน':>5} {'%':>7}")
        for (lo, hi), lab in zip(bands, labels):
            n = sum(1 for d, *_ in checked if lo <= d < hi)
            if n:
                p(f"  {lab:<20} {n:>5} {n / len(checked) * 100:>6.1f}%")

        bad = [x for x in checked if x[0] >= DRIFT_FIX_M]
        p("")
        p(f"  พิกัดเพี้ยนเกิน {DRIFT_FIX_M:.0f} ม. : {len(bad)} ร้าน")
        if checked:
            p(f"  คลาดมากสุด {checked[0][0]:,.0f} ม. · "
              f"มัธยฐาน {checked[len(checked) // 2][0]:,.0f} ม.")

        if not bad:
            p("")
            p("  ✅ ไม่มีพิกัดที่ต้องซ่อม")
            p("=" * 82)
            return 0

        # ── ผลต่อ zone ──
        zone_changes = []
        for d, r, rlat, rlng, src in bad:
            new_zone = assign_zone(rlat, rlng)
            if new_zone != r.zone:
                zone_changes.append((r, r.zone, new_zone, d))

        p("")
        p(f"  ร้านที่ zone จะเปลี่ยนหลังซ่อม: {len(zone_changes)} ร้าน")
        if zone_changes:
            moves: dict[tuple, int] = {}
            for r, old, new, d in zone_changes:
                moves[(old, new)] = moves.get((old, new), 0) + 1
            for (old, new), n in sorted(moves.items(), key=lambda kv: -kv[1]):
                p(f"    {str(old):<12} -> {str(new):<12} {n:>4} ร้าน")

        n_show = args.list or 25
        p("")
        p(f"  รายการที่เพี้ยนมากสุด {min(n_show, len(bad))} อันดับ:")
        p(f"  {'id':>5} {'คลาด(ม.)':>9} {'lng ฐาน':>10} {'lng API':>10} "
          f"{'โซนเดิม':>11} {'โซนใหม่':>11} {'รีวิว':>5}  ชื่อร้าน")
        for d, r, rlat, rlng, src in bad[:n_show]:
            nz = assign_zone(rlat, rlng)
            flag = " *" if nz != r.zone else "  "
            p(f"  {r.id:>5} {d:>9,.0f} {float(r.lng):>10.5f} {rlng:>10.5f} "
              f"{str(r.zone):>11} {nz:>11}{flag}{r.sc:>4}  {r.name[:26]}")
        if len(bad) > n_show:
            p(f"  ... และอีก {len(bad) - n_show} ร้าน (ใช้ --list {len(bad)})")

        if cannot:
            p("")
            p(f"  เทียบไม่ได้ {len(cannot)} ร้าน:")
            why: dict[str, int] = {}
            for r, w in cannot:
                why[w] = why.get(w, 0) + 1
            for w, n in sorted(why.items(), key=lambda kv: -kv[1]):
                p(f"    {w:<28} {n:>4} ร้าน")

        if not args.apply:
            p("")
            p("  ยังไม่ได้แก้อะไร — เติม --apply เพื่อซ่อม")
            p("  สิ่งที่จะทำ:")
            p(f"    location                -> พิกัดจาก API ({len(bad)} ร้าน)")
            p(f"    zone                    -> คำนวณใหม่เฉพาะร้านที่ซ่อม")
            p(f"    distance_nu_km/psru_km  -> คำนวณใหม่เฉพาะร้านที่ซ่อม")
            p(f"    ไม่แตะรีวิว · ไม่แตะนิยาม ZONES · ไม่แตะร้านอื่น")
            p("=" * 82)
            return 0

        # ── ซ่อม ──
        for d, r, rlat, rlng, src in bad:
            nz = assign_zone(rlat, rlng)
            d_nu, d_psru = distance_to_campus_km(rlat, rlng)
            await s.execute(text("""
                UPDATE places SET
                    -- ⚠️ places.location เป็น geometry(POINT,4326) ไม่ใช่ geography
                    --   แคสต์เป็น ::geography จะได้ DatatypeMismatchError
                    --   ส่วนการ "วัดระยะ" ต้องแคสต์เป็น geography เพื่อให้ได้เมตร
                    --   (ST_Distance บน geometry SRID 4326 คืนหน่วยองศา)
                    location = ST_SetSRID(ST_MakePoint(:lng, :lat), 4326),
                    zone = :zone,
                    distance_nu_km = :dnu,
                    distance_psru_km = :dpsru
                WHERE id = :id
            """), {"lat": rlat, "lng": rlng, "zone": nz,
                   "dnu": d_nu, "dpsru": d_psru, "id": r.id})
        await s.commit()

        after = (await s.execute(text("""
            SELECT zone, count(*) n FROM places WHERE NOT scrape_excluded
            GROUP BY 1 ORDER BY 2 DESC"""))).fetchall()
        rev = (await s.execute(text("SELECT count(*) FROM reviews"))).scalar()

        p("")
        p(f"  ✅ ซ่อมพิกัดแล้ว {len(bad)} ร้าน · zone เปลี่ยน {len(zone_changes)} ร้าน")
        p(f"  รีวิว {rev:,} อัน (ไม่ถูกแตะ)")
        p("")
        p("  จำนวนร้านต่อโซนหลังซ่อม:")
        for x in after:
            p(f"    {str(x.zone):<12} {x.n:>4} ร้าน")
        p("")
        p("  ⚠️ สถิติ pain point แยกตามโซนเปลี่ยนตาม — ควรเก็บ snapshot ใหม่")
        p("    uv run python scripts/take_snapshot.py --label <วันที่> --note 'หลังซ่อมพิกัด'")
        p("=" * 82)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="ตรวจพิกัดทุกร้านเทียบกับ Places API และซ่อมที่เพี้ยน")
    ap.add_argument("--use-api", action="store_true",
                    help="ยิง place_details เติมร้านที่ไม่มีพิกัดอ้างอิงฟรี")
    ap.add_argument("--apply", action="store_true",
                    help="ซ่อมจริง (ไม่ใส่ = ตรวจและรายงานเท่านั้น)")
    ap.add_argument("--list", type=int, default=0, metavar="N",
                    help="โชว์รายการที่เพี้ยน N อันดับ (ค่าเริ่มต้น 25)")
    sys.exit(asyncio.run(main(ap.parse_args())))
