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

# ── ตัวตัดวงจรเมื่อ Google จำกัดอัตราแบบเงียบ ──
#
# เกิดขึ้นจริง 25-26 ก.ย. 2026: Google เสิร์ฟรีวิวให้น้อยลงเรื่อย ๆ จนเกือบศูนย์
# โดย**ไม่ขึ้น CAPTCHA และไม่ขึ้นหน้า sorry** ตัวตรวจจับบล็อกเดิมดูแค่สองอย่างนั้น
# จึงไม่ทำงาน งาน refresh จบด้วย status='done' ทุกรอบ ระบบรันต่ออีก 10 ชั่วโมง
# แล้วตี scraped_at ให้ร้าน 131 แห่งที่เก็บได้ไม่ถึง 20% ของที่ควรได้
#
# วัดรายชั่วโมงแล้วแยกได้ชัด: ชั่วโมงที่ทำงานปกติได้ 86-91% ของเพดาน
# ชั่วโมงที่พังได้ 13-31% → ตั้งเส้นแบ่งที่ 40% แยกสองกลุ่มนี้ออกจากกันสบาย
#
# วัดจาก "ร้านที่ scrape ในรอบนี้" เทียบ LEAST(google_reviews_total, 850)
# ไม่ใช้ reviews_new เพราะร้านที่เก็บครบแล้วจะได้ 0 อย่างถูกต้อง แยกจากความล้มเหลวไม่ได้
YIELD_MIN_RATIO = 0.40
# ต้องมีปริมาณที่คาดหวังพอสมควรก่อนตัดสิน ไม่งั้นรอบที่เจอร้านเล็ก 3 ร้านจะสะดุด
YIELD_MIN_EXPECTED = 200


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

    รวมตัวกรอง NOT scrape_excluded ด้วย — ร้านนอกขอบเขต (โรงแรม/เชน/ห้าง)
    ไม่ถูกนับเป็นงานเหลือ เพราะ load_places_to_refresh ไม่หยิบมาทำ
    """
    r = await session.execute(
        text("""
            SELECT COUNT(*) FROM places
            WHERE NOT scrape_excluded
              AND (scraped_at IS NULL
               OR scraped_at < NOW() - (
                    CASE
                        WHEN COALESCE(consecutive_no_change, 0) >= 3 THEN INTERVAL '30 days'
                        WHEN COALESCE(consecutive_no_change, 0) = 2  THEN INTERVAL '14 days'
                        ELSE INTERVAL '7 days'
                    END
                  ))
        """)
    )
    return r.scalar()


async def round_yield(session, since) -> tuple[int, int, float | None]:
    """
    รอบที่เพิ่งจบเก็บรีวิวได้กี่ % ของที่ควรได้

    คืน (เก็บได้, เพดานที่ควรได้, สัดส่วน) — สัดส่วนเป็น None ถ้าวัดไม่ได้
    (ไม่มีร้านที่มี google_reviews_total ในรอบนั้น หรือปริมาณน้อยเกินตัดสิน)

    อ่านจาก DB ด้วย scraped_at ของร้าน ไม่ต้องแก้ run_refresh ให้คืนรายชื่อร้าน

    ⚠️ ตัวส่วนใช้ LEAST(google_reviews_total, 850) ไม่ใช่ google_reviews_total
      เพราะ Google เสิร์ฟผ่าน scroll ได้สูงสุดราว 850/ร้าน ถ้าเทียบกับยอดเต็ม
      ร้านใหญ่จะดูล้มเหลวทั้งหมดทั้งที่ทำได้เต็มที่แล้ว (วัดพระศรีฯ 832/10,058)
    """
    r = (await session.execute(
        text("""
            SELECT
              coalesce(sum((SELECT count(*) FROM reviews rv
                            WHERE rv.place_id = p.id)), 0) AS got,
              coalesce(sum(LEAST(p.google_reviews_total, 850)), 0) AS expected
            FROM places p
            WHERE p.scraped_at >= :since
              AND p.google_reviews_total IS NOT NULL
              AND p.google_reviews_total >= 50
        """), {"since": since})).fetchone()
    got, expected = int(r.got or 0), int(r.expected or 0)
    if expected < YIELD_MIN_EXPECTED:
        return got, expected, None
    return got, expected, got / expected


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

            round_start = datetime.now()
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

            # ── ไม่เจอสัญญาณบล็อก แต่เก็บได้น้อยผิดปกติ = ถูกจำกัดอัตราแบบเงียบ ──
            # ปฏิบัติเหมือนโดนบล็อก เพราะผลเสียเหมือนกัน: รันต่อได้แต่ไม่ได้ข้อมูล
            # และแย่กว่าตรงที่ระบบตี scraped_at ให้ร้านที่ยังไม่ได้เก็บจริง
            got, expected, ratio = await round_yield(session, round_start)
            if ratio is not None and ratio < YIELD_MIN_RATIO:
                log(f"   ⚠️ เก็บได้ {got:,}/{expected:,} = {ratio * 100:.0f}% "
                    f"ของที่ควรได้ (เกณฑ์ {YIELD_MIN_RATIO * 100:.0f}%)")
                if block_count >= len(BLOCK_BACKOFF_HOURS):
                    log(f"🛑 เก็บได้ต่ำผิดปกติซ้ำ {block_count} ครั้งแม้พักยาวแล้ว — หยุด")
                    log("   Google น่าจะจำกัดอัตราแบบเงียบ (ไม่ขึ้น CAPTCHA แต่เสิร์ฟให้น้อย)")
                    log("   แนะนำ: เปลี่ยน IP (mobile hotspot / VPN) แล้วรันใหม่ด้วย --limit น้อยลง")
                    log("   ร้านที่เก็บได้ไม่ครบในรอบนี้: "
                        "uv run python scripts/requeue_shortfall.py")
                    return "throttled"
                hrs = BLOCK_BACKOFF_HOURS[block_count]
                block_count += 1
                log(f"🛑 น่าจะถูกจำกัดอัตราแบบเงียบ — พัก {hrs} ชม. แล้วลองใหม่ "
                    f"(ครั้งที่ {block_count}/{len(BLOCK_BACKOFF_HOURS)})")
                await asyncio.sleep(hrs * 3600)
                continue
            if ratio is not None:
                log(f"   เก็บได้ {got:,}/{expected:,} = {ratio * 100:.0f}% ของที่ควรได้")

            # ไม่โดนบล็อกและเก็บได้ปกติ → รีเซ็ตตัวนับ
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
    elif status == "throttled":
        log("ข้าม analyze/classify เพราะเก็บรีวิวได้ต่ำผิดปกติ (น่าจะถูกจำกัดอัตราแบบเงียบ)")
        log("  1. เปลี่ยน IP (mobile hotspot / VPN)")
        log("  2. uv run python scripts/requeue_shortfall.py          # ดูร้านที่เก็บไม่ครบ")
        log("  3. uv run python scripts/requeue_shortfall.py --apply  # ส่งกลับเข้าคิว")
        log("  4. uv run python scripts/auto_refresh.py --limit 20    # รันใหม่ช้าลง")

    log("จบการทำงาน")
