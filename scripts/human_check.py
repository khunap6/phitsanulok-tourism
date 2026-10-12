"""human_check.py — สร้างชุดให้ "คน" ตรวจป้าย gold แล้วคำนวณความสอดคล้อง

ทำไมต้องมี
  ตัวเลขทุกตัวในรายงานตอนนี้วัดว่าโมเดลตรงกับป้ายชุด gold แค่ไหน
  แต่ป้าย gold นั้น Claude ติดเอง ยังไม่มีคนตรวจสักใบ
  จึงยังไม่รู้ว่า "เพดานความแม่น" อยู่ตรงไหน — ถ้าคนกับ Claude เห็นตรงกันแค่ 0.80
  โมเดลที่ได้ 0.84 ก็แปลว่าชนเพดานแล้ว จ่ายเพิ่มเท่าไรก็ไม่ขึ้น
  ค่า Cohen's kappa จากชุดนี้คือสิ่งที่ต้องรายงานในเล่มเพื่อบอกความน่าเชื่อถือของป้าย

⚠️ สุ่มแบบถ่วงน้ำหนัก ไม่ใช่สุ่มล้วน
  ชุด gold เป็น positive 88% ถ้าสุ่มล้วน คนจะได้ตรวจแต่รีวิวชมซึ่งง่ายและตรงกันอยู่แล้ว
  ค่า kappa จะสวยเกินจริง จึงบังคับให้มี negative/neutral และรีวิวที่อารมณ์ผสม
  ⚠️ ตัวเลขที่ได้จึงเป็น "ความสอดคล้องบนเคสที่ยากกว่าค่าเฉลี่ย" ต้องระบุในเล่ม

⚠️ ห้ามเปิดไฟล์เฉลยก่อนกรอกเสร็จ
  ถ้าเห็นป้ายของ Claude ก่อน จะเผลอกรอกตาม แล้วค่าที่ได้ใช้อ้างอิงไม่ได้เลย

รัน
  uv run python scripts/human_check.py --make --n 100
  (กรอกไฟล์ human_check_blank.csv แล้วค่อยรัน)
  uv run python scripts/human_check.py --score
"""
import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LAB = ROOT / "data" / "labeling"
OUT = ROOT / "reports" / "evaluation"
BLANK = OUT / "human_check_blank.csv"
KEY = OUT / "human_check_key.csv"
GUIDE = OUT / "human_check_guide.md"
SEED = 20261012

OVERALL = {"p": "positive", "n": "neutral", "g": "negative"}
SIGN = {"+": "positive", "n": "neutral", "-": "negative"}
SENTS = ["positive", "neutral", "negative"]


def p(m: str = "") -> None:
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        print(m.encode("ascii", "replace").decode("ascii"), flush=True)


def load_gold():
    clean = {int(x) for x in
             (OUT / "gold300_clean_ids.txt").read_text(encoding="utf-8").split()}
    rev = {}
    for r in csv.DictReader(open(LAB / "reviews_labeled.csv", encoding="utf-8-sig")):
        rid = int(r["review_id"])
        if rid in clean:
            rev[rid] = {"text": r["text"].strip(),
                        "overall": r["overall_sentiment"].strip()}
    asp = defaultdict(dict)
    for r in csv.DictReader(open(LAB / "review_aspects.csv", encoding="utf-8-sig")):
        rid = int(r["review_id"])
        if rid in clean:
            asp[rid][int(r["category_id"])] = r["aspect_sentiment"].strip()
    return rev, dict(asp)


def kappa(a: list, b: list, labels: list) -> float:
    """Cohen's kappa — วัดความสอดคล้องโดยหักส่วนที่ตรงกันเพราะบังเอิญออก"""
    n = len(a)
    if n == 0:
        return 0.0
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((a.count(l) / n) * (b.count(l) / n) for l in labels)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def kappa_word(k: float) -> str:
    """เกณฑ์ Landis & Koch (1977)"""
    if k < 0:
        return "แย่กว่าการสุ่ม"
    for lim, w in ((0.20, "สอดคล้องเล็กน้อย"), (0.40, "พอใช้"),
                   (0.60, "ปานกลาง"), (0.80, "ดี")):
        if k <= lim:
            return w
    return "ดีมาก"


