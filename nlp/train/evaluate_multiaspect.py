"""evaluate_multiaspect.py — Phase 5: รายงานผลการวัดทั้งชุดสำหรับเขียนลงเล่ม

สร้างทุกอย่างจากโมเดลกับชุด gold ในครั้งเดียว เพื่อให้ตัวเลขทุกที่ตรงกันแน่นอน
ไม่ใช่ไปรวมผลจากหลายสคริปต์ที่อาจรันคนละเวอร์ชัน

ไฟล์ที่ได้ (reports/evaluation/)
  multiaspect_report.md            รายงานฉบับอ่านได้ เอาไปเรียบเรียงลงเล่มได้เลย
  multiaspect_summary.json         ตัวเลขทั้งหมดแบบเครื่องอ่าน
  cm_overall_sentiment.csv         confusion matrix อารมณ์รวม
  cm_aspect_sentiment.csv          confusion matrix อารมณ์รายหมวด
  per_category.csv                 P/R/F1 รายหมวด
  per_class_overall.csv            P/R/F1 รายคลาสอารมณ์รวม
  per_class_aspect.csv             P/R/F1 รายคลาสอารมณ์รายหมวด

⚠️ ตามข้อกำหนดของผู้ใช้
  - ห้ามใช้ accuracy เป็นตัวชี้วัดหลัก (ข้อมูล positive ~88% ทายบวกหมดก็ได้ 0.88)
  - ต้องรายงาน macro-F1 + precision/recall ของ negative แยกรายคลาส
  - ต้องเทียบกับ baseline ที่ทายว่า positive ทุกรีวิว
  - ต้องมี confusion matrix

⚠️ ประเมินบนชุด gold ที่ตัดรายการรั่วออกแล้ว 251 จาก 300
  49 รายการที่เหลือมีข้อความซ้ำกับชุดเทรนของโมเดลหมวดรุ่นเดิม
  (ดู reports/evaluation/gold300_leakage.csv)

รัน:
  uv run python nlp/train/evaluate_multiaspect.py
"""
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
LAB = ROOT / "data" / "labeling"
OUT = ROOT / "reports" / "evaluation"
M_CAT = ROOT / "models" / "wangchanberta-category-multilabel"
M_ASP = ROOT / "models" / "wangchanberta-aspect-sentiment"
M_OVR = ROOT / "models" / "wangchanberta-overall-sentiment"
M_OLD_SEN = ROOT / "models" / "wangchanberta-sentiment"
SENTS = ["positive", "neutral", "negative"]


def p(m: str = "") -> None:
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        print(m.encode("ascii", "replace").decode("ascii"), flush=True)


def prf(tp, fp, fn):
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return pr, rc, (2 * pr * rc / (pr + rc) if pr + rc else 0.0)


def class_report(gold: list, pred: list, labels: list):
    per = {}
    for lab in labels:
        per[lab] = prf(sum(1 for g, q in zip(gold, pred) if g == lab and q == lab),
                       sum(1 for g, q in zip(gold, pred) if g != lab and q == lab),
                       sum(1 for g, q in zip(gold, pred) if g == lab and q != lab))
    macro = sum(v[2] for v in per.values()) / len(labels)
    acc = sum(1 for g, q in zip(gold, pred) if g == q) / len(gold) if gold else 0.0
    return macro, acc, per


def confusion(gold: list, pred: list, labels: list):
    cm = {g: {q: 0 for q in labels} for g in labels}
    for g, q in zip(gold, pred):
        cm[g][q] += 1
    return cm


def write_cm(path: Path, cm: dict, labels: list) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ของจริง \\ ที่ทาย"] + labels + ["รวม"])
        for g in labels:
            row = [cm[g][q] for q in labels]
            w.writerow([g] + row + [sum(row)])
        w.writerow(["รวม"] + [sum(cm[g][q] for g in labels) for q in labels]
                   + [sum(sum(cm[g].values()) for g in labels)])


