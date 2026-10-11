"""build_categories_json.py — สร้าง shared/categories.json จาก data/labeling/categories.csv

ทำไมต้อง generate ไม่ใช่พิมพ์มือ:
  ชื่อหมวดต้องมีแหล่งเดียว ถ้าพิมพ์ซ้ำในหลายที่ วันหนึ่งจะเพี้ยนจากกัน
  (เคยเกิดมาแล้ว: หน้าเว็บมี 10 หมวด โมเดลมี 12 ผู้ใช้กรองสองหมวดใหญ่สุดไม่ได้)
  categories.csv เป็นไฟล์ที่ผู้ใช้กำหนด จึงยึดเป็นต้นทาง

⚠️ การ map หมวดเก่า -> ใหม่ ต้องเทียบด้วย "ชื่อ" ไม่ใช่เลข
  เลขใน categories.csv เป็นลำดับของผู้ใช้เอง ไม่ตรงกับ id2label ของโมเดล
  ถ้า map ด้วยเลขจะย้ายผิด 93,682 แถว

รัน:
  uv run python scripts/build_categories_json.py
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_IN = ROOT / "data" / "labeling" / "categories.csv"
OUT = ROOT / "shared" / "categories.json"

# ชื่อหมวดเดิมในฐานข้อมูล -> id หมวดใหม่  (ยืนยันกับผู้ใช้แล้ว)
#   หมวดใหม่ 7 = การเดินทางและที่จอดรถ + ข้อมูลและป้ายบอกทาง
#   หมวดใหม่ 9 = สิ่งอำนวยความสะดวก + ความปลอดภัย
#   "อื่นๆ" เดิมแยกได้สองทาง (10 สถานที่/กิจกรรม/สินค้า หรือ 11 นอกเรื่อง)
#     ผู้ใช้สั่งให้ตั้งเป็น 10 ไว้ก่อน แล้ว mark needs_review
OLD_TO_NEW: dict[str, int] = {
    "รสชาติและคุณภาพอาหาร/เครื่องดื่ม": 1,
    "ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)": 2,
    "บรรยากาศและการตกแต่งร้าน": 3,
    "การบริการและเจ้าหน้าที่": 4,
    "ราคาและความคุ้มค่า": 5,
    "ความสะอาดและสิ่งแวดล้อม": 6,
    "การเดินทางและที่จอดรถ": 7,
    "ข้อมูลและป้ายบอกทาง": 7,
    "ความแออัดและการจัดการ": 8,
    "สิ่งอำนวยความสะดวก": 9,
    "ความปลอดภัย": 9,
    "อื่นๆ": 10,
}
# หมวดที่ map มาแล้วต้องให้คนตรวจซ้ำ เพราะต้นทางแยกได้หลายทาง
NEEDS_REVIEW_FROM = {"อื่นๆ"}
# หมวดที่ไม่ใช่ปัญหา — ไม่นับเป็น pain point ไม่ว่ากรณีใด (ผู้ใช้ยืนยันข้อ 7)
NON_PROBLEM_IDS = {2, 11}


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def main() -> None:
    rows = list(csv.DictReader(open(CSV_IN, encoding="utf-8-sig")))
    cats = []
    for r in rows:
        cid = int(r["category_id"])
        cats.append({
            "id": cid,
            "name": r["category_name"].strip(),
            "is_non_problem": cid in NON_PROBLEM_IDS,
            "old_names": sorted(o for o, n in OLD_TO_NEW.items() if n == cid),
            "note_from_csv": r["old_category_ids"].strip(),
        })

    ids = {c["id"] for c in cats}
    missing = sorted(set(OLD_TO_NEW.values()) - ids)
    if missing:
        p(f"หยุด: map ชี้ไปยัง id ที่ไม่มีใน csv -> {missing}")
        sys.exit(1)

    doc = {
        "_readme": [
            "หมวดหมู่ของรีวิว ฉบับ v2 (11 หมวด) — แหล่งความจริงเดียว",
            "",
            "สร้างด้วย scripts/build_categories_json.py จาก data/labeling/categories.csv",
            "ห้ามแก้ไฟล์นี้ตรง ๆ ให้แก้ csv หรือ OLD_TO_NEW ในสคริปต์แล้ว generate ใหม่",
            "",
            "ใครอ่านไฟล์นี้: api/filters.py, frontend/src/utils/categoryLabel.ts,",
            "nlp (พรอมป์และการ map ผลโมเดลเก่า), สคริปต์ย้ายข้อมูล",
            "",
            "old_names = ชื่อหมวดชุด v1 (12 หมวด) ที่ยุบเข้ามาเป็นหมวดนี้",
            "  map ด้วยชื่อเท่านั้น เพราะเลขใน csv เป็นลำดับของผู้ใช้",
            "  ไม่ตรงกับ id2label ของโมเดล ถ้า map ด้วยเลขจะย้ายผิดทั้งฐาน",
            "",
            "หมวด 10 และ 11 ไม่มีใน v1 โมเดลเดิมจึงทำนายไม่ได้เลย",
            "  ข้อมูลเดิมที่เป็น 'อื่นๆ' (19 แถว) ตั้งเป็น 10 ไว้ก่อนและ mark needs_review",
            "  หมวด 10 จะมีข้อมูลจริงก็ต่อเมื่อเทรนโมเดลใหม่แล้วเท่านั้น",
        ],
        "version": "v2",
        "non_problem_ids": sorted(NON_PROBLEM_IDS),
        "needs_review_from_old": sorted(NEEDS_REVIEW_FROM),
        "categories": cats,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    p(f"เขียน {OUT.relative_to(ROOT)} แล้ว — {len(cats)} หมวด")
    p("")
    p(f"{'id':>3}  {'หมวดใหม่':<42} {'ปัญหา?':<7} ชื่อเดิมที่ยุบเข้ามา")
    p("-" * 108)
    for c in cats:
        flag = "ไม่ใช่" if c["is_non_problem"] else "ใช่"
        old = ", ".join(c["old_names"]) or "(ไม่มีใน v1)"
        p(f"{c['id']:>3}  {c['name']:<42} {flag:<7} {old}")


if __name__ == "__main__":
    main()