def make(n: int) -> None:
    rev, asp = load_gold()
    rnd = random.Random(SEED)
    ids = sorted(rev)
    mixed = [i for i in ids if len(set(asp.get(i, {}).values())) > 1]
    by_ov = defaultdict(list)
    for i in ids:
        by_ov[rev[i]["overall"]].append(i)
    for v in by_ov.values():
        rnd.shuffle(v)
    rnd.shuffle(mixed)

    # โควตา: บังคับให้มีเคสยากพอจะวัดได้ ไม่ใช่ positive ล้วน
    picked: list[int] = []

    def take(src, k):
        for i in src:
            if i not in picked and len(picked) < n:
                picked.append(i)
                k -= 1
                if k <= 0:
                    return

    take(by_ov["negative"], len(by_ov["negative"]))      # เอาคำบ่นทั้งหมด (มีน้อย)
    take(by_ov["neutral"], len(by_ov["neutral"]))        # เอากลางๆ ทั้งหมด
    take(mixed, max(1, n // 4))                          # รีวิวอารมณ์ผสม
    take(by_ov["positive"], n)                           # ที่เหลือเติมด้วยคำชม
    rnd.shuffle(picked)

    OUT.mkdir(parents=True, exist_ok=True)
    with open(BLANK, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "ข้อความรีวิว", "อารมณ์รวม(คนกรอก)",
                    "หมวด+อารมณ์(คนกรอก)"])
        for i in picked:
            w.writerow([i, rev[i]["text"], "", ""])
    with open(KEY, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "อารมณ์รวม(gold)", "หมวด+อารมณ์(gold)"])
        for i in picked:
            spec = ",".join(
                f"{c}{'+' if s == 'positive' else '-' if s == 'negative' else 'n'}"
                for c, s in asp.get(i, {}).items())
            w.writerow([i, rev[i]["overall"], spec])

    cats = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    dist = Counter(rev[i]["overall"] for i in picked)
    g = ["# ชุดให้คนตรวจป้าย — คู่มือกรอก", "",
         f"ไฟล์ที่ต้องกรอก: `{BLANK.name}` ({len(picked)} รายการ)", "",
         "## ทำไมต้องกรอก", "",
         "ป้ายในชุดประเมินทั้งหมดติดโดย Claude ยังไม่มีคนตรวจ",
         "ตัวเลขในรายงานจึงบอกได้แค่ว่าโมเดลตรงกับป้ายชุดนั้นแค่ไหน",
         "ไม่ได้บอกว่าป้ายชุดนั้นถูกหรือไม่ การกรอกชุดนี้ทำให้รู้ **เพดานความแม่น**",
         "ซึ่งเป็นตัวเลขที่ต้องมีในเล่มเพื่อบอกความน่าเชื่อถือของการติดป้าย", "",
         "## กติกาการกรอก", "",
         "1. **ห้ามเปิด `human_check_key.csv` ก่อนกรอกเสร็จ** ถ้าเห็นเฉลยก่อน ค่าที่ได้ใช้ไม่ได้",
         "2. ช่อง `อารมณ์รวม(คนกรอก)` กรอก **p** = ชม, **n** = กลางๆ, **g** = ติ",
         "3. ช่อง `หมวด+อารมณ์(คนกรอก)` กรอกทุกหมวดที่รีวิวนั้น *ประเมิน* คั่นด้วยจุลภาค",
         "   รูปแบบ `<เลขหมวด><เครื่องหมาย>` โดย `+` = ชม · `n` = กลางๆ · `-` = ติ",
         "   ตัวอย่าง `4-,1+` = ติบริการ ชมอาหาร",
         "4. ไม่แน่ใจจริง ๆ ให้เว้นว่าง ดีกว่าเดา (ช่องว่างถูกข้าม ไม่นับผิด)",
         "5. กรอกเสร็จรัน `uv run python scripts/human_check.py --score`", "",
         "## นิยามที่ต้องใช้", "",
         "ใช้กติกาชุดเดียวกับที่ติดป้าย gold — อ่านได้ที่",
         "`reports/evaluation/sentiment_guideline.md` (อารมณ์ + กติกาเลือกหมวด)", "",
         "⚠️ กติกาที่ตกลงเพิ่มภายหลัง: รีวิวที่พูดถึง **กราบ / สักการะ / ไหว้พระ / ขอพร**",
         "ให้เป็น **หมวด 2** ไม่ใช่หมวด 10 (ยกเว้นมีเรื่องตลาด ของฝาก โบราณสถาน",
         "นิทรรศการ หรือกิจกรรมอื่นด้วย จึงใช้หมวด 10)", "",
         "## หมวดทั้งหมด", ""]
    for c in cats["categories"]:
        g.append(f"{c['id']}. {c['name']}")
    g += ["", "## การกระจายของชุดนี้", "",
          "⚠️ ชุดนี้ **ถ่วงน้ำหนักให้มีเคสยาก** ไม่ใช่สุ่มล้วน",
          "เพราะ gold เป็นคำชม 88% ถ้าสุ่มล้วนจะได้ตรวจแต่รีวิวที่ง่ายและตรงกันอยู่แล้ว",
          "ค่าที่ได้จึงเป็นความสอดคล้องบน *เคสที่ยากกว่าค่าเฉลี่ย* ต้องระบุข้อนี้ในเล่ม", "",
          "| อารมณ์รวมตาม gold | จำนวน |", "|---|---|"]
    for s in SENTS:
        g.append(f"| {s} | {dist[s]} |")
    GUIDE.write_text("\n".join(g) + "\n", encoding="utf-8")

    p(f"สร้างชุดให้คนตรวจ {len(picked)} รายการ")
    p(f"  ไฟล์ให้กรอก : {BLANK.relative_to(ROOT)}")
    p(f"  คู่มือ      : {GUIDE.relative_to(ROOT)}")
    p(f"  เฉลย       : {KEY.relative_to(ROOT)}  (อย่าเปิดก่อนกรอกเสร็จ)")
    p("")
    p("  การกระจาย : " + " | ".join(f"{s} {dist[s]}" for s in SENTS))
    p(f"  รีวิวที่อารมณ์ผสม : {sum(1 for i in picked if i in set(mixed))}")


