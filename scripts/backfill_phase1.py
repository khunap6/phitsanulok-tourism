"""
backfill_phase1.py — เติมข้อมูล Phase 1 ให้ข้อมูลเดิมที่คำนวณได้ทันที (ไม่ต้อง scrape)

เติม 2 อย่าง:
  1. distance_nu_km / distance_psru_km  ← คำนวณจาก GPS ที่มีอยู่แล้ว
  2. review_date_approx                 ← แปลงจาก review_date text ("3 เดือนที่แล้ว")

หมายเหตุ: opening_hours และ price_level ต้อง re-scrape (ทำใน Phase 2)

รัน: uv run python scripts/backfill_phase1.py
"""
import asyncio
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from db.database import AsyncSessionLocal
from scraper.date_parser import parse_relative_date
from scraper.zones import distance_to_campus_km


async def backfill_distances(session) -> int:
    """คำนวณระยะทางไป ม.นเรศวร/ราชภัฏ จาก GPS ที่มีอยู่"""
    result = await session.execute(
        text("""
            SELECT id, ST_Y(location) AS lat, ST_X(location) AS lng
            FROM places
            WHERE location IS NOT NULL
        """)
    )
    rows = result.fetchall()
    updated = 0
    for r in rows:
        d_nu, d_psru = distance_to_campus_km(r.lat, r.lng)
        await session.execute(
            text("""
                UPDATE places
                SET distance_nu_km = :d_nu, distance_psru_km = :d_psru
                WHERE id = :id
            """),
            {"d_nu": d_nu, "d_psru": d_psru, "id": r.id},
        )
        updated += 1
    await session.commit()
    return updated


async def backfill_review_dates(session) -> tuple[int, int]:
    """แปลง review_date text → review_date_approx (date)"""
    result = await session.execute(
        text("""
            SELECT id, review_date, scraped_at
            FROM reviews
            WHERE review_date IS NOT NULL
              AND review_date_approx IS NULL
        """)
    )
    rows = result.fetchall()
    parsed = 0
    failed = 0
    for r in rows:
        # ใช้ scraped_at เป็นจุดอ้างอิง (ถ้ามี) เพื่อความแม่นยำกว่าใช้เวลาปัจจุบัน
        ref = r.scraped_at
        approx = parse_relative_date(r.review_date, reference=ref)
        if approx:
            await session.execute(
                text("UPDATE reviews SET review_date_approx = :approx WHERE id = :id"),
                {"approx": approx, "id": r.id},
            )
            parsed += 1
        else:
            failed += 1
    await session.commit()
    return parsed, failed


async def main():
    async with AsyncSessionLocal() as session:
        print("── Backfill Phase 1 ─────────────────────────────")

        print("\n[1/2] คำนวณระยะทางไปมหาวิทยาลัย...")
        n_dist = await backfill_distances(session)
        print(f"  ✅ อัพเดตระยะทาง {n_dist} สถานที่")

        print("\n[2/2] แปลงวันที่รีวิว (relative → date)...")
        n_parsed, n_failed = await backfill_review_dates(session)
        print(f"  ✅ แปลงสำเร็จ {n_parsed} รีวิว")
        print(f"  ⚠️  แปลงไม่ได้ {n_failed} รีวิว (รูปแบบวันที่ไม่รู้จัก)")

        # สรุปตัวอย่าง
        print("\n── ตัวอย่างผลลัพธ์ ──────────────────────────────")
        sample = await session.execute(
            text("""
                SELECT name, zone,
                       distance_nu_km, distance_psru_km
                FROM places
                WHERE distance_nu_km IS NOT NULL
                ORDER BY distance_nu_km ASC
                LIMIT 5
            """)
        )
        print("\n5 ร้านที่ใกล้ ม.นเรศวร ที่สุด:")
        for r in sample.fetchall():
            print(f"  {r.name[:40]:42} NU {r.distance_nu_km} km | PSRU {r.distance_psru_km} km")

        date_range = await session.execute(
            text("""
                SELECT MIN(review_date_approx) AS oldest,
                       MAX(review_date_approx) AS newest,
                       COUNT(*) AS total
                FROM reviews
                WHERE review_date_approx IS NOT NULL
            """)
        )
        dr = date_range.fetchone()
        print(f"\nช่วงเวลารีวิว: {dr.oldest} ถึง {dr.newest} ({dr.total} รีวิว)")


asyncio.run(main())
