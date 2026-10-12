"""classify_scope.py — จัดสถานที่ทุกแห่งว่าอยู่ในขอบเขตไหม ตาม shared/scope.json

⚠️ อ่านอย่างเดียว ไม่แก้ฐานข้อมูล
  ออกเป็นรายงาน + ไฟล์ reports/scope_classification.csv ให้คนตรวจก่อน
  ถ้าจะเอาผลไปใช้กรองจริง ต้องเพิ่มคอลัมน์ในตาราง places ซึ่งเป็นคนละขั้น
  และต้องถามก่อน เพราะกระทบตัวส่วนของทุกสัดส่วนในระบบ

รัน:
  uv run python scripts/classify_scope.py
  uv run python scripts/classify_scope.py --write
"""
import argparse
import asyncio
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from db.database import engine  # noqa: E402

OUT_CSV = ROOT / "reports" / "scope_classification.csv"


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def classify(pid: int, types: str, cat_th: str, scope: dict) -> tuple[bool, str]:
    """คืน (อยู่ในขอบเขตไหม, เหตุผล) — ลำดับตามที่เขียนไว้ใน scope.json"""
    t = set((types or "").split(","))
    if str(pid) in scope["override_out"]:
        return False, "ตัดสินรายแห่ง: " + scope["override_out"][str(pid)]
    if str(pid) in scope["override_in"]:
        return True, "ตัดสินรายแห่ง: " + scope["override_in"][str(pid)]
    # ⚠️ searchable type ชนะ type นอกขอบเขตเสมอ
    #   คาเฟ่ที่มีห้องพัก (cafe+lodging) หรือล้างรถ (cafe+car_wash) ก็ยังเป็นคาเฟ่
    hit_srch = t & set(scope["searchable_types"])
    if hit_srch:
        return True, "type ที่ค้นหาได้: " + ",".join(sorted(hit_srch))
    hit_out = t & set(scope["out_of_scope_types"])
    if hit_out:
        return False, "type นอกขอบเขต: " + ",".join(sorted(hit_out))
    hit_in = t & set(scope["in_scope_types"])
    if hit_in:
        return True, "type ในขอบเขต: " + ",".join(sorted(hit_in))
    # ⚠️ ทางสำรอง: google_types ใช้ไม่ได้ (NULL หรือมีแค่ establishment)
    #   ตัดสินด้วยป้ายภาษาไทยแทน ตรวจ out ก่อน in เพราะเจาะจงกว่า
    cat = (cat_th or "").strip()
    for pre in scope["category_out_prefix"]:
        if cat.startswith(pre):
            return False, f"ป้าย Google: {cat} (นอกขอบเขต)"
    for pre in scope["category_in_prefix"]:
        if cat.startswith(pre):
            return True, f"ป้าย Google: {cat} (ในขอบเขต)"
    return False, f"ไม่มี type และป้าย '{cat or '(ว่าง)'}' ไม่อยู่ในรายการ"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    scope = json.loads((ROOT / "shared" / "scope.json").read_text(encoding="utf-8"))

    async with engine.connect() as c:
        rows = [dict(r) for r in (await c.execute(text("""
            SELECT p.id, p.name, p.google_category, p.google_types,
                   COALESCE(p.discovered_by,'(null)') AS discovered_by,
                   (SELECT COUNT(*) FROM reviews r WHERE r.place_id=p.id) AS rev_all,
                   (SELECT COUNT(*) FROM reviews r WHERE r.place_id=p.id
                      AND r.text_clean <> '') AS rev_text
            FROM places p ORDER BY p.id"""))).mappings()]
    await engine.dispose()

    for r in rows:
        r["in_scope"], r["reason"] = classify(
            r["id"], r["google_types"], r["google_category"], scope)

    inn = [r for r in rows if r["in_scope"]]
    out = [r for r in rows if not r["in_scope"]]
    t_all = sum(r["rev_text"] for r in rows)
    t_out = sum(r["rev_text"] for r in out)

    p("=" * 72)
    p("ผลการจัดขอบเขต")
    p("=" * 72)
    p(f"สถานที่ทั้งหมด {len(rows)}  ->  ในขอบเขต {len(inn)} · นอกขอบเขต {len(out)}")
    p(f"รีวิวที่มีข้อความ {t_all:,}  ->  ในขอบเขต {t_all - t_out:,} · "
      f"นอกขอบเขต {t_out:,} ({t_out / t_all * 100:.2f}%)")
    p("")
    p("นอกขอบเขต แยกตามเหตุผล")
    byr: Counter = Counter()
    byr_rev: Counter = Counter()
    for r in out:
        k = r["reason"].split(":")[0]
        byr[k] += 1
        byr_rev[k] += r["rev_text"]
    for k, v in byr.most_common():
        p(f"  {k:<28} {v:>4} แห่ง  {byr_rev[k]:>6,} รีวิว")
    p("")
    p("นอกขอบเขต แยกตามทางเข้า")
    bysrc: Counter = Counter()
    for r in out:
        bysrc[r["discovered_by"]] += 1
    for k, v in bysrc.most_common():
        p(f"  {k:<12} {v:>4} แห่ง")
    p("")
    p("นอกขอบเขตที่มีรีวิวเยอะสุด 15 อันดับ")
    for r in sorted(out, key=lambda x: -x["rev_text"])[:15]:
        p(f"  {r['rev_text']:>5,}  id={r['id']:<5} "
          f"[{str(r['google_category'])[:18]:<20}] {r['name'][:34]}")
        p(f"         {r['reason'][:92]}")

    if not a.write:
        p("")
        p("DRY-RUN — ยังไม่เขียนไฟล์  ลงมือจริงด้วย --write")
        return

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "id", "name", "google_category", "google_types", "discovered_by",
            "rev_all", "rev_text", "in_scope", "reason"])
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x["in_scope"], -x["rev_text"])):
            w.writerow({k: r[k] for k in w.fieldnames})
    p("")
    p(f"เขียน {OUT_CSV.relative_to(ROOT)} ({len(rows)} แถว)")


if __name__ == "__main__":
    asyncio.run(main())
