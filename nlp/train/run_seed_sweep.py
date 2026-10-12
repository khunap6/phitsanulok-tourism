"""run_seed_sweep.py — เทรนซ้ำหลายรอบ แล้วรายงานค่าเฉลี่ยกับส่วนเบี่ยงเบน

⚠️ ทำไมต้องมีสคริปต์นี้
  ระหว่างทำโปรเจกต์ เทรนโมเดลอารมณ์รายหมวดสองรอบแล้วได้ macro-F1
  0.5933 กับ 0.7322 ตอนนั้นสรุปว่าเป็นความผันผวนของ seed

  สคริปต์นี้ถูกเขียนขึ้นมาเพื่อยืนยันข้อสรุปนั้น และผลคือ **ข้อสรุปนั้นผิด**
    ตรึง config รัน 3 seed  12 epoch -> อารมณ์รายหมวด 0.6721 ± 0.0107
                           16 epoch -> อารมณ์รายหมวด 0.6814 ± 0.0355
    ความผันผวนของ seed เล็กกว่า 0.139 มาก และ epoch ก็ไม่ใช่สาเหตุ
    สองรอบนั้นไม่ได้บันทึก seed และ hyperparameter ไว้ จึงย้อนตรวจไม่ได้

  ความผันผวนที่วัดได้จริงอยู่ที่โมเดลหมวด
    micro-F1 0.8449 ± 0.0310 · macro-F1 0.7139 ± 0.0502
    หมวด 7 ±0.2074 · หมวด 2 ±0.1406 · หมวด 8 ±0.1168 (gold ไม่ถึง 20 ทั้งสาม)

  ชุดประเมินมี 251 รีวิว / 493 คู่ และบางหมวดมีตัวอย่างไม่ถึง 20
  บนขนาดนี้ ตัวเลขจากการรันครั้งเดียว "ไม่ใช่ผลของวิธี" แต่เป็นผลของวิธี + การสุ่ม
  ต้องรันหลาย seed แล้วรายงาน mean ± sd เสมอ ไม่งั้นเทียบวิธีกันไม่ได้

⚠️ ส่วนแบ่ง train/val คงที่ทุกรอบ (ตรึงด้วย SEED ในสคริปต์เทรน)
  ที่เปลี่ยนคือการสุ่มค่าเริ่มต้นของหัวจำแนก ลำดับ batch และ dropout
  จึงวัดได้เฉพาะ "ความผันผวนของการเทรน" ไม่ปนกับ "ความผันผวนของการแบ่งข้อมูล"
  (อย่างหลังต้องวัดด้วย cross-validation ซึ่งแพงกว่าและเป็นงานคนละชิ้น)

⚠️ สคริปต์เทรนเขียนทับโมเดลใน models/ ทุกรอบ
  จบ sweep แล้วโมเดลบนดิสก์คือของ seed สุดท้าย ไม่ใช่ของ seed ที่ดีที่สุด
  ต้องสำรอง models/ ไว้ก่อนรัน และเลือกเทรนรอบสุดท้ายด้วย seed ที่ประกาศไว้

⚠️ ไม่แตะชุด gold และไม่แก้ข้อมูล แค่เทรนกับประเมินซ้ำ

รัน:
  uv run python nlp/train/run_seed_sweep.py --seeds 20261012 1 2
"""
import argparse
import json
import statistics
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SUMMARY = ROOT / "reports" / "evaluation" / "multiaspect_summary.json"
OUT_JSON = ROOT / "reports" / "evaluation" / "seed_sweep.json"
OUT_MD = ROOT / "reports" / "evaluation" / "seed_sweep.md"

