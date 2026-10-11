"""apply_cat2_rule.py — ปรับป้าย silver ให้ตรงกติกาหมวด 2 ที่ตกลงกันแล้ว

กติกาที่ผู้ใช้ตัดสิน (2026-10-12): "กราบ / สักการะ / ไหว้พระ / ขอพร" = หมวด 2
ไม่ใช่หมวด 10 ตามที่คู่มือบรรทัด 57 เขียนไว้

ที่มาของปัญหา
  คู่มือขัดกันเอง — บรรทัด 57 เขียน "ไหว้พระ -> 10" แต่อีกข้อเขียนว่า
  "นับเป็นหมวดเฉพาะเรื่องที่ผู้รีวิวประเมิน" และ "หมวด 2 ใช้เมื่อไม่มีหมวดเจาะจง"
  ชุด gold ติดตามข้อหลัง ส่วนผมติดตามบรรทัด 57 -> สองชุดขัดกัน
  วัดผลได้ว่าทำให้ F1 หมวด 2 เหลือ 0.095 และ precision หมวด 10 เหลือ 0.316
  (โมเดลทายหมวด 10 เกิน 21 ครั้ง ในนั้น 7 ครั้ง gold บอกว่าเป็นหมวด 2)

วิธีแก้
  ย้ายหมวด 10 -> 2 เฉพาะรีวิวที่เนื้อหาหมวด 10 "มีแต่เรื่องไหว้พระ/ทำบุญ"
  รีวิวที่มีเนื้อหาหมวด 10 อย่างอื่นด้วย (ตลาด ของฝาก โบราณสถาน นิทรรศการ
  พุทธพาณิชย์) ให้คงหมวด 10 ไว้ -> รายการนี้ตรวจด้วยตาทีละใบ ไม่ใช้ regex
  เพราะการเหมารวมจะทำให้เสียตัวอย่างหมวด 10 ที่ถูกต้องไป

⚠️ ไม่แตะชุด gold ตามข้อห้ามในโจทย์

รัน:
  uv run python scripts/apply_cat2_rule.py --apply
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

# ตรวจด้วยตาทีละใบ — คงหมวด 10 ไว้เพราะมีเนื้อหาหมวด 10 นอกเหนือจากการไหว้พระ
KEEP_10 = {
    1996: "ตลาดเช้าหน้าวัด มีขนม อาหารขาย",
    30700: "ชมประวัติความเป็นมาเมืองพิษณุโลก = นิทรรศการ",
    45992: "บรรยายโบราณสถาน พระปรางค์ พระอุโบสถ มณฑป",
    68595: "ร้านล็อตเตอรี่ ร้านขายของกิน ของฝากเยอะมาก",
    68677: "ร้านขายของเป็นตลาดใหญ่มาก",
    238671: "มีการซื้อของฝากประจำ",
    238920: "พุทธพาณิชย์ มีพระให้เช่า = เชิงพาณิชย์",
}
# รีวิวที่ต้องย้าย 10 -> 2 (ตรวจแล้วว่าเนื้อหาหมวด 10 มีแต่เรื่องไหว้พระ/ทำบุญ)
MOVE = [26, 66, 76, 596, 806, 39431, 39439, 68575, 68629, 68684, 68722, 68837,
        68844, 68900, 68907, 69066, 96447, 179171, 179209, 179237, 179280,
        179351, 179659, 238664, 238783, 238951, 239046, 239103, 239408,
        239515, 239523, 239745, 239934]


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
        by.setdefault(int(r["review_id"]), []).append(r)

    changed, skipped, clash = 0, [], []
    for rid in MOVE:
        if rid not in by:
            skipped.append(rid)
            continue
        cats = {int(r["category_id"]): r for r in by[rid]}
        if 10 not in cats:
            skipped.append(rid)
            continue
        if 2 in cats:
            clash.append(rid)
            continue
        r = cats[10]
        r["category_id"] = "2"
        r["category_name"] = "ความคิดเห็นทั่วไป (ไม่ระบุประเด็น)"
        changed += 1

    p(f"ย้ายหมวด 10 -> 2 : {changed} รีวิว")
    p(f"คงหมวด 10 ไว้    : {len(KEEP_10)} รีวิว (ตรวจด้วยตาแล้ว)")
    for rid, why in sorted(KEEP_10.items()):
        p(f"   id={rid:<7} {why}")
    if skipped:
        p(f"ข้าม (ไม่มีหมวด 10 แล้ว) : {skipped}")
    if clash:
        p(f"⚠️ มีหมวด 2 อยู่แล้ว ไม่ย้ายซ้ำ : {clash}")

    # ป้ายระดับรีวิวต้องตามไปด้วยถ้าหมวดหลักคือ 10
    revs = list(csv.DictReader(open(REV, encoding="utf-8-sig")))
    fixed_primary = 0
    moved = set(MOVE)
    for rv in revs:
        rid = int(rv["review_id"])
        if rid in moved and rv["primary_category_id"] == "10":
            rv["primary_category_id"] = "2"
            fixed_primary += 1
    p(f"แก้ primary_category_id ตามไปด้วย : {fixed_primary} รีวิว")

    if not args.apply:
        p("")
        p("นี่คือ DRY-RUN — ยังไม่เขียนไฟล์  ลงมือจริงด้วย --apply")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = ROOT / "backup" / f"silver_before_cat2_{stamp}"
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
    p("เขียนไฟล์เรียบร้อย — ต้องเทรนทั้งสองโมเดลใหม่")


if __name__ == "__main__":
    main()
