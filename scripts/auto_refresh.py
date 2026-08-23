"""
auto_refresh.py — เก็บข้อมูลที่ขาดจากร้านเดิมแบบอัตโนมัติ (คำสั่งเดียว เดินจากเครื่องได้)

ทำงานวนเอง:
  1. เช็คว่ายังมีร้านที่ต้องทำไหม (adaptive cooldown 7/14/30 วัน) → ถ้าไม่มี = จบ
  2. scrape N ร้าน (default 40) แบบ incremental (หยุด scroll เมื่อชนรีวิวเดิม)
  3. ถ้าเจอสัญญาณบล็อกจริง (CAPTCHA/sorry-page) → พักยาวขึ้น 2→4→6 ชม.
     แล้วลองใหม่เอง (เกิน 3 ครั้งค่อยหยุดจริงให้ไปเปลี่ยน IP)
  4. รอ M นาที (default 15) แล้ววนกลับข้อ 1
  5. เมื่อครบทุกร้าน → รัน analyze + classify + snapshot ให้อัตโนมัติ

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
    """
    จำนวนร้านที่ยังต้อง refresh — ต้องใช้เกณฑ์เดียวกับ load_places_to_refresh()
    (adaptive cooldown: ร้านนิ่งจะถูกเว้นนานขึ้น) ไม่งั้น loop จะวนไม่จบ
    เพราะนับว่ามีงานเหลือ แต่ run_refresh ไม่หยิบร้านไหนมาทำ
    """
    r = await session.execute(
        text("""
            SELECT COUNT(*) FROM places
            WHERE scraped_at IS NULL
               OR scraped_at < NOW() - (
                    CASE
                        WHEN COALESCE(consecutive_no_change, 0) >= 3 THEN INTERVAL '30 days'
                        WHEN COALESCE(consecutive_no_change, 0) = 2  THEN INTERVAL '14 days'
                        ELSE INTERVAL '7 days'
                    END
                  )
        """)
    )
    return r.scalar()


async def cooldown_summary(session) -> str:
    """สรุปว่าร้านถูกจัดกลุ่มรอบ scan ยังไง (ใช้รายงานผลตอนจบ)"""
    r = await session.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE COALESCE(consecutive_no_change,0) = 0)  AS active,
                COUNT(*) FILTER (WHERE COALESCE(consecutive_no_change,0) = 1)  AS w7,
                COUNT(*) FILTER (WHERE COALESCE(consecutive_no_change,0) = 2)  AS w14,
                COUNT(*) FILTER (WHERE COALESCE(consecutive_no_change,0) >= 3) AS w30
            FROM places
        """)
    )
    x = r.fetchone()
    return (f"รอบ scan: มีรีวิวใหม่ล่าสุด {x.active} ร้าน | "
            f"เว้น 7 วัน {x.w7} | เว้น 14 วัน {x.w14} | เว้น 30 วัน {x.w30}")


async def scrape_loop(limit: int, wait_min: int) -> str:
    """วน scrape จนครบ คืนสถานะจบ: 'done' | 'blocked' | 'maxrounds'"""
    async with AsyncSessionLocal() as session:
        total_start = await eligible_count(session)
        log(f"เริ่ม auto-refresh — ร้านที่ต้องทำ {total_start} ร้าน (รอบละ {limit}, พัก {wait_min} นาที)")
        if total_start == 0:
            log("ไม่มีร้านที่ต้อง refresh (ทุกร้าน scrape ภายใน 7 วันแล้ว)")
            return "done"

        # B3: เมื่อเจอบล็อกจริง → พักยาวขึ้นเรื่อยๆ แล้วลองใหม่เอง (2 → 4 → 6 ชม.)
        BLOCK_BACKOFF_HOURS = [2, 4, 6]
        block_count = 0

        for rnd in range(1, MAX_ROUNDS + 1):
            remaining = await eligible_count(session)
            if remaining == 0:
                log(f"✅ ครบทุกร้านแล้ว (จบที่รอบ {rnd - 1})")
                return "done"

            log(f"── รอบ {rnd} | เหลือ {remaining} ร้าน ──")

            result = await run_refresh(session, headless=True, max_places=limit)
            reviews_new = result.get("reviews_new", 0)
            places_done = result.get("places", 0)
            blocked = result.get("blocked")
            dur = result.get("duration_sec", 0)
            per_place = dur / places_done if places_done else 0
            log(f"   ทำ {places_done} ร้าน | รีวิวใหม่ {reviews_new} "
                f"| ใช้เวลา {dur:.0f} วิ ({per_place:.1f} วิ/ร้าน)")

            # ── เจอสัญญาณบล็อกจริง (CAPTCHA/sorry-page) — พักยาวแล้วลองใหม่ ──
            if blocked:
                if block_count >= len(BLOCK_BACKOFF_HOURS):
                    log(f"🛑 โดนบล็อกซ้ำ {block_count} ครั้งแม้พักยาวแล้ว — หยุดจริง")
                    log("   แนะนำเปลี่ยน IP (mobile hotspot / VPN) แล้วรัน auto_refresh ใหม่")
                    return "blocked"
                hrs = BLOCK_BACKOFF_HOURS[block_count]
                block_count += 1
                log(f"🛑 เจอสัญญาณบล็อก ({blocked}) — พัก {hrs} ชม. แล้วลองใหม่อัตโนมัติ "
                    f"(ครั้งที่ {block_count}/{len(BLOCK_BACKOFF_HOURS)})")
                await asyncio.sleep(hrs * 3600)
                continue   # ไม่นับเป็นรอบเสีย ลองรอบเดิมใหม่

            # ไม่โดนบล็อก → รีเซ็ตตัวนับ
            block_count = 0

            # เช็คอีกทีว่าจบหรือยัง (ถ้าจบ ไม่ต้องรอ)
            if await eligible_count(session) == 0:
                log(f"✅ ครบทุกร้านแล้ว (จบที่รอบ {rnd})")
                log(f"   {await cooldown_summary(session)}")
                return "done"

            log(f"   ⏳ พัก {wait_min} นาที...")
            await asyncio.sleep(wait_min * 60)

        log(f"⚠️  ครบ {MAX_ROUNDS} รอบแล้วยังไม่จบ — หยุดกันวนไม่รู้จบ")
        return "maxrounds"


def run_followup():
    """รัน analyze + classify + เก็บ snapshot ต่ออัตโนมัติ (ใช้ interpreter เดียวกัน)"""
    py = sys.executable
    log("── ต่อ: วิเคราะห์ NLP (analyze.py) ──")
    subprocess.run([py, "scripts/analyze.py"], check=False)
    log("── ต่อ: จัดหมวด 'อื่นๆ' ด้วย Claude (classify_other_llm.py) ──")
    subprocess.run([py, "scripts/classify_other_llm.py"], check=False)

    # เก็บ snapshot หลังวิเคราะห์เสร็จ → มีจุดอ้างอิงให้เทียบว่ารอบหน้าอะไรเปลี่ยน
    label = datetime.now().strftime("%Y-%m-%d")
    log(f"── ต่อ: เก็บ snapshot สถิติ ({label}) ──")
    subprocess.run([py, "scripts/take_snapshot.py", "--label", label,
                    "--note", "เก็บอัตโนมัติหลัง auto_refresh"], check=False)

    log("✅ analyze + classify + snapshot เสร็จ")


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
