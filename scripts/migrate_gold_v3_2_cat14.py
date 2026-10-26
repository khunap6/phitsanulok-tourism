"""migrate_gold_v3_2_cat14.py — ย้ายแถวที่ติดธง no_specific_topic เป็นหมวด 14

ธง no_specific_topic ถูกถอดใน v3.2 แล้วแทนด้วยหมวด 14 "ความประทับใจโดยรวม"
สคริปต์นี้ย้ายแถวในชุด gold ที่ยังติดธงอยู่ ให้ไปเป็นหมวด 14 พร้อมเครื่องหมาย
ที่มาจากอารมณ์รวมเดิมของแถวนั้น

⚠️ สคริปต์นี้ **แก้ป้ายในชุด gold** ซึ่งปกติห้ามทำ
  ทำได้เพราะผู้ใช้อนุมัติเป็นรายครั้งหลังเห็นรายการทั้ง 9 แถวแล้ว
  ถ้าจะรันกับแถวอื่นในอนาคต ต้องขออนุมัติใหม่ ห้ามถือว่าครั้งนี้อนุมัติไว้แล้ว

⚠️ ไม่เดาอารมณ์ใหม่เลย
  เครื่องหมายของหมวด 14 มาจาก overall_sentiment ที่แถวนั้นมีอยู่แล้ว
  positive -> 14+ · neutral -> 14n · negative -> 14-
  ถ้าแถวใดไม่มีอารมณ์รวม สคริปต์จะหยุด ไม่เติมค่าให้เอง

⚠️ ไม่ลบข้อมูลเดิม
  สภาพเดิมของแถว (ธงและ aspects) ถูกเขียนต่อท้ายคอลัมน์ note
  label_source เปลี่ยนเป็น migrated_v3_2_cat14 เพื่อให้ย้อนได้ว่าแถวไหนถูกย้าย
  และสำรองไฟล์ทั้งไฟล์ไว้ใน backup/ ก่อนเขียนทุกครั้ง

⚠️ เกณฑ์ที่ใช้ตัดสินว่าแถวไหนควรเป็น 14 ไม่ใช่ 13
  "ข้อความนี้ประเมินสถานที่ไหม" — ถ้าประเมิน -> 14 ถ้าไม่ -> 13
  ดู labeling_rules.overall_impression_is_a_category.boundary_13_vs_14
  สคริปต์นี้ย้ายเฉพาะแถวที่ติดธง ซึ่งนิยามของธงคือ "ชมหรือติแบบไม่บอกเรื่อง"
  = เป็นการประเมินอยู่แล้วโดยนิยาม จึงไป 14 ทุกแถว
  แถวที่ติด 13 อยู่แล้วไม่ถูกแตะ เพราะตรวจแล้วว่าไม่ใช่การประเมิน

รัน:
  uv run python scripts/migrate_gold_v3_2_cat14.py
  uv run python scripts/migrate_gold_v3_2_cat14.py --write
"""
import argparse
import csv
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "reports" / "evaluation" / "gold_v3_2_labeled.csv"
BACKUP_DIR = ROOT / "backup"
NEW_SOURCE = "migrated_v3_2_cat14"
TARGET_ID = "14"
SIGN = {"positive": "+", "neutral": "n", "negative": "-"}


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    v3 = json.loads((ROOT / "shared" / "categories_v3.json").read_text(encoding="utf-8"))
    if TARGET_ID not in {str(c["id"]) for c in v3["categories"]}:
        p(f"หยุด: หมวด {TARGET_ID} ไม่มีใน shared/categories_v3.json")
        p("   ให้รัน scripts/build_categories_v3.py ก่อน")
        sys.exit(1)
    name14 = next(c["name"] for c in v3["categories"] if str(c["id"]) == TARGET_ID)
    if TARGET_ID not in {str(i) for i in v3["non_problem_ids"]}:
        p(f"หยุด: หมวด {TARGET_ID} ต้องอยู่ใน non_problem_ids ไม่งั้นจะไปบวมสถิติ pain point")
        sys.exit(1)

    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    fields = list(rows[0])
    todo = [r for r in rows if (r["no_specific_topic"] or "").strip()]

    p(f"ชุด gold {len(rows)} แถว · ติดธง no_specific_topic {len(todo)} แถว")
    p(f"หมวดเป้าหมาย {TARGET_ID} = {name14}")
    p("")

    errs = []
    for r in todo:
        ov = (r["overall_sentiment"] or "").strip()
        if ov not in SIGN:
            errs.append(f"  id={r['review_id']} อารมณ์รวม {ov!r} แปลงเป็นเครื่องหมายไม่ได้")
        if (r["aspects"] or "").strip():
            errs.append(f"  id={r['review_id']} ติดธงแต่มี aspects {r['aspects']!r} "
                        f"อยู่แล้ว — ต้องให้คนตัดสิน ไม่ย้ายอัตโนมัติ")
    if errs:
        p(f"หยุด: พบ {len(errs)} จุดที่ย้ายอัตโนมัติไม่ได้")
        for e in errs:
            p(e)
        sys.exit(1)

    p(f"{'review_id':<10} {'อารมณ์เดิม':<10} {'ป้ายใหม่':<9} ข้อความ")
    for r in todo:
        tok = TARGET_ID + SIGN[r["overall_sentiment"].strip()]
        p(f"{r['review_id']:<10} {r['overall_sentiment']:<10} {tok:<9} {r['text'][:52]!r}")

    if not a.write:
        p("")
        p("DRY-RUN — ยังไม่เขียนไฟล์  ลงมือจริงด้วย --write")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"gold_before_cat14_{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC, dest / SRC.name)
    p("")
    p(f"สำรองไฟล์เดิมไว้ที่ {(dest / SRC.name).relative_to(ROOT)}")

    for r in todo:
        tok = TARGET_ID + SIGN[r["overall_sentiment"].strip()]
        was = (f"ย้ายจากธง no_specific_topic=1 (aspects ว่าง) เป็น {tok} "
               f"ตามกติกา v3.2 overall_impression_is_a_category")
        note = (r["note"] or "").strip()
        r["note"] = f"{note} | {was}" if note else was
        r["aspects"] = tok
        r["no_specific_topic"] = ""
        r["label_source"] = NEW_SOURCE

    with open(SRC, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    left = sum(1 for r in rows if (r["no_specific_topic"] or "").strip())
    got = sum(1 for r in rows
              if TARGET_ID in [t.strip()[:-1] for t in r["aspects"].split(",") if t.strip()])
    p(f"เขียน {SRC.relative_to(ROOT)} แล้ว")
    p(f"  แถวที่ยังติดธง {left} (ต้องเป็น 0)")
    p(f"  แถวที่มีหมวด {TARGET_ID} {got} (ต้องเป็น {len(todo)})")
    if left or got != len(todo):
        p("⚠️ ตัวเลขไม่ตรงที่คาด — ตรวจไฟล์สำรองแล้วหาสาเหตุก่อนใช้ต่อ")
        sys.exit(1)


if __name__ == "__main__":
    main()
