"""verify_place_locations.py — ยิง Places API ตรวจที่ตั้งของสถานที่ทุกแห่งอีกครั้ง

⚠️ ทำไมต้องตรวจ
  พบเมื่อ 2026-10-13 ว่าอุทยานแห่งชาติทุ่งแสลงหลวง (id=13) มีที่อยู่ตาม Google
  เป็นจังหวัดเพชรบูรณ์ จึงอยู่นอกขอบเขตการศึกษา สคริปต์นี้ตรวจว่ามีกรณีอื่นอีกไหม
  โดยถาม Google ใหม่ แทนที่จะเชื่อค่าที่เก็บไว้เมื่อ 25 ก.ย. - 1 ต.ค. 2026

⚠️ ขอเฉพาะฟิลด์ที่ใช้ตรวจที่ตั้ง ไม่ขอชุดเต็ม
  ชุดเต็ม (_WANTED) มี opening_hours + rating + user_ratings_total ซึ่งเป็น
  Contact Data และ Atmosphere Data คิดเงินเพิ่มจาก Basic Data
  การตรวจครั้งนี้ต้องการแค่ที่อยู่กับพิกัด จึงขอ Basic อย่างเดียว
  ลดค่าใช้จ่ายลงราว 1 ใน 3 โดยไม่เสียข้อมูลที่ต้องใช้

⚠️ อ่านอย่างเดียวโดยปริยาย ไม่เขียนฐานจนกว่าจะสั่ง --write
  และต่อให้ --write ก็อัปเดตแค่ formatted_address กับ api_fetched_at
  **ไม่แตะ location** เพราะพิกัดถูกใช้คำนวณโซนและระยะทางที่ตรึงไว้แล้ว
  ถ้าพิกัดขยับจะรายงานให้เห็น แต่ให้คนตัดสินใจเอง

⚠️ ไม่ตัดสินขอบเขตเอง
  ถ้าเจอแห่งที่ที่อยู่เปลี่ยนเป็นจังหวัดอื่น จะรายงานอย่างเดียว
  การตัดออกต้องไปแก้ OVERRIDE_OUT ใน scripts/build_scope.py แล้วรันสามขั้นตาม
  ลำดับ build_scope -> classify_scope -> apply_scope_to_db

รัน:
  uv run python scripts/verify_place_locations.py              # ประเมินค่าใช้จ่าย
  uv run python scripts/verify_place_locations.py --run        # ยิงจริง ไม่เขียนฐาน
  uv run python scripts/verify_place_locations.py --run --write
  uv run python scripts/verify_place_locations.py --run --limit 20   # ลองน้อย ๆ ก่อน
"""
import argparse
import asyncio
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from db.database import AsyncSessionLocal, engine  # noqa: E402
from scraper import places_api  # noqa: E402

