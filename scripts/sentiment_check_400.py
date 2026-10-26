"""sentiment_check_400.py — สุ่มรีวิว 400 ใบให้คนตรวจอารมณ์รวม แล้วคำนวณความแม่น

⚠️ ทำไมไฟล์ที่ให้กรอกถึง "ไม่มีคำตอบของโมเดล"
  ถ้าเห็นคำตอบของโมเดลก่อนกรอก คนจะเห็นด้วยกับมันโดยไม่รู้ตัว (anchoring)
  ค่าที่ได้จะสูงกว่าจริงและเอาไปเขียนในเล่มไม่ได้ รอบ 95 แถวก่อนหน้านี้
  ทำแบบปิดตา ค่าที่รายงานในเล่มจึงอ้างได้ — รอบนี้ต้องทำแบบเดียวกัน
  คำตอบของโมเดลถูกเก็บไว้ในไฟล์ _KEY แยกต่างหาก ห้ามเปิดก่อนกรอกเสร็จ

⚠️ ทำไมไม่มีคอลัมน์ดาว
  ดาวเป็นคำใบ้ที่แรงมาก ถ้าเห็น 5 ดาวแล้วจะติดป้ายบวกแทบอัตโนมัติ
  สิ่งที่ต้องการวัดคือ "คนอ่านข้อความแล้วคิดว่าอารมณ์อะไร" ไม่ใช่ "คนเดาจากดาว"

⚠️ สุ่มจากประชากรเดียวกับตัวเลขในเล่ม
  ตัวกรอง = in_scope + เปิดกิจการ + มีข้อความ + วิเคราะห์แล้ว (กฎข้อ 1)
  และตัดแถวที่ label_source ไม่ใช่ 'model' ออก เพราะนั่นคือชุด gold/silver
  ที่โมเดลเคยเห็นตอนเทรน ถ้าปนเข้ามา ค่าความแม่นจะสูงกว่าจริง

⚠️ สุ่มล้วน ไม่ถ่วงน้ำหนัก
  ต่างจาก human_check_v3.py ที่จงใจเลือกเคสยาก รอบนี้ต้องการค่าที่เป็นตัวแทน
  ของประชากรจริง จึงสุ่มล้วนด้วย seed คงที่ (บันทึกไว้ในหัวไฟล์)

⚠️ ตัวเลขที่ได้ห้ามรายงานเป็น accuracy เดี่ยว ๆ
  --score จะพิมพ์ macro-F1 · P/R รายคลาส · และ baseline "ทายบวกหมด" มาด้วยเสมอ
  ถ้าโมเดลไม่ชนะ baseline ก็ต้องเขียนตามนั้น

รหัสอารมณ์ (ใช้ชุดเดียวกับ human_check_v3.py ห้ามสลับ)
  p = positive (บวก)   n = neutral (กลาง)   g = negative (ลบ)

รัน
  uv run python scripts/sentiment_check_400.py --make
  (กรอกคอลัมน์ อารมณ์(กรอก) ในไฟล์ sentiment_check_400_blank.csv ให้ครบ)
  uv run python scripts/sentiment_check_400.py --score
"""
import argparse
import asyncio
import csv
import hashlib
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text  # noqa: E402

from api.filters import scope_filter, status_filter  # noqa: E402
from db.database import AsyncSessionLocal  # noqa: E402

OUT_DIR = ROOT / "reports" / "evaluation"
BLANK = OUT_DIR / "sentiment_check_400_blank.csv"
KEY = OUT_DIR / "sentiment_check_400_KEY_ห้ามเปิดก่อนกรอก.csv"

N = 400
SEED = 20261014

SENTS = ["positive", "neutral", "negative"]
TH = {"positive": "บวก", "neutral": "กลาง", "negative": "ลบ"}
# ⚠️ ชุดเดียวกับ human_check_v3.py — n คือ neutral ไม่ใช่ negative
CODE = {"p": "positive", "n": "neutral", "g": "negative",
        "positive": "positive", "neutral": "neutral", "negative": "negative",
        "บวก": "positive", "กลาง": "neutral", "ลบ": "negative"}


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


async def fetch_population() -> list[dict]:
    sql = f"""
        SELECT r.id          AS review_id,
               r.text_clean  AS txt,
               ar.overall_sentiment AS pred
        FROM analyzed_reviews ar
        JOIN reviews r ON r.id = ar.review_id
        JOIN places  p ON p.id = r.place_id
        WHERE r.text_clean <> ''
          AND ar.overall_sentiment IS NOT NULL
          AND COALESCE(ar.label_source, 'model') = 'model'
          {status_filter('operational')}
          {scope_filter()}
    """
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text(sql))).fetchall()
    return [{"review_id": r.review_id, "txt": r.txt, "pred": r.pred} for r in rows]


