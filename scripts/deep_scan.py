"""
deep_scan.py — เก็บรีวิวย้อนหลังให้ครบสำหรับร้านที่เก็บไม่ครบ (โหมด deep)

ต่างจาก auto_refresh.py:
  - auto_refresh = incremental เอาเฉพาะรีวิว "ใหม่" ที่เพิ่มมาหลังรอบก่อน (เร็ว)
  - deep_scan    = ไล่ scroll ให้สุดจริงๆ ไม่สนใจว่ามีรีวิวไหนอยู่ใน DB แล้ว
                   ใช้กับร้านที่เคยติดเพดาน scroll เดิม (60 รอบ) จนได้รีวิวไม่ครบ

เลือกร้านจาก places.deep_scanned_at IS NULL + เกณฑ์ตาม --targets:
  capped   จำนวนรีวิว >= 190           (น่าจะโดนเพดานตัด)
  zero     จำนวนรีวิว = 0              (ยังไม่เคยได้รีวิวเลย)
  shallow  จำนวนรีวิว >= 50 และช่วงวันที่ของรีวิวแคบกว่า 730 วัน (เก็บได้แค่ช่วงล่าสุด)
  all      รวมทั้ง 3 กลุ่ม

รัน:
  uv run python scripts/deep_scan.py --dry-run          # ดูรายชื่อร้านก่อน ไม่แตะเน็ต
  uv run python scripts/deep_scan.py                    # capped ทีละ 5 ร้าน พัก 20 นาที
  uv run python scripts/deep_scan.py --targets all --limit 3 --wait 30

หมายเหตุ:
  - ร้านละไม่เกิน 10 นาที (DEEP_TIME_BUDGET_SEC) รอบละ 5 ร้าน = ~1 ชม./รอบ
  - สคริปต์นี้ "ไม่" รัน analyze/classify ต่อให้ เพราะรีวิวจะเพิ่มเยอะและ classify มีค่าใช้จ่าย
    เก็บครบแล้วค่อยสั่งเองทีเดียว: uv run python scripts/analyze.py
"""
import argparse
import asyncio
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from scraper.scraper import DEEP_MAX_ATTEMPTS, run_deep_scan

MAX_ROUNDS = 60                      # กันวนไม่รู้จบ (94 ร้าน ÷ 5 = ~19 รอบ)
BLOCK_BACKOFF_HOURS = [2, 4, 6]      # เจอบล็อก → พักยาวขึ้นเรื่อยๆ แล้วลองใหม่

# เกณฑ์เลือกร้าน — ใช้ใน HAVING (ทุกกลุ่มบังคับ deep_scanned_at IS NULL ใน WHERE อยู่แล้ว)
TARGET_CONDITIONS = {
    "capped": "COUNT(r.id) >= 190",
    "zero": "COUNT(r.id) = 0",
    "shallow": (
        "COUNT(r.id) >= 50 AND "
        "(MAX(r.review_date_approx) - MIN(r.review_date_approx)) < 730"
    ),
}


