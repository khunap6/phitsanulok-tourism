"""apply_gold_v3_labels.py — ใส่ป้ายที่ติดแล้วลงไฟล์ชุด gold v3 + ตรวจความถูกต้อง

⚠️ ป้ายในชุดนี้ติดโดย Claude ตามกติกาใน shared/categories_v3.json
  เป็นข้อจำกัดเดียวกับชุด gold เดิม (claude_guided) และต้องระบุในเล่ม
  ขั้นถัดไปคือให้คนตรวจชุดย่อย แล้วคำนวณ Cohen's kappa เหมือนที่ทำกับ v2
  ซึ่งวัดได้ว่า kappa อารมณ์รวม 0.8156 และหมวด micro-F1 0.8101

⚠️ รับป้ายจากไฟล์ข้อความ ไม่ฝังในสคริปต์
  รูปแบบ: <review_id>|<อารมณ์รวม>|<หมวด+อารมณ์>|<หมายเหตุ>
  เช่น    153718|p|9+,6-
          26934|||อ่านไม่เข้าใจ          (เว้นว่างทั้งสองช่อง = ไม่ตัดสิน)
          100795|p||ไม่ระบุประเด็น       (ติดธงแทนการใส่หมวด)

⚠️ ตรวจก่อนเขียนทุกครั้ง
  เลขหมวดต้องมีจริงใน v3 · เครื่องหมายต้องเป็น + n - · ห้ามใส่หมวดซ้ำในรีวิวเดียว
  ถ้ามีธง "ไม่ระบุประเด็น" ต้องไม่มีหมวด (ไม่งั้นขัดกันเอง)
  อารมณ์รวมต้องเป็น p/n/g

รัน:
  uv run python scripts/apply_gold_v3_labels.py <ไฟล์ป้าย> [<ไฟล์ป้าย> ...]
  uv run python scripts/apply_gold_v3_labels.py <ไฟล์ป้าย> --write
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "reports" / "evaluation"
BLANK = OUT_DIR / "gold_v3_blank.csv"
FILLED = OUT_DIR / "gold_v3_labeled.csv"

OVERALL = {"p": "positive", "n": "neutral", "g": "negative"}
SIGN = {"+": "positive", "n": "neutral", "-": "negative"}


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

    rows = list(csv.DictReader(open(BLANK, encoding="utf-8-sig")))
    order = [r["review_id"] for r in rows]
    text = {r["review_id"]: r["ข้อความรีวิว"] for r in rows}

    lab: dict[str, dict] = {}
    errs: list[str] = []
    for fn in a.files:
        f = Path(fn)
        if not f.is_absolute():
            f = ROOT / fn if (ROOT / fn).exists() else f
        for ln, raw in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            parts = raw.split("|")
            while len(parts) < 4:
                parts.append("")
            rid, ov, spec, note = (x.strip() for x in parts[:4])
            if rid not in text:
                errs.append(f"{f.name}:{ln} review_id {rid} ไม่อยู่ในชุด")
                continue
            if rid in lab:
                errs.append(f"{f.name}:{ln} review_id {rid} ซ้ำ")
                continue
            if ov and ov not in OVERALL:
                errs.append(f"{f.name}:{ln} อารมณ์รวม '{ov}' ต้องเป็น p/n/g")
                continue
            cats: dict[int, str] = {}
            ok = True
            for tok in (t.strip() for t in spec.split(",") if t.strip()):
                if len(tok) < 2 or not tok[:-1].isdigit() or tok[-1] not in SIGN:
                    errs.append(f"{f.name}:{ln} รูปแบบ '{tok}' ไม่ถูก")
                    ok = False
                    continue
                cid = int(tok[:-1])
                if cid not in valid:
                    errs.append(f"{f.name}:{ln} หมวด {cid} ไม่มีใน v3")
                    ok = False
                    continue
                if cid in cats:
                    errs.append(f"{f.name}:{ln} หมวด {cid} ซ้ำในรีวิวเดียว")
                    ok = False
                    continue
                cats[cid] = SIGN[tok[-1]]
            if not ok:
                continue
            flag = "ไม่ระบุประเด็น" in note
            if flag and cats:
                errs.append(f"{f.name}:{ln} ติดธงไม่ระบุประเด็น แต่ยังใส่หมวด {sorted(cats)}")
                continue
            if ov and not cats and not flag and "ไม่เข้าใจ" not in note:
                errs.append(f"{f.name}:{ln} มีอารมณ์รวมแต่ไม่มีหมวดและไม่ติดธง")
                continue
            lab[rid] = {"ov": ov, "cats": cats, "flag": flag, "note": note}

    missing = [r for r in order if r not in lab]
    p(f"ชุด gold v3 {len(order)} รายการ · มีป้ายแล้ว {len(lab)} · ยังไม่มี {len(missing)}")
    if missing:
        p(f"  ยังไม่มีป้าย: {missing[:12]}{' ...' if len(missing) > 12 else ''}")
    if errs:
        p("")
        p(f"พบข้อผิดพลาด {len(errs)} จุด — ไม่เขียนไฟล์")
        for e in errs[:25]:
            p(f"  {e}")
        sys.exit(1)

    decided = {k: v for k, v in lab.items() if v["ov"]}
    p("")
    p(f"ตัดสินได้ {len(decided)} · เว้นว่าง {len(lab) - len(decided)}")
    dist = Counter(OVERALL[v["ov"]] for v in decided.values())
    p("  อารมณ์รวม : " + " · ".join(f"{k} {dist[k]}" for k in
                                    ("positive", "neutral", "negative")))
    nflag = sum(1 for v in lab.values() if v["flag"])
    npair = sum(len(v["cats"]) for v in lab.values())
    p(f"  ติดธงไม่ระบุประเด็น {nflag} · คู่ (หมวด, อารมณ์) {npair} "
      f"= {npair / max(len(decided) - nflag, 1):.2f} หมวด/รีวิวที่ระบุประเด็น")
    p("")
    p(f"{'id':>3} {'หมวด':<42} {'ทั้งหมด':>7} {'+':>5} {'n':>5} {'-':>5}  วัดได้ไหม")
    agg = {cid: Counter() for cid in sorted(valid)}
    for v in lab.values():
        for cid, s in v["cats"].items():
            agg[cid][s] += 1
    for cid in sorted(valid):
        c = agg[cid]
        tot = sum(c.values())
        verdict = "วัดได้" if tot >= 20 else ("ข้อมูลน้อย" if tot else "ไม่มีเลย")
        p(f"{cid:>3} {names[cid][:41]:<42} {tot:>7} {c['positive']:>5} "
          f"{c['neutral']:>5} {c['negative']:>5}  {verdict}")

    if not a.write:
        p("")
        p("DRY-RUN — ยังไม่เขียนไฟล์  ลงมือจริงด้วย --write")
        return

    with open(FILLED, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "text", "overall_sentiment", "aspects",
                    "no_specific_topic", "note", "label_source"])
        for rid in order:
            v = lab.get(rid)
            if not v:
                continue
            spec = ",".join(
                f"{cid}{'+' if s == 'positive' else '-' if s == 'negative' else 'n'}"
                for cid, s in sorted(v["cats"].items()))
            w.writerow([rid, text[rid], OVERALL.get(v["ov"], ""), spec,
                        "1" if v["flag"] else "", v["note"], "claude_guided_v3"])
    p("")
    p(f"เขียน {FILLED.relative_to(ROOT)} แล้ว")


if __name__ == "__main__":
    main()
