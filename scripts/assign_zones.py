"""
assign_zones.py — กำหนด zone ให้สถานที่ที่มีอยู่ใน DB แล้วจาก GPS coordinates
รัน: uv run python scripts/assign_zones.py
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from db.database import AsyncSessionLocal
from scraper.zones import assign_zone, get_zone_label, ZONES


def safe_print(text_val: str) -> None:
    """print ภาษาไทยตรงๆ ถ้า terminal รองรับ ถ้าไม่รองรับ fallback เป็น ? แทนการ crash"""
    try:
        print(text_val)
    except UnicodeEncodeError:
        print(text_val.encode("ascii", errors="replace").decode("ascii"))


async def main():
    async with AsyncSessionLocal() as session:
        # ดึงสถานที่ทั้งหมดที่มี GPS
        result = await session.execute(
            text("""
                SELECT id, name,
                       ST_Y(location) AS lat,
                       ST_X(location) AS lng,
                       zone
                FROM places
                WHERE location IS NOT NULL
                ORDER BY id
            """)
        )
        places = result.fetchall()

        print(f"พบสถานที่ที่มี GPS: {len(places)} แห่ง\n")

        counts: dict[str, int] = {}
        updated = 0

        for p in places:
            zone = assign_zone(p.lat, p.lng)
            counts[zone] = counts.get(zone, 0) + 1

            if p.zone != zone:
                await session.execute(
                    text("UPDATE places SET zone = :zone WHERE id = :id"),
                    {"zone": zone, "id": p.id},
                )
                updated += 1
                safe_print(f"  [{zone}] {p.name}")

        # สถานที่ที่ไม่มี GPS → zone = other
        no_gps = await session.execute(
            text("SELECT COUNT(*) FROM places WHERE location IS NULL")
        )
        no_gps_count = no_gps.scalar()
        if no_gps_count:
            await session.execute(
                text("UPDATE places SET zone = 'other' WHERE location IS NULL AND (zone IS NULL OR zone = '')")
            )
            counts["other"] = counts.get("other", 0) + no_gps_count
            print(f"\n  [other] สถานที่ไม่มี GPS: {no_gps_count} แห่ง")

        await session.commit()

        print(f"\n✅ อัพเดตแล้ว {updated} แห่ง")
        print("\n📊 สรุปตามโซน:")
        for zone_key in list(ZONES.keys()) + ["other"]:
            c = counts.get(zone_key, 0)
            label = get_zone_label(zone_key)
            bar = "█" * c
            print(f"  {label:<25} {bar} ({c})")


asyncio.run(main())
