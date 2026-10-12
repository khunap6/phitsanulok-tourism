"""merge_gold_v3_2.py — รวมแถวที่ติดป้ายใหม่เข้ากับชุด gold v3.2 แล้วตรวจ

⚠️ แถวเดิม 179 แถวไม่ถูกแตะเลย รวมถึง label_source
  แถวใหม่ได้ label_source = claude_guided_v3_2 เพื่อให้แยกออกว่ามาจากรอบไหน
  ถ้าภายหลังพบว่ารอบใดติดป้ายคลาดเคลื่อน จะย้อนดูได้ว่ากระทบแถวไหนบ้าง

⚠️ ตรวจเงื่อนไขเดียวกับ check_gold_v3_1.py ก่อนเขียนเสมอ
  ถ้าไม่ตรวจ แถวผิดรูปจะหลุดเข้าชุดวัดผล แล้วตัวเลขทุกตัวที่คำนวณจากมันเชื่อไม่ได้

รัน:
  uv run python scripts/merge_gold_v3_2.py <ไฟล์ป้าย> [--write]
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "evaluation"
KEPT = OUT / "gold_v3_2_labeled.csv"
TODO = OUT / "gold_v3_2_to_label.csv"
TOKEN = re.compile(r"^(1[0-3]|[1-9])[+n-]$")
OVERALL = {"p": "positive", "n": "neutral", "g": "negative"}
NEW_SRC = "claude_guided_v3_2"


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    v3 = json.loads((ROOT / "shared" / "categories_v3.json").read_text(encoding="utf-8"))
    valid = {c["id"] for c in v3["categories"]}
    names = {c["id"]: c["name"] for c in v3["categories"]}

    kept = list(csv.DictReader(open(KEPT, encoding="utf-8-sig")))
    fields = list(kept[0])
    todo = {r["review_id"]: r for r in csv.DictReader(open(TODO, encoding="utf-8-sig"))}

    new: list[dict] = []
    errs: list[str] = []
    seen: set[str] = set()
    for fn in a.files:
        f = Path(fn)
        if not f.is_absolute() and not f.exists():
            f = ROOT / fn
        for ln, raw in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            parts = (raw.split("|") + ["", "", ""])[:4]
            rid, ov, spec, note = (x.strip() for x in parts)
            if rid not in todo:
                errs.append(f"{f.name}:{ln} review_id {rid} ไม่อยู่ในรายการที่รอติดป้าย")
                continue
            if rid in seen:
                errs.append(f"{f.name}:{ln} review_id {rid} ซ้ำ")
                continue
            seen.add(rid)
            if ov and ov not in OVERALL:
                errs.append(f"{f.name}:{ln} อารมณ์รวม '{ov}' ต้องเป็น p/n/g")
                continue
            toks = [t.strip() for t in spec.split(",") if t.strip()]
            bad = [t for t in toks if not TOKEN.match(t) or int(t[:-1]) not in valid]
            if bad:
                errs.append(f"{f.name}:{ln} โทเคนผิดรูป {bad}")
                continue
            cids = [t[:-1] for t in toks]
            if len(cids) != len(set(cids)):
                errs.append(f"{f.name}:{ln} มีหมวดซ้ำในแถวเดียว")
                continue
            flag = "ไม่ระบุประเด็น" in note
            if flag and toks:
                errs.append(f"{f.name}:{ln} ติดธงแต่ยังมีหมวด")
                continue
            if ov and not toks and not flag:
                errs.append(f"{f.name}:{ln} มีอารมณ์รวมแต่ไม่มีหมวดและไม่ติดธง")
                continue
            signs = {t[-1] for t in toks}
            o = OVERALL.get(ov, "")
            if toks and not flag:
                if o == "positive" and signs == {"-"}:
                    errs.append(f"{f.name}:{ln} positive แต่มีแต่หมวดลบ")
                    continue
                if o == "negative" and signs == {"+"}:
                    errs.append(f"{f.name}:{ln} negative แต่มีแต่หมวดบวก")
                    continue
                if o == "neutral" and signs == {"+"}:
                    errs.append(f"{f.name}:{ln} neutral แต่มีแต่หมวดบวก")
                    continue
            new.append({"review_id": rid, "text": todo[rid]["ข้อความรีวิว"],
                        "overall_sentiment": o, "aspects": ",".join(toks),
                        "no_specific_topic": "1" if flag else "",
                        "note": note, "label_source": NEW_SRC})

    miss = [k for k in todo if k not in seen]
    p(f"รอติดป้าย {len(todo)} · ติดแล้ว {len(new)} · ยังไม่ติด {len(miss)}")
    if miss:
        p(f"  {miss}")
    if errs:
        p("")
        p(f"พบข้อผิดพลาด {len(errs)} จุด — ไม่เขียนไฟล์")
        for e in errs[:20]:
            p(f"  {e}")
        sys.exit(1)

    allrows = kept + new
    ids = [r["review_id"] for r in allrows]
    dup = [k for k, v in Counter(ids).items() if v > 1]
    if dup:
        p(f"หยุด: review_id ซ้ำ {dup[:6]}")
        sys.exit(1)

    p("")
    p(f"ชุดใหม่ {len(allrows)} แถว (เดิม {len(kept)} + ใหม่ {len(new)})")
    d = Counter(r["overall_sentiment"] or "(ว่าง)" for r in allrows)
    p("อารมณ์รวม: " + " · ".join(f"{k} {v}" for k, v in d.most_common()))
    agg: Counter = Counter()
    sign: dict[int, Counter] = {c: Counter() for c in sorted(valid)}
    for r in allrows:
        for t in (x.strip() for x in r["aspects"].split(",") if x.strip()):
            cid = int(t[:-1])
            agg[cid] += 1
            sign[cid][t[-1]] += 1
    p(f"คู่ (หมวด, อารมณ์) {sum(agg.values())} · ติดธง "
      f"{sum(1 for r in allrows if r['no_specific_topic'])}")
    p("")
    p(f"{'id':>3} {'หมวด':<40} {'รวม':>5} {'+':>4} {'n':>4} {'-':>4}  วัดได้ไหม")
    for cid in sorted(valid):
        tot = agg[cid]
        p(f"{cid:>3} {names[cid][:39]:<40} {tot:>5} {sign[cid]['+']:>4} "
          f"{sign[cid]['n']:>4} {sign[cid]['-']:>4}  "
          f"{'วัดได้' if tot >= 20 else 'ข้อมูลน้อย'}")

    if not a.write:
        p("")
        p("DRY-RUN — ยังไม่เขียนไฟล์  ลงมือจริงด้วย --write")
        return

    with open(KEPT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(allrows)
    p("")
    p(f"เขียน {KEPT.relative_to(ROOT)} ({len(allrows)} แถว)")


if __name__ == "__main__":
    main()
