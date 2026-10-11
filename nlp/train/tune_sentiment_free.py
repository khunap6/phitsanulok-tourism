"""tune_sentiment_free.py — ดึง macro-F1 ของอารมณ์ขึ้นโดยไม่เทรนใหม่

ปัญหาที่แก้: โมเดลอารมณ์ถูกเทรนบนข้อมูลที่ positive ~88%
มันจึงเอนไปทาง positive จนคลาสน้อยถูกกลืน — วัดได้ว่า neutral recall = 0.235
ทั้งที่ accuracy สูงถึง 0.9203 (ซึ่งหลอก เพราะทายบวกหมดก็ได้ 0.88 แล้ว)

วิธีที่ใช้: ปรับน้ำหนักรายคลาส แล้วค่อย argmax
    label = argmax_c ( p(c) * w(c) )
w(c) > 1 ทำให้คลาสนั้นชนะง่ายขึ้น เป็นการชดเชยความเอนของ prior
ไม่ต้องเทรนใหม่ ไม่ต้องติดป้ายใหม่ ใช้ความน่าจะเป็นที่โมเดลคายออกมาอยู่แล้ว

⚠️ ประเมินแบบ 5-fold CV — จูน w บน 4 ส่วน วัดบนส่วนที่เหลือ
   ถ้าจูนแล้ววัดบนชุดเดียวกัน ตัวเลขจะสวยเกินจริง

⚠️ การปรับ w แลก accuracy กับ macro-F1 เสมอ
   accuracy จะลดลงเล็กน้อย เพราะยอมทายผิดคลาสใหญ่เพื่อจับคลาสเล็กได้มากขึ้น
   ซึ่งเป็นสิ่งที่ต้องการ เพราะ accuracy ไม่ใช่ตัวชี้วัดหลักของงานนี้

รัน:
  uv run python nlp/train/cache_gold_preds.py      # ครั้งเดียว
  uv run python nlp/train/tune_sentiment_free.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "reports" / "evaluation"
CACHE = OUT / "gold_preds_cache.json"

SENTS = ["positive", "neutral", "negative"]
N_FOLD = 5
# น้ำหนักที่ลอง — 1.0 คือไม่ปรับ ค่ามากกว่านั้นคือดันคลาสนั้นให้ชนะง่ายขึ้น
WGRID = [1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0]


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def prf(tp, fp, fn):
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return pr, rc, (2 * pr * rc / (pr + rc) if pr + rc else 0.0)


def per_class(gold, pred):
    out = {}
    for lab in SENTS:
        tp = sum(1 for g, q in zip(gold, pred) if g == lab and q == lab)
        fp = sum(1 for g, q in zip(gold, pred) if g != lab and q == lab)
        fn = sum(1 for g, q in zip(gold, pred) if g == lab and q != lab)
        out[lab] = prf(tp, fp, fn)
    return out


def macro(gold, pred):
    return sum(v[2] for v in per_class(gold, pred).values()) / len(SENTS)


def predict(prob, ids, w):
    return [max(SENTS, key=lambda c: prob[r].get(c, 0.0) * w[c]) for r in ids]


def tune(prob, gold, ids, passes=3):
    """coordinate ascent บนน้ำหนักรายคลาส เป้าหมาย macro-F1"""
    w = {c: 1.0 for c in SENTS}
    g = [gold[r] for r in ids]
    for _ in range(passes):
        changed = False
        for c in SENTS:
            cur, best, bv = w[c], w[c], macro(g, predict(prob, ids, w))
            for cand in WGRID:
                w[c] = cand
                v = macro(g, predict(prob, ids, w))
                if v > bv + 1e-9:
                    best, bv = cand, v
            w[c] = best
            changed = changed or best != cur
        if not changed:
            break
    return w


def main() -> None:
    doc = json.loads(CACHE.read_text(encoding="utf-8"))
    R = doc["reviews"]
    ids = sorted(R, key=int)
    gold = {r: R[r]["gold_overall"] for r in ids}
    prob = {r: R[r]["sent_prob"] for r in ids}

    p("=" * 74)
    p("  ปรับน้ำหนักคลาสของโมเดลอารมณ์ — ไม่เทรนใหม่ ไม่เสียค่า API")
    p("=" * 74)
    dist = {s: sum(1 for r in ids if gold[r] == s) for s in SENTS}
    p(f"ชุด gold {len(ids)} รีวิว : " +
      " | ".join(f"{s} {dist[s]}" for s in SENTS))
    p(f"ประเมินแบบ {N_FOLD}-fold CV")
    p("")

    folds = [ids[i::N_FOLD] for i in range(N_FOLD)]
    rows = {"A. เดิม (argmax)": [], "B. ปรับน้ำหนักคลาส": []}
    wlog = []
    for fi in range(N_FOLD):
        te = folds[fi]
        tr = [r for j, f in enumerate(folds) if j != fi for r in f]
        g = [gold[r] for r in te]
        rows["A. เดิม (argmax)"].append((g, predict(prob, te, {c: 1.0 for c in SENTS})))
        w = tune(prob, gold, tr)
        wlog.append(w)
        rows["B. ปรับน้ำหนักคลาส"].append((g, predict(prob, te, w)))

    p(f"{'วิธี':<22} {'macro-F1':>9} {'accuracy':>9}   รายคลาส (P / R / F1)")
    p("-" * 74)
    summary = {}
    for nm, parts in rows.items():
        g = [x for gg, _ in parts for x in gg]
        q = [x for _, qq in parts for x in qq]
        m, a = macro(g, q), sum(1 for x, y in zip(g, q) if x == y) / len(g)
        pc = per_class(g, q)
        summary[nm] = {"macro_f1": m, "accuracy": a,
                       "per_class": {s: list(pc[s]) for s in SENTS}}
        p(f"{nm:<22} {m:>9.4f} {a:>9.4f}")
        for s in SENTS:
            pr, rc, f1 = pc[s]
            p(f"{'':<22} {s:>9}   {pr:.3f} / {rc:.3f} / {f1:.3f}")
    gall = [x for gg, _ in rows["A. เดิม (argmax)"] for x in gg]
    mf0 = macro(gall, ["positive"] * len(gall))
    p("-" * 74)
    p(f"{'baseline ทายบวกหมด':<22} {mf0:>9.4f} "
      f"{gall.count('positive') / len(gall):>9.4f}")
    p("")
    p("น้ำหนักที่จูนได้ (เฉลี่ย 5 fold):")
    for s in SENTS:
        vs = [w[s] for w in wlog]
        p(f"   {s:<9} w = {sum(vs) / len(vs):.2f}")

    (OUT / "free_sentiment_tuning.json").write_text(json.dumps({
        "n_reviews": len(ids), "n_folds": N_FOLD, "gold_distribution": dist,
        "results": summary, "baseline_all_positive_macro_f1": mf0,
        "weights_mean": {s: sum(w[s] for w in wlog) / len(wlog) for s in SENTS},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    p("")
    p(f"บันทึก {(OUT / 'free_sentiment_tuning.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
