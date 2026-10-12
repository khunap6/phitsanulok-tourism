"""compare_sweeps.py — เทียบผล sweep หลายชุดที่ config ต่างกัน

⚠️ ทำไมต้องมี
  run_seed_sweep.py บอกได้แค่ว่า "ที่ config นี้ ตัวเลขแกว่งเท่าไร"
  แต่คำถามที่ต้องตอบตอนเลือก config คือ "config ไหนดีกว่า และดีกว่าจริงไหม"
  ซึ่งตอบจากค่าเฉลี่ยเฉย ๆ ไม่ได้ ต้องเทียบผลต่างกับ sd ของทั้งสองชุด

⚠️ เกณฑ์ที่ใช้ตัดสินในสคริปต์นี้
  ผลต่างของค่าเฉลี่ย > sd ที่ใหญ่กว่าของสองชุด  -> "ต่างเกิน sd"
  นอกนั้น                                      -> "อยู่ในช่วง sd" = สรุปไม่ได้
  เกณฑ์นี้หยาบและ **ไม่ใช่การทดสอบนัยสำคัญทางสถิติ** ด้วย n=3 ต่อชุด
  จะทำ t-test ก็ยังไม่มีกำลังพอ จึงใช้เป็นเกณฑ์กันตัวเองเผลอสรุปเท่านั้น
  ถ้าผลต่าง "อยู่ในช่วง sd" ให้ถือว่า **เท่ากัน** ไม่ใช่ "ดีกว่าเล็กน้อย"

⚠️ เทียบได้เฉพาะ sweep ที่ใช้ seed ชุดเดียวกันและชุดประเมินเดียวกัน
  ถ้า seed ไม่ตรง สคริปต์จะเตือน เพราะการเทียบจะปนความผันผวนของ seed เข้ามา

รัน:
  uv run python nlp/train/compare_sweeps.py \
      reports/evaluation/seed_sweep_asp12.json \
      reports/evaluation/seed_sweep_asp16.json
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_MD = ROOT / "reports" / "evaluation" / "sweep_comparison.md"


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def tag(d: dict) -> str:
    return (f"หมวด {d.get('epochs_cat', '?')} ep / "
            f"อารมณ์ {d.get('epochs_asp', '?')} ep")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()

    docs = []
    for fn in a.files:
        pth = Path(fn)
        if not pth.is_absolute():
            pth = ROOT / fn
        docs.append(json.loads(pth.read_text(encoding="utf-8")))

    seeds = {tuple(d["seeds"]) for d in docs}
    warn = len(seeds) > 1
    if warn:
        p("⚠️ seed ของแต่ละชุดไม่ตรงกัน การเทียบจะปนความผันผวนของ seed เข้ามา")

    # ⚠️ sweep ชุดเก่ารันก่อนที่จะเพิ่มตัวชี้วัดบางตัว จึงไม่มีคีย์ครบ
    #   เทียบเฉพาะคีย์ที่มีครบทุกชุด แล้วบอกให้รู้ว่าข้ามอะไรไป
    keys = [k for k in docs[0]["summary"] if all(k in d["summary"] for d in docs)]
    missing = [k for k in docs[0]["summary"] if k not in keys]
    extra = sorted({k for d in docs[1:] for k in d["summary"]} - set(docs[0]["summary"]))
    if missing or extra:
        p(f"⚠️ ข้ามตัวชี้วัดที่ไม่มีครบทุกชุด: {missing + extra}")
    L = ["# เทียบผล sweep ต่าง config", "",
         f"สร้างเมื่อ {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    for d, fn in zip(docs, a.files):
        L.append(f"- **{tag(d)}** — {d['n_runs']} รอบ · seed {d['seeds']} · `{fn}`")
    L += ["",
          "⚠️ **เกณฑ์อ่านผล** ผลต่างที่ไม่เกิน sd ให้ถือว่า **เท่ากัน**",
          "ไม่ใช่ \"ดีกว่าเล็กน้อย\" — ด้วย n=3 ต่อชุด ไม่มีกำลังพอจะสรุปละเอียดกว่านี้",
          ""]
    if warn:
        L += ["⚠️ seed ของแต่ละชุดไม่ตรงกัน ผลเทียบจึงปนความผันผวนของ seed", ""]
    if missing or extra:
        L += [f"⚠️ ข้ามตัวชี้วัดที่ไม่มีครบทุกชุด (sweep คนละรุ่นของสคริปต์): "
              f"`{'`, `'.join(missing + extra)}`", ""]

    L += ["## 1. ตัวชี้วัดหลัก", "",
          "| ตัวชี้วัด | " + " | ".join(tag(d) for d in docs) + " | ผลต่าง | อ่านว่า |",
          "|---" * (len(docs) + 3) + "|"]
    verdicts = {}
    for k in keys:
        cells, means, sds = [], [], []
        for d in docs:
            v = d["summary"][k]
            cells.append(f"{v['mean']:.4f} ±{v['sd']:.4f}")
            means.append(v["mean"])
            sds.append(v["sd"])
        diff = means[-1] - means[0]
        beyond = abs(diff) > max(sds)
        verdicts[k] = beyond
        L.append(f"| {docs[0]['summary'][k]['label']} | " + " | ".join(cells)
                 + f" | {diff:+.4f} | "
                 + ("**ต่างเกิน sd**" if beyond else "อยู่ในช่วง sd = เท่ากัน")
                 + " |")

    L += ["", "## 2. แยกตาม seed", "",
          "ดูรายตัว seed เพื่อตรวจว่าผลต่างไปทางเดียวกันหรือสลับทิศ",
          "ถ้าสลับทิศ แปลว่าไม่ใช่ผลของ config แน่นอน", ""]
    for k in keys:
        row = []
        flip = set()
        for d in docs:
            row.append([r[k] for r in d["runs"]])
        if len(docs) == 2:
            signs = {(b - a0) > 0 for a0, b in zip(row[0], row[1])}
            flip = signs
        L.append(f"**{docs[0]['summary'][k]['label']}**")
        L.append("")
        L.append("| seed | " + " | ".join(tag(d) for d in docs)
                 + (" | ต่าง |" if len(docs) == 2 else " |"))
        L.append("|---" * (len(docs) + (2 if len(docs) == 2 else 1)) + "|")
        for i, sd_ in enumerate(docs[0]["seeds"]):
            cells = [f"{r[i]:.4f}" for r in row]
            extra = (f" | {row[1][i] - row[0][i]:+.4f} |") if len(docs) == 2 else " |"
            L.append(f"| {sd_} | " + " | ".join(cells) + extra)
        if len(docs) == 2 and len(flip) > 1:
            L.append("")
            L.append("→ **สลับทิศระหว่าง seed** ไม่ใช่ผลของ config")
        L.append("")

    same = [docs[0]["summary"][k]["label"] for k in keys if not verdicts[k]]
    diff_ = [docs[0]["summary"][k]["label"] for k in keys if verdicts[k]]
    L += ["## 3. สรุป", ""]
    if diff_:
        L.append("ต่างเกิน sd: " + ", ".join(diff_))
    else:
        L.append("**ไม่มีตัวชี้วัดใดต่างเกิน sd** — config ที่เทียบกันถือว่าให้ผลเท่ากัน")
        L.append("")
        L.append("กรณีนี้ให้เลือก config ที่ **ถูกกว่าหรือเร็วกว่า** "
                 "ไม่ใช่ที่ค่าเฉลี่ยสูงกว่า เพราะค่าเฉลี่ยที่สูงกว่าอยู่ในช่วงความผันผวน")
    if same and diff_:
        L.append("")
        L.append("อยู่ในช่วง sd (ถือว่าเท่ากัน): " + ", ".join(same))
    L.append("")

    OUT_MD.write_text("\n".join(L), encoding="utf-8")

    p("=" * 72)
    for k in keys:
        cells = " | ".join(f"{d['summary'][k]['mean']:.4f}+-{d['summary'][k]['sd']:.4f}"
                           for d in docs)
        p(f"  {docs[0]['summary'][k]['label']:<34} {cells}  "
          f"{'ต่างเกิน sd' if verdicts[k] else 'เท่ากัน'}")
    p("")
    p(f"เขียนที่ {OUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
