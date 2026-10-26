"""drop_out_of_scope_labels.py — ถอดรีวิวของสถานที่นอกขอบเขตออกจากชุดติดป้าย

⚠️ ทำไมต้องมี
  ธง places.in_scope ถูกใช้กรองที่ชั้นสถิติ (api/filters.py) ตั้งแต่ 2026-10-13
  แต่ **ไม่เคยถูกใช้กับไฟล์ชุดติดป้าย** ชุด gold และ silver จึงยังมีรีวิวของ
  สถานที่ที่ประกาศว่าอยู่นอกขอบเขตปนอยู่
    gold v2 (ใช้รายงานผลหลัก)  9 / 300 = 3.0%
    silver (ชุดเทรน)          49 / 996 = 4.9%
  ผลคือตัวเลขความแม่นยำที่รายงาน วัดบนข้อมูลที่กว้างกว่าขอบเขตที่ประกาศไว้

⚠️ เกณฑ์เดียวกับชั้นสถิติเป๊ะ — อ่าน places.in_scope จากฐาน ไม่ตีความเอง
  ถ้าเกณฑ์ขอบเขตเปลี่ยน ต้องรัน build_scope -> classify_scope -> apply_scope_to_db
  ก่อน แล้วค่อยรันตัวนี้ ไม่งั้นสองชั้นจะไม่ตรงกัน

⚠️ ไม่ลบข้อมูลดิบ รีวิวทุกใบยังอยู่ในฐานครบ นี่คือการถอนออกจาก *ชุดติดป้าย*
  เท่านั้น และสำรองไฟล์เดิมไว้ใน backup/ ทุกครั้งก่อนเขียน

⚠️ การถอดแถวออกจากชุดเทรน (silver) ทำให้โมเดลที่เทรนไว้แล้วไม่ตรงกับชุดใหม่
  ต้องเทรนใหม่และรัน seed sweep ใหม่ ไม่งั้นตัวเลขที่รายงานจะมาจากโมเดล
  ที่เห็นข้อมูลนอกขอบเขต สคริปต์นี้จะเตือนตอนจบว่าต้องทำอะไรต่อ

รัน:
  uv run python scripts/drop_out_of_scope_labels.py
  uv run python scripts/drop_out_of_scope_labels.py --write
"""
import argparse
import asyncio
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from db.database import engine  # noqa: E402

BACKUP_DIR = ROOT / "backup"

# (ชื่อที่อ่านเข้าใจ, path, ต้องเทรน/ประเมินใหม่ไหมถ้าเปลี่ยน)
#
# ⚠️ ต้องครบทั้งชุดเทรน *และ* ชุดประเมิน
#   รอบแรกล้างแต่ชุดเทรน (silver) แล้วเทรนใหม่ ปรากฏว่า baseline ทายบวกหมด
#   ได้ค่าเดิมเป๊ะ 0.3121 ซึ่งเป็นสัญญาณว่าชุดประเมินไม่ได้เปลี่ยน
#   เพราะชุดประเมินถูกเลือกด้วย reports/evaluation/gold300_clean_ids.txt
#   ซึ่งไม่ได้อยู่ในรายการตอนนั้น ผลคือเทรนด้วยข้อมูลสะอาดแต่วัดบนข้อมูลที่ปน
TARGETS = [
    ("ชุด gold v3", "reports/evaluation/gold_v3_2_labeled.csv", False),
    ("ชุดตรวจคน", "reports/evaluation/human_check_v3_blank.csv", False),
    ("silver_reviews", "data/labeling/silver_reviews.csv", True),
    ("silver_aspects", "data/labeling/silver_aspects.csv", True),
    ("gold reviews (ประเมิน)", "data/labeling/reviews_labeled.csv", True),
    ("gold aspects (ประเมิน)", "data/labeling/review_aspects.csv", True),
]

