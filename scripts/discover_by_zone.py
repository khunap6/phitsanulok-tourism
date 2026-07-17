"""
discover_by_zone.py — ค้นหาสถานที่แบบแยกโซน แล้วติด zone ให้อัตโนมัติ

รัน:
  uv run python scripts/discover_by_zone.py              # ทุกโซน
  uv run python scripts/discover_by_zone.py --zone naresuan
  uv run python scripts/discover_by_zone.py --zone rajabhat
  uv run python scripts/discover_by_zone.py --zone city_center
"""
import argparse
import asyncio
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from db.database import AsyncSessionLocal
from scraper.scraper import save_to_db
from scraper.scraper_core import run_scraper, PHITSANULOK_BBOX
from scraper.zones import ZONES, assign_zone, all_zone_queries


async def discover_zone(session, zone_key: str, max_per_query: int = 20):
    """ค้นหาสถานที่ในโซนที่กำหนด แล้วบันทึก + ติด zone"""
    zone = ZONES[zone_key]
    queries = zone["queries"]
    print(f"\n{'='*55}")
    print(f"  โซน: {zone['name_th']}")
    print(f"  ศูนย์กลาง: ({zone['center_lat']}, {zone['center_lng']}) รัศมี {zone['radius_km']} km")
    print(f"{'='*55}")

    all_results = []
    for query in queries:
        print(f"\n  🔍 ค้นหา: {query}")
        try:
            results = await run_scraper(
                places=None,
                headless=True,
                max_places=max_per_query,
                auto_discover=True,
                discover_query=query,
            )
            # กรองเฉพาะที่ตรงโซน
            zone_results = []
            for r in results:
                detected = assign_zone(r.get("lat"), r.get("lng"))
                if detected == zone_key:
                    r["zone"] = zone_key
                    zone_results.append(r)
                else:
                    # ยังบันทึกไว้ แต่ติด zone ที่ตรวจพบจาก GPS จริง
                    r["zone"] = detected
                    zone_results.append(r)
            all_results.extend(zone_results)
            print(f"  ✅ พบ {len(zone_results)} แห่งในโซนนี้")
        except Exception as e:
            print(f"  ⚠️  query ล้มเหลว: {e}")

    if all_results:
        places_count, reviews_new = await save_to_db_with_zone(all_results, session)
        print(f"\n  💾 บันทึก {places_count} สถานที่, {reviews_new} รีวิวใหม่")
    else:
        print(f"\n  ⚠️  ไม่พบข้อมูลในโซนนี้")

    return all_results


async def save_to_db_with_zone(results: list[dict], session) -> tuple[int, int]:
    """บันทึกลง DB พร้อมอัพเดต zone"""
    from scraper.scraper import save_to_db
    places_count, reviews_new = await save_to_db(results, session)

    # อัพเดต zone สำหรับสถานที่ที่ scrape มาได้
    for r in results:
        zone = r.get("zone", "other")
        place_name = r.get("place_name", "")
        if place_name and zone:
            await session.execute(
                text("UPDATE places SET zone = :zone WHERE name = :name"),
                {"zone": zone, "name": place_name},
            )
    await session.commit()
    return places_count, reviews_new


async def main(zone_filter: str | None = None):
    async with AsyncSessionLocal() as session:
        if zone_filter:
            if zone_filter not in ZONES:
                print(f"❌ โซนไม่ถูกต้อง: {zone_filter}")
                print(f"   ใช้ได้: {', '.join(ZONES.keys())}")
                return
            await discover_zone(session, zone_filter)
        else:
            for zone_key in ZONES:
                await discover_zone(session, zone_key)

        # สรุปผล
        result = await session.execute(
            text("""
                SELECT zone, COUNT(*) as cnt
                FROM places
                GROUP BY zone
                ORDER BY cnt DESC
            """)
        )
        rows = result.fetchall()
        print(f"\n{'='*40}")
        print("📊 สรุปสถานที่ทั้งหมดในแต่ละโซน:")
        for row in rows:
            label = row.zone or "ไม่ระบุ"
            print(f"  {label:<25} {row.cnt} แห่ง")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zone", choices=list(ZONES.keys()), default=None,
                        help="โซนที่ต้องการค้นหา (ถ้าไม่ระบุ = ทุกโซน)")
    args = parser.parse_args()
    asyncio.run(main(args.zone))
