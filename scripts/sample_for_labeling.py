"""sample_for_labeling.py — เลือกรีวิวให้ติดป้าย โดยเลือกเฉพาะที่ "คุ้มค่าติด"

ปัญหาที่ต้องแก้ (วัดไว้แล้ว): macro-F1 ติดอยู่ที่คลาสหายาก
  อารมณ์ : negative 13 / neutral 17 จาก gold 251
  หมวด   : หมวด 2/6/7/8/10 มีแค่ 11-17 ครั้ง เกณฑ์จึงไม่นิ่ง (sd สูงถึง 0.177)

ถ้าสุ่มเฉย ๆ จะได้ positive 88% ซึ่งโมเดลทำได้ดีอยู่แล้ว เสียแรงเปล่า
จึงเลือกสองชั้น

  ชั้น A — รีวิว 1-3 ดาว          แก้คลาสอารมณ์ที่หายาก
           ทั้งฐานมีแค่ 8,083 ใบ (11.71%) เลือกจากตรงนี้ให้มากที่สุด
  ชั้น B — รีวิวที่โมเดลให้ความน่าจะเป็นหมวดหายากสูง   แก้หมวดที่หายาก
           ใช้โมเดลเดิมช่วยหา ไม่ต้องอ่านเองทั้งฐาน (active learning อย่างง่าย)

⚠️ กันข้อมูลรั่ว
  ตัด review_id ของชุด gold 300 ออก และตัด "ข้อความซ้ำ" กับ gold ด้วย
  เพราะข้อความเดียวกันโผล่ได้หลาย review_id ถ้ากันแค่ id จะยังรั่ว

รัน:
  uv run python scripts/sample_for_labeling.py --n-low 300 --n-rare 200
"""
import argparse
import asyncio
import csv
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import engine

LAB = ROOT / "data" / "labeling"
OUT_DIR = LAB / "batches"
RARE_CATS = {6, 7, 8, 9, 10}   # หมวดที่ตัวอย่างน้อยใน gold
POOL_FOR_RARE = 20000
SEED = 20261012


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def gold_blocklist() -> tuple[set, set]:
    ids, texts = set(), set()
    for r in csv.DictReader(open(LAB / "reviews_labeled.csv", encoding="utf-8-sig")):
        ids.add(int(r["review_id"]))
        texts.add(r["text"].strip())
    return ids, texts


async def fetch_pool(bad_ids: set) -> dict:
    """ดึงรีวิวที่มีข้อความพอจะติดป้ายได้ แยกตามดาว"""
    async with engine.connect() as c:
        rows = (await c.execute(text("""
            SELECT r.id, r.rating, r.text_clean AS txt, p.name AS place
            FROM reviews r JOIN places p ON p.id = r.place_id
            WHERE r.text_clean <> '' AND length(r.text_clean) >= 12
              AND r.rating IS NOT NULL
        """))).fetchall()
    return {x.id: {"rating": x.rating, "text": x.txt.strip(), "place": x.place}
            for x in rows if x.id not in bad_ids}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-low", type=int, default=300)
    ap.add_argument("--n-rare", type=int, default=200)
    ap.add_argument("--batch-size", type=int, default=50)
    args = ap.parse_args()

    bad_ids, bad_texts = gold_blocklist()
    pool = asyncio.run(fetch_pool(bad_ids))
    pool = {k: v for k, v in pool.items() if v["text"] not in bad_texts}
    p(f"รีวิวที่เลือกได้ (ตัด gold และข้อความซ้ำกับ gold แล้ว) : {len(pool):,}")

    rnd = random.Random(SEED)

    # ---- ชั้น A: 1-3 ดาว ถ่วงให้ 1-2 ดาวมาก่อนเพราะหายากที่สุด ----
    by_star = {s: [i for i, v in pool.items() if v["rating"] == s] for s in (1, 2, 3)}
    for s in by_star:
        rnd.shuffle(by_star[s])
    quota = {1: 0.40, 2: 0.25, 3: 0.35}
    low = []
    for s, frac in quota.items():
        take = min(int(args.n_low * frac), len(by_star[s]))
        low += by_star[s][:take]
    p(f"ชั้น A (1-3 ดาว) : {len(low)} ใบ  " +
      " ".join(f"{s}ดาว={sum(1 for i in low if pool[i]['rating'] == s)}"
               for s in (1, 2, 3)))

    # ---- ชั้น B: ใช้โมเดลหาคนที่น่าจะพูดถึงหมวดหายาก ----
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                              pipeline)
    cats = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    old2new = {o: c["id"] for c in cats["categories"] for o in c["old_names"]}
    names = {c["id"]: c["name"] for c in cats["categories"]}

    cand = [i for i in pool if i not in set(low)]
    rnd.shuffle(cand)
    cand = cand[:POOL_FOR_RARE]
    p(f"ชั้น B : ให้โมเดลคัดจาก {len(cand):,} ใบ…")

    pth = str(ROOT / "models" / "wangchanberta-category")
    clf = pipeline("text-classification",
                   model=AutoModelForSequenceClassification.from_pretrained(pth),
                   tokenizer=AutoTokenizer.from_pretrained(pth),
                   truncation=True, max_length=256, device=0, top_k=None)
    scores = clf([pool[i]["text"] for i in cand], batch_size=64)

    rare_score = []
    for i, sc in zip(cand, scores):
        agg = {}
        for x in sc:
            if x["label"] in old2new:
                cid = old2new[x["label"]]
                agg[cid] = agg.get(cid, 0.0) + x["score"]
        best = max(RARE_CATS, key=lambda c: agg.get(c, 0.0))
        rare_score.append((agg.get(best, 0.0), best, i))
    rare_score.sort(reverse=True)

    # กระจายให้ทุกหมวดหายากได้ส่วนแบ่งเท่า ๆ กัน ไม่ให้หมวดเดียวกินหมด
    per = args.n_rare // len(RARE_CATS)
    rare, got = [], {c: 0 for c in RARE_CATS}
    for sc, c, i in rare_score:
        if got[c] < per and i not in set(low):
            rare.append(i)
            got[c] += 1
        if len(rare) >= args.n_rare:
            break
    p(f"ชั้น B (หมวดหายาก) : {len(rare)} ใบ  " +
      " ".join(f"{names[c][:12]}={got[c]}" for c in sorted(RARE_CATS)))

    picked = low + rare
    rnd.shuffle(picked)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("batch_*.csv"):
        old.unlink()
    n_batch = 0
    for bi in range(0, len(picked), args.batch_size):
        chunk = picked[bi:bi + args.batch_size]
        f = OUT_DIR / f"batch_{bi // args.batch_size + 1:02d}.csv"
        with open(f, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["review_id", "rating", "text"])
            for i in chunk:
                w.writerow([i, pool[i]["rating"], pool[i]["text"]])
        n_batch += 1

    stars = {s: sum(1 for i in picked if pool[i]["rating"] == s) for s in range(1, 6)}
    p("")
    p(f"รวม {len(picked)} ใบ แบ่งเป็น {n_batch} แฟ้ม ที่ {OUT_DIR.relative_to(ROOT)}")
    p("การกระจายดาว : " + " | ".join(f"{s}ดาว {stars[s]}" for s in range(1, 6)))
    p(f"ความยาวเฉลี่ย : "
      f"{sum(len(pool[i]['text']) for i in picked) // len(picked)} อักขระ")


if __name__ == "__main__":
    main()
