"""report_gold_leakage.py — หา gold 300 ที่รั่วไปอยู่ในชุดเทรนของโมเดลหมวด

ทำไมต้องมี (พบ 2026-10-11):
  ชุด gold 300 รีวิวถูกสุ่มมาจาก analyzed_reviews ทั้งหมดโดยไม่ได้กันชุดเทรนออก
  จึงมีบางรายการที่โมเดลหมวดเคย "เห็นตอนเทรน" มาแล้ว
  ถ้ารายงาน F1 บนทั้ง 300 โดยไม่ตัดออก ตัวเลขจะสูงเกินจริง

เกณฑ์ที่ใช้ (ตามที่ผู้ใช้สั่ง):
  อยู่ใน split train หรือ val = รั่ว ตัดออกจากชุดประเมิน
  อยู่ใน split test = ไม่ถือว่ารั่ว เพราะโมเดลไม่ได้เรียนจากมัน
  ชุดเทรนไม่เก็บ review_id จึงเทียบด้วยข้อความ (ตรงทั้งสตริงหลัง strip)

⚠️ ชุด 300 นี้ต้องถูกกันออกจากชุดเทรนรอบใหม่ทั้งหมด 300 รายการ ไม่ใช่แค่ 54

รัน:
  uv run python scripts/report_gold_leakage.py
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / "data" / "labeling"
OUT = ROOT / "reports" / "evaluation"


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def main() -> None:
    gold = list(csv.DictReader(
        open(LAB / "reviews_labeled.csv", encoding="utf-8-sig")))
    ds = json.loads(
        (ROOT / "data" / "training" / "category_dataset.json").read_text(encoding="utf-8"))

    # ข้อความ -> รายชื่อ split ที่พบ (ข้อความซ้ำอาจอยู่หลาย split)
    where: dict[str, list[str]] = {}
    for split in ("train", "val", "test"):
        for r in ds[split]:
            where.setdefault(r["text"].strip(), []).append(split)

    rows = []
    for g in gold:
        hits = where.get(g["text"].strip(), [])
        if not hits:
            continue
        leaked = any(h in ("train", "val") for h in hits)
        rows.append({
            "review_id": g["review_id"],
            "splits": "+".join(sorted(set(hits))),
            "leaked": "ใช่" if leaked else "ไม่",
            "reason": ("โมเดลเคยเห็นตอนเทรน (อยู่ใน " + "+".join(sorted(set(hits))) + ")"
                       if leaked else "อยู่ใน test split เท่านั้น โมเดลไม่ได้เรียนจากมัน"),
            "overall_sentiment": g["overall_sentiment"],
            "primary_category": g["primary_category"],
            "needs_review": g["needs_review"],
            "text": g["text"],
        })

    leaked = [r for r in rows if r["leaked"] == "ใช่"]
    clean_n = len(gold) - len(leaked)

    OUT.mkdir(parents=True, exist_ok=True)
    f = OUT / "gold300_leakage.csv"
    with open(f, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["leaked"] != "ใช่", r["splits"])))

    ids = OUT / "gold300_clean_ids.txt"
    bad = {r["review_id"] for r in leaked}
    ids.write_text(
        "\n".join(g["review_id"] for g in gold if g["review_id"] not in bad) + "\n",
        encoding="utf-8")

    p("=" * 70)
    p("  ตรวจการรั่วของชุด gold 300 ไปยังชุดเทรนของโมเดลหมวด")
    p("=" * 70)
    p(f"gold ทั้งหมด                 : {len(gold)}")
    p(f"พบข้อความซ้ำกับชุดเทรน       : {len(rows)}")
    p(f"  - รั่ว (train/val)         : {len(leaked)}  <- ตัดออกจากชุดประเมิน")
    p(f"  - อยู่ใน test เท่านั้น      : {len(rows) - len(leaked)}  (ไม่ถือว่ารั่ว)")
    p(f"ชุดประเมินที่สะอาด            : {clean_n}")
    p("")
    from collections import Counter
    p("แยกตาม split ที่พบ:")
    for k, v in sorted(Counter(r["splits"] for r in rows).items()):
        p(f"   {k:<16} {v:>3}")
    p("")
    p("อารมณ์รวมของรายการที่รั่ว (ดูว่าตัดออกแล้วชุดเสียสมดุลไหม):")
    gc = Counter(g["overall_sentiment"] for g in gold)
    lc = Counter(r["overall_sentiment"] for r in leaked)
    for s in ("positive", "neutral", "negative"):
        left = gc[s] - lc[s]
        p(f"   {s:<9} ทั้งหมด {gc[s]:>3} | รั่ว {lc[s]:>2} | เหลือ {left:>3}")
    p("")
    p(f"บันทึกไว้ที่")
    p(f"   {f}")
    p(f"   {ids}  (รายชื่อ {clean_n} id ที่ใช้ประเมินได้)")


if __name__ == "__main__":
    main()
