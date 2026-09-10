"""
test_deep_block.py — พิสูจน์ว่า run_deep_scan จัดการ "โดนบล็อก" ถูกต้อง (offline ไม่แตะเน็ต)

ตรวจ 2 สถานการณ์:
  A) ทุกร้านโดนบล็อก          → ต้องคืน blocked ออกมา และ "ห้าม" มีร้านไหนถูกตั้ง deep_scanned_at
  B) ร้านแรกบล็อก ร้านที่ 2 ผ่าน → บล็อกไม่ติดกัน 2 ร้าน จึงไปต่อจนจบ (blocked = None)
                                 ตั้ง deep_scanned_at เฉพาะร้านที่ 2 เท่านั้น

ความปลอดภัยของข้อมูล: ทั้งหมดรันใน transaction ที่ถูก rollback ทิ้งตอนจบ
(session ผูกกับ connection เดียวแบบ join_transaction_mode="create_savepoint"
 → commit ข้างใน run_deep_scan กลายเป็นแค่ release savepoint ไม่ลงดิสก์จริง)
DB จริงจึงไม่มีอะไรเปลี่ยน — ไม่มีรีวิวปลอม ไม่มีแถว scrape_jobs ค้าง

รัน: uv run python scripts/test_deep_block.py
"""
import asyncio
import os
import sys
import types
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import engine
from scraper import scraper as sc

sys.path.insert(0, os.path.join(os.getcwd(), "scripts"))
import deep_scan  # noqa: E402  (ใช้คิวรีเลือกร้านตัวจริงมาตรวจการจัดกลุ่ม)


def safe_print(t: str) -> None:
    try:
        print(t)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"))


def fake_place_result(name: str) -> dict:
    """ผลลัพธ์ปลอมของร้านที่ scrape สำเร็จ — หน้าตาเหมือนที่ scrape_place คืนจริง"""
    return {
        "place_name": name,
        "search_query": name,
        "overall_rating": "4.5",
        "google_category": None,
        "opening_hours": None,
        "price_level": None,
        "business_status": "operational",
        "lat": 16.8258,
        "lng": 100.2654,
        "reviews": [{
            "rating": 5,
            "text": "รีวิวทดสอบจาก test_deep_block " + "x" * 40,
            "date": "1 เดือนที่แล้ว",
        }],
        "scraped_at": datetime.now().isoformat(),
    }


async def pick_targets(session, n: int = 2) -> list[str]:
    """หยิบชื่อร้านจริงที่ยังไม่เคย deep scan มาใช้ทดสอบ"""
    result = await session.execute(
        text("SELECT name FROM places WHERE deep_scanned_at IS NULL ORDER BY id LIMIT :n"),
        {"n": n},
    )
    return [row[0] for row in result.fetchall()]


async def attempts_of(session, names: list[str]) -> list[int]:
    """ค่า deep_attempts ของร้านที่ใช้ทดสอบ"""
    result = await session.execute(
        text("SELECT deep_attempts FROM places WHERE name = ANY(:names)"),
        {"names": names},
    )
    return [row[0] for row in result.fetchall()]


async def marked_names(session, names: list[str]) -> list[str]:
    """ชื่อร้านที่ถูกตั้ง deep_scanned_at แล้ว (ในบรรดาที่ส่งไปตรวจ)"""
    result = await session.execute(
        text("SELECT name FROM places WHERE name = ANY(:names) AND deep_scanned_at IS NOT NULL"),
        {"names": names},
    )
    return [row[0] for row in result.fetchall()]


def fake_unreachable_result(name: str) -> dict:
    """ร้านที่ "เข้าไม่ถึงหน้ารีวิว" — metadata ครบแต่ติดธง _reviews_failed และไม่มีรีวิว"""
    r = fake_place_result(name)
    r["reviews"] = []
    r["_reviews_failed"] = "scroll 3 รอบแล้วไม่พบการ์ดรีวิวเลย (feed ไม่ render)"
    return r


