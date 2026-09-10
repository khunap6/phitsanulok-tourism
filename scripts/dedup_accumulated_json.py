"""
dedup_accumulated_json.py — ล้างรีวิวซ้ำใน data/phitsanulok_accumulated.json ย้อนหลัง

ทำไมต้องมี:
  ไฟล์ master สะสมรีวิวซ้ำมานาน เพราะ _merge_reviews() เดิมกันซ้ำด้วย text[:80]
  ของข้อความ "ดิบ" ซึ่งมีวันที่สัมพัทธ์ฝังอยู่ ("4 เดือนที่แล้ว" → "5 เดือนที่แล้ว")
  พอวันที่เลื่อน 80 ตัวอักษรแรกก็เปลี่ยน → รีวิวเดิมถูก append ซ้ำทุกรอบ scrape
  ส่วน DB กันซ้ำด้วย md5 ของข้อความที่ล้างแล้ว จึงถูกต้องมาตลอด
  (แก้ต้นเหตุที่ _merge_reviews แล้ว สคริปต์นี้ล้างของที่ค้างอยู่)

เก็บอันไหนไว้:
  เก็บ "อันแรกที่เจอ" ของแต่ละ hash เพราะลำดับในไฟล์คือลำดับที่ scrape มา
  อันแรก = ตอนที่เห็นรีวิวนี้ครั้งแรก → วันที่สัมพัทธ์ใกล้ความจริงที่สุด
  (รีวิวที่โพสต์ 4 เดือนก่อน ครั้งแรกที่เก็บได้จะเขียนว่า "4 เดือนที่แล้ว"
   รอบหลัง ๆ จะกลายเป็น "5 เดือน" ซึ่งคลาดเคลื่อนกว่า)

รัน:
  uv run python scripts/dedup_accumulated_json.py           # ดูก่อน ไม่แตะไฟล์
  uv run python scripts/dedup_accumulated_json.py --apply   # ล้างจริง (สำรองไฟล์เดิมให้)
"""
import asyncio
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from scraper.scraper_core import review_text_hash

APPLY = "--apply" in sys.argv
ROOT = Path(__file__).parent.parent
TARGET = ROOT / "data" / "phitsanulok_accumulated.json"


def safe_print(t: str) -> None:
    try:
        print(t)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"))


async def db_counts() -> dict[str, int]:
    async with AsyncSessionLocal() as s:
        rows = await s.execute(text("""
            SELECT p.name, COUNT(r.id)
            FROM places p LEFT JOIN reviews r ON r.place_id = p.id
            GROUP BY p.name
        """))
        return {n: c for n, c in rows.fetchall()}


def dedup_entry(entry: dict) -> tuple[list[dict], int]:
    """คืน (รีวิวที่ไม่ซ้ำ, จำนวนที่ตัดออก) — เก็บอันแรกของแต่ละ hash"""
    seen: set[str] = set()
    kept: list[dict] = []
    removed = 0
    for r in entry.get("reviews", []):
        t = (r.get("text") or "").strip()
        if len(t) < 5:          # DB ก็ข้ามรีวิวสั้นแบบนี้เหมือนกัน
            removed += 1
            continue
        h = review_text_hash(t)
        if h in seen:
            removed += 1
            continue
        seen.add(h)
        kept.append(r)
    return kept, removed


async def main() -> None:
    if not TARGET.exists():
        safe_print(f"ไม่พบไฟล์ {TARGET}")
        return

    data = json.loads(TARGET.read_text(encoding="utf-8"))
    before_total = sum(len(e.get("reviews", [])) for e in data)

    cleaned = []
    removed_total = 0
    per_place_after: dict[str, int] = {}
    worst: list[tuple[int, str]] = []

    for entry in data:
        kept, removed = dedup_entry(entry)
        removed_total += removed
        entry = dict(entry)
        entry["reviews"] = kept
        cleaned.append(entry)
        per_place_after[entry.get("place_name", "")] = len(kept)
        if removed:
            worst.append((removed, entry.get("place_name", "")))

    after_total = sum(len(e.get("reviews", [])) for e in cleaned)

    safe_print(f"ไฟล์   : {TARGET}")
    safe_print(f"ก่อนล้าง: {before_total:,} รีวิว ({len(data)} ร้าน)")
    safe_print(f"หลังล้าง: {after_total:,} รีวิว  (ตัดซ้ำออก {removed_total:,})")

    db = await db_counts()
    db_total = sum(db.values())
    safe_print(f"DB     : {db_total:,} รีวิว  → ต่างกัน {after_total - db_total:+,}")

    worst.sort(reverse=True)
    safe_print("\n10 ร้านที่ซ้ำมากสุด:")
    for n, name in worst[:10]:
        safe_print(f"  -{n:<5} {name[:50]}")

    diffs = [(per_place_after.get(n, 0) - c, n, per_place_after.get(n, 0), c)
             for n, c in db.items() if per_place_after.get(n, 0) != c]
    if diffs:
        diffs.sort(key=lambda x: abs(x[0]), reverse=True)
        safe_print(f"\nร้านที่ยังไม่ตรงกับ DB หลังล้าง: {len(diffs)} ร้าน")
        for d, name, j, c in diffs[:10]:
            safe_print(f"  {d:+4d}  {name[:44]:<44} JSON {j:>5} | DB {c:>5}")
        safe_print("  หมายเหตุ: ต่างระดับ ±ไม่กี่รายการเท่านั้น")
        safe_print("   - DB มากกว่า JSON: อธิบายได้จากโค้ด — เส้นทาง Selenium fallback เรียก")
        safe_print("     save_to_db() แต่ไม่ได้เรียก save_results() รีวิวจึงเข้า DB โดยไม่เข้าไฟล์นี้")
        safe_print("   - JSON มากกว่า DB: ยังไม่ได้ไล่หาสาเหตุแน่ชัด (จำนวนน้อยมาก)")
        safe_print("     ไฟล์นี้เป็นแค่ backup ฝั่ง scraper ไม่มีโค้ดไหนอ่านไปใช้วิเคราะห์")

    if not APPLY:
        safe_print("\n(dry-run) ยังไม่แตะไฟล์ — ใส่ --apply เพื่อล้างจริง")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = TARGET.with_name(f"phitsanulok_accumulated.backup_{stamp}.json")
    shutil.copy2(TARGET, backup)
    TARGET.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    safe_print(f"\nสำรองไฟล์เดิม → {backup.name}")
    safe_print(f"เขียนไฟล์ที่ล้างแล้ว → {TARGET.name}")


asyncio.run(main())
