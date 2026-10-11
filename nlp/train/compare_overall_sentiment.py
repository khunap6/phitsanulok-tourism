"""compare_overall_sentiment.py — เทียบโมเดลอารมณ์รวมสองตัวบนชุด gold

ตัวเดิม models/wangchanberta-sentiment      เทรนบนข้อมูล positive 88%
ตัวใหม่ models/wangchanberta-overall-sentiment เทรนบน silver ที่สมดุลกว่า

ใช้ gold ที่สะอาด 251 รีวิว — ตัวใหม่ไม่เคยเห็นชุดนี้ (silver กัน gold ออกแล้ว)
ส่วนตัวเดิมอาจเคยเห็นบางส่วน จึงได้เปรียบเล็กน้อย ถ้าตัวใหม่ยังชนะก็ยิ่งชัด

รัน:
  uv run python nlp/train/compare_overall_sentiment.py
"""
import csv
import json
import sys
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
LAB = ROOT / "data" / "labeling"
OUT = ROOT / "reports" / "evaluation"
SENTS = ["positive", "neutral", "negative"]


def p(m=""):
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        print(m.encode("ascii", "replace").decode("ascii"), flush=True)


def prf(tp, fp, fn):
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return pr, rc, (2 * pr * rc / (pr + rc) if pr + rc else 0.0)


def main():
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    clean = {int(x) for x in
             (OUT / "gold300_clean_ids.txt").read_text(encoding="utf-8").split()}
    rows = [(int(r["review_id"]), r["text"].strip(), r["overall_sentiment"].strip())
            for r in csv.DictReader(open(LAB / "reviews_labeled.csv",
                                         encoding="utf-8-sig"))
            if int(r["review_id"]) in clean]
    gold = [x[2] for x in rows]
    texts = [x[1] for x in rows]
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    p("=" * 70)
    p(f"  เทียบโมเดลอารมณ์รวม บน gold สะอาด {len(rows)} รีวิว")
    p("=" * 70)
    dist = {s: gold.count(s) for s in SENTS}
    p("ของจริง : " + " | ".join(f"{s} {dist[s]}" for s in SENTS))
    p("")

    base = ["positive"] * len(gold)
    res = {}
    for name in ("wangchanberta-sentiment", "wangchanberta-overall-sentiment"):
        path = ROOT / "models" / name
        tok = AutoTokenizer.from_pretrained(str(path))
        mdl = AutoModelForSequenceClassification.from_pretrained(
            str(path)).to(dev).eval()
        pred = []
        with torch.no_grad():
            for i in range(0, len(texts), 32):
                enc = tok(texts[i:i + 32], padding=True, truncation=True,
                          max_length=256, return_tensors="pt").to(dev)
                pred += [mdl.config.id2label[j] for j in
                         mdl(**enc).logits.argmax(-1).cpu().tolist()]
        res[name] = pred

    p(f"{'โมเดล':<34} {'macro-F1':>9} {'acc':>7}   รายคลาส P/R/F1")
    p("-" * 70)
    summary = {}
    for name, pred in [("baseline ทายบวกหมด", base)] + list(res.items()):
        per = {s: prf(sum(1 for g, q in zip(gold, pred) if g == s and q == s),
                      sum(1 for g, q in zip(gold, pred) if g != s and q == s),
                      sum(1 for g, q in zip(gold, pred) if g == s and q != s))
               for s in SENTS}
        m = sum(v[2] for v in per.values()) / 3
        a = sum(1 for g, q in zip(gold, pred) if g == q) / len(gold)
        summary[name] = {"macro_f1": m, "accuracy": a,
                         "per_class": {s: list(per[s]) for s in SENTS}}
        p(f"{name:<34} {m:>9.4f} {a:>7.4f}")
        for s in SENTS:
            p(f"{'':<34} {s:>9}   "
              f"{per[s][0]:.3f} / {per[s][1]:.3f} / {per[s][2]:.3f}")
    best = max(res, key=lambda k: summary[k]["macro_f1"])
    p("")
    p(f"ดีกว่า: {best}  macro-F1 {summary[best]['macro_f1']:.4f}")
    (OUT / "overall_sentiment_compare.json").write_text(
        json.dumps({"n": len(rows), "gold_distribution": dist,
                    "results": summary, "winner": best},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    p(f"บันทึก {(OUT / 'overall_sentiment_compare.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