async def run_attempts_scenario(rounds: int):
    """
    จำลองร้านเดียวที่เข้าไม่ถึงหน้ารีวิวซ้ำ ๆ rounds ครั้ง
    คืน (deep_attempts หลังแต่ละครั้ง, deep_scanned_at, ยังอยู่ในคิวไหม, อยู่กลุ่มยอมแพ้ไหม)
    """
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
    )

    async def fake_fallback(places, headless, max_places, auto_discover,
                            max_reviews=None, known_hashes_by_place=None, deep=False):
        return [fake_unreachable_result(places[0])]

    real_fallback = sc._run_with_fallback
    real_random = sc.random
    sc._run_with_fallback = fake_fallback
    sc.random = types.SimpleNamespace(uniform=lambda a, b: 0.0)

    try:
        # ต้องหยิบร้านที่ "อยู่ในคิวจริง" (เข้าเกณฑ์ capped/zero/shallow) ไม่ใช่ร้านแรกใน DB
        # ไม่งั้นร้านที่ไม่เข้าเกณฑ์จะไม่โผล่ทั้งในคิวและในกลุ่มยอมแพ้ (ถูกต้องแล้ว แต่ทดสอบไม่ได้)
        queued = await deep_scan.load_targets(session, "all", 1, set())
        name = queued[0][0]
        # รีเซ็ตตัวนับใน transaction ที่จะถูก rollback — ให้ผลเทสต์ไม่ขึ้นกับค่าจริงใน DB
        await session.execute(
            text("UPDATE places SET deep_attempts = 0 WHERE name = :n"), {"n": name}
        )
        seen = []
        stamp = None
        for _ in range(rounds):
            await sc.run_deep_scan(session, [name], headless=True)
            r = await session.execute(
                text("SELECT deep_attempts, deep_scanned_at FROM places WHERE name = :n"),
                {"n": name},
            )
            attempts, stamp = r.fetchone()
            seen.append(attempts)

        in_queue = any(n == name for n, _ in
                       await deep_scan.load_targets(session, "all", None, set()))
        in_given_up = any(n == name for n, _ in
                          await deep_scan.load_targets(session, "all", None, set(), given_up=True))
        return seen, stamp, in_queue, in_given_up
    finally:
        sc._run_with_fallback = real_fallback
        sc.random = real_random
        await session.close()
        await trans.rollback()
        await conn.close()


async def run_scenario(label: str, block_plan: list[bool]) -> tuple[dict, list[str], list[str]]:
    """
    block_plan = ลำดับว่าร้านที่ i โดนบล็อกไหม (True = บล็อก)
    คืน (ผลลัพธ์ของ run_deep_scan, ชื่อร้านที่ใช้ทดสอบ, ชื่อร้านที่ถูกตั้ง deep_scanned_at)
    """
    conn = await engine.connect()
    trans = await conn.begin()
    session = AsyncSession(
        bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
    )

    calls = {"i": 0}

    async def fake_fallback(places, headless, max_places, auto_discover,
                            max_reviews=None, known_hashes_by_place=None, deep=False):
        idx = calls["i"]
        calls["i"] += 1
        assert deep is True, "run_deep_scan ต้องเรียกด้วย deep=True"
        assert known_hashes_by_place is None, "deep scan ต้องไม่ส่ง known_hashes"
        if block_plan[idx]:
            return [{"_blocked": "test-captcha"}]
        return [fake_place_result(places[0])]

    real_fallback = sc._run_with_fallback
    real_random = sc.random
    sc._run_with_fallback = fake_fallback
    sc.random = types.SimpleNamespace(uniform=lambda a, b: 0.0)   # ข้ามการหน่วง 20-40 วิ

    try:
        names = await pick_targets(session, len(block_plan))
        result = await sc.run_deep_scan(session, names, headless=True)
        marked = await marked_names(session, names)
        attempts = await attempts_of(session, names)
        return result, names, marked, attempts
    finally:
        sc._run_with_fallback = real_fallback
        sc.random = real_random
        await session.close()
        await trans.rollback()      # ทิ้งทุกอย่างที่เขียนระหว่างทดสอบ
        await conn.close()