def parse_spec(spec: str) -> dict:
    out = {}
    for tok in (spec or "").split(","):
        tok = tok.strip()
        if len(tok) >= 2 and tok[:-1].isdigit() and tok[-1] in SIGN:
            out[int(tok[:-1])] = SIGN[tok[-1]]
    return out


def score() -> None:
    if not BLANK.exists():
        p(f"ไม่พบ {BLANK} — รัน --make ก่อน")
        return
    human = {int(r["review_id"]): r for r in
             csv.DictReader(open(BLANK, encoding="utf-8-sig"))}
    gold = {int(r["review_id"]): r for r in
            csv.DictReader(open(KEY, encoding="utf-8-sig"))}

    ov_h, ov_g = [], []
    for rid, r in human.items():
        v = (r["อารมณ์รวม(คนกรอก)"] or "").strip().lower()
        if v in OVERALL:
            ov_h.append(OVERALL[v])
            ov_g.append(gold[rid]["อารมณ์รวม(gold)"])
        elif v in SENTS:
            ov_h.append(v)
            ov_g.append(gold[rid]["อารมณ์รวม(gold)"])

    p("=" * 68)
    p("  ความสอดคล้องระหว่างคนกับป้าย gold")
    p("=" * 68)
    p(f"กรอกแล้ว {len(ov_h)} จาก {len(human)} รายการ")
    if not ov_h:
        p("ยังไม่ได้กรอกช่องอารมณ์รวมเลย")
        return

    agree = sum(1 for a, b in zip(ov_h, ov_g) if a == b) / len(ov_h)
    k = kappa(ov_h, ov_g, SENTS)
    p("")
    p(f"[1] อารมณ์รวม   ตรงกัน {agree * 100:.1f}%  |  kappa {k:.4f} ({kappa_word(k)})")
    p("    ที่ไม่ตรงกัน (คน -> gold):")
    for rid, r in human.items():
        v = (r["อารมณ์รวม(คนกรอก)"] or "").strip().lower()
        hv = OVERALL.get(v, v if v in SENTS else None)
        if hv and hv != gold[rid]["อารมณ์รวม(gold)"]:
            p(f"      id={rid}: {hv} -> {gold[rid]['อารมณ์รวม(gold)']}")

    # ระดับหมวด
    tp = fp = fn = 0
    sh, sg = [], []
    n_asp = 0
    for rid, r in human.items():
        spec = (r["หมวด+อารมณ์(คนกรอก)"] or "").strip()
        if not spec:
            continue
        n_asp += 1
        H = parse_spec(spec)
        G = parse_spec(gold[rid]["หมวด+อารมณ์(gold)"])
        tp += len(set(H) & set(G))
        fp += len(set(H) - set(G))
        fn += len(set(G) - set(H))
        for c in set(H) & set(G):
            sh.append(H[c])
            sg.append(G[c])
    if n_asp:
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
        p("")
        p(f"[2] หมวด (กรอกแล้ว {n_asp} รายการ)")
        p(f"    precision {pr:.3f} | recall {rc:.3f} | micro-F1 {f1:.4f}")
        if sh:
            ak = kappa(sh, sg, SENTS)
            aa = sum(1 for a, b in zip(sh, sg) if a == b) / len(sh)
            p("")
            p(f"[3] อารมณ์รายหมวด (เฉพาะหมวดที่ตรงกัน {len(sh)} คู่)")
            p(f"    ตรงกัน {aa * 100:.1f}% | kappa {ak:.4f} ({kappa_word(ak)})")
    else:
        p("")
        p("[2] ยังไม่ได้กรอกช่องหมวด+อารมณ์เลย — ข้ามการวัดระดับหมวด")

    p("")
    p("วิธีอ่านค่านี้")
    p("  kappa คือเพดานความแม่นที่เป็นไปได้ของโมเดล")
    p("  ถ้าโมเดลได้ใกล้เคียงค่านี้แล้ว แปลว่าชนเพดาน เพิ่มข้อมูลก็ไม่ขึ้นมาก")
    p("  ถ้าโมเดลยังต่ำกว่ามาก แปลว่ายังมีที่ให้ปรับปรุงจริง")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--make", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--n", type=int, default=100)
    a = ap.parse_args()
    if a.make:
        make(a.n)
    elif a.score:
        score()
    else:
        ap.print_help()