# ไฟล์รายการ id ของชุดประเมิน — เป็นข้อความล้วน ไม่ใช่ CSV จึงจัดการแยก
#   nlp/train/evaluate_multiaspect.py ใช้ไฟล์นี้กรองว่าจะวัดผลบนรีวิวใดบ้าง
CLEAN_IDS = "reports/evaluation/gold300_clean_ids.txt"


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    async with engine.connect() as c:
        oos = {str(r[0]) for r in (await c.execute(text("""
            SELECT r.id FROM reviews r JOIN places p ON p.id = r.place_id
            WHERE NOT p.in_scope"""))).all()}
        nplace = (await c.execute(text(
            "SELECT COUNT(*) FROM places WHERE NOT in_scope"))).scalar()
        by_place = (await c.execute(text("""
            SELECT p.id, p.name, COUNT(*) n FROM reviews r
            JOIN places p ON p.id = r.place_id
            WHERE NOT p.in_scope GROUP BY 1,2 ORDER BY n DESC"""))).all()
        # review_id ของแต่ละสถานที่นอกขอบเขต — ใช้บอกว่าแถวที่ถอดมาจากที่ไหน
        oos_by_place: dict[int, set[str]] = {}
        for pid, rid in (await c.execute(text("""
            SELECT r.place_id, r.id FROM reviews r
            JOIN places p ON p.id = r.place_id WHERE NOT p.in_scope"""))).all():
            oos_by_place.setdefault(pid, set()).add(str(rid))
    await engine.dispose()

    p(f"สถานที่นอกขอบเขต {nplace} แห่ง · รีวิวของสถานที่เหล่านั้น {len(oos):,} ใบ")
    p("")

    plan: list[tuple] = []
    need_retrain = False
    for lab, rel, retrain in TARGETS:
        f = ROOT / rel
        if not f.exists():
            p(f"  {lab:<20} ไม่มีไฟล์ — ข้าม")
            continue
        rows = list(csv.DictReader(open(f, encoding="utf-8-sig")))
        if not rows or "review_id" not in rows[0]:
            p(f"  {lab:<20} ไม่มีคอลัมน์ review_id — ข้าม")
            continue
        keep = [r for r in rows if r["review_id"] not in oos]
        drop = [r for r in rows if r["review_id"] in oos]
        mark = "  <- ต้องเทรนใหม่" if (drop and retrain) else ""
        p(f"  {lab:<20} {len(rows):>5} -> {len(keep):>5}  (ถอด {len(drop):>3}){mark}")
        if drop:
            plan.append((lab, f, rows, keep, drop))
            need_retrain = need_retrain or retrain

    # ไฟล์รายการ id ของชุดประเมิน
    ids_file = ROOT / CLEAN_IDS
    ids_plan = None
    if ids_file.exists():
        cur = ids_file.read_text(encoding="utf-8").split()
        keep_ids = [x for x in cur if x not in oos]
        drop_ids = [x for x in cur if x in oos]
        mark = "  <- ต้องประเมินใหม่" if drop_ids else ""
        p(f"  {'gold300_clean_ids':<20} {len(cur):>5} -> {len(keep_ids):>5}  "
          f"(ถอด {len(drop_ids):>3}){mark}")
        if drop_ids:
            ids_plan = (ids_file, cur, keep_ids, drop_ids)
            need_retrain = True

    if not plan and not ids_plan:
        p("")
        p("ไม่มีอะไรต้องถอด ทุกชุดตรงกับขอบเขตแล้ว")
        return

    # นับว่าแต่ละสถานที่เป็นต้นเหตุของการถอดกี่แถว รวมทุกชุด
    dropped_ids: list[str] = [r["review_id"] for _, _, _, _, d in plan for r in d]
    p("")
    p("สถานที่ที่เป็นต้นเหตุ (เฉพาะที่มีแถวถูกถอดจริง)")
    for pid, nm, n in by_place:
        hit = sum(1 for rid in dropped_ids if rid in oos_by_place.get(pid, set()))
        if hit:
            p(f"  place={pid:<6} {nm[:44]:<45} ถอด {hit:>3} แถว "
              f"(รีวิวในฐาน {n})")

    if not a.write:
        p("")
        p("DRY-RUN — ยังไม่เขียนไฟล์  ลงมือจริงด้วย --write")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"labelsets_before_scope_cleanup_{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    p("")
    for lab, f, rows, keep, drop in plan:
        shutil.copy2(f, dest / f.name)
        with open(f, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), quoting=csv.QUOTE_ALL)
            w.writeheader()
            w.writerows(keep)
        p(f"  เขียน {f.relative_to(ROOT)} ({len(keep)} แถว · ถอด {len(drop)})")
    if ids_plan:
        f, cur, keep_ids, drop_ids = ids_plan
        shutil.copy2(f, dest / f.name)
        f.write_text("\n".join(keep_ids) + "\n", encoding="utf-8")
        p(f"  เขียน {f.relative_to(ROOT)} ({len(keep_ids)} id · ถอด {len(drop_ids)})")
    p("")
    p(f"สำรองไฟล์เดิมไว้ที่ {dest.relative_to(ROOT)}")

    p("")
    p("=" * 64)
    p("ต้องทำต่อให้ครบ ไม่งั้นตัวเลขจะไม่ตรงกัน")
    p("  1. uv run python scripts/human_check_v3.py --score")
    p("     (ชุดตรวจคนเล็กลง ค่าความสอดคล้องเปลี่ยน)")
    if need_retrain:
        p("  2. เทรนใหม่ทั้งสามหัว แล้วรัน seed sweep ใหม่")
        p("     เพราะชุดเทรนเปลี่ยน โมเดลเดิมเห็นข้อมูลนอกขอบเขตไปแล้ว")
        p("     ตัวเลขความแม่นยำที่รายงานอยู่จึงใช้ไม่ได้จนกว่าจะเทรนใหม่")
    p("  3. uv run python scripts/measure_everything.py")
    p("  4. อัปเดต docs/limitations.md และ export_for_chat/")
    p("=" * 64)


if __name__ == "__main__":
    asyncio.run(main())