async def main() -> None:
    safe_print("=" * 66)
    safe_print("ทดสอบการจัดการสัญญาณบล็อกของ run_deep_scan (offline — rollback ทุกอย่าง)")
    safe_print("=" * 66)
    passed = True

    # ── A) ทุกร้านโดนบล็อก ──
    result, names, marked, attempts = await run_scenario("A", [True, True])
    safe_print("\n[A] ร้านแรกโดนบล็อก (และร้านถัดไปก็โดน)")
    safe_print(f"  ร้านที่ใช้ทดสอบ : {names}")
    safe_print(f"  blocked ที่คืนมา : {result.get('blocked')!r}")
    safe_print(f"  รีวิวใหม่        : {result.get('reviews_new')}")
    safe_print(f"  ร้านที่ถูกตั้ง deep_scanned_at : {marked or 'ไม่มี'}")
    safe_print(f"  deep_attempts หลังโดนบล็อก      : {attempts} (ต้องเป็น 0 ทุกตัว)")
    ok_a = (result.get("blocked") is not None and not marked
            and result.get("reviews_new") == 0 and all(a == 0 for a in attempts))
    safe_print(f"  {'ผ่าน' if ok_a else 'ไม่ผ่าน'} — ต้องคืน blocked, ไม่ตั้ง deep_scanned_at, "
               f"และไม่นับ deep_attempts (โดนบล็อกไม่ใช่ความผิดของร้าน)")
    passed = passed and ok_a

    # ── B) ร้านแรกบล็อก ร้านที่สองสำเร็จ ──
    result, names, marked, attempts = await run_scenario("B", [True, False])
    safe_print("\n[B] ร้านแรกบล็อก ร้านที่สองสำเร็จ")
    safe_print(f"  ร้านที่ใช้ทดสอบ : {names}")
    safe_print(f"  blocked ที่คืนมา : {result.get('blocked')!r}  (บล็อกไม่ติดกัน 2 ร้าน จึงไปต่อ)")
    safe_print(f"  ร้านที่ถูกตั้ง deep_scanned_at : {marked}")
    ok_b = (result.get("blocked") is None
            and marked == [names[1]]
            and names[0] not in marked)
    safe_print(f"  {'ผ่าน' if ok_b else 'ไม่ผ่าน'} — ต้องตั้งเฉพาะร้านที่ scrape สำเร็จจริง")
    passed = passed and ok_b

    # ── C) เข้าไม่ถึงหน้ารีวิวซ้ำ ๆ จนครบ DEEP_MAX_ATTEMPTS → ยอมแพ้ ──
    seen, stamp, in_queue, in_given_up = await run_attempts_scenario(sc.DEEP_MAX_ATTEMPTS)
    safe_print("")
    safe_print(f"[C] เข้าไม่ถึงหน้ารีวิว {sc.DEEP_MAX_ATTEMPTS} ครั้งติด")
    safe_print(f"  deep_attempts หลังแต่ละครั้ง : {seen}")
    safe_print(f"  deep_scanned_at              : {stamp}")
    safe_print(f"  ยังอยู่ในคิว                  : {in_queue}")
    safe_print(f"  อยู่ในกลุ่มยอมแพ้              : {in_given_up}")
    ok_c = (seen == list(range(1, sc.DEEP_MAX_ATTEMPTS + 1))
            and stamp is None and not in_queue and in_given_up)
    safe_print(f"  {'ผ่าน' if ok_c else 'ไม่ผ่าน'} — ต้องนับครบ, ไม่ตั้ง deep_scanned_at, "
               f"ออกจากคิวไปอยู่กลุ่มยอมแพ้")
    passed = passed and ok_c

    safe_print("\n" + "=" * 66)
    safe_print(f"สรุป: {'ผ่านทั้งหมด' if passed else 'ไม่ผ่าน'}")
    safe_print("=" * 66)
    if not passed:
        raise SystemExit(1)


asyncio.run(main())