# ตัวชี้วัดที่ดึงออกมาจาก multiaspect_summary.json ของแต่ละรอบ
# ⚠️ ไม่เก็บ accuracy เป็นตัวชี้วัดหลักตามข้อกำหนดของโจทย์
#    (ข้อมูลเอียง 88% เป็นบวก ทายบวกหมดก็ได้ accuracy 0.88 แล้ว)
METRICS = [
    ("cat_micro_f1", ["category_multilabel", "micro_f1"], "หมวด micro-F1"),
    ("cat_macro_f1", ["category_multilabel", "macro_f1"], "หมวด macro-F1"),
    ("cat_precision", ["category_multilabel", "precision"], "หมวด precision"),
    ("cat_recall", ["category_multilabel", "recall"], "หมวด recall"),
    ("overall_macro_f1",
     ["overall_sentiment", "โมเดลใหม่ (overall-sentiment)", "macro_f1"],
     "อารมณ์รวม macro-F1"),
    ("overall_neg_f1",
     ["overall_sentiment", "โมเดลใหม่ (overall-sentiment)", "per_class", "negative", 2],
     "อารมณ์รวม F1 ของ negative"),
    ("asp_macro_f1",
     ["aspect_sentiment", "โมเดลอารมณ์รายหมวด", "macro_f1"],
     "อารมณ์รายหมวด macro-F1"),
    ("asp_neg_f1",
     ["aspect_sentiment", "โมเดลอารมณ์รายหมวด", "per_class", "negative", 2],
     "อารมณ์รายหมวด F1 ของ negative"),
    ("asp_neu_f1",
     ["aspect_sentiment", "โมเดลอารมณ์รายหมวด", "per_class", "neutral", 2],
     "อารมณ์รายหมวด F1 ของ neutral"),
    ("mixed_macro_f1",
     ["aspect_sentiment_mixed_subset", "โมเดลอารมณ์รายหมวด", "macro_f1"],
     "กลุ่มอารมณ์ผสม macro-F1"),
    ("e2e_micro_f1",
     ["end_to_end", "คู่ (หมวด, อารมณ์) ต้องตรงทั้งคู่", "micro_f1"],
     "ทั้งระบบ micro-F1"),
    # ---- baseline ----
    # ⚠️ baseline 3 ใน 4 ตัวคำนวณจากผลของโมเดล จึงแกว่งตามไปด้วย
    #   ถ้ารายงาน baseline เป็นค่านิ่งแต่รายงานผลระบบเป็น mean ± sd
    #   จะดูเหมือนระบบชนะมากกว่าความจริง ต้องวัดด้วยเกณฑ์เดียวกัน
    ("bl_cat_argmax",
     ["category_multilabel", "baseline_argmax_micro_f1"],
     "baseline หมวด: เอาหมวดเดียวที่คะแนนสูงสุด"),
    ("bl_overall_allpos",
     ["overall_sentiment", "baseline ทายบวกหมด", "macro_f1"],
     "baseline อารมณ์รวม: ทายบวกหมด (sd ต้องเป็น 0)"),
    ("bl_asp_use_overall",
     ["aspect_sentiment", "ใช้อารมณ์รวมกับทุกหมวด", "macro_f1"],
     "baseline อารมณ์รายหมวด: ใช้อารมณ์รวมกับทุกหมวด"),
    ("bl_e2e_use_overall",
     ["end_to_end", "ถ้าใช้อารมณ์รวมแทน", "micro_f1"],
     "baseline ทั้งระบบ: ใช้อารมณ์รวมแทน"),
]

PER_CAT = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def dig(d, path):
    for k in path:
        d = d[k]
    return d


