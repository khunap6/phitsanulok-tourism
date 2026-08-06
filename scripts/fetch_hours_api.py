"""
fetch_hours_api.py — เติมเวลาทำการทั้งสัปดาห์ผ่าน Google Places API (ทางการ, เชื่อถือได้)

ใช้เมื่อ: ร้านที่ scrape จากเว็บได้เวลาไม่ครบ (Google เดสก์ท็อปซ่อนร้านที่ยังไม่ยืนยัน)
Places API คืน opening_hours.weekday_text ครบ 7 วัน + business_status แบบมีโครงสร้าง

ต้องมีใน .env:  GOOGLE_PLACES_API_KEY=xxxx   (เปิด Places API + billing ใน Google Cloud)

รัน:
  uv run python scripts/fetch_hours_api.py                # DRY-RUN: นับร้าน + ประเมินค่าใช้จ่าย (ไม่ยิง API)
  uv run python scripts/fetch_hours_api.py --limit 5      # ทดสอบ 5 ร้านแรก (ยิงจริง)
  uv run python scripts/fetch_hours_api.py --all          # ยิงทุกร้านที่ยังขาดเวลาครบ
  uv run python scripts/fetch_hours_api.py --all --force   # ยิงทุกร้าน (รวมที่มีเวลาครบแล้ว)
"""
import argparse
import asyncio
import json
import os
import time
import urllib.parse
import urllib.request

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from scraper.scraper_core import _parse_weekly_hours

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()
FIND_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
NO_HOURS = "ไม่ระบุ"
COST_PER_PLACE = 0.04  # ประมาณ (findplace + details) USD

_STATUS_MAP = {
    "OPERATIONAL": "operational",
    "CLOSED_TEMPORARILY": "closed_temporarily",
    "CLOSED_PERMANENTLY": "closed_permanently",
}


def safe_print(t: str) -> None:
    try:
        print(t)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"))


def _get(url: str, params: dict) -> dict:
    full = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(full, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_place_hours(name: str, lat, lng) -> dict | None:
    """หา place_id จากชื่อ (+พิกัด) แล้วดึง opening_hours/business_status"""
    find_params = {
        "input": name,
        "inputtype": "textquery",
        "fields": "place_id",
        "language": "th",
        "key": API_KEY,
    }
    if lat is not None and lng is not None:
        find_params["locationbias"] = f"point:{lat},{lng}"

    fr = _get(FIND_URL, find_params)
    if fr.get("status") != "OK" or not fr.get("candidates"):
        return {"_status": fr.get("status", "NO_CANDIDATE")}
    place_id = fr["candidates"][0]["place_id"]

    dr = _get(DETAILS_URL, {
        "place_id": place_id,
        "fields": "opening_hours,business_status",
        "language": "th",
        "key": API_KEY,
    })
    if dr.get("status") != "OK":
        return {"_status": dr.get("status", "DETAILS_FAIL")}

    result = dr.get("result", {})
    weekday = (result.get("opening_hours") or {}).get("weekday_text") or []
    hours = _parse_weekly_hours(weekday) if weekday else None
    status = _STATUS_MAP.get(result.get("business_status", ""), None)
    return {"opening_hours": hours, "business_status": status, "_status": "OK"}


async def load_targets(session, limit, force_all):
    """ร้านที่ต้องเติมเวลา — ค่าเริ่มต้น: เวลายังไม่ครบสัปดาห์ (ไม่มี 'ทุกวัน' และไม่มี '|')"""
    if force_all:
        where = "TRUE"
    else:
        where = ("(opening_hours IS NULL OR opening_hours = :sentinel "
                 "OR (opening_hours NOT LIKE '%ทุกวัน%' AND opening_hours NOT LIKE '%|%'))")
    q = f"""
        SELECT id, name, search_query,
               ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lng
        FROM places
        WHERE {where}
        ORDER BY id
    """
    if limit:
        q += f" LIMIT {int(limit)}"
    result = await session.execute(text(q), {"sentinel": NO_HOURS})
    return [
        {"id": r.id, "name": r.name,
         "query": (r.search_query or r.name), "lat": r.lat, "lng": r.lng}
        for r in result.fetchall()
    ]


async def main(limit, force_all, force_places, do_run):
    if not API_KEY:
        print("❌ ไม่พบ GOOGLE_PLACES_API_KEY ใน .env — ใส่คีย์ก่อน (ดูขั้นตอนใน chat)")
        return

    async with AsyncSessionLocal() as session:
        targets = await load_targets(session, limit, force_places)
        n = len(targets)

        # DRY-RUN: ไม่ระบุ --limit และไม่ระบุ --all → แค่นับ
        if not do_run:
            print(f"📊 ร้านที่ต้องเติมเวลาทำการ: {n} แห่ง")
            print(f"   ประเมินค่าใช้จ่าย: ~${n * COST_PER_PLACE:.2f} (เครดิตฟรี $200/เดือน)")
            print(f"   ทดสอบก่อน:  uv run python scripts/fetch_hours_api.py --limit 5")
            print(f"   ยิงเต็ม:    uv run python scripts/fetch_hours_api.py --all")
            return

        if n == 0:
            print("✅ ทุกร้านมีเวลาทำการครบแล้ว")
            return

        print(f"เริ่มดึงเวลาทำการผ่าน Places API: {n} แห่ง (~${n * COST_PER_PLACE:.2f})\n")
        ok = 0
        no_hours = 0
        failed = 0

        for i, p in enumerate(targets):
            safe_print(f"[{i+1}/{n}] {p['name']}")
            try:
                data = fetch_place_hours(p["query"], p["lat"], p["lng"])
            except Exception as e:
                print(f"  ❌ error: {e}")
                data = None

            if not data or data.get("_status") != "OK":
                st = data.get("_status") if data else "ERROR"
                print(f"  ⚠️  ดึงไม่ได้ ({st})")
                failed += 1
            else:
                hours = data.get("opening_hours") or NO_HOURS
                await session.execute(
                    text("""
                        UPDATE places SET
                            opening_hours   = :hours,
                            business_status = COALESCE(:status, business_status)
                        WHERE id = :id
                    """),
                    {"hours": hours, "status": data.get("business_status"), "id": p["id"]},
                )
                await session.commit()
                safe_print(f"  ✅ {hours}"
                           + (f" | สถานะ: {data['business_status']}" if data.get("business_status") else ""))
                if data.get("opening_hours"):
                    ok += 1
                else:
                    no_hours += 1

            time.sleep(0.15)  # กัน rate ของ API

        print(f"\n{'='*50}")
        print(f"✅ ได้เวลาครบ:      {ok} แห่ง")
        print(f"➖ Google ไม่มีเวลา: {no_hours} แห่ง")
        print(f"⚠️  ดึงไม่ได้:       {failed} แห่ง")
        print(f"💰 ใช้ไปประมาณ:     ${n * COST_PER_PLACE:.2f}")
        print("=" * 50)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="จำกัดจำนวนร้าน (ทดสอบ) — ยิงจริง")
    ap.add_argument("--all", action="store_true", dest="run_all",
                    help="ยิงทุกร้านที่ยังขาดเวลาครบ")
    ap.add_argument("--force", action="store_true",
                    help="รวมร้านที่มีเวลาครบแล้วด้วย (ใช้คู่ --all)")
    args = ap.parse_args()
    # do_run = มี --limit หรือ --all เท่านั้น (ไม่งั้น dry-run นับเฉยๆ)
    do_run = bool(args.limit) or args.run_all
    asyncio.run(main(limit=args.limit, force_all=args.run_all,
                     force_places=args.force, do_run=do_run))
