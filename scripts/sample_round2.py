"""sample_round2.py — เลือกรีวิวรอบ 2 ให้ตรงช่องว่างที่วัดเจอจากรอบแรก

ช่องว่างที่ต้องแก้ (วัดจาก reports/evaluation/absa_gold_result.json และ
multilabel_gold_result.json)

  ก) กลุ่ม "หมวดต่าง ๆ มีอารมณ์ไม่เหมือนกัน" มีแค่ 83 คู่ใน gold
     ซึ่งเป็นกลุ่มเดียวที่ ABSA ต่างจากการใช้อารมณ์รวม ตัวเลขจึงยังแกว่ง
     -> เลือกรีวิวที่มีคำขัดแย้ง (แต่/ยกเว้น/...) ซึ่งมีโอกาสเป็นกลุ่มนี้สูง

  ข) หมวด 2, 8, 9, 10 ได้ F1 แค่ 0.25-0.49 เพราะตัวอย่างน้อย
     -> ให้โมเดล multi-label ตัวใหม่ช่วยหารีวิวที่น่าจะอยู่ในหมวดพวกนี้

⚠️ กันข้อมูลรั่วสามชั้น
  ตัด review_id และข้อความของ gold 300
  ตัด review_id และข้อความของ silver รอบแรก 500 (กันติดป้ายซ้ำใบเดิม)

รัน:
  uv run python scripts/sample_round2.py --n-mixed 250 --n-weak 250
"""
import argparse
import asyncio
import csv
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import engine

LAB = ROOT / "data" / "labeling"
OUT_DIR = LAB / "batches2"
WEAK_CATS = [2, 8, 9, 10]
CONTRAST = re.compile(r"(แต่|ยกเว้น|เสียแต่|เพียงแต่|แค่ว่า|อย่างเดียวคือ|ติดอย่าง)")
POOL = 25000
SEED = 20261012


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def blocklist():
    ids, txt = set(), set()
    for f, col in ((LAB / "reviews_labeled.csv", "text"),
                   (LAB / "silver_reviews.csv", "text")):
        if not f.exists():
            continue
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            ids.add(int(r["review_id"]))
            txt.add(r[col].strip())
    return ids, txt


async def fetch(bad_ids: set) -> dict:
    async with engine.connect() as c:
        rows = (await c.execute(text("""
            SELECT r.id, r.rating, r.text_clean AS txt
            FROM reviews r
            WHERE r.text_clean <> '' AND length(r.text_clean) >= 20
              AND r.rating IS NOT NULL
        """))).fetchall()
    return {x.id: {"rating": x.rating, "text": x.txt.strip()}
            for x in rows if x.id not in bad_ids}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-mixed", type=int, default=250)
    ap.add_argument("--n-weak", type=int, default=250)
    ap.add_argument("--batch-size", type=int, default=50)
    args = ap.parse_args()

    bad_ids, bad_txt = blocklist()
    pool = asyncio.run(fetch(bad_ids))
    pool = {k: v for k, v in pool.items() if v["text"] not in bad_txt}
    p(f"เลือกได้ {len(pool):,} ใบ (ตัด gold 300 และ silver รอบแรก 500 ออกแล้ว)")

    rnd = random.Random(SEED)

    # ---- ชั้น ก: มีคำขัดแย้ง = มีโอกาสอารมณ์ผสม ----
    cand = [i for i, v in pool.items() if CONTRAST.search(v["text"])]
    rnd.shuffle(cand)
    # ถ่วงให้มีทั้งรีวิวที่ให้ดาวสูงและต่ำ เพราะอารมณ์ผสมเกิดได้ทั้งสองทาง
    by_star = {s: [i for i in cand if pool[i]["rating"] == s] for s in range(1, 6)}
    quota = {1: 0.15, 2: 0.15, 3: 0.25, 4: 0.25, 5: 0.20}
    mixed = []
    for s, f in quota.items():
        mixed += by_star[s][:int(args.n_mixed * f)]
    p(f"ชั้น ก (มีคำขัดแย้ง) : {len(mixed)} ใบ  " +
      " ".join(f"{s}ดาว={sum(1 for i in mixed if pool[i]['rating'] == s)}"
               for s in range(1, 6)))

    # ---- ชั้น ข: หมวดที่ยังอ่อน ----
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    doc = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    ids_cat = [c["id"] for c in doc["categories"]]
    names = {c["id"]: c["name"] for c in doc["categories"]}
    M = ROOT / "models" / "wangchanberta-category-multilabel"
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(str(M))
    mdl = AutoModelForSequenceClassification.from_pretrained(str(M)).to(dev).eval()

    rest = [i for i in pool if i not in set(mixed)]
    rnd.shuffle(rest)
    rest = rest[:POOL]
    p(f"ชั้น ข : ให้โมเดลใหม่คัดจาก {len(rest):,} ใบ…")

    scores = {c: [] for c in WEAK_CATS}
    with torch.no_grad():
        for i in range(0, len(rest), 64):
            ch = rest[i:i + 64]
            enc = tok([pool[x]["text"] for x in ch], padding=True, truncation=True,
                      max_length=256, return_tensors="pt").to(dev)
            pr = torch.sigmoid(mdl(**enc).logits).cpu()
            for j, rid in enumerate(ch):
                for c in WEAK_CATS:
                    scores[c].append((pr[j][ids_cat.index(c)].item(), rid))

    per = args.n_weak // len(WEAK_CATS)
    weak, taken = [], set(mixed)
    got = {}
    for c in WEAK_CATS:
        scores[c].sort(reverse=True)
        n = 0
        for sc, rid in scores[c]:
            if rid in taken:
                continue
            weak.append(rid)
            taken.add(rid)
            n += 1
            if n >= per:
                break
        got[c] = n
    p("ชั้น ข (หมวดอ่อน) : " + " ".join(f"{c}:{names[c][:10]}={got[c]}" for c in WEAK_CATS))

    picked = mixed + weak
    rnd.shuffle(picked)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("b2_*.csv"):
        old.unlink()
    n = 0
    for bi in range(0, len(picked), args.batch_size):
        ch = picked[bi:bi + args.batch_size]
        f = OUT_DIR / f"b2_{bi // args.batch_size + 1:02d}.csv"
        with open(f, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["review_id", "rating", "text"])
            for i in ch:
                w.writerow([i, pool[i]["rating"], pool[i]["text"]])
        n += 1
    stars = {s: sum(1 for i in picked if pool[i]["rating"] == s) for s in range(1, 6)}
    p("")
    p(f"รวม {len(picked)} ใบ / {n} แฟ้ม ที่ {OUT_DIR.relative_to(ROOT)}")
    p("ดาว : " + " | ".join(f"{s}ดาว {stars[s]}" for s in range(1, 6)))
    p(f"ยาวเฉลี่ย {sum(len(pool[i]['text']) for i in picked) // len(picked)} อักขระ")


if __name__ == "__main__":
    main()
