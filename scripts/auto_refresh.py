"""
auto_refresh.py — เก็บข้อมูลที่ขาดจากร้านเดิมแบบอัตโนมัติ (คำสั่งเดียว เดินจากเครื่องได้)

ทำงานวนเอง:
  1. เช็คว่ายังมีร้านที่ต้องทำไหม (scraped_at เก่ากว่า 7 วัน) → ถ้าไม่มี = จบ
  2. scrape N ร้าน (default 40)
  3. ตรวจจับการโดนบล็อก (ถ้าได้ทั้งรีวิว 0 + เวลาเปิด 0 ติดกัน 2 รอบ → หยุดเตือน)
  4. รอ M นาที (default 15) แล้ววนกลับข้อ 1
  5. เมื่อครบทุกร้าน → รัน analyze + classify ให้อัตโนมัติ

รัน:
  uv run python scripts/auto_refresh.py                    # เต็มรูปแบบ (แนะนำ)
  uv run python scripts/auto_refresh.py --limit 40 --wait 15
  uv run python scripts/auto_refresh.py --no-followup      # ไม่ต่อ analyze/classify

⚠️ ต้องเปิดเครื่อง + terminal ค้างไว้ตลอด (ใช้เวลาหลายชั่วโมง)
"""
import argparse
import asyncio
import subprocess
import sys
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from db.database import AsyncSessionLocal
from scraper.scraper import run_refresh

MAX_ROUNDS = 30  # กันวนไม่รู้จบในกรณีผิดปกติ


def log(msg: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{stamp}] {msg}"
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", errors="replace").decode("ascii"), flush=True)


async def eligible_count(session) -> int:
    """จำนวนร้านที่ยังต้อง refresh (scrape เกิน 7 วัน หรือยังไม่เคย)"""
    r = await session.execute(
        text("""SELECT COUNT(*) FROM places
                WHERE scraped_at IS NULL OR scraped_at < NOW() - INTERVAL '7 days'""")
    )
    return r.scalar()


async def hours_count(session) -> int:
    """จำนวนร้านที่มีเวลาเปิด-ปิดแล้ว (ใช้ตรวจว่ารอบนี้เก็บข้อมูลได้จริงไหม)"""
    r = await session.execute(text("SELECT COUNT(*) FROM places WHERE opening_hours IS NOT NULL"))
    return r.scalar()


async def scrape_loop(limit: int, wait_min: int) -> str:
    """วน scrape จนครบ คืนสถานะจบ: 'done' | 'blocked' | 'maxrounds'"""
    async with AsyncSessionLocal() as session:
        total_start = await eligible_count(session)
        log(f"เริ่ม auto-refresh — ร้านที่ต้องทำ {total_start} ร้าน (รอบละ {limit}, พัก {wait_min} นาที)")
        if total_start == 0:
            log("ไม่มีร้านที่ต้อง refresh (ทุกร้าน scrape ภายใน 7 วันแล้ว)")
            return "done"

        bad_streak = 0
        for rnd in range(1, MAX_ROUNDS + 1):
            remaining = await eligible_count(session)
            if remaining == 0:
                log(f"✅ ครบทุกร้านแล้ว (จบที่รอบ {rnd - 1})")
                return "done"

            log(f"── รอบ {rnd} | เหลือ {remaining} ร้าน ──")
            hours_before = await hours_count(session)

            result = await run_refresh(session, headless=True, max_places=limit)
            reviews_new = result.get("reviews_new", 0)
            places_done = result.get("places", 0)

            hours_after = await hours_count(session)
            new_hours = hours_after - hours_before

            log(f"   ทำ {places_done} ร้าน | รีวิวใหม่ {reviews_new} | เวลาเปิดใหม่ {new_hours}")

            # ตรวจจับบล็อก: ทำร้านไปแล้วแต่ไม่ได้ทั้งรีวิวและเวลาเปิด = น่าจะโดนบล็อก
            if places_done > 0 and reviews_new == 0 and new_hours == 0:
                bad_streak += 1
                log(f"   ⚠️  รอบนี้ไม่ได้ข้อมูลใหม่เลย (streak {bad_streak}/2)")
                if bad_streak >= 2:
                    log("🛑 น่าจะโดน Google บล็อก — หยุดอัตโนมัติ")
                    log("   ลองเปลี่ยน IP (mobile hotspot) หรือรอสักพักแล้วรันใหม่")
                    return "blocked"
            else:
                bad_streak = 0

            # เช็คอีกทีว่าจบหรือยัง (ถ้าจบ ไม่ต้องรอ)
            if await eligible_count(session) == 0:
                log(f"✅ ครบทุกร้านแล้ว (จบที่รอบ {rnd})")
                return "done"

            log(f"   ⏳ พัก {wait_min} นาที...")
            await asyncio.sleep(wait_min * 60)

        log(f"⚠️  ครบ {MAX_ROUNDS} รอบแล้วยังไม่จบ — หยุดกันวนไม่รู้จบ")
        return "maxrounds"


def run_followup():
    """รัน analyze + classify ต่ออัตโนมัติ (ใช้ interpreter เดียวกัน)"""
    py = sys.executable
    log("── ต่อ: วิเคราะห์ NLP (analyze.py) ──")
    subprocess.run([py, "scripts/analyze.py"], check=False)
    log("── ต่อ: จัดหมวด 'อื่นๆ' ด้วย Claude (classify_other_llm.py) ──")
    subprocess.run([py, "scripts/classify_other_llm.py"], check=False)
    log("✅ analyze + classify เสร็จ")


async def _amain(limit, wait_min):
    return await scrape_loop(limit, wait_min)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=40, help="ร้านต่อรอบ (default 40)")
    parser.add_argument("--wait", type=int, default=15, help="นาทีที่พักระหว่างรอบ (default 15)")
    parser.add_argument("--no-followup", action="store_true", help="ไม่ต่อ analyze/classify")
    args = parser.parse_args()

    status = asyncio.run(_amain(args.limit, args.wait))

    # ต่อ analyze + classify เฉพาะเมื่อ scrape จบครบ (ไม่ต่อถ้าโดนบล็อก)
    if status == "done" and not args.no_followup:
        run_followup()
    elif status == "blocked":
        log("ข้าม analyze/classify เพราะ scrape ไม่ครบ — รัน auto_refresh ใหม่หลังแก้ปัญหาบล็อก")

    log("จบการทำงาน")
