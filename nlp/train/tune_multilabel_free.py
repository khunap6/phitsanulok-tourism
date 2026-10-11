"""tune_multilabel_free.py — รีดความแม่นจากโมเดลเดิมโดยไม่เทรนใหม่ ไม่เสียค่า API

แนวคิด: โมเดลหมวดเป็น single-label (softmax) แต่มันคายความน่าจะเป็นครบทุกหมวด
ถ้าเลือก "ทุกหมวดที่เกินเกณฑ์" ก็ได้ multi-label ฟรี คำถามคือเกณฑ์ควรเป็นเท่าไร

  A. argmax         เอาหมวดเดียวที่คะแนนสูงสุด  (ของปัจจุบัน)
  B. เกณฑ์เดียว     ทุกหมวดที่ >= t  โดย t เดียวใช้ทั้ง 11 หมวด
  C. เกณฑ์รายหมวด   แต่ละหมวดมี t ของตัวเอง   <- ตัวที่คาดว่าดีที่สุด
  D. top-k          เอา k หมวดแรกเสมอ
  E. ตัดประโยค      รวมหมวดที่ได้จากแต่ละประโยคย่อย
  F. C รวมกับ E     union ของสองวิธี

⚠️ ทำไมต้อง cross-validation
  ชุด gold มีแค่ 251 รายการ ถ้าจูนเกณฑ์แล้ววัดบนชุดเดียวกัน ตัวเลขจะสวยเกินจริง
  ที่นี่แบ่ง 5 ส่วน จูนบน 4 ส่วน วัดบนส่วนที่เหลือ วนครบทุกส่วน แล้วเฉลี่ย
  ตัวเลขที่ได้จึงเป็นค่าที่คาดว่าจะเจอกับข้อมูลที่โมเดลไม่เคยเห็น

⚠️ หมวด 10 และ 11 โมเดลเดิมทำนายไม่ได้เลย (ไม่มีใน v1)
  การกล่าวถึงหมวดพวกนั้นจึงนับเป็นพลาดเสมอ ไม่ว่าจะจูนยังไง

รัน:
  uv run python nlp/train/cache_gold_preds.py      # ครั้งเดียว
  uv run python nlp/train/tune_multilabel_free.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "reports" / "evaluation"
CACHE = OUT / "gold_preds_cache.json"

N_FOLD = 5
GRID = [i / 100 for i in range(1, 71, 1)]


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def prf(tp: int, fp: int, fn: int):
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return pr, rc, (2 * pr * rc / (pr + rc) if pr + rc else 0.0)


def counts(gold: dict, pred: dict, ids: list):
    """คืน (tp, fp, fn รวม) และแยกรายหมวด"""
    tp = fp = fn = 0
    per = defaultdict(lambda: [0, 0, 0])
    for rid in ids:
        g, q = gold[rid], pred[rid]
        tp += len(g & q)
        fp += len(q - g)
        fn += len(g - q)
        for c in g & q:
            per[c][0] += 1
        for c in q - g:
            per[c][1] += 1
        for c in g - q:
            per[c][2] += 1
    return (tp, fp, fn), per


def micro_f1(gold, pred, ids):
    return prf(*counts(gold, pred, ids)[0])[2]


def macro_f1(gold, pred, ids, all_cats):
    _, per = counts(gold, pred, ids)
    return sum(prf(*per[c])[2] for c in all_cats) / len(all_cats)


def apply_thresholds(prob: dict, th: dict, ids: list, force_one=True):
    out = {}
    for rid in ids:
        pr = prob[rid]
        s = {c for c, v in pr.items() if v >= th.get(c, 0.5)}
        if not s and force_one and pr:
            s = {max(pr, key=pr.get)}
        out[rid] = s
    return out


def tune_global(gold, prob, ids, all_cats, objective):
    best_t, best = 0.5, -1.0
    for t in GRID:
        pred = apply_thresholds(prob, {c: t for c in all_cats}, ids)
        v = objective(gold, pred, ids)
        if v > best:
            best_t, best = t, v
    return {c: best_t for c in all_cats}, best_t


def tune_per_cat(gold, prob, ids, all_cats, objective, start_t, passes=3):
    """coordinate ascent — ไล่ปรับทีละหมวด ค้างหมวดอื่นไว้ วนหลายรอบ"""
    th = {c: start_t for c in all_cats}
    for _ in range(passes):
        changed = False
        for c in all_cats:
            cur = th[c]
            best_t, best = cur, objective(gold, apply_thresholds(prob, th, ids), ids)
            for t in GRID:
                th[c] = t
                v = objective(gold, apply_thresholds(prob, th, ids), ids)
                if v > best + 1e-9:
                    best_t, best = t, v
            th[c] = best_t
            changed = changed or best_t != cur
        if not changed:
            break
    return th


def main() -> None:
    doc = json.loads(CACHE.read_text(encoding="utf-8"))
    R = doc["reviews"]
    ids = sorted(R, key=int)

    gold = {r: {int(c) for c in R[r]["gold_aspects"]} for r in ids}
    prob = {r: {int(c): v for c, v in R[r]["cat_prob"].items()} for r in ids}
    clause = {r: {int(c) for cl in R[r]["clauses"]
                  for c, v in cl["cat_prob"].items()
                  if v == max(cl["cat_prob"].values())} for r in ids}
    all_cats = sorted({c for g in gold.values() for c in g}
                      | {c for pr in prob.values() for c in pr})

    p("=" * 76)
    p("  รีดความแม่นจากโมเดลเดิม — ไม่เทรนใหม่ ไม่เสียค่า API")
    p("=" * 76)
    p(f"ชุด gold {len(ids)} รีวิว · หมวดที่เกี่ยวข้อง {len(all_cats)} หมวด")
    reach = {c for pr in prob.values() for c in pr}
    miss = [c for c in all_cats if c not in reach]
    p(f"หมวดที่โมเดลเดิมทำนายไม่ได้เลย : {miss or 'ไม่มี'}")
    p(f"ประเมินแบบ {N_FOLD}-fold CV (จูนบน {N_FOLD-1} ส่วน วัดบนส่วนที่เหลือ)")
    p("")

    folds = [ids[i::N_FOLD] for i in range(N_FOLD)]
    methods = ["A. argmax (ปัจจุบัน)", "B. เกณฑ์เดียว", "C. เกณฑ์รายหมวด",
               "D. top-k", "E. ตัดประโยค", "F. C รวม E",
               "G. เกณฑ์รายหมวด (จูน macro)"]
    acc = {m: {"mi": [], "ma": [], "p": [], "r": [], "n": []} for m in methods}
    th_log = []

    for fi in range(N_FOLD):
        te = folds[fi]
        tr = [r for j, f in enumerate(folds) if j != fi for r in f]

        th_g, t_global = tune_global(gold, prob, tr, all_cats, micro_f1)
        th_c = tune_per_cat(gold, prob, tr, all_cats, micro_f1, t_global)
        th_log.append(dict(th_c))

        best_k, best_v = 1, -1.0
        for k in (1, 2, 3, 4):
            pk = {r: set(sorted(prob[r], key=prob[r].get, reverse=True)[:k])
                  for r in tr}
            v = micro_f1(gold, pk, tr)
            if v > best_v:
                best_k, best_v = k, v

        preds = {
            methods[0]: {r: ({max(prob[r], key=prob[r].get)} if prob[r] else set())
                         for r in te},
            methods[1]: apply_thresholds(prob, th_g, te),
            methods[2]: apply_thresholds(prob, th_c, te),
            methods[3]: {r: set(sorted(prob[r], key=prob[r].get,
                                       reverse=True)[:best_k]) for r in te},
            methods[4]: {r: clause[r] for r in te},
        }
        pc = apply_thresholds(prob, th_c, te)
        preds[methods[5]] = {r: pc[r] | clause[r] for r in te}

        # จูนด้วยเป้าหมาย macro-F1 แทน — ให้น้ำหนักหมวดเล็กเท่าหมวดใหญ่
        th_m = tune_per_cat(gold, prob, tr, all_cats,
                            lambda g, p_, i: macro_f1(g, p_, i, all_cats), t_global)
        preds[methods[6]] = apply_thresholds(prob, th_m, te)

        for m, pr in preds.items():
            (tp, fp, fn), _ = counts(gold, pr, te)
            pp, rr, ff = prf(tp, fp, fn)
            acc[m]["mi"].append(ff)
            acc[m]["ma"].append(macro_f1(gold, pr, te, all_cats))
            acc[m]["p"].append(pp)
            acc[m]["r"].append(rr)
            acc[m]["n"].append(sum(len(pr[r]) for r in te) / len(te))

    def mean(xs):
        return sum(xs) / len(xs)

    def sd(xs):
        m = mean(xs)
        return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5

    p("-" * 76)
    p(f"{'วิธี':<24} {'ทาย/รีวิว':>9} {'P':>7} {'R':>7} {'micro-F1':>16} {'macro-F1':>8}")
    p("-" * 76)
    base = mean(acc[methods[0]]["mi"])
    for m in methods:
        a = acc[m]
        d = mean(a["mi"]) - base
        tag = "" if m == methods[0] else f" ({d:+.3f})"
        p(f"{m:<24} {mean(a['n']):>9.2f} {mean(a['p']):>7.3f} {mean(a['r']):>7.3f} "
          f"{mean(a['mi']):>8.4f}±{sd(a['mi']):.3f}{tag:<9} {mean(a['ma']):>8.4f}")
    p("-" * 76)
    p(f"{'(ของจริงใน gold)':<24} "
      f"{sum(len(gold[r]) for r in ids) / len(ids):>9.2f}")

    p("")
    p("เกณฑ์รายหมวดที่จูนได้ (เฉลี่ยจาก 5 fold):")
    for c in all_cats:
        vals = [t[c] for t in th_log]
        n_gold = sum(1 for r in ids if c in gold[r])
        flag = "  <- โมเดลทำนายไม่ได้" if c in miss else ""
        p(f"   หมวด {c:>2} : t={mean(vals):.3f} (sd {sd(vals):.3f})  "
          f"ของจริง {n_gold:>3} ครั้ง{flag}")

    best = max(methods, key=lambda m: mean(acc[m]["mi"]))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "free_threshold_tuning.json").write_text(json.dumps({
        "n_reviews": len(ids), "n_folds": N_FOLD,
        "unreachable_categories": miss,
        "results": {m: {"micro_f1_mean": mean(acc[m]["mi"]),
                        "micro_f1_sd": sd(acc[m]["mi"]),
                        "macro_f1_mean": mean(acc[m]["ma"]),
                        "precision": mean(acc[m]["p"]),
                        "recall": mean(acc[m]["r"]),
                        "preds_per_review": mean(acc[m]["n"])}
                    for m in methods},
        "best_method": best,
        "per_category_threshold_mean": {str(c): mean([t[c] for t in th_log])
                                        for c in all_cats},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    p("")
    p(f"ดีที่สุด: {best}  micro-F1 {mean(acc[best]['mi']):.4f}")
    p(f"บันทึก {(OUT / 'free_threshold_tuning.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
