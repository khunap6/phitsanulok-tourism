"""
test_dedup.py — เทสต์ป้องกันรีวิวซ้ำกลับมาอีก (offline, ไม่ต่อเน็ต)

เคยมีบั๊ก: hash คำนวณจากข้อความดิบซึ่งมีวันที่ติดมาด้วย ("7 เดือนที่แล้ว")
พอ scrape รอบใหม่วันที่เลื่อน → hash เปลี่ยน → บันทึกซ้ำ (เกิดขึ้นจริง 3,453 แถว)

รันเทสต์นี้ทุกครั้งที่แก้ text_cleaner หรือ review_text_hash:
  uv run python scripts/test_dedup.py
"""
import asyncio
import sys

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from scraper.scraper_core import review_text_hash

PASS, FAIL = "✅ ผ่าน", "❌ ไม่ผ่าน"
failures: list[str] = []


def safe_print(t: str) -> None:
    try:
        print(t)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"))


def check(name: str, ok: bool, detail: str = "") -> None:
    safe_print(f"  {PASS if ok else FAIL}  {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        failures.append(name)


def test_date_stable() -> None:
    """แก่นของบั๊กเดิม: วันที่เปลี่ยน แต่ hash ต้องคงที่"""
    body = "\n\n{d}\n- เจ้าหน้าที่เยอะ ดูแลสถานที่และตรวจตรา ดีมากๆ"
    dates = ["1 สัปดาห์ที่แล้ว", "7 เดือนที่แล้ว", "8 เดือนที่แล้ว", "1 ปีที่แล้ว", "2 ปีที่แล้ว"]
    hashes = {review_text_hash(body.format(d=d)) for d in dates}
    check("วันที่เปลี่ยน → hash คงที่", len(hashes) == 1, f"ได้ {len(hashes)} ค่า (ต้องได้ 1)")


def test_different_reviews_differ() -> None:
    """รีวิวคนละอันต้องได้ hash ต่างกัน (ไม่งั้นจะลบของจริงทิ้ง)"""
    a = review_text_hash("7 เดือนที่แล้ว\nร้านนี้บริการแย่มาก รอนาน")
    b = review_text_hash("7 เดือนที่แล้ว\nร้านนี้อร่อยมาก ประทับใจ")
    check("รีวิวคนละอัน → hash ต่างกัน", a != b)


def test_star_only_fallback() -> None:
    """รีวิวให้ดาวอย่างเดียว (ล้างแล้วว่าง) ต้องยังได้ hash ไม่ error"""
    h = review_text_hash("\n\n\n3 เดือนที่แล้ว")
    check("รีวิวดาวอย่างเดียว → ได้ hash", bool(h) and len(h) == 32)


def test_empty_input() -> None:
    check("ข้อความว่าง → ไม่ crash", len(review_text_hash("")) == 32)


async def test_db_no_duplicates() -> None:
    """ฐานข้อมูลจริงต้องไม่มีรีวิวซ้ำ และ hash ต้องตรงสูตร"""
    async with AsyncSessionLocal() as s:
        r = await s.execute(text("""
            SELECT COUNT(*) FROM (
              SELECT 1 FROM reviews r
              GROUP BY r.place_id, COALESCE(NULLIF(r.text_clean,''), TRIM(r.text))
              HAVING COUNT(*) > 1) t
        """))
        dup = r.scalar()
        check("ฐานข้อมูลไม่มีรีวิวซ้ำ", dup == 0, f"เจอ {dup:,} กลุ่ม")

        r = await s.execute(text("""
            SELECT COUNT(*) FROM reviews r
            WHERE r.text_hash IS DISTINCT FROM
                  MD5(COALESCE(NULLIF(r.text_clean,''), TRIM(r.text)))
        """))
        bad = r.scalar()
        check("text_hash ตรงกับสูตรใหม่ทุกแถว", bad == 0, f"ไม่ตรง {bad:,} แถว")

        r = await s.execute(text("""
            SELECT COUNT(*) FROM pg_constraint
            WHERE conname = 'uq_place_text_hash'
        """))
        check("มี unique constraint กันซ้ำระดับฐานข้อมูล", r.scalar() == 1)


async def main() -> None:
    safe_print("=" * 60)
    safe_print("เทสต์ป้องกันรีวิวซ้ำ")
    safe_print("=" * 60)
    safe_print("\n[สูตร hash]")
    test_date_stable()
    test_different_reviews_differ()
    test_star_only_fallback()
    test_empty_input()
    safe_print("\n[ฐานข้อมูลจริง]")
    await test_db_no_duplicates()

    safe_print("\n" + "=" * 60)
    if failures:
        safe_print(f"❌ ไม่ผ่าน {len(failures)} ข้อ: {', '.join(failures)}")
        sys.exit(1)
    safe_print("✅ ผ่านทุกข้อ — ระบบกันรีวิวซ้ำทำงานปกติ")


asyncio.run(main())