def load_gold():
    clean = {int(x) for x in
             (OUT / "gold300_clean_ids.txt").read_text(encoding="utf-8").split()}
    texts, overall = {}, {}
    n_all = 0
    for r in csv.DictReader(open(LAB / "reviews_labeled.csv", encoding="utf-8-sig")):
        n_all += 1
        rid = int(r["review_id"])
        if rid in clean:
            texts[rid] = r["text"].strip()
            overall[rid] = r["overall_sentiment"].strip()
    asp = defaultdict(dict)
    for r in csv.DictReader(open(LAB / "review_aspects.csv", encoding="utf-8-sig")):
        rid = int(r["review_id"])
        if rid in clean:
            asp[rid][int(r["category_id"])] = r["aspect_sentiment"].strip()
    return sorted(texts), texts, overall, dict(asp), n_all


def main() -> None:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    doc = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    cat_ids_all = [c["id"] for c in doc["categories"]]
    names = {c["id"]: c["name"] for c in doc["categories"]}
    ids, texts, g_overall, g_asp, n_gold_all = load_gold()
    present = sorted({c for v in g_asp.values() for c in v})
    dev = "cuda" if torch.cuda.is_available() else "cpu"

    def load(pth):
        return (AutoTokenizer.from_pretrained(str(pth)),
                AutoModelForSequenceClassification.from_pretrained(str(pth))
                .to(dev).eval())

    tok_c, m_cat = load(M_CAT)
    tok_a, m_asp = load(M_ASP)
    tok_o, m_ovr = load(M_OVR)
    tok_s, m_old = load(M_OLD_SEN)
    th_doc = json.loads((M_CAT / "thresholds.json").read_text(encoding="utf-8"))
    th = {int(k): v for k, v in th_doc["thresholds"].items()}
    tx = [texts[r] for r in ids]

    @torch.no_grad()
    def run_single(tok, mdl, items, pairs=False):
        out = []
        for i in range(0, len(items), 32):
            ch = items[i:i + 32]
            enc = (tok([x[0] for x in ch], [x[1] for x in ch], padding=True,
                       truncation=True, max_length=256, return_tensors="pt")
                   if pairs else
                   tok(ch, padding=True, truncation=True, max_length=256,
                       return_tensors="pt")).to(dev)
            out += [mdl.config.id2label[j]
                    for j in mdl(**enc).logits.argmax(-1).cpu().tolist()]
        return out

    # ---- หมวด ----
    probs = {}
    with torch.no_grad():
        for i in range(0, len(ids), 32):
            ch = ids[i:i + 32]
            enc = tok_c([texts[r] for r in ch], padding=True, truncation=True,
                        max_length=256, return_tensors="pt").to(dev)
            pr = torch.sigmoid(m_cat(**enc).logits).cpu()
            for j, r in enumerate(ch):
                probs[r] = {cat_ids_all[k]: pr[j][k].item()
                            for k in range(len(cat_ids_all))}
    pred_cat = {r: ({c for c, v in probs[r].items() if v >= th[c]}
                    or {max(probs[r], key=probs[r].get)}) for r in ids}

    tp = fp = fn = 0
    percat = defaultdict(lambda: [0, 0, 0])
    for r in ids:
        g, q = set(g_asp.get(r, {})), pred_cat[r]
        tp += len(g & q); fp += len(q - g); fn += len(g - q)
        for c in g & q: percat[c][0] += 1
        for c in q - g: percat[c][1] += 1
        for c in g - q: percat[c][2] += 1
    cat_micro = prf(tp, fp, fn)
    cat_macro = sum(prf(*percat[c])[2] for c in present) / len(present)
    base_cat = {r: {max(probs[r], key=probs[r].get)} for r in ids}
    btp = bfp = bfn = 0
    for r in ids:
        g, q = set(g_asp.get(r, {})), base_cat[r]
        btp += len(g & q); bfp += len(q - g); bfn += len(g - q)
    cat_base = prf(btp, bfp, bfn)

    # ---- อารมณ์รวม ----
    g_ov = [g_overall[r] for r in ids]
    q_new = run_single(tok_o, m_ovr, tx)
    q_old = run_single(tok_s, m_old, tx)
    q_pos = ["positive"] * len(ids)
    ov = {}
    for nm, q in (("baseline ทายบวกหมด", q_pos),
                  ("โมเดลเดิม (wangchanberta-sentiment)", q_old),
                  ("โมเดลใหม่ (overall-sentiment)", q_new)):
        m, a, per = class_report(g_ov, q, SENTS)
        ov[nm] = {"macro_f1": m, "accuracy": a,
                  "per_class": {s: list(per[s]) for s in SENTS}}
    cm_ov = confusion(g_ov, q_new, SENTS)

    # ---- อารมณ์รายหมวด (กำหนดหมวดให้ถูกไว้ก่อน) ----
    flat = [(r, c) for r in ids for c in g_asp.get(r, {})]
    g_as = [g_asp[r][c] for r, c in flat]
    q_as = run_single(tok_a, m_asp, [(names[c], texts[r]) for r, c in flat], True)
    ovmap = dict(zip(ids, q_new))
    q_as_ov = [ovmap[r] for r, _ in flat]
    asp = {}
    for nm, q in (("baseline ทายบวกหมด", ["positive"] * len(flat)),
                  ("ใช้อารมณ์รวมกับทุกหมวด", q_as_ov),
                  ("โมเดลอารมณ์รายหมวด", q_as)):
        m, a, per = class_report(g_as, q, SENTS)
        asp[nm] = {"macro_f1": m, "accuracy": a,
                   "per_class": {s: list(per[s]) for s in SENTS}}
    cm_as = confusion(g_as, q_as, SENTS)

    mixed = {r for r in ids if len(set(g_asp.get(r, {}).values())) > 1}
    sub = [i for i, (r, _) in enumerate(flat) if r in mixed]
    mix = {}
    for nm, q in (("ใช้อารมณ์รวมกับทุกหมวด", q_as_ov),
                  ("โมเดลอารมณ์รายหมวด", q_as)):
        gg = [g_as[i] for i in sub]
        qq = [q[i] for i in sub]
        m, a, _ = class_report(gg, qq, SENTS)
        mix[nm] = {"n": len(sub), "macro_f1": m, "accuracy": a}

    # ---- ทั้งระบบ ----
    pairs = [(r, c) for r in ids for c in sorted(pred_cat[r])]
    ps = dict(zip(pairs, run_single(tok_a, m_asp,
                                    [(names[c], texts[r]) for r, c in pairs], True)))
    e2e = {}
    for nm, fn_s in (("คู่ (หมวด, อารมณ์) ต้องตรงทั้งคู่", lambda r, c: ps[(r, c)]),
                     ("ถ้าใช้อารมณ์รวมแทน", lambda r, c: ovmap[r])):
        a = b = d = 0
        for r in ids:
            G = {(c, s) for c, s in g_asp.get(r, {}).items()}
            Q = {(c, fn_s(r, c)) for c in pred_cat[r]}
            a += len(G & Q); b += len(Q - G); d += len(G - Q)
        pr_, rc_, f1_ = prf(a, b, d)
        e2e[nm] = {"precision": pr_, "recall": rc_, "micro_f1": f1_}
    hit_cat = sum(len(set(g_asp.get(r, {})) & pred_cat[r]) for r in ids)
    hit_both = sum(len({(c, s) for c, s in g_asp.get(r, {}).items()}
                       & {(c, ps[(r, c)]) for c in pred_cat[r]}) for r in ids)

    # ---- เขียนไฟล์ ----
    OUT.mkdir(parents=True, exist_ok=True)
    write_cm(OUT / "cm_overall_sentiment.csv", cm_ov, SENTS)
    write_cm(OUT / "cm_aspect_sentiment.csv", cm_as, SENTS)
    with open(OUT / "per_category.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["category_id", "หมวด", "ของจริง", "precision", "recall", "f1"])
        for c in present:
            pr_, rc_, f1_ = prf(*percat[c])
            w.writerow([c, names[c], sum(1 for r in ids if c in g_asp.get(r, {})),
                        round(pr_, 4), round(rc_, 4), round(f1_, 4)])
    for fname, block in (("per_class_overall.csv", ov),
                         ("per_class_aspect.csv", asp)):
        with open(OUT / fname, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["วิธี", "คลาส", "precision", "recall", "f1"])
            for nm, d_ in block.items():
                for s in SENTS:
                    w.writerow([nm, s] + [round(x, 4) for x in d_["per_class"][s]])

    n_asp = sum(len(v) for v in g_asp.values())
    summary = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "eval_set": {"gold_total": n_gold_all, "clean_used": len(ids),
                     "excluded_leaked": n_gold_all - len(ids),
                     "aspect_mentions": n_asp,
                     "aspects_per_review": round(n_asp / len(ids), 3),
                     "mixed_sentiment_reviews": len(mixed),
                     "label_source": "claude_guided (ยังไม่ผ่านการตรวจโดยคน)"},
        "category_multilabel": {
            "precision": cat_micro[0], "recall": cat_micro[1],
            "micro_f1": cat_micro[2], "macro_f1": cat_macro,
            "baseline_argmax_micro_f1": cat_base[2],
            "per_category": {str(c): dict(zip(("precision", "recall", "f1"),
                                              prf(*percat[c]))) for c in present}},
        "overall_sentiment": ov,
        "aspect_sentiment": asp,
        "aspect_sentiment_mixed_subset": mix,
        "end_to_end": e2e,
        "category_hits": hit_cat, "category_and_sentiment_hits": hit_both,
    }
    (OUT / "multiaspect_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- รายงานอ่านได้ ----
    L = [f"# ผลการวัดระบบวิเคราะห์รีวิวแบบ Multi-Aspect", "",
         f"สร้างอัตโนมัติ {summary['generated_at']} ด้วย "
         f"`nlp/train/evaluate_multiaspect.py`", "",
         "> ⚠️ **ตัวเลขในรายงานนี้มาจากการเทรนรอบเดียว**",
         "> ค่าที่ต้องใช้อ้างอิงคือ mean ± sd จาก 3 seed ที่",
         "> `reports/evaluation/seed_sweep_final.md`",
         "> (หมวด micro-F1 0.8771 ± 0.0116 · macro-F1 0.7593 ± 0.0174 ·",
         "> อารมณ์รวม 0.7061 ± 0.0366 · อารมณ์รายหมวด 0.6721 ± 0.0107 ·",
         "> ทั้งระบบ 0.8263 ± 0.0101)",
         "> ตัวเลขในรายงานนี้ใช้ได้แค่สำหรับดูรายละเอียดรายหมวดและ confusion matrix",
         "> ของโมเดลที่อยู่บนดิสก์ตอนนี้เท่านั้น", "",
         "## 1. ชุดประเมิน", "",
         f"- ชุด gold ทั้งหมด **{n_gold_all}** รีวิว",
         f"- ใช้ประเมินจริง **{len(ids)}** รีวิว "
         f"(ตัด {n_gold_all - len(ids)} รายการที่ข้อความซ้ำกับชุดเทรนของโมเดลรุ่นเดิม)",
         f"- การกล่าวถึงรายหมวด **{n_asp}** ครั้ง = "
         f"**{n_asp / len(ids):.2f} หมวด/รีวิว**",
         f"- รีวิวที่หมวดต่าง ๆ มีอารมณ์ไม่เหมือนกัน **{len(mixed)}** "
         f"({len(mixed) / len(ids) * 100:.1f}%)", "",
         "⚠️ ป้ายในชุดนี้ติดโดย Claude ตามคู่มือ **ยังไม่ผ่านการตรวจโดยคน** "
         "จึงยังไม่ทราบเพดานความแม่นที่แท้จริง (ดูหัวข้อ 7)", "",
         "## 2. การจำแนกหมวด (multi-label)", "",
         "| ตัวชี้วัด | ค่า |", "|---|---|",
         f"| precision | {cat_micro[0]:.4f} |",
         f"| recall | {cat_micro[1]:.4f} |",
         f"| **micro-F1** | **{cat_micro[2]:.4f}** |",
         f"| **macro-F1** | **{cat_macro:.4f}** |",
         f"| baseline เลือกหมวดเดียวที่คะแนนสูงสุด (micro-F1) | {cat_base[2]:.4f} |",
         "", "### รายหมวด", "",
         "| id | หมวด | ของจริง | precision | recall | F1 |", "|---|---|---|---|---|---|"]
    for c in present:
        pr_, rc_, f1_ = prf(*percat[c])
        L.append(f"| {c} | {names[c]} | "
                 f"{sum(1 for r in ids if c in g_asp.get(r, {}))} | "
                 f"{pr_:.3f} | {rc_:.3f} | **{f1_:.3f}** |")

    L += ["", "## 3. อารมณ์รวมของรีวิว", "",
          "| วิธี | macro-F1 | accuracy |", "|---|---|---|"]
    for nm, d_ in ov.items():
        L.append(f"| {nm} | {d_['macro_f1']:.4f} | {d_['accuracy']:.4f} |")
    L += ["", "รายคลาสของโมเดลใหม่", "",
          "| คลาส | precision | recall | F1 |", "|---|---|---|---|"]
    for s in SENTS:
        v = ov["โมเดลใหม่ (overall-sentiment)"]["per_class"][s]
        L.append(f"| {s} | {v[0]:.3f} | {v[1]:.3f} | {v[2]:.3f} |")
    L += ["", "confusion matrix (แถว = ของจริง, คอลัมน์ = ที่ทาย)", "",
          "| | " + " | ".join(SENTS) + " |", "|---|" + "---|" * len(SENTS)]
    for g in SENTS:
        L.append(f"| **{g}** | " + " | ".join(str(cm_ov[g][q]) for q in SENTS) + " |")

    L += ["", "## 4. อารมณ์รายหมวด", "",
          f"วัดบน {len(flat)} คู่ (หมวด, อารมณ์) โดยกำหนดหมวดให้ถูกไว้ก่อน "
          "เพื่อแยกความสามารถของโมเดลอารมณ์ออกจากความผิดพลาดของโมเดลหมวด", "",
          "| วิธี | macro-F1 | accuracy | negative P | negative R |",
          "|---|---|---|---|---|"]
    for nm, d_ in asp.items():
        n_ = d_["per_class"]["negative"]
        L.append(f"| {nm} | {d_['macro_f1']:.4f} | {d_['accuracy']:.4f} | "
                 f"{n_[0]:.3f} | {n_[1]:.3f} |")
    L += ["", f"### เฉพาะรีวิวที่หมวดต่าง ๆ มีอารมณ์ไม่เหมือนกัน ({len(sub)} คู่)", "",
          "กลุ่มนี้คือกลุ่มเดียวที่การแยกอารมณ์รายหมวดให้ผลต่างจากการใช้อารมณ์รวม", "",
          "| วิธี | macro-F1 | accuracy |", "|---|---|---|"]
    for nm, d_ in mix.items():
        L.append(f"| {nm} | {d_['macro_f1']:.4f} | {d_['accuracy']:.4f} |")
    L += ["", "confusion matrix ของอารมณ์รายหมวด", "",
          "| | " + " | ".join(SENTS) + " |", "|---|" + "---|" * len(SENTS)]
    for g in SENTS:
        L.append(f"| **{g}** | " + " | ".join(str(cm_as[g][q]) for q in SENTS) + " |")

    L += ["", "## 5. ทั้งระบบ (end-to-end)", "",
          "ทำนายหมวดเองแล้วทำนายอารมณ์ของแต่ละหมวดที่ทายได้ "
          "นับว่าถูกเมื่อ **ทั้งหมวดและอารมณ์ตรงกัน**", "",
          "| วิธี | precision | recall | micro-F1 |", "|---|---|---|---|"]
    for nm, d_ in e2e.items():
        L.append(f"| {nm} | {d_['precision']:.3f} | {d_['recall']:.3f} | "
                 f"**{d_['micro_f1']:.4f}** |")
    L += ["", f"หมวดที่ทายถูก {hit_cat} จาก {n_asp} และในนั้นอารมณ์ถูกด้วย "
          f"{hit_both} = **{hit_both / hit_cat * 100:.1f}%**", "",
          "## 6. วิธีรายงานตัวเลขให้ไม่ชวนเข้าใจผิด", "",
          "- **ห้ามใช้ accuracy เป็นตัวชี้วัดหลัก** ข้อมูลเป็น positive ~88% "
          "แค่ทายบวกทุกรีวิวก็ได้ accuracy 0.88 แล้ว",
          "- รายงาน macro-F1 คู่กับ precision/recall ของคลาส negative เสมอ",
          "- ร้อยละรายหมวดคิดจาก **จำนวนรีวิว** ไม่ใช่จากผลรวมของทุกหมวด "
          "เพราะ 1 รีวิวอยู่ได้หลายหมวด ผลรวมจึงเกินจำนวนรีวิว",
          "- แยกหน่วยให้ชัดระหว่าง *จำนวนรีวิว* กับ *จำนวนการกล่าวถึง (mentions)*", "",
          "## 7. ข้อจำกัด", "",
          "1. **ป้ายในชุดประเมินติดโดย Claude ยังไม่มีคนตรวจ** "
          "ตัวเลขทุกตัวจึงวัดความสอดคล้องกับป้ายชุดนั้น ไม่ใช่ความถูกต้องสัมบูรณ์ "
          "ต้องให้คนตรวจอย่างน้อย 100 รายการแล้วคำนวณ Cohen's kappa "
          "เพื่อทราบเพดานความแม่นที่เป็นไปได้",
          "2. **ชุดเทรนก็ติดโดย Claude เช่นกัน** (คนละรอบ คนละชุด แต่แหล่งเดียวกัน)",
          f"3. **กลุ่มอารมณ์ผสมมีเพียง {len(sub)} คู่** ตัวเลขในหัวข้อ 4.1 จึงยังแกว่ง",
          "4. **ตัวเลขทุกตัวในรายงานนี้มาจากการเทรนรอบเดียว** วัดด้วย "
          "`nlp/train/run_seed_sweep.py` 3 seed ที่ config ปิดท้าย "
          "(หมวด 16 ep · อารมณ์รายหมวด 12 ep · อารมณ์รวม 12 ep) ได้ "
          "หมวด micro-F1 0.8771 ± 0.0116 · macro-F1 0.7593 ± 0.0174 · "
          "ทั้งระบบ micro-F1 0.8263 ± 0.0101 "
          "**ผลต่างระดับ 0.01-0.02 จึงอ่านเป็นการปรับปรุงไม่ได้** "
          "และ F1 รายหมวดของหมวดที่มีตัวอย่างน้อยกว่า 20 แกว่งได้ถึง ±0.2 "
          "(วัดได้ หมวด 7 ±0.2074 · หมวด 2 ±0.1406 · หมวด 8 ±0.1168) "
          "ก่อนเทียบสองวิธีหรือเขียนลงเล่ม ให้ใช้ "
          "`reports/evaluation/seed_sweep_final.md` แทนตัวเลขในรายงานนี้",
          "5. หมวดที่มีตัวอย่างน้อยกว่า 20 รายการในชุดประเมิน "
          "ค่า F1 ไม่ควรนำไปสรุปเชิงสถิติ ควรติดป้าย 'ข้อมูลน้อย' กำกับ",
          "6. ระบบวัด **การแสดงความไม่พอใจ** ไม่ใช่ **การมีอยู่ของปัญหา** "
          "ข้อเสนอแนะที่พูดอย่างสุภาพโดยไม่ติจะถูกจัดเป็น neutral", ""]
    (OUT / "multiaspect_report.md").write_text("\n".join(L) + "\n",
                                               encoding="utf-8")

    p("=" * 70)
    p("  Phase 5 — รายงานผลการวัด")
    p("=" * 70)
    p(f"ชุดประเมิน {len(ids)} รีวิว / {n_asp} คู่ ({n_asp / len(ids):.2f} หมวด/รีวิว)")
    p("")
    p(f"หมวด     micro-F1 {cat_micro[2]:.4f} | macro-F1 {cat_macro:.4f} "
      f"| P {cat_micro[0]:.3f} R {cat_micro[1]:.3f}")
    p(f"อารมณ์รวม macro-F1 {ov['โมเดลใหม่ (overall-sentiment)']['macro_f1']:.4f} "
      f"(baseline {ov['baseline ทายบวกหมด']['macro_f1']:.4f})")
    p(f"อารมณ์รายหมวด macro-F1 {asp['โมเดลอารมณ์รายหมวด']['macro_f1']:.4f} "
      f"(ใช้อารมณ์รวม {asp['ใช้อารมณ์รวมกับทุกหมวด']['macro_f1']:.4f})")
    p(f"ทั้งระบบ micro-F1 "
      f"{e2e['คู่ (หมวด, อารมณ์) ต้องตรงทั้งคู่']['micro_f1']:.4f}")
    p("")
    for f in sorted(OUT.glob("*.csv")) + [OUT / "multiaspect_report.md",
                                          OUT / "multiaspect_summary.json"]:
        if f.name.startswith(("cm_", "per_", "multiaspect")):
            p(f"  {f.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