def log(msg: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", errors="replace").decode("ascii"), flush=True)


def _having(targets: str) -> str:
    if targets == "all":
        return " OR ".join(f"({c})" for c in TARGET_CONDITIONS.values())
    return TARGET_CONDITIONS[targets]


async def load_targets(session, targets: str, limit: int | None, skip: set[str],
                       given_up: bool = False):
    """
    คืน [(ชื่อร้าน, จำนวนรีวิวปัจจุบัน), ...] เรียงร้านที่มีรีวิวเยอะก่อน (คุ้มเวลาที่สุด)

    skip = ร้านที่ลองในรอบก่อนของการรันครั้งนี้แล้วแต่ไม่ถูกตี deep_scanned_at
           (เช่นหน้าโหลดไม่ขึ้น หรือชื่อจริงบนหน้าเว็บไม่ตรงกับชื่อใน DB)
           ถ้าไม่กันไว้ จะถูกหยิบมาทำซ้ำทุกรอบจนครบ MAX_ROUNDS

    given_up=False → คิวที่ยังต้องทำ  (deep_attempts <  DEEP_MAX_ATTEMPTS)
    given_up=True  → กลุ่มที่ยอมแพ้แล้ว (deep_attempts >= DEEP_MAX_ATTEMPTS)
      ทั้งสองกลุ่ม deep_scanned_at ยังเป็น NULL เหมือนกัน — แยกกันที่ตัวนับเท่านั้น
      จึงคิวรีนับ "เก็บสำเร็จ / ยอมแพ้ / ยังอยู่ในคิว" ออกจากกันได้
    """
    attempts_cmp = ">=" if given_up else "<"
    sql = f"""
        SELECT p.name, COUNT(r.id) AS cnt
        FROM places p
        LEFT JOIN reviews r ON r.place_id = p.id
        WHERE p.deep_scanned_at IS NULL
          AND COALESCE(p.deep_attempts, 0) {attempts_cmp} :max_attempts
          AND NOT (p.name = ANY(:skip))
        GROUP BY p.id, p.name
        HAVING {_having(targets)}
        ORDER BY cnt DESC, p.name
    """
    params: dict = {"skip": list(skip), "max_attempts": DEEP_MAX_ATTEMPTS}
    if limit:
        sql += " LIMIT :lim"
        params["lim"] = limit
    result = await session.execute(text(sql), params)
    return [(row[0], row[1]) for row in result.fetchall()]


async def count_targets(session, targets: str, skip: set[str]) -> int:
    rows = await load_targets(session, targets, None, skip)
    return len(rows)


async def dry_run(targets: str, limit: int) -> None:
    """แสดงรายชื่อร้านที่จะทำแล้วออก — อ่าน DB อย่างเดียว ไม่เปิด browser ไม่แตะเน็ต"""
    async with AsyncSessionLocal() as session:
        rows = await load_targets(session, targets, None, set())
        gave_up = await load_targets(session, targets, None, set(), given_up=True)
        log(f"เกณฑ์ '{targets}' — คิวที่ต้องทำ {len(rows)} ร้าน | "
            f"ยอมแพ้แล้ว {len(gave_up)} ร้าน")
        if gave_up:
            log(f"⛔ กลุ่มยอมแพ้ (ล้มเหลวครบ {DEEP_MAX_ATTEMPTS} ครั้ง — เข้าไม่ถึงหน้ารีวิว) "
                f"ไม่ถูกหยิบมาทำอีก แต่ deep_scanned_at ยังเป็น NULL:")
            for name, cnt in gave_up:
                print(f"       - {name[:55]:<55} {cnt:>5} รีวิว")
            log("   กลุ่มนี้คือชุดที่ควรไปตรวจซ้ำด้วย Places API")
        if not rows:
            return
        for i, (name, cnt) in enumerate(rows, 1):
            marker = "  <- รอบแรก" if i <= limit else ""
            print(f"  {i:3d}. {name[:55]:<55} {cnt:>5} รีวิว{marker}")
        rounds = (len(rows) + limit - 1) // limit
        log(f"รอบละ {limit} ร้าน → ประมาณ {rounds} รอบ (ยังไม่รวมเวลาพักระหว่างรอบ)")


async def scan_loop(targets: str, limit: int, wait_min: int) -> str:
    """วน deep scan จนครบ คืนสถานะ: 'done' | 'blocked' | 'maxrounds'"""
    attempted: set[str] = set()
    total_places = 0
    total_reviews = 0
    block_count = 0

    async with AsyncSessionLocal() as session:
        start_total = await count_targets(session, targets, attempted)
        log(f"เริ่ม deep scan — เกณฑ์ '{targets}' | ต้องทำ {start_total} ร้าน "
            f"(รอบละ {limit}, พัก {wait_min} นาที)")
        if start_total == 0:
            log("ไม่มีร้านที่เข้าเกณฑ์ — จบ")
            return "done"

        for rnd in range(1, MAX_ROUNDS + 1):
            batch = await load_targets(session, targets, limit, attempted)
            if not batch:
                log(f"ครบทุกร้านแล้ว (จบที่รอบ {rnd - 1})")
                log(f"รวม {total_places} ร้าน | รีวิวใหม่ {total_reviews} รายการ")
                return "done"

            remaining = await count_targets(session, targets, attempted)
            log(f"-- รอบ {rnd} | เหลือ {remaining} ร้าน | รอบนี้ทำ {len(batch)} ร้าน --")
            for name, cnt in batch:
                log(f"   . {name[:55]} (ตอนนี้ {cnt} รีวิว)")

            result = await run_deep_scan(session, [n for n, _ in batch], headless=True)
            total_places += result.get("places", 0)
            total_reviews += result.get("reviews_new", 0)
            dur = result.get("duration_sec", 0)
            log(f"   ทำได้ {result.get('places', 0)} ร้าน | "
                f"รีวิวใหม่ {result.get('reviews_new', 0)} | ใช้เวลา {dur:.0f} วิ")

            if result.get("blocked"):
                if block_count >= len(BLOCK_BACKOFF_HOURS):
                    log(f"โดนบล็อกซ้ำ {block_count} ครั้งแม้พักยาวแล้ว — หยุดจริง")
                    log("   แนะนำเปลี่ยน IP (mobile hotspot / VPN) แล้วรัน deep_scan ใหม่")
                    return "blocked"
                hrs = BLOCK_BACKOFF_HOURS[block_count]
                block_count += 1
                log(f"เจอสัญญาณบล็อก ({result['blocked']}) — พัก {hrs} ชม. แล้วลองใหม่ "
                    f"(ครั้งที่ {block_count}/{len(BLOCK_BACKOFF_HOURS)})")
                # ไม่ใส่ batch ลง attempted — ร้านที่ยังไม่ได้ทำต้องถูกหยิบมาใหม่หลังพัก
                await asyncio.sleep(hrs * 3600)
                continue

            block_count = 0
            # รอบนี้จบปกติ — ร้านที่สำเร็จถูกตี deep_scanned_at ใน DB ไปแล้ว
            # ที่เหลือ (หน้าโหลดไม่ขึ้น ฯลฯ) กันไว้ไม่ให้วนซ้ำในการรันครั้งนี้
            attempted.update(n for n, _ in batch)

            if await count_targets(session, targets, attempted) == 0:
                log(f"ครบทุกร้านแล้ว (จบที่รอบ {rnd})")
                log(f"รวม {total_places} ร้าน | รีวิวใหม่ {total_reviews} รายการ")
                return "done"

            log(f"   พัก {wait_min} นาที...")
            await asyncio.sleep(wait_min * 60)

        log(f"ครบ {MAX_ROUNDS} รอบแล้วยังไม่จบ — หยุดกันวนไม่รู้จบ")
        return "maxrounds"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Deep scan — เก็บรีวิวให้ครบสำหรับร้านที่เก็บไม่ครบ"
    )
    parser.add_argument("--targets", choices=["capped", "zero", "shallow", "all"],
                        default="capped", help="กลุ่มร้านที่จะทำ (default capped)")
    parser.add_argument("--limit", type=int, default=5, help="ร้านต่อรอบ (default 5)")
    parser.add_argument("--wait", type=int, default=20, help="นาทีที่พักระหว่างรอบ (default 20)")
    parser.add_argument("--dry-run", action="store_true", help="แสดงรายชื่อร้านแล้วออก ไม่ scrape")
    args = parser.parse_args()

    if args.dry_run:
        asyncio.run(dry_run(args.targets, args.limit))
    else:
        status = asyncio.run(scan_loop(args.targets, args.limit, args.wait))
        log(f"จบการทำงาน (สถานะ: {status})")
        log("รีวิวใหม่ยังไม่ถูกวิเคราะห์ — สั่งเองเมื่อพร้อม: uv run python scripts/analyze.py")
