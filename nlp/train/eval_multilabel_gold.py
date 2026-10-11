"""eval_multilabel_gold.py — วัดโมเดล multi-label บนชุด gold ที่สะอาด

ทำไมชุดนี้ถึงใช้วัดได้
  - gold ถูกติดป้ายคนละรอบกับ silver จึงไม่ใช่การวัดกับป้ายของตัวเอง
  - ตัดรายการที่รั่วไปชุดเทรนของโมเดลเดิมออกแล้ว (เหลือ 251)
  - ชุด silver ถูกกัน review_id และข้อความของ gold ออกตั้งแต่ตอนสุ่ม
  - threshold จูนบน val ของ silver ไม่ได้จูนบน gold จึงเป็น held-out จริง

เทียบกับอะไร
  A  โมเดลเดิม argmax                     ของปัจจุบัน
  B  โมเดลเดิม + เกณฑ์รายหมวด (ฟรี)       ที่ทำไว้ก่อนหน้า
  C  โมเดล multi-label ที่เทรนใหม่         ตัวนี้

⚠️ gold เป็น positive 88% ส่วน silver ที่ใช้เทรนเป็น negative 56%
  การกระจายต่างกันมาก ตัวเลขบน gold จึงเป็นการวัดข้ามการกระจาย
  ซึ่งเข้มกว่าการวัดบน val ของตัวเอง

รัน:
  uv run python nlp/train/eval_multilabel_gold.py
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
LAB = ROOT / "data" / "labeling"
OUT = ROOT / "reports" / "evaluation"
MODEL = ROOT / "models" / "wangchanberta-category-multilabel"


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def prf(tp, fp, fn):
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return pr, rc, (2 * pr * rc / (pr + rc) if pr + rc else 0.0)


def score(gold: dict, pred: dict, ids: list, cats: list):
    tp = fp = fn = 0
    per = defaultdict(lambda: [0, 0, 0])
    jac, exact = [], 0
    for r in ids:
        g, q = gold[r], pred[r]
        tp += len(g & q)
        fp += len(q - g)
        fn += len(g - q)
        for c in g & q:
            per[c][0] += 1
        for c in q - g:
            per[c][1] += 1
        for c in g - q:
            per[c][2] += 1
        jac.append(len(g & q) / len(g | q) if g | q else 1.0)
        exact += (g == q)
    micro = prf(tp, fp, fn)
    macro = sum(prf(*per[c])[2] for c in cats) / len(cats)
    return {"p": micro[0], "r": micro[1], "micro_f1": micro[2], "macro_f1": macro,
            "jaccard": sum(jac) / len(jac), "exact": exact / len(ids),
            "per": {c: prf(*per[c]) for c in cats},
            "n_pred": sum(len(pred[r]) for r in ids) / len(ids)}


def main() -> None:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    cats_doc = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    ids_cat = [c["id"] for c in cats_doc["categories"]]
    names = {c["id"]: c["name"] for c in cats_doc["categories"]}

    clean = {int(x) for x in
             (OUT / "gold300_clean_ids.txt").read_text(encoding="utf-8").split()}
    texts = {}
    for r in csv.DictReader(open(LAB / "reviews_labeled.csv", encoding="utf-8-sig")):
        if int(r["review_id"]) in clean:
            texts[int(r["review_id"])] = r["text"].strip()
    gold = defaultdict(set)
    for r in csv.DictReader(open(LAB / "review_aspects.csv", encoding="utf-8-sig")):
        if int(r["review_id"]) in clean:
            gold[int(r["review_id"])].add(int(r["category_id"]))
    ids = sorted(texts)
    gold = {r: gold[r] for r in ids}
    present = sorted({c for g in gold.values() for c in g})

    p("=" * 76)
    p("  โมเดล multi-label บนชุด gold ที่สะอาด")
    p("=" * 76)
    n_asp = sum(len(g) for g in gold.values())
    p(f"gold {len(ids)} รีวิว · {n_asp} การกล่าวถึง ({n_asp / len(ids):.2f} หมวด/รีวิว)")
    p("")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(str(MODEL))
    model = AutoModelForSequenceClassification.from_pretrained(str(MODEL)).to(device)
    model.eval()
    th_doc = json.loads((MODEL / "thresholds.json").read_text(encoding="utf-8"))
    th = {int(k): v for k, v in th_doc["thresholds"].items()}

    probs = {}
    B = 32
    with torch.no_grad():
        for i in range(0, len(ids), B):
            chunk = ids[i:i + B]
            enc = tok([texts[r] for r in chunk], padding=True, truncation=True,
                      max_length=256, return_tensors="pt").to(device)
            pr = torch.sigmoid(model(**enc).logits).cpu()
            for j, r in enumerate(chunk):
                probs[r] = {ids_cat[k]: pr[j][k].item() for k in range(len(ids_cat))}

    pred_tuned = {r: ({c for c, v in probs[r].items() if v >= th[c]}
                      or {max(probs[r], key=probs[r].get)}) for r in ids}
    pred_half = {r: ({c for c, v in probs[r].items() if v >= 0.5}
                     or {max(probs[r], key=probs[r].get)}) for r in ids}

    prev = json.loads((OUT / "free_threshold_tuning.json").read_text(encoding="utf-8"))
    rows = [
        ("A. เดิม argmax (ก่อนหน้า)", None, prev["results"]["A. argmax (ปัจจุบัน)"]),
        ("B. เดิม + เกณฑ์รายหมวด (ฟรี)", None,
         prev["results"]["C. เกณฑ์รายหมวด"]),
        ("C. multi-label th=0.5", pred_half, None),
        ("D. multi-label + เกณฑ์จูน", pred_tuned, None),
    ]

    p(f"{'วิธี':<30} {'ทาย/รีวิว':>9} {'P':>7} {'R':>7} {'micro-F1':>9} {'macro-F1':>9}")
    p("-" * 76)
    out = {}
    for nm, pred, cached in rows:
        if pred is None:
            p(f"{nm:<30} {cached['preds_per_review']:>9.2f} "
              f"{cached['precision']:>7.3f} {cached['recall']:>7.3f} "
              f"{cached['micro_f1_mean']:>9.4f} {cached['macro_f1_mean']:>9.4f}")
            out[nm] = cached
            continue
        s = score(gold, pred, ids, present)
        out[nm] = {k: v for k, v in s.items() if k != "per"}
        p(f"{nm:<30} {s['n_pred']:>9.2f} {s['p']:>7.3f} {s['r']:>7.3f} "
          f"{s['micro_f1']:>9.4f} {s['macro_f1']:>9.4f}")
    p("-" * 76)
    p(f"{'(ของจริงใน gold)':<30} {n_asp / len(ids):>9.2f}")

    s = score(gold, pred_tuned, ids, present)
    p("")
    p("รายหมวดของ D (multi-label + เกณฑ์จูน)")
    p(f"{'id':>3} {'หมวด':<36} {'ของจริง':>7} {'P':>7} {'R':>7} {'F1':>7}")
    for c in present:
        pr_, rc_, f1_ = s["per"][c]
        n = sum(1 for r in ids if c in gold[r])
        p(f"{c:>3} {names[c][:35]:<36} {n:>7} {pr_:>7.3f} {rc_:>7.3f} {f1_:>7.3f}")

    (OUT / "multilabel_gold_result.json").write_text(json.dumps({
        "n_reviews": len(ids), "n_aspects": n_asp,
        "thresholds": th, "results": out,
        "per_category_D": {str(c): {"n": sum(1 for r in ids if c in gold[r]),
                                    "precision": s["per"][c][0],
                                    "recall": s["per"][c][1],
                                    "f1": s["per"][c][2]} for c in present},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    p("")
    p(f"บันทึก {(OUT / 'multilabel_gold_result.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