def run(args: list[str], label: str) -> None:
    p(f"  -> {label}")
    r = subprocess.run([sys.executable, *args], cwd=str(ROOT),
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        p(r.stdout[-3000:])
        p(r.stderr[-3000:])
        raise SystemExit(f"{label} ล้มเหลว (exit {r.returncode})")


def mean_sd(xs: list[float]) -> tuple[float, float]:
    if len(xs) < 2:
        return (xs[0] if xs else float("nan")), 0.0
    return statistics.mean(xs), statistics.stdev(xs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[20261012, 1, 2])
    ap.add_argument("--epochs-cat", type=int, default=8)
    ap.add_argument("--epochs-asp", type=int, default=12)
    ap.add_argument("--skip-cat", action="store_true",
                    help="ไม่เทรนโมเดลหมวดใหม่ วัดเฉพาะความผันผวนของโมเดลอารมณ์")
    ap.add_argument("--epochs-overall", type=int, default=12)
    # ⚠️ ปิดไว้เป็นค่าตั้งต้นเพราะทำให้แต่ละรอบนานขึ้นอีกเท่าตัว
    #   แต่ถ้าจะรายงานตัวเลขอารมณ์รวมลงเล่ม ต้องเปิด ไม่งั้นค่านั้นยังเป็นรอบเดียว
    ap.add_argument("--with-overall", action="store_true",
                    help="เทรนโมเดลอารมณ์รวมใหม่ทุกรอบด้วย")
    a = ap.parse_args()

    runs = []
    for i, sd in enumerate(a.seeds, 1):
        p("=" * 72)
        p(f"รอบ {i}/{len(a.seeds)}  seed = {sd}")
        p("=" * 72)
        if not a.skip_cat:
            run(["nlp/train/train_multilabel.py", "--seed", str(sd),
                 "--epochs", str(a.epochs_cat)], "เทรนโมเดลหมวด (multi-label)")
        run(["nlp/train/train_aspect_sentiment.py", "--seed", str(sd),
             "--epochs", str(a.epochs_asp)], "เทรนโมเดลอารมณ์รายหมวด")
        if a.with_overall:
            run(["nlp/train/train_overall_sentiment.py", "--seed", str(sd),
                 "--epochs", str(a.epochs_overall)], "เทรนโมเดลอารมณ์รวม")
        run(["nlp/train/evaluate_multiaspect.py"], "ประเมินบน gold")

        s = json.loads(SUMMARY.read_text(encoding="utf-8"))
        rec = {"seed": sd}
        for key, path, _ in METRICS:
            rec[key] = float(dig(s, path))
        rec["per_category_f1"] = {
            c: float(s["category_multilabel"]["per_category"][c]["f1"])
            for c in PER_CAT if c in s["category_multilabel"]["per_category"]}
        runs.append(rec)
        p("")
        p(f"  หมวด micro {rec['cat_micro_f1']:.4f} | "
          f"อารมณ์รายหมวด {rec['asp_macro_f1']:.4f} | "
          f"ทั้งระบบ {rec['e2e_micro_f1']:.4f}")
        p("")

    # ---- สรุป ----
    agg = {}
    for key, _, label in METRICS:
        xs = [r[key] for r in runs]
        m, sd_ = mean_sd(xs)
        agg[key] = {"label": label, "mean": m, "sd": sd_,
                    "min": min(xs), "max": max(xs), "values": xs}
    # ⚠️ baseline ทายบวกหมดไม่ขึ้นกับโมเดลเลย ถ้า sd ไม่เป็น 0 แปลว่า
    #   ชุดประเมินเปลี่ยนระหว่างรอบ = มีบั๊ก ต้องหยุดดูก่อนเชื่อตัวเลขอื่น
    if agg.get("bl_overall_allpos", {}).get("sd", 0) > 1e-9:
        p("")
        p("⚠️⚠️ baseline 'ทายบวกหมด' ควรเท่ากันทุกรอบแต่ไม่เท่า "
          f"(sd {agg['bl_overall_allpos']['sd']:.6f}) "
          "แปลว่าชุดประเมินเปลี่ยนระหว่างรอบ ตัวเลขอื่นเชื่อไม่ได้")

    cat_agg = {}
    for c in PER_CAT:
        xs = [r["per_category_f1"][c] for r in runs if c in r["per_category_f1"]]
        if xs:
            m, sd_ = mean_sd(xs)
            cat_agg[c] = {"mean": m, "sd": sd_, "min": min(xs), "max": max(xs)}

    doc = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "n_runs": len(runs),
        "seeds": a.seeds,
        "เทรนโมเดลหมวดใหม่ทุกรอบ": not a.skip_cat,
        # ⚠️ ต้องติดไว้ทุกครั้ง เทียบ sweep สองชุดที่ epoch ต่างกันไม่ได้
        "epochs_cat": a.epochs_cat, "epochs_asp": a.epochs_asp,
        "เทรนโมเดลอารมณ์รวมใหม่ทุกรอบ": a.with_overall,
        "epochs_overall": a.epochs_overall if a.with_overall else None,
        "_readme": [
            "ส่วนแบ่ง train/val คงที่ทุกรอบ ที่เปลี่ยนคือการสุ่มของรอบการเทรน",
            "sd ที่เห็นคือความผันผวนของการเทรน ไม่ใช่ความผันผวนของการแบ่งข้อมูล",
            "เทียบสองวิธีกันได้เฉพาะเมื่อผลต่างมากกว่า sd อย่างชัดเจน",
        ],
        "summary": agg,
        "per_category_f1": cat_agg,
        "runs": runs,
    }
    OUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    L = [f"# ความผันผวนระหว่างรอบการเทรน ({len(runs)} รอบ)", "",
         f"สร้างเมื่อ {doc['generated_at']} · seed ที่ใช้ {a.seeds}", "",
         f"**config** โมเดลหมวด {a.epochs_cat} epoch · "
         f"โมเดลอารมณ์รายหมวด {a.epochs_asp} epoch"
         + (f" · โมเดลอารมณ์รวม {a.epochs_overall} epoch" if a.with_overall
            else " · โมเดลอารมณ์รวม **ไม่ได้เทรนใหม่** (ค่าคงเดิมทุกรอบ sd=0)"), "",
         "⚠️ เทียบ sweep สองชุดที่ config ต่างกันไม่ได้", "",
         "ส่วนแบ่ง train/val **คงที่ทุกรอบ** ที่เปลี่ยนคือการสุ่มค่าเริ่มต้น",
         "ของหัวจำแนก ลำดับ batch และ dropout ตัวเลข sd ด้านล่างจึงเป็น",
         "**ความผันผวนของการเทรน** ไม่ใช่ความผันผวนของการแบ่งข้อมูล", "",
         "## 1. ตัวชี้วัดหลัก", "",
         "| ตัวชี้วัด | ค่าเฉลี่ย | sd | ต่ำสุด | สูงสุด | ช่วงกว้าง |",
         "|---|---|---|---|---|---|"]
    for key, _, label in METRICS:
        v = agg[key]
        L.append(f"| {label} | **{v['mean']:.4f}** | ±{v['sd']:.4f} | "
                 f"{v['min']:.4f} | {v['max']:.4f} | {v['max'] - v['min']:.4f} |")

    L += ["", "## 2. F1 รายหมวด", "",
          "| หมวด | ค่าเฉลี่ย | sd | ช่วงกว้าง |", "|---|---|---|---|"]
    doc_c = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    nm = {str(c["id"]): c["name"] for c in doc_c["categories"]}
    for c, v in cat_agg.items():
        L.append(f"| {c} {nm.get(c, '')} | {v['mean']:.4f} | ±{v['sd']:.4f} | "
                 f"{v['max'] - v['min']:.4f} |")

    worst = max(agg.values(), key=lambda v: v["max"] - v["min"])
    L += ["", "## 3. อ่านผลอย่างไร", "",
          f"ตัวชี้วัดที่แกว่งมากที่สุดคือ **{worst['label']}** "
          f"ช่วงกว้าง {worst['max'] - worst['min']:.4f} "
          f"(sd ±{worst['sd']:.4f})", "",
          "**กติกาที่ต้องใช้ตอนเขียนเล่ม**", "",
          "1. รายงานเป็น mean ± sd เสมอ ห้ามรายงานตัวเลขจากการรันครั้งเดียว",
          "2. จะสรุปว่าวิธี A ดีกว่าวิธี B ได้ ผลต่างต้องมากกว่า sd อย่างชัดเจน",
          "   ไม่ใช่แค่มากกว่าเฉย ๆ",
          "3. หมวดที่มีตัวอย่างใน gold น้อยกว่า 20 รายการ ค่า sd จะใหญ่",
          "   ต่อให้ค่าเฉลี่ยดูดีก็สรุปเชิงสถิติไม่ได้", "",
          "## 4. ข้อจำกัดของการวัดนี้เอง", "",
          f"1. {len(runs)} รอบยังน้อย sd ที่ได้เป็นเพียงค่าประมาณคร่าว ๆ",
          "2. วัดเฉพาะความผันผวนของการเทรน ยังไม่ได้วัดความผันผวนของการแบ่งข้อมูล",
          "   ซึ่งต้องทำ cross-validation",
          "3. ชุดประเมินยังเป็นป้ายที่ Claude ติด ยังไม่ผ่านการตรวจโดยคน",
          "   ตัวเลขทุกตัวจึงวัดความสอดคล้องกับป้ายชุดนั้น ไม่ใช่ความถูกต้องสัมบูรณ์", ""]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")

    p("=" * 72)
    p(f"สรุป {len(runs)} รอบ")
    p("=" * 72)
    for key, _, label in METRICS:
        v = agg[key]
        p(f"  {label:<34} {v['mean']:.4f} ± {v['sd']:.4f}  "
          f"(ช่วง {v['min']:.4f}-{v['max']:.4f})")
    p("")
    p(f"เขียนที่ {OUT_MD.relative_to(ROOT)} และ {OUT_JSON.relative_to(ROOT)}")
    p("")
    p("⚠️ โมเดลใน models/ คือของ seed สุดท้าย "
      f"({a.seeds[-1]}) ไม่ใช่ของ seed ที่ดีที่สุด")


if __name__ == "__main__":
    main()
