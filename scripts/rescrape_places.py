"""
rescrape_places.py — อัปเดต "ข้อมูลร้าน" ของสถานที่ที่มีอยู่แล้วทั้งหมด ให้ตรงกับโค้ดสcrape ปัจจุบัน
(เวลาทำการทั้งสัปดาห์แบบใหม่ + สถานะร้าน + ช่วงราคา + หมวดหมู่) โดย "ไม่เก็บรีวิว"

ต่างจาก refresh_all.py / auto_refresh.py:
  - ไม่ดึงรีวิว (max_reviews=0) → เร็วมาก เน้นข้อมูลร้าน
  - ไม่แตะ scraped_at → ไม่รบกวนคิวรีเฟรชรีวิว (auto_refresh ยังทำงานปกติ)
  - resume ได้: หยิบเฉพาะร้านที่ opening_hours ยังเป็นฟอร์แมตเก่า/ว่าง
    ร้านที่ดึงไม่ได้จริง จะเซ็ต sentinel 'ไม่ระบุ' เพื่อไม่ให้ถูกหยิบซ้ำทุกรอบ

รัน:
  uv run python scripts/rescrape_places.py --limit 10   # ทดสอบ 10 ร้านก่อน
  uv run python scripts/rescrape_places.py               # ทั้งหมดที่ยังเป็นฟอร์แมตเก่า
  uv run python scripts/rescrape_places.py --all         # บังคับทุกร้าน (ไม่สนฟอร์แมต)
"""
import argparse
import asyncio
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from playwright.async_api import async_playwright

from db.database import AsyncSessionLocal
from scraper.scraper_core import scrape_place, random_delay

# sentinel เมื่อ Google ไม่มีเวลาทำการจริง → กันไม่ให้ถูกหยิบมา rescrape ซ้ำทุกรอบ
NO_HOURS = "ไม่ระบุ"

# ร่องรอยฟอร์แมตเก่า/ข้อความชั่วขณะ/noise ที่ต้อง rescrape ใหม่
# (ฟอร์แมตใหม่จะเป็น "ทุกวัน 6:00-20:00" / "จ 8:00-17:00 | ..." ซึ่งไม่มีคำเหล่านี้)
_OLD_MARKERS = ("อยู่", "ยืนยัน", "เวลา", "รูปภาพ", "รายงาน", "ต่อคน", "แนะนำ", "สัปดาห์")


def _to_float(v) -> float | None:
    """แปลง rating เป็นตัวเลข; ถ้าเป็น 'N/A'/ว่าง/แปลงไม่ได้ → None (คง rating เดิมไว้)"""
    try:
        return float(str(v).replace(",", "."))
    except (ValueError, TypeError):
        return None


def safe_print(text_val: str) -> None:
    try:
        print(text_val)
    except UnicodeEncodeError:
        print(text_val.encode("ascii", errors="replace").decode("ascii"))


async def load_places(session, limit: int | None, force_all: bool) -> list[dict]:
    """หาร้านที่ต้องอัปเดตข้อมูล — ค่าเริ่มต้น: เฉพาะที่ opening_hours ว่าง/ฟอร์แมตเก่า"""
    if force_all:
        where = "TRUE"
    else:
        # opening_hours ว่าง หรือมีร่องรอยฟอร์แมตเก่า
        conds = ["opening_hours IS NULL"]
        conds += [f"opening_hours LIKE '%{m}%'" for m in _OLD_MARKERS]
        where = "(" + " OR ".join(conds) + ")"

    query = f"""
        SELECT id, name, search_query
        FROM places
        WHERE {where}
        ORDER BY scraped_at ASC NULLS FIRST, id
    """
    if limit:
        query += f" LIMIT {int(limit)}"
    result = await session.execute(text(query))
    return [
        {"id": r.id, "name": r.name, "search_query": r.search_query or r.name}
        for r in result.fetchall()
    ]


async def update_place(session, place_id: int, data: dict) -> None:
    """
    อัปเดตเฉพาะฟิลด์ข้อมูลร้าน — ไม่แตะ scraped_at (คิวรีเฟรชรีวิวไม่ถูกรบกวน)
    - opening_hours: เขียนทับเสมอ (ถ้า None → sentinel กันหยิบซ้ำ)
    - business_status: เขียนทับเสมอ (ค่าล่าสุด)
    - google_category / price_level / rating: COALESCE (ไม่ทับด้วย NULL)
    (ไม่แตะพิกัด location — ร้านเดิมพิกัดไม่เปลี่ยน)
    """
    hours = data.get("opening_hours") or NO_HOURS
    await session.execute(
        text("""
            UPDATE places SET
                opening_hours   = :hours,
                business_status = COALESCE(:status, business_status),
                google_category = COALESCE(:category, google_category),
                price_level     = COALESCE(:price, price_level),
                overall_rating  = COALESCE(:rating, overall_rating)
            WHERE id = :id
        """),
        {
            "hours": hours,
            "status": data.get("business_status"),
            "category": data.get("google_category"),
            "price": data.get("price_level"),
            "rating": _to_float(data.get("overall_rating")),
            "id": place_id,
        },
    )
    await session.commit()


async def main(limit: int | None, headless: bool, force_all: bool):
    async with AsyncSessionLocal() as session:
        places = await load_places(session, limit, force_all)

        if not places:
            print("✅ ไม่มีร้านที่ต้องอัปเดต — ข้อมูลร้านเป็นฟอร์แมตใหม่ครบแล้ว")
            return

        print(f"พบร้านที่ต้องอัปเดตข้อมูล: {len(places)} แห่ง (ไม่เก็บรีวิว)\n")

        updated = 0
        failed = 0

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(
                locale="th-TH", viewport={"width": 1280, "height": 900}
            )
            page = await context.new_page()

            for i, place in enumerate(places):
                safe_print(f"[{i+1}/{len(places)}] {place['name']}")
                try:
                    # max_reviews=0 → ข้ามการเก็บรีวิว เน้นข้อมูลร้าน
                    data = await scrape_place(page, place["search_query"], max_reviews=0)
                except Exception as e:
                    print(f"  ❌ error: {e}")
                    data = None

                if data:
                    try:
                        await update_place(session, place["id"], data)
                        safe_print(
                            f"  ✅ เวลา: {data.get('opening_hours') or NO_HOURS}"
                            f" | สถานะ: {data.get('business_status')}"
                            f" | ราคา: {data.get('price_level')}"
                        )
                        updated += 1
                    except Exception as e:
                        await session.rollback()
                        print(f"  ❌ อัปเดต DB ไม่ได้ (ข้าม): {e}")
                        failed += 1
                else:
                    print("  ⚠️  ดึงข้อมูลไม่ได้ (ข้าม)")
                    failed += 1

                if i < len(places) - 1:
                    await random_delay(3.0, 6.0)

            await browser.close()

        print(f"\n{'='*50}")
        print(f"✅ อัปเดตสำเร็จ: {updated} แห่ง")
        print(f"⚠️  ดึงไม่ได้:   {failed} แห่ง")
        print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="จำกัดจำนวนร้าน (ทดสอบ)")
    parser.add_argument("--visible", action="store_true", help="เปิด browser ให้เห็น")
    parser.add_argument("--all", action="store_true", dest="force_all",
                        help="บังคับ rescrape ทุกร้าน (ไม่สนฟอร์แมตเดิม)")
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit, headless=not args.visible, force_all=args.force_all))
