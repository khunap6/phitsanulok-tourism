"""run_seed_sweep.py — เทรนซ้ำหลายรอบ แล้วรายงานค่าเฉลี่ยกับส่วนเบี่ยงเบน

⚠️ ทำไมต้องมีสคริปต์นี้
  ระหว่างทำโปรเจกต์ เทรนโมเดลอารมณ์รายหมวดสองรอบด้วยข้อมูลชุดเดียวกันทุกประการ
  ได้ macro-F1 0.5933 กับ 0.7322 ห่างกัน 0.139 (ทั้งระบบ 0.8056 กับ 0.8479)
  เกือบสรุปผิดว่าการแก้ป้ายรอบนั้นทำให้โมเดลแย่ลง — ที่จริงเป็นความผันผวนล้วน ๆ

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