OUT = ROOT / "reports" / "place_location_verify.csv"
# Basic Data เท่านั้น — พอสำหรับตรวจที่ตั้ง และถูกกว่าชุดเต็ม
FIELDS = "place_id,formatted_address,geometry"
# Basic Data ของ Place Details ราคาตามหน้า pricing ของ Google
# ⚠️ ตัวเลขนี้ใช้ประเมินเท่านั้น ต้องเปิด Cloud Console ยืนยันเอง
COST_BASIC_USD = 0.017
SLEEP_S = 0.05
PROVINCES = ["พิษณุโลก", "Phitsanulok", "เพชรบูรณ์", "Phetchabun", "เลย", "Loei",
             "สุโขทัย", "Sukhothai", "อุตรดิตถ์", "Uttaradit", "กำแพงเพชร",
             "Kamphaeng Phet", "พิจิตร", "Phichit", "ตาก", "Tak"]


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def province_of(addr: str | None) -> str:
    if not addr:
        return "(ไม่มีที่อยู่)"
    for k in PROVINCES:
        if k in addr:
            return "พิษณุโลก" if k in ("พิษณุโลก", "Phitsanulok") else k
    return "(ไม่ระบุจังหวัด)"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="ยิง API จริง")
    ap.add_argument("--write", action="store_true",
                    help="เขียน formatted_address ใหม่ลงฐาน (ต้องมี --run)")
    ap.add_argument("--limit", type=int, default=0, help="จำกัดจำนวนที่ยิง")
    a = ap.parse_args()

    async with engine.connect() as c:
        rows = (await c.execute(text("""
            SELECT id, name, google_place_id, formatted_address, in_scope,
                   ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon,
                   (SELECT COUNT(*) FROM reviews r WHERE r.place_id = places.id) AS n
            FROM places
            WHERE google_place_id IS NOT NULL AND google_place_id <> ''
            ORDER BY id"""))).mappings().all()
    todo = list(rows)[:a.limit] if a.limit else list(rows)

    p(f"สถานที่ที่มี google_place_id {len(rows)} แห่ง · จะยิง {len(todo)}")
    p(f"ฟิลด์ที่ขอ: {FIELDS}  (Basic Data เท่านั้น)")
    p(f"ประเมินค่าใช้จ่าย {len(todo)} x ${COST_BASIC_USD} = "
      f"**${len(todo) * COST_BASIC_USD:.2f}**")
    p("  (ชุดฟิลด์เต็มที่สคริปต์อื่นใช้คือ $0.025/คำขอ = "
      f"${len(todo) * 0.025:.2f} — เลี่ยงไว้เพราะไม่ต้องใช้)")
    if not a.run:
        p("")
        p("ยังไม่ยิง — ใส่ --run เพื่อยิงจริง")
        return

    places_api.require_api_key()
    p("")
    out: list[dict] = []
    err = 0
    t0 = time.time()
    for i, r in enumerate(todo, 1):
        try:
            d = places_api.place_details(r["google_place_id"], fields=FIELDS)
        except places_api.PlacesApiError as e:
            d = {"_status": f"ERROR:{e}"}
        st = d.get("_status", "?")
        if st != "OK":
            err += 1
        new_addr = d.get("formatted_address")
        nlat, nlon = d.get("lat"), d.get("lng")
        moved_m = None
        if nlat is not None and r["lat"] is not None:
            # ระยะหยาบแบบ equirectangular พอสำหรับดูว่าหมุดขยับไหม
            dy = (nlat - r["lat"]) * 111_000
            dx = (nlon - r["lon"]) * 106_000
            moved_m = (dx * dx + dy * dy) ** 0.5
        out.append({
            "id": r["id"], "name": r["name"], "in_scope": r["in_scope"],
            "reviews": r["n"], "status": st,
            "addr_เดิม": r["formatted_address"] or "",
            "addr_ใหม่": new_addr or "",
            "จังหวัดเดิม": province_of(r["formatted_address"]),
            "จังหวัดใหม่": province_of(new_addr),
            "ที่อยู่เปลี่ยน": "ใช่" if (new_addr or "") != (r["formatted_address"] or "") else "",
            "หมุดขยับ_เมตร": "" if moved_m is None else f"{moved_m:.0f}",
        })
        if i % 50 == 0:
            p(f"  ยิงแล้ว {i}/{len(todo)} · ผิดพลาด {err} · "
              f"{time.time() - t0:.0f} วินาที")
        time.sleep(SLEEP_S)

    p("")
    p(f"ยิงจริง {places_api.request_count} คำขอ · ใช้เวลา {time.time() - t0:.0f} วินาที")
    p(f"ค่าใช้จ่ายโดยประมาณ ${places_api.request_count * COST_BASIC_USD:.2f}")
    p("")

    bad = [x for x in out if x["status"] != "OK"]
    chg = [x for x in out if x["ที่อยู่เปลี่ยน"]]
    prov_chg = [x for x in out if x["จังหวัดเดิม"] != x["จังหวัดใหม่"]]
    not_psl = [x for x in out if x["จังหวัดใหม่"] not in ("พิษณุโลก",)]
    moved = [x for x in out if x["หมุดขยับ_เมตร"] and float(x["หมุดขยับ_เมตร"]) > 500]

    p(f"{'ยิงไม่สำเร็จ':<34} {len(bad):>4}")
    p(f"{'ที่อยู่เปลี่ยนจากเดิม':<34} {len(chg):>4}")
    p(f"{'จังหวัดในที่อยู่เปลี่ยน':<34} {len(prov_chg):>4}")
    p(f"{'ที่อยู่ใหม่ไม่ใช่พิษณุโลก':<34} {len(not_psl):>4}  <- จุดที่ต้องตัดสินใจ")
    p(f"{'หมุดขยับเกิน 500 เมตร':<34} {len(moved):>4}")
    p("")
    if not_psl:
        p("รายการที่ที่อยู่ใหม่ไม่ใช่พิษณุโลก")
        for x in sorted(not_psl, key=lambda y: -y["reviews"]):
            p(f"  id={x['id']:<6} in_scope={'Y' if x['in_scope'] else 'N'} "
              f"รีวิว {x['reviews']:>4}  {x['name'][:38]:<39} "
              f"[{x['จังหวัดเดิม']} -> {x['จังหวัดใหม่']}]")
            p(f"        {x['addr_ใหม่'][:96]!r}")
    if prov_chg:
        p("")
        p("รายการที่จังหวัดเปลี่ยนจากค่าที่เก็บไว้")
        for x in prov_chg:
            p(f"  id={x['id']:<6} {x['จังหวัดเดิม']} -> {x['จังหวัดใหม่']}  "
              f"{x['name'][:40]}")
    if bad:
        p("")
        p("ยิงไม่สำเร็จ")
        for x in bad[:12]:
            p(f"  id={x['id']:<6} {x['status']}  {x['name'][:44]}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]), quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(out)
    p("")
    p(f"เขียนผลเต็มที่ {OUT.relative_to(ROOT)} ({len(out)} แถว)")

    if not a.write:
        p("")
        p("ไม่ได้เขียนฐาน — ใส่ --write ถ้าต้องการอัปเดต formatted_address")
        await engine.dispose()
        return

    upd = [x for x in chg if x["status"] == "OK" and x["addr_ใหม่"]]
    if not upd:
        p("ไม่มีที่อยู่ที่ต้องอัปเดต")
        await engine.dispose()
        return
    async with AsyncSessionLocal() as s:
        await s.execute(text("""
            UPDATE places SET formatted_address = v.addr, api_fetched_at = :ts
            FROM (SELECT UNNEST(CAST(:ids AS int[])) AS id,
                         UNNEST(CAST(:addrs AS text[])) AS addr) v
            WHERE places.id = v.id"""),
            {"ids": [x["id"] for x in upd],
             "addrs": [x["addr_ใหม่"] for x in upd],
             "ts": datetime.now(timezone.utc)})
        await s.commit()
    p(f"อัปเดต formatted_address {len(upd)} แห่ง (ไม่แตะ location)")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
