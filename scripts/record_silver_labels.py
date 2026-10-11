"""record_silver_labels.py — รับป้ายแบบย่อแล้วเขียนเป็น CSV ชุดเทรน

รูปแบบย่อ (บรรทัดละ 1 รีวิว)
    <review_id>|<overall>|<cat><sign>,<cat><sign>,...

    overall : p = positive, n = neutral, g = negative
    sign    : +  พอใจ      n  กลางๆ      -  ไม่พอใจ
    หมวดแรกในรายการ = หมวดหลัก (is_primary = 1)

    ตัวอย่าง  48275|g|4-,1+     ติบริการ ชมอาหาร หมวดหลัก = 4

⚠️ ป้ายชุดนี้เป็น claude_silver ใช้ "เทรนเท่านั้น" ห้ามใช้ประเมินผล
   เพราะติดโดยโมเดลเดียวกับที่จะถูกนำไปใช้ ไม่ใช่ ground truth
   ชุดประเมินคือ gold 251 รายการที่แยกไว้ต่างหาก

⚠️ ตรวจความถูกต้องก่อนเขียน
   - review_id ต้องอยู่ในแฟ้มที่สั่งให้ติด (กันติดผิดใบ)
   - หมวดต้องมีใน shared/categories.json
   - ถ้าหมวดเดิมถูกระบุซ้ำในรีวิวเดียว จะยุบเหลือแถวเดียวและเตือน

รัน:
  uv run python scripts/record_silver_labels.py --batch 01 --file <ไฟล์ป้าย>
  uv run python scripts/record_silver_labels.py --status
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAB = ROOT / "data" / "labeling"
BATCHES = LAB / "batches"
OUT_REV = LAB / "silver_reviews.csv"
OUT_ASP = LAB / "silver_aspects.csv"

OVERALL = {"p": "positive", "n": "neutral", "g": "negative"}
SIGN = {"+": "positive", "n": "neutral", "-": "negative"}


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def valid_cats() -> dict:
    doc = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    return {c["id"]: c["name"] for c in doc["categories"]}


def load_existing():
    rev, asp = {}, []
    if OUT_REV.exists():
        for r in csv.DictReader(open(OUT_REV, encoding="utf-8-sig")):
            rev[int(r["review_id"])] = r
    if OUT_ASP.exists():
        asp = list(csv.DictReader(open(OUT_ASP, encoding="utf-8-sig")))
    return rev, asp


def status() -> None:
    rev, asp = load_existing()
    done = set(rev)
    p(f"ติดป้ายแล้ว {len(rev)} รีวิว | {len(asp)} aspect "
      f"({len(asp) / len(rev):.2f} หมวด/รีวิว)" if rev else "ยังไม่มีป้าย")
    from collections import Counter
    if rev:
        p("  overall : " + " | ".join(
            f"{k} {v}" for k, v in Counter(
                r["overall_sentiment"] for r in rev.values()).most_common()))
        p("  aspect  : " + " | ".join(
            f"{k} {v}" for k, v in Counter(
                a["aspect_sentiment"] for a in asp).most_common()))
    for f in sorted(BATCHES.glob("batch_*.csv")) + sorted((LAB / "batches2").glob("b2_*.csv")):
        ids = {int(r["review_id"]) for r in
               csv.DictReader(open(f, encoding="utf-8-sig"))}
        n = len(ids & done)
        mark = "เสร็จ" if n == len(ids) else f"{n}/{len(ids)}"
        p(f"   {f.name} : {mark}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch")
    ap.add_argument("--file")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--round", type=int, default=1, choices=[1, 2],
                    help="1 = data/labeling/batches, 2 = data/labeling/batches2")
    args = ap.parse_args()

    if args.status or not args.batch:
        status()
        return

    # รอบแรกอยู่ batches/batch_NN.csv รอบสองอยู่ batches2/b2_NN.csv
    # เลขแฟ้มซ้ำกันได้ จึงต้องระบุรอบด้วย --round
    cand = ([BATCHES / f"batch_{args.batch}.csv"] if args.round == 1
            else [LAB / "batches2" / f"b2_{args.batch}.csv"])
    bf = next((f for f in cand if f.exists()), None)
    if bf is None:
        p(f"ไม่พบแฟ้ม {args.batch} ใน {[str(c) for c in cand]}")
        return
    allowed = {int(r["review_id"]): r["text"] for r in
               csv.DictReader(open(bf, encoding="utf-8-sig"))}
    cats = valid_cats()
    rev, asp = load_existing()

    lines = [x.strip() for x in
             Path(args.file).read_text(encoding="utf-8").splitlines()
             if x.strip() and not x.strip().startswith("#")]

    added, warn = 0, []
    for ln in lines:
        parts = ln.split("|")
        if len(parts) != 3:
            warn.append(f"รูปแบบผิด: {ln[:50]}")
            continue
        rid_s, ov, catspec = (x.strip() for x in parts)
        rid = int(rid_s)
        if rid not in allowed:
            warn.append(f"id {rid} ไม่ได้อยู่ในแฟ้ม {bf.name}")
            continue
        if ov not in OVERALL:
            warn.append(f"id {rid}: overall '{ov}' ไม่ถูกต้อง")
            continue
        seen = {}
        for tok in catspec.split(","):
            tok = tok.strip()
            if not tok:
                continue
            cid, sg = int(tok[:-1]), tok[-1]
            if cid not in cats or sg not in SIGN:
                warn.append(f"id {rid}: '{tok}' ไม่ถูกต้อง")
                continue
            if cid in seen:
                warn.append(f"id {rid}: หมวด {cid} ซ้ำ — ใช้ค่าแรก")
                continue
            seen[cid] = SIGN[sg]
        if not seen:
            warn.append(f"id {rid}: ไม่มีหมวด")
            continue
        primary = next(iter(seen))
        rev[rid] = {"review_id": str(rid), "text": allowed[rid],
                    "overall_sentiment": OVERALL[ov],
                    "primary_category_id": str(primary),
                    "label_source": "claude_silver", "batch": args.batch}
        asp = [a for a in asp if int(a["review_id"]) != rid]
        for i, (cid, sn) in enumerate(seen.items()):
            asp.append({"review_id": str(rid), "category_id": str(cid),
                        "category_name": cats[cid], "aspect_sentiment": sn,
                        "is_primary": "1" if i == 0 else "0"})
        added += 1

    with open(OUT_REV, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["review_id", "text", "overall_sentiment",
                                           "primary_category_id", "label_source",
                                           "batch"])
        w.writeheader()
        for k in sorted(rev, key=int):
            w.writerow(rev[k])
    with open(OUT_ASP, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["review_id", "category_id",
                                           "category_name", "aspect_sentiment",
                                           "is_primary"])
        w.writeheader()
        for a in sorted(asp, key=lambda x: (int(x["review_id"]),
                                            x["is_primary"] != "1")):
            w.writerow(a)

    p(f"รับป้าย {added} รีวิวจาก batch_{args.batch}")
    miss = sorted(set(allowed) - set(rev))
    if miss:
        p(f"⚠️ ยังไม่ได้ติดในแฟ้มนี้ {len(miss)} ใบ: {miss[:8]}")
    for w_ in warn:
        p(f"   ⚠️ {w_}")
    p("")
    status()


if __name__ == "__main__":
    main()
