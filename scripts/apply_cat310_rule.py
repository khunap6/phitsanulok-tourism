"""apply_cat310_rule.py — ปรับป้าย silver ตามกติกาเส้นแบ่งหมวด 3 / 9 / 10

กติกาที่ผู้ใช้ตัดสิน (2026-10-12)
  หมวด 10 ใช้เฉพาะ "กิจกรรมที่ทำ" กับ "สินค้าที่ซื้อ"
  ความสวย / สภาพ / ขนาดของสถานที่           -> หมวด 3
  สิ่งที่มีไว้ให้ใช้ (ทางเดิน เครื่องเล่น ห้องน้ำ) -> หมวด 9
  พูดถึงแบบไม่ระบุประเด็น                     -> หมวด 2

ที่มาของปัญหา (วัดได้จาก gold 251)
  หมวด 10 มี recall 0.923 แต่ precision แค่ 0.414 — ทายเกิน 17 ครั้ง
  และ gold บอกว่ารีวิวพวกนั้นเป็นหมวด 3 ถึง 11 ครั้ง
  ตรวจแล้วไม่ใช่ปัญหาข้อมูลน้อย: silver มีหมวด 10 ถึง 191 ตัวอย่าง (gold มี 13)
  แต่สองรอบการติดป้ายลากเส้นแบ่งคนละที่ — เติมข้อมูลอีกเท่าไรก็ไม่หาย
  เป็นปัญหาแบบเดียวกับหมวด 2 ที่แก้ไปแล้ว

⚠️ ตรวจด้วยตาทีละใบทั้ง 191 รายการ ไม่ใช้ regex เหมารวม
  เพราะคำว่า "วัด" "น้ำตก" "ตลาด" ปรากฏได้ทั้งในบริบทกิจกรรมและบริบทสภาพสถานที่
  การเหมารวมจะเสียตัวอย่างหมวด 10 ที่ถูกต้องไป (บทเรียนจากรอบหมวด 2)

⚠️ ไม่แตะชุด gold ตามข้อห้ามในโจทย์

รัน:
  uv run python scripts/apply_cat310_rule.py --apply
"""
import argparse
import csv
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / "data" / "labeling"
ASP = LAB / "silver_aspects.csv"
REV = LAB / "silver_reviews.csv"

NAMES = {2: "ความคิดเห็นทั่วไป (ไม่ระบุประเด็น)",
         3: "บรรยากาศ ทัศนียภาพ และการตกแต่ง"}

# ความสวย / สภาพ / ขนาดของสถานที่ — ไม่ได้พูดถึงกิจกรรมหรือสินค้า
TO_3 = [1169, 3230, 210855, 22142, 31321, 36361, 37232, 39924, 82139, 85940,
        98618, 195988, 195997, 238964, 70780, 70758, 46019, 226210, 39923,
        8322, 53957, 70290, 70379, 3317, 626, 195691, 2324, 36408]
# พูดถึงแบบไม่ระบุประเด็น / เอ่ยแค่ชื่อสถานที่
TO_2 = [179479, 239218, 239752, 30668, 10853, 76122, 69085, 239265, 214792]
# มีหมวดปลายทางอยู่แล้ว -> ลบแถวหมวด 10 ทิ้งเฉย ๆ ไม่ย้าย
DROP = [166, 239533, 238671, 207780, 140211, 39904]


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(ASP, encoding="utf-8-sig")))
    by = {}
    for r in rows:
        by.setdefault(int(r["review_id"]), {})[int(r["category_id"])] = r

    moved = {2: 0, 3: 0}
    dropped, skipped, clash = 0, [], []
    drop_set = set()

    for target, ids in ((3, TO_3), (2, TO_2)):
        for rid in ids:
            cats = by.get(rid)
            if not cats or 10 not in cats:
                skipped.append(rid)
                continue
            if target in cats:
                clash.append((rid, target))
                drop_set.add(id(cats[10]))
                continue
            r = cats[10]
            r["category_id"] = str(target)
            r["category_name"] = NAMES[target]
            moved[target] += 1

    for rid in DROP:
        cats = by.get(rid)
        if not cats or 10 not in cats:
            skipped.append(rid)
            continue
        drop_set.add(id(cats[10]))
        dropped += 1

    rows = [r for r in rows if id(r) not in drop_set]

    # ถ้าแถวที่ถูกลบคือ is_primary ต้องยกให้แถวอื่นของรีวิวนั้นแทน
    # ไม่งั้นรีวิวนั้นจะไม่มีหมวดหลักเลย
    seen_primary = set()
    by2 = {}
    for r in rows:
        by2.setdefault(int(r["review_id"]), []).append(r)
    fixed_primary = 0
    for rid, lst in by2.items():
        if not any(r["is_primary"] == "1" for r in lst):
            lst[0]["is_primary"] = "1"
            fixed_primary += 1
        seen_primary.add(rid)

    p(f"ย้ายหมวด 10 -> 3  : {moved[3]} รีวิว (ความสวย/สภาพ/ขนาดของสถานที่)")
    p(f"ย้ายหมวด 10 -> 2  : {moved[2]} รีวิว (ไม่ระบุประเด็น / เอ่ยแค่ชื่อ)")
    p(f"ลบแถวหมวด 10     : {dropped} รีวิว (มีหมวดปลายทางอยู่แล้ว)")
    p(f"คงหมวด 10 ไว้     : {191 - moved[3] - moved[2] - dropped} รีวิว "
      f"(กิจกรรม ตลาด สินค้า ของฝาก กางเต็นท์ นิทรรศการ ประวัติศาสตร์)")
    if fixed_primary:
        p(f"ยกหมวดหลักให้แถวอื่นแทน : {fixed_primary} รีวิว")
    if skipped:
        p(f"⚠️ ข้าม (ไม่มีหมวด 10 แล้ว) : {skipped}")
    if clash:
        p(f"⚠️ มีหมวดปลายทางอยู่แล้ว จึงลบแทนการย้าย : {clash}")

    revs = list(csv.DictReader(open(REV, encoding="utf-8-sig")))
    prim_of = {}
    for rid, lst in by2.items():
        for r in lst:
            if r["is_primary"] == "1":
                prim_of[rid] = r["category_id"]
    n_prim = 0
    for rv in revs:
        rid = int(rv["review_id"])
        if rid in prim_of and rv["primary_category_id"] != prim_of[rid]:
            rv["primary_category_id"] = prim_of[rid]
            n_prim += 1
    p(f"แก้ primary_category_id ตามไปด้วย : {n_prim} รีวิว")

    if not args.apply:
        p("")
        p("นี่คือ DRY-RUN — ยังไม่เขียนไฟล์  ลงมือจริงด้วย --apply")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = ROOT / "backup" / f"silver_before_cat310_{stamp}"
    bak.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ASP, bak / ASP.name)
    shutil.copy2(REV, bak / REV.name)
    with open(ASP, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    with open(REV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=revs[0].keys())
        w.writeheader()
        w.writerows(revs)
    p("")
    p(f"สำรองของเดิมไว้ที่ {bak.relative_to(ROOT)}")
    p("เขียนไฟล์เรียบร้อย — ต้องเทรนโมเดลหมวดใหม่")


if __name__ == "__main__":
    main()
