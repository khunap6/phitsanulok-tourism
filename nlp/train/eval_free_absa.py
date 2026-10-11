"""eval_free_absa.py — วัดว่าทำ ABSA ได้ไหมโดยไม่ต้องจ่ายค่า API

เทียบ 3 แบบ ใช้โมเดลที่เทรนไว้แล้วทั้งคู่ ไม่เทรนใหม่ ไม่ติดป้ายใหม่

  A. ปัจจุบัน     ข้อความเต็ม -> 1 หมวด + 1 อารมณ์   (เป็นพื้นให้เทียบ)
  B. เกณฑ์ softmax ข้อความเต็ม -> ทุกหมวดที่ความน่าจะเป็น >= t
                  ได้ multi-label ฟรี แต่อารมณ์มีค่าเดียว ต้องใช้ค่านั้น
                  กับทุกหมวด <- จุดที่คาดว่าจะพัง
  C. ตัดประโยค    ตัดที่คำขัดแย้ง แล้วยิงสองโมเดลทีละประโยคย่อย
                  ได้คู่ (หมวด, อารมณ์) จริง

ประเมินบนชุด gold ที่สะอาด (ตัดรายการที่รั่วไปชุดเทรนออกแล้ว)

⚠️ ข้อจำกัดที่ต้องระบุเวลารายงาน
  - โมเดลเดิมรู้จักหมวด v1 เท่านั้น ทำนายหมวดใหม่ 10/11 ไม่ได้เลย
    การกล่าวถึงหมวดพวกนั้นใน gold จึงนับเป็น "พลาด" เสมอ รายงานแยกไว้
  - โมเดลถูกเทรนด้วยรีวิวเต็ม การยิงด้วยประโยคย่อยคือใช้นอก distribution
  - เกณฑ์ t ของแบบ B จูนบนครึ่งแรกของชุด แล้วรายงานผลบนทั้งชุด
    ตัวเลขของ B จึงมองในแง่ดีกว่าความจริงเล็กน้อย

รัน:
  uv run python nlp/train/eval_free_absa.py
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
LAB = ROOT / "data" / "labeling"
OUT = ROOT / "reports" / "evaluation"

SENTS = ["positive", "neutral", "negative"]
SPLIT_RE = re.compile(r"(?:แต่|ยกเว้น|เสียแต่ว่า|เสียแต่|เพียงแต่|แค่ว่า)")
MIN_CLAUSE = 4


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def load_gold():
    """คืน (ids สะอาด, {rid: overall}, {rid: {cat_id: sentiment}}, {rid: text})"""
    clean = {int(x) for x in
             (OUT / "gold300_clean_ids.txt").read_text(encoding="utf-8").split()}
    overall, text = {}, {}
    for r in csv.DictReader(open(LAB / "reviews_labeled.csv", encoding="utf-8-sig")):
        rid = int(r["review_id"])
        if rid in clean:
            overall[rid] = r["overall_sentiment"].strip()
            text[rid] = r["text"].strip()
    aspects = defaultdict(dict)
    for r in csv.DictReader(open(LAB / "review_aspects.csv", encoding="utf-8-sig")):
        rid = int(r["review_id"])
        if rid in clean:
            aspects[rid][int(r["category_id"])] = r["aspect_sentiment"].strip()
    return sorted(clean), overall, dict(aspects), text


def load_map():
    """ชื่อหมวดเดิม -> id หมวดใหม่"""
    doc = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    m = {}
    for c in doc["categories"]:
        for old in c["old_names"]:
            m[old] = c["id"]
    return m, {c["id"]: c["name"] for c in doc["categories"]}


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
    return pr, rc, f1


def score_sets(gold: dict, pred: dict, ids: list) -> dict:
    """วัดหมวดแบบ multi-label: micro/macro-F1 + Jaccard + ตรงทั้งชุด"""
    tp = fp = fn = 0
    per = defaultdict(lambda: [0, 0, 0])
    jac, exact = [], 0
    for rid in ids:
        g, q = set(gold.get(rid, {})), set(pred.get(rid, set()))
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
    f1s = [prf(*per[c])[2] for c in sorted(per)]
    return {"micro_p": micro[0], "micro_r": micro[1], "micro_f1": micro[2],
            "macro_f1": sum(f1s) / len(f1s) if f1s else 0.0,
            "jaccard": sum(jac) / len(jac), "exact": exact / len(ids),
            "per_cat": {c: prf(*per[c]) for c in sorted(per)}}


def macro_f1_labels(gold: list, pred: list, labels: list):
    out = {}
    for lab in labels:
        tp = sum(1 for g, q in zip(gold, pred) if g == lab and q == lab)
        fp = sum(1 for g, q in zip(gold, pred) if g != lab and q == lab)
        fn = sum(1 for g, q in zip(gold, pred) if g == lab and q != lab)
        out[lab] = prf(tp, fp, fn)
    return sum(v[2] for v in out.values()) / len(labels), out


def main() -> None:
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                              pipeline)

    ids, gold_overall, gold_asp, text = load_gold()
    old2new, names = load_map()

    p("=" * 78)
    p("  ABSA แบบไม่เสียค่า API — ใช้โมเดลที่มีอยู่แล้ว")
    p("=" * 78)
    p(f"ชุดประเมิน : {len(ids)} รีวิว (gold ที่สะอาด)")
    n_asp = sum(len(v) for v in gold_asp.values())
    p(f"การกล่าวถึงรายหมวดใน gold : {n_asp} ครั้ง ({n_asp / len(ids):.2f} หมวด/รีวิว)")
    unreachable = sum(1 for v in gold_asp.values() for c in v if c in (10, 11))
    p(f"   เป็นหมวด 10/11 ที่โมเดลเดิมทำนายไม่ได้เลย : {unreachable} ครั้ง "
      f"({unreachable / n_asp * 100:.1f}%)")
    p("")

    def mk(name):
        pth = str(ROOT / "models" / f"wangchanberta-{name}")
        return pipeline("text-classification",
                        model=AutoModelForSequenceClassification.from_pretrained(pth),
                        tokenizer=AutoTokenizer.from_pretrained(pth),
                        truncation=True, max_length=256, device=0, top_k=None)

    cat_clf, sen_clf = mk("category"), mk("sentiment")

    whole = [text[r] for r in ids]
    cat_whole = cat_clf(whole, batch_size=32)
    sen_whole = sen_clf(whole, batch_size=32)

    clauses, owner = [], []
    for rid in ids:
        parts = [x.strip() for x in SPLIT_RE.split(text[rid])
                 if len(x.strip()) >= MIN_CLAUSE] or [text[rid]]
        for x in parts:
            clauses.append(x)
            owner.append(rid)
    cat_cl = cat_clf(clauses, batch_size=32)
    sen_cl = sen_clf(clauses, batch_size=32)
    p(f"ตัดประโยค : {len(ids)} รีวิว -> {len(clauses)} ประโยคย่อย "
      f"({len(clauses) / len(ids):.2f} ต่อรีวิว)")
    p("")

    def top(scores):
        return max(scores, key=lambda x: x["score"])

    pred_overall = {r: top(s)["label"] for r, s in zip(ids, sen_whole)}

    # A. ปัจจุบัน — 1 หมวด
    pred_A = {r: {old2new[top(s)["label"]]} for r, s in zip(ids, cat_whole)
              if top(s)["label"] in old2new}

    # B. เกณฑ์ softmax
    probs = {r: {old2new[x["label"]]: x["score"] for x in s if x["label"] in old2new}
             for r, s in zip(ids, cat_whole)}

    def apply_t(t, subset):
        return {r: ({c for c, v in probs[r].items() if v >= t}
                    or {max(probs[r], key=probs[r].get)}) for r in subset}

    tune = ids[:len(ids) // 2]
    curve = []
    best_t, best_f1 = 0.5, -1.0
    # เริ่มที่ 0.01 เพราะรอบแรกค่าที่ดีที่สุดไปชนขอบล่างของช่วงที่ค้น (0.05)
    # ถ้าไม่ขยายช่วงจะไม่รู้ว่าค่าจริงอยู่ต่ำกว่านั้นหรือไม่
    for i in [1, 2, 3, 5, 8, 10, 15, 20, 25, 30, 40, 50]:
        t = i / 100
        f1 = score_sets(gold_asp, apply_t(t, tune), tune)["micro_f1"]
        curve.append((t, f1))
        if f1 > best_f1:
            best_t, best_f1 = t, f1
    pred_B = apply_t(best_t, ids)

    # C. ตัดประโยค
    byrid = defaultdict(list)
    for rid, c, s in zip(owner, cat_cl, sen_cl):
        lab = top(c)["label"]
        if lab in old2new:
            byrid[rid].append((old2new[lab], top(s)["label"]))
    pred_C, asp_sent_C = {}, {}
    for rid in ids:
        got = defaultdict(list)
        for cid, sn in byrid.get(rid, []):
            got[cid].append(sn)
        pred_C[rid] = set(got)
        # หมวดเดียวมีทั้งชมและติ -> neutral (คู่มือข้อ 2)
        asp_sent_C[rid] = {c: (v[0] if len(set(v)) == 1 else "neutral")
                           for c, v in got.items()}

    p("-" * 78)
    p(f"  [1] หมวด (multi-label) — วัดบน {len(ids)} รีวิว")
    p("-" * 78)
    p(f"{'แบบ':<30} {'ทาย/รีวิว':>9} {'micro-P':>8} {'micro-R':>8} "
      f"{'micro-F1':>9} {'macro-F1':>9} {'ตรงชุด':>8}")
    res = {}
    for nm, pr in (("A. ปัจจุบัน (1 หมวด)", pred_A),
                   (f"B. เกณฑ์ softmax (t={best_t:.2f})", pred_B),
                   ("C. ตัดประโยค", pred_C)):
        s = score_sets(gold_asp, pr, ids)
        res[nm] = s
        npr = sum(len(pr.get(r, ())) for r in ids) / len(ids)
        p(f"{nm:<30} {npr:>9.2f} {s['micro_p']:>8.4f} {s['micro_r']:>8.4f} "
          f"{s['micro_f1']:>9.4f} {s['macro_f1']:>9.4f} {s['exact'] * 100:>7.1f}%")
    p(f"{'(ของจริงใน gold)':<30} {n_asp / len(ids):>9.2f}")
    p("")
    p("  เกณฑ์ t ที่ลองบนครึ่งแรก (micro-F1):")
    p("   " + "  ".join(f"{t:.2f}={f:.3f}" for t, f in curve[:6]))
    p("   " + "  ".join(f"{t:.2f}={f:.3f}" for t, f in curve[6:]))

    p("")
    p("-" * 78)
    p("  [2] อารมณ์รวมของรีวิว")
    p("-" * 78)
    g = [gold_overall[r] for r in ids]
    q = [pred_overall[r] for r in ids]
    mf, per = macro_f1_labels(g, q, SENTS)
    mf0, _ = macro_f1_labels(g, ["positive"] * len(ids), SENTS)
    acc = sum(1 for a, b in zip(g, q) if a == b) / len(g)
    acc0 = g.count("positive") / len(g)
    p(f"โมเดล                macro-F1 {mf:.4f} | accuracy {acc:.4f}")
    p(f"baseline ทายบวกหมด    macro-F1 {mf0:.4f} | accuracy {acc0:.4f}")
    p(f"   -> ดีกว่า baseline {mf - mf0:+.4f} macro-F1")
    p("")
    p(f"{'คลาส':<10} {'จำนวนจริง':>9} {'precision':>10} {'recall':>8} {'F1':>8}")
    for s in SENTS:
        pr_, rc_, f1_ = per[s]
        p(f"{s:<10} {g.count(s):>9} {pr_:>10.4f} {rc_:>8.4f} {f1_:>8.4f}")

    p("")
    p("-" * 78)
    p("  [3] อารมณ์รายหมวด — วัดเฉพาะหมวดที่ทายถูก")
    p("-" * 78)
    aspect_res = {}
    for nm, asp in (("B. ใช้อารมณ์รวมกับทุกหมวด",
                     {r: {c: pred_overall[r] for c in pred_B[r]} for r in ids}),
                    ("C. อารมณ์ของประโยคย่อยนั้น", asp_sent_C)):
        gl, ql = [], []
        for rid in ids:
            for c, sn in asp.get(rid, {}).items():
                if c in gold_asp.get(rid, {}):
                    gl.append(gold_asp[rid][c])
                    ql.append(sn)
        if not gl:
            continue
        m, pc = macro_f1_labels(gl, ql, SENTS)
        a = sum(1 for x, y in zip(gl, ql) if x == y) / len(gl)
        aspect_res[nm] = {"n": len(gl), "macro_f1": m, "accuracy": a,
                          "negative_precision": pc["negative"][0],
                          "negative_recall": pc["negative"][1]}
        p(f"{nm:<30} n={len(gl):>4} | macro-F1 {m:.4f} | acc {a:.4f}")
        p(f"   negative: precision {pc['negative'][0]:.3f} "
          f"recall {pc['negative'][1]:.3f}  (ของจริง {gl.count('negative')} ครั้ง)")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "free_absa_baseline.json").write_text(json.dumps({
        "n_reviews": len(ids), "n_aspects": n_asp,
        "unreachable_cat_10_11": unreachable,
        "clauses_per_review": len(clauses) / len(ids),
        "best_threshold": best_t,
        "category": {k: {kk: vv for kk, vv in v.items() if kk != "per_cat"}
                     for k, v in res.items()},
        "overall_sentiment": {"macro_f1": mf, "accuracy": acc,
                              "baseline_all_positive_macro_f1": mf0,
                              "baseline_all_positive_accuracy": acc0},
        "aspect_sentiment": aspect_res,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    p("")
    p(f"บันทึก {OUT / 'free_absa_baseline.json'}")


if __name__ == "__main__":
    main()
