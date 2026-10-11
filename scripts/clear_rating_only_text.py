"""
clear_rating_only_text.py — ล้าง text_clean ของรีวิวที่ "ให้ดาวอย่างเดียว"

ปัญหาที่แก้ (พบ 2026-10-11 จากข้อสังเกตของผู้ใช้):
  ผู้รีวิวที่กดดาวแล้วไม่เขียนอะไร ยังมีการ์ดที่ประกอบด้วย
  ชื่อผู้รีวิว / ไอคอนดาว / วันที่ / เมตา ("อาหาร: 5", "ราคาต่อคน", "฿200-300")
  clean_review_text() ตัดไอคอนกับคำ UI ออกได้ แต่ตัดชื่อคนและค่าเมตาไม่ออก
  เศษที่เหลือจึงถูกเก็บเป็น "เนื้อรีวิว"

  ตัวอย่างจริง
    id=201127  ดิบ 'Awadsada Boonjaroen ... 8 เดือนที่แล้ว'  -> text_clean = ชื่อคน
    id=201110  ดิบ '... ปีที่แล้ว ราคาต่อคน ฿200-300…'       -> text_clean = '฿200-300'

  วัดได้ 6,020 แถว = 7.62% ของรีวิวที่ระบบถือว่า "มีข้อความ"
  ทั้งหมดอยู่ในตัวส่วนของอัตราการบ่นและทุกสัดส่วนบนแดชบอร์ดและในรายงาน
  และพองหมวด "ความคิดเห็นทั่วไป" ขึ้น 3,944 แถว

⚠️ ทำไมตั้ง text_clean = '' แทนที่จะลบแถว
  1. รีวิวพวกนี้ "มีอยู่จริง" — เป็นการให้ดาวที่นับรวมใน google_reviews_total
     ลบทิ้งจะทำให้ความครบของข้อมูลเพี้ยนและจะถูก scrape กลับมาใหม่ทุกครั้ง
  2. ทุก endpoint และรายงานกรองด้วย text_clean <> '' อยู่แล้ว
     ตั้งเป็นค่าว่างจึงหลุดจากทุกตัวส่วนทันทีโดยไม่ต้องแก้คิวรีสักบรรทัด
  3. ไปรวมอยู่กับรีวิวให้ดาวเปล่าอีก 35,064 แถวที่ text_clean = '' อยู่แล้ว
     ซึ่งเป็นที่ที่มันควรอยู่ตั้งแต่แรก

⚠️ ไม่แตะ text และไม่แตะ text_hash เด็ดขาด
  text_hash คำนวณจาก clean_review_text(text) ตอน INSERT
  ถ้าแก้ text หรือแก้ตัวล้าง รีวิวเดิมจะถูก INSERT ซ้ำทั้งฐาน
  (บั๊กเดิมที่เคยทำให้มีแถวซ้ำ 3,453 แถว)
  สคริปต์นี้แก้เฉพาะ text_clean ซึ่งเป็นค่าที่ derive มาแล้ว ไม่ใช่ตัวระบุตัวตน

⚠️ ต้นเหตุถูกปิดแล้วที่ scraper/scraper_core.py
  extract_reviews() ข้ามการ์ดที่ is_rating_only() เป็นจริงตั้งแต่ตอนเก็บ
  สคริปต์นี้จึงเป็นการล้างของเก่าครั้งเดียว ไม่ใช่งานที่ต้องรันประจำ

ใช้งาน
  uv run python scripts/clear_rating_only_text.py            # DRY-RUN
  uv run python scripts/clear_rating_only_text.py --apply
  uv run python scripts/clear_rating_only_text.py --restore <ไฟล์สำรอง>
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from nlp.text_cleaner import is_rating_only

BACKUP_DIR = Path(__file__).resolve().parent.parent / "backup"
CHUNK = 500


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


async def scan(session) -> list[tuple[int, str]]:
    """คืน [(review_id, text_clean เดิม), ...] ของแถวที่เข้าข่าย"""
    rows = (await session.execute(text("""
        SELECT id, text, text_clean FROM reviews
        WHERE text_clean IS NOT NULL AND text_clean <> ''
    """))).fetchall()
    return [(r.id, r.text_clean) for r in rows if is_rating_only(r.text)]


async def run(apply: bool, restore: str | None) -> None:
    async with AsyncSessionLocal() as session:
        if restore:
            data = json.loads(Path(restore).read_text(encoding="utf-8"))
            p(f"กู้คืน {len(data):,} แถว จาก {restore}")
            for i in range(0, len(data), CHUNK):
                part = data[i:i + CHUNK]
                await session.execute(
                    text("""
                        UPDATE reviews AS r SET text_clean = v.tc
                        FROM (SELECT UNNEST(CAST(:ids AS int[])) AS id,
                                     UNNEST(CAST(:tcs AS text[])) AS tc) AS v
                        WHERE r.id = v.id
                    """),
                    {"ids": [x[0] for x in part], "tcs": [x[1] for x in part]},
                )
            await session.commit()
            p("กู้คืนเรียบร้อย")
            return

        total = (await session.execute(text(
            "SELECT count(*) FROM reviews WHERE text_clean <> ''"))).scalar()
        hits = await scan(session)
        p(f"รีวิวที่ระบบถือว่ามีข้อความ : {total:,}")
        p(f"เข้าข่ายให้ดาวอย่างเดียว    : {len(hits):,} "
          f"({len(hits) / total * 100:.2f}%)")
        p("")
        p("ตัวอย่าง 10 รายการ:")
        for rid, tc in hits[:10]:
            p(f"   id={rid:<8} [{len(tc):>2}] {tc[:50]}")

        if not apply:
            p("")
            p("นี่คือ DRY-RUN — ยังไม่เขียนอะไรลงฐานข้อมูล")
            p("ลงมือจริงด้วย: uv run python scripts/clear_rating_only_text.py --apply")
            return

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = BACKUP_DIR / f"rating_only_text_{stamp}.json"
        bak.write_text(json.dumps(hits, ensure_ascii=False), encoding="utf-8")
        p("")
        p(f"สำรอง text_clean เดิมไว้แล้ว -> {bak}")

        for i in range(0, len(hits), CHUNK):
            part = [x[0] for x in hits[i:i + CHUNK]]
            await session.execute(
                text("UPDATE reviews SET text_clean = '' WHERE id = ANY(:ids)"),
                {"ids": part})
        await session.commit()

        # ยืนยันจากฐานข้อมูลจริง ไม่ใช่เชื่อว่า UPDATE สำเร็จ
        left = (await session.execute(
            text("SELECT count(*) FROM reviews WHERE id = ANY(:ids) "
                 "AND text_clean <> ''"),
            {"ids": [x[0] for x in hits]})).scalar()
        after = (await session.execute(text(
            "SELECT count(*) FROM reviews WHERE text_clean <> ''"))).scalar()
        p(f"อัปเดตแล้ว {len(hits):,} แถว | ยังเหลือที่ไม่ว่าง {left} แถว")
        p(f"รีวิวที่มีข้อความ {total:,} -> {after:,}")
        p("")
        p(f"ย้อนกลับได้ด้วย: uv run python scripts/clear_rating_only_text.py "
          f"--restore {bak}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="ล้าง text_clean ของรีวิวที่ให้ดาวอย่างเดียว")
    ap.add_argument("--apply", action="store_true",
                    help="เขียนลงฐานข้อมูลจริง (ไม่ใส่ = DRY-RUN)")
    ap.add_argument("--restore", metavar="FILE",
                    help="กู้ค่า text_clean เดิมจากไฟล์สำรอง")
    args = ap.parse_args()
    asyncio.run(run(apply=args.apply, restore=args.restore))