async def make() -> None:
    pop = await fetch_population()
    print(f"ประชากรที่เข้าเกณฑ์ : {len(pop):,} รีวิว")
    dist = Counter(r["pred"] for r in pop)
    print("การกระจายอารมณ์ของประชากรทั้งหมด (ผลของโมเดล)")
    for s in SENTS:
        n = dist.get(s, 0)
        print(f"  {TH[s]:<5} {n:>8,}  {n / len(pop) * 100:>5.2f}%")

    if len(pop) < N:
        print(f"ประชากรน้อยกว่า {N} แถว — หยุด")
        return

    rng = random.Random(SEED)
    sample = rng.sample(pop, N)
    sample.sort(key=lambda r: r["review_id"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with BLANK.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([f"# สุ่ม {N} แถว seed={SEED} จากประชากร {len(pop)} แถว"])
        w.writerow(["# กรอกคอลัมน์สุดท้าย: p=บวก  n=กลาง  g=ลบ (กรอกคำไทยก็ได้)"])
        w.writerow(["# ห้ามเปิดไฟล์ _KEY ก่อนกรอกเสร็จ"])
        w.writerow(["review_id", "sha1", "ข้อความรีวิว", "อารมณ์(กรอก)"])
        for r in sample:
            w.writerow([r["review_id"], sha1(r["txt"]), r["txt"], ""])

    with KEY.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "sha1", "โมเดลทำนาย"])
        for r in sample:
            w.writerow([r["review_id"], sha1(r["txt"]), r["pred"]])

    print()
    print(f"ไฟล์ให้กรอก : {BLANK}")
    print(f"เฉลย (ห้ามเปิด) : {KEY}")


def read_filled() -> dict[int, str]:
    out: dict[int, str] = {}
    bad: list[str] = []
    with BLANK.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row or row[0].startswith("#") or row[0] == "review_id":
                continue
            rid, _h, _txt, val = row[0], row[1], row[2], (row[3] if len(row) > 3 else "")
            val = val.strip().lower()
            if not val:
                continue
            if val not in CODE:
                bad.append(f"  review_id {rid}: ค่า '{val}' ไม่รู้จัก")
                continue
            out[int(rid)] = CODE[val]
    if bad:
        print("แถวที่กรอกไม่ถูกรูปแบบ (ข้ามไป)")
        print("\n".join(bad))
    return out


def prf(gold: list[str], pred: list[str]) -> dict:
    res = {}
    for s in SENTS:
        tp = sum(1 for g, p in zip(gold, pred) if g == s and p == s)
        fp = sum(1 for g, p in zip(gold, pred) if g != s and p == s)
        fn = sum(1 for g, p in zip(gold, pred) if g == s and p != s)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        res[s] = {"n": gold.count(s), "p": prec, "r": rec, "f1": f1}
    res["_macro_f1"] = sum(res[s]["f1"] for s in SENTS) / len(SENTS)
    res["_acc"] = sum(1 for g, p in zip(gold, pred) if g == p) / len(gold)
    return res


def kappa(gold: list[str], pred: list[str]) -> float:
    n = len(gold)
    po = sum(1 for g, p in zip(gold, pred) if g == p) / n
    pe = sum((gold.count(s) / n) * (pred.count(s) / n) for s in SENTS)
    return (po - pe) / (1 - pe) if pe != 1 else 0.0


def score() -> None:
    if not BLANK.exists() or not KEY.exists():
        print("ยังไม่มีไฟล์ — รัน --make ก่อน")
        return
    filled = read_filled()
    keymap = {}
    with KEY.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row or row[0] == "review_id":
                continue
            keymap[int(row[0])] = row[2]

    ids = sorted(set(filled) & set(keymap))
    print(f"กรอกแล้ว {len(filled)} / {len(keymap)} แถว · นำมาคิด {len(ids)} แถว")
    if not ids:
        return
    gold = [filled[i] for i in ids]
    pred = [keymap[i] for i in ids]

    r = prf(gold, pred)
    print()
    print("ผลของโมเดล เทียบกับป้ายที่คนกรอก")
    print(f"  macro-F1 : {r['_macro_f1']:.4f}   <- ตัวชี้วัดหลัก")
    print(f"  kappa    : {kappa(gold, pred):.4f}")
    print(f"  accuracy : {r['_acc']:.4f}   <- ห้ามรายงานเดี่ยว ๆ")
    print()
    print(f"  {'คลาส':<6}{'n(คน)':>7}{'P':>9}{'R':>9}{'F1':>9}")
    for s in SENTS:
        d = r[s]
        print(f"  {TH[s]:<6}{d['n']:>7}{d['p']:>9.4f}{d['r']:>9.4f}{d['f1']:>9.4f}")

    # baseline: ทายบวกหมด — ถ้าโมเดลไม่ชนะค่านี้ ก็ยังพิสูจน์อะไรไม่ได้
    b = prf(gold, ["positive"] * len(gold))
    print()
    print("baseline ทายบวกหมด")
    print(f"  macro-F1 : {b['_macro_f1']:.4f}   accuracy : {b['_acc']:.4f}")
    diff = r["_macro_f1"] - b["_macro_f1"]
    print(f"  โมเดลดีกว่า baseline (macro-F1) : {diff:+.4f}")

    print()
    print("ตารางสับสน (แถว = คนกรอก, คอลัมน์ = โมเดล)")
    cm: dict[str, Counter] = defaultdict(Counter)
    for g, p in zip(gold, pred):
        cm[g][p] += 1
    print(f"  {'':<8}" + "".join(f"{TH[s]:>8}" for s in SENTS))
    for g in SENTS:
        print(f"  {TH[g]:<8}" + "".join(f"{cm[g][p]:>8}" for p in SENTS))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--make", action="store_true", help="สร้างไฟล์ให้กรอก")
    ap.add_argument("--score", action="store_true", help="คำนวณผลหลังกรอกเสร็จ")
    a = ap.parse_args()
    if a.make:
        asyncio.run(make())
    elif a.score:
        score()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
