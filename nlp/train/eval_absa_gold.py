"""eval_absa_gold.py — วัด ABSA ทั้งระบบบนชุด gold ที่สะอาด

วัด 2 ระดับ แยกกันเพื่อให้รู้ว่าความผิดพลาดมาจากไหน

  [1] อารมณ์รายหมวด โดยกำหนดหมวดให้ถูกไว้ก่อน (ใช้หมวดของ gold)
      แยกความสามารถของโมเดลอารมณ์ออกจากความผิดพลาดของโมเดลหมวด
      เทียบกับ  - ใช้อารมณ์รวมกับทุกหมวด  <- สิ่งที่ multi-label เพียว ๆ จะทำ
                - ทายบวกหมด               <- baseline ที่ต้องเอาชนะให้ได้

  [2] ทั้งระบบ: ทำนายหมวดเอง แล้วทำนายอารมณ์ของแต่ละหมวดที่ทายได้
      นับว่าถูกเมื่อ "ทั้งหมวดและอารมณ์" ตรงกับ gold (คู่ต้องตรงทั้งคู่)
      นี่คือตัวเลขที่เอาไปอ้างในเล่มได้ว่าระบบทำงานได้แค่ไหนจริง ๆ

⚠️ ชุด gold เป็น positive 88% เคส "ชมอย่างติอย่าง" จึงมีน้อย
  ส่วน [1] จึงรายงานแยกเฉพาะรีวิวที่มีหลายหมวดและอารมณ์ไม่เหมือนกันด้วย
  เพราะนั่นคือกลุ่มเดียวที่ ABSA ต่างจากการใช้อารมณ์รวม

รัน:
  uv run python nlp/train/eval_absa_gold.py
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
LAB = ROOT / "data" / "labeling"
OUT = ROOT / "reports" / "evaluation"
M_CAT = ROOT / "models" / "wangchanberta-category-multilabel"
M_ASP = ROOT / "models" / "wangchanberta-aspect-sentiment"
M_SEN = ROOT / "models" / "wangchanberta-sentiment"
SENTS = ["positive", "neutral", "negative"]


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def prf(tp, fp, fn):
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return pr, rc, (2 * pr * rc / (pr + rc) if pr + rc else 0.0)


def sent_report(gold: list, pred: list):
    per = {}
    for s in SENTS:
        per[s] = prf(sum(1 for g, q in zip(gold, pred) if g == s and q == s),
                     sum(1 for g, q in zip(gold, pred) if g != s and q == s),
                     sum(1 for g, q in zip(gold, pred) if g == s and q != s))
    macro = sum(v[2] for v in per.values()) / 3
    acc = sum(1 for g, q in zip(gold, pred) if g == q) / len(gold) if gold else 0.0
    return macro, acc, per


def main() -> None:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    doc = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    ids_cat = [c["id"] for c in doc["categories"]]
    names = {c["id"]: c["name"] for c in doc["categories"]}

    clean = {int(x) for x in
             (OUT / "gold300_clean_ids.txt").read_text(encoding="utf-8").split()}
    texts, overall = {}, {}
    for r in csv.DictReader(open(LAB / "reviews_labeled.csv", encoding="utf-8-sig")):
        rid = int(r["review_id"])
        if rid in clean:
            texts[rid] = r["text"].strip()
            overall[rid] = r["overall_sentiment"].strip()
    gold = defaultdict(dict)
    for r in csv.DictReader(open(LAB / "review_aspects.csv", encoding="utf-8-sig")):
        rid = int(r["review_id"])
        if rid in clean:
            gold[rid][int(r["category_id"])] = r["aspect_sentiment"].strip()
    ids = sorted(texts)

    device = "cuda" if torch.cuda.is_available() else "cpu"

    def load(path):
        return (AutoTokenizer.from_pretrained(str(path)),
                AutoModelForSequenceClassification.from_pretrained(str(path)).to(device).eval())

    tok_a, mdl_a = load(M_ASP)
    tok_c, mdl_c = load(M_CAT)
    tok_s, mdl_s = load(M_SEN)

    @torch.no_grad()
    def aspect_sent(pairs):
        """pairs = [(ชื่อหมวด, ข้อความ), ...] -> [อารมณ์, ...]"""
        out = []
        for i in range(0, len(pairs), 32):
            ch = pairs[i:i + 32]
            enc = tok_a([x[0] for x in ch], [x[1] for x in ch], padding=True,
                        truncation=True, max_length=256, return_tensors="pt").to(device)
            out += [SENTS[j] for j in mdl_a(**enc).logits.argmax(-1).cpu().tolist()]
        return out

    @torch.no_grad()
    def whole_sent(tx):
        out = []
        for i in range(0, len(tx), 32):
            enc = tok_s(tx[i:i + 32], padding=True, truncation=True,
                        max_length=256, return_tensors="pt").to(device)
            lg = mdl_s(**enc).logits.argmax(-1).cpu().tolist()
            out += [mdl_s.config.id2label[j] for j in lg]
        return out

    @torch.no_grad()
    def pred_cats(tx):
        res = []
        for i in range(0, len(tx), 32):
            enc = tok_c(tx[i:i + 32], padding=True, truncation=True,
                        max_length=256, return_tensors="pt").to(device)
            pr = torch.sigmoid(mdl_c(**enc).logits).cpu()
            for j in range(pr.shape[0]):
                s = {ids_cat[k] for k in range(len(ids_cat)) if pr[j][k] >= 0.5}
                res.append(s or {ids_cat[int(pr[j].argmax())]})
        return res

    p("=" * 76)
    p("  ABSA ทั้งระบบ บนชุด gold ที่สะอาด")
    p("=" * 76)
    n_pair = sum(len(v) for v in gold.values())
    p(f"gold {len(ids)} รีวิว · {n_pair} คู่ (หมวด, อารมณ์)")
    mixed = [r for r in ids if len(set(gold[r].values())) > 1]
    p(f"รีวิวที่หมวดต่าง ๆ มีอารมณ์ไม่เหมือนกัน : {len(mixed)} "
      f"({len(mixed) / len(ids) * 100:.1f}%)  <- กลุ่มที่ ABSA ต่างจากอารมณ์รวม")
    p("")

    # ---------- [1] อารมณ์รายหมวด โดยให้หมวดถูกไว้ก่อน ----------
    flat = [(r, c) for r in ids for c in gold[r]]
    g_lab = [gold[r][c] for r, c in flat]
    ov = dict(zip(ids, whole_sent([texts[r] for r in ids])))
    pred_ov = [ov[r] for r, _ in flat]
    pred_as = aspect_sent([(names[c], texts[r]) for r, c in flat])
    pred_pos = ["positive"] * len(flat)

    p("-" * 76)
    p("  [1] อารมณ์รายหมวด (กำหนดหมวดให้ถูกไว้ก่อน)")
    p("-" * 76)
    p(f"{'วิธี':<34} {'n':>5} {'macro-F1':>9} {'acc':>7}  negative P/R")
    res1 = {}
    for nm, pr in (("ทายบวกหมด (baseline)", pred_pos),
                   ("ใช้อารมณ์รวมกับทุกหมวด", pred_ov),
                   ("โมเดลอารมณ์รายหมวด", pred_as)):
        macro, acc, per = sent_report(g_lab, pr)
        res1[nm] = {"macro_f1": macro, "accuracy": acc,
                    "per_class": {s: list(per[s]) for s in SENTS}}
        p(f"{nm:<34} {len(flat):>5} {macro:>9.4f} {acc:>7.4f}  "
          f"{per['negative'][0]:.3f} / {per['negative'][1]:.3f}")

    sub = [i for i, (r, _) in enumerate(flat) if r in mixed]
    p("")
    p(f"  เฉพาะรีวิวที่อารมณ์ไม่เหมือนกันทุกหมวด ({len(sub)} คู่)")
    res1b = {}
    for nm, pr in (("ใช้อารมณ์รวมกับทุกหมวด", pred_ov),
                   ("โมเดลอารมณ์รายหมวด", pred_as)):
        gg = [g_lab[i] for i in sub]
        qq = [pr[i] for i in sub]
        macro, acc, per = sent_report(gg, qq)
        res1b[nm] = {"macro_f1": macro, "accuracy": acc}
        p(f"  {nm:<32} {len(sub):>5} {macro:>9.4f} {acc:>7.4f}")

    # ---------- [2] ทั้งระบบ ----------
    pc = dict(zip(ids, pred_cats([texts[r] for r in ids])))
    pairs = [(r, c) for r in ids for c in sorted(pc[r])]
    ps = dict(zip(pairs, aspect_sent([(names[c], texts[r]) for r, c in pairs])))

    p("")
    p("-" * 76)
    p("  [2] ทั้งระบบ — ทายหมวดเอง แล้วทายอารมณ์ของหมวดนั้น")
    p("-" * 76)
    res2 = {}
    for nm, sent_of in (("คู่ (หมวด, อารมณ์) ต้องตรงทั้งคู่", lambda r, c: ps[(r, c)]),
                        ("ถ้าใช้อารมณ์รวมแทน", lambda r, c: ov[r])):
        tp = fp = fn = 0
        for r in ids:
            g = {(c, s) for c, s in gold[r].items()}
            q = {(c, sent_of(r, c)) for c in pc[r]}
            tp += len(g & q)
            fp += len(q - g)
            fn += len(g - q)
        pr_, rc_, f1_ = prf(tp, fp, fn)
        res2[nm] = {"precision": pr_, "recall": rc_, "micro_f1": f1_}
        p(f"{nm:<42} P {pr_:.3f}  R {rc_:.3f}  micro-F1 {f1_:.4f}")

    tp = sum(len({(c, s) for c, s in gold[r].items()} & {(c, ps[(r, c)]) for c in pc[r]})
             for r in ids)
    tp_cat = sum(len(set(gold[r]) & pc[r]) for r in ids)
    p("")
    p(f"หมวดที่ทายถูก {tp_cat} จาก {n_pair} | ในนั้นอารมณ์ถูกด้วย {tp} "
      f"({tp / tp_cat * 100:.1f}%)")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "absa_gold_result.json").write_text(json.dumps({
        "n_reviews": len(ids), "n_pairs": n_pair,
        "n_mixed_sentiment_reviews": len(mixed),
        "aspect_sentiment_given_gold_categories": res1,
        "aspect_sentiment_mixed_subset": res1b,
        "end_to_end": res2,
        "category_hits": tp_cat, "category_and_sentiment_hits": tp,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    p("")
    p(f"บันทึก {(OUT / 'absa_gold_result.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
