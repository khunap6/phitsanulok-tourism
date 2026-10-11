"""cache_gold_preds.py — เก็บผลดิบของโมเดลบนชุด gold ไว้ใช้ซ้ำ

ทำไม: การทดลองจูน threshold ต้องวนหลายรอบ ถ้ายิงโมเดลใหม่ทุกครั้ง
เสียเวลาโหลดโมเดลซ้ำ ๆ โดยไม่จำเป็น ผลของโมเดลไม่เปลี่ยน จึงเก็บไว้ครั้งเดียว

เก็บทั้งระดับรีวิวเต็มและระดับประโยคย่อย เพื่อให้ทดลองได้ทั้งสองแนว

รัน:
  uv run python nlp/train/cache_gold_preds.py
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
LAB = ROOT / "data" / "labeling"
OUT = ROOT / "reports" / "evaluation"
CACHE = OUT / "gold_preds_cache.json"

SPLIT_RE = re.compile(r"(?:แต่|ยกเว้น|เสียแต่ว่า|เสียแต่|เพียงแต่|แค่ว่า)")
MIN_CLAUSE = 4


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def main() -> None:
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer,
                              pipeline)

    clean = {int(x) for x in
             (OUT / "gold300_clean_ids.txt").read_text(encoding="utf-8").split()}
    rows = {}
    for r in csv.DictReader(open(LAB / "reviews_labeled.csv", encoding="utf-8-sig")):
        rid = int(r["review_id"])
        if rid in clean:
            rows[rid] = {"text": r["text"].strip(),
                         "overall": r["overall_sentiment"].strip()}
    asp = defaultdict(dict)
    for r in csv.DictReader(open(LAB / "review_aspects.csv", encoding="utf-8-sig")):
        rid = int(r["review_id"])
        if rid in clean:
            asp[rid][r["category_id"]] = r["aspect_sentiment"].strip()

    cats = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    old2new = {o: c["id"] for c in cats["categories"] for o in c["old_names"]}

    def mk(name):
        pth = str(ROOT / "models" / f"wangchanberta-{name}")
        return pipeline("text-classification",
                        model=AutoModelForSequenceClassification.from_pretrained(pth),
                        tokenizer=AutoTokenizer.from_pretrained(pth),
                        truncation=True, max_length=256, device=0, top_k=None)

    cat_clf, sen_clf = mk("category"), mk("sentiment")
    ids = sorted(rows)
    whole = [rows[r]["text"] for r in ids]

    p(f"ยิงโมเดลบนรีวิวเต็ม {len(ids)} รายการ…")
    cw = cat_clf(whole, batch_size=32)
    sw = sen_clf(whole, batch_size=32)

    clauses, owner = [], []
    for rid in ids:
        parts = [x.strip() for x in SPLIT_RE.split(rows[rid]["text"])
                 if len(x.strip()) >= MIN_CLAUSE] or [rows[rid]["text"]]
        for x in parts:
            clauses.append(x)
            owner.append(rid)
    p(f"ยิงโมเดลบนประโยคย่อย {len(clauses)} รายการ…")
    cc = cat_clf(clauses, batch_size=32)
    sc = sen_clf(clauses, batch_size=32)

    def as_prob(scores):
        """รวมความน่าจะเป็นของหมวดเก่าที่ยุบเป็นหมวดใหม่เดียวกัน"""
        out = defaultdict(float)
        for x in scores:
            if x["label"] in old2new:
                out[str(old2new[x["label"]])] += x["score"]
        return dict(out)

    clause_by = defaultdict(list)
    for rid, c, s in zip(owner, cc, sc):
        clause_by[rid].append({
            "cat_prob": as_prob(c),
            "sentiment": max(s, key=lambda x: x["score"])["label"],
        })

    doc = {
        "_readme": [
            "ผลดิบของโมเดล wangchanberta-{category,sentiment} บนชุด gold ที่สะอาด",
            "สร้างด้วย nlp/train/cache_gold_preds.py — ถ้าเทรนโมเดลใหม่ต้อง generate ใหม่",
            "",
            "cat_prob = ความน่าจะเป็นต่อหมวด v2 (รวมหมวด v1 ที่ยุบเข้าด้วยกันแล้ว)",
            "  เช่น หมวด 7 = การเดินทางและที่จอดรถ + ข้อมูลและป้ายบอกทาง",
            "  จึงบวกความน่าจะเป็นของสองหมวดเดิมเข้าด้วยกัน",
            "",
            "gold_aspects = ป้ายจริง {category_id: aspect_sentiment}",
        ],
        "n_reviews": len(ids),
        "reviews": {
            str(rid): {
                "text": rows[rid]["text"],
                "gold_overall": rows[rid]["overall"],
                "gold_aspects": asp.get(rid, {}),
                "cat_prob": as_prob(c),
                "pred_overall": max(s, key=lambda x: x["score"])["label"],
                # เก็บความน่าจะเป็นครบทุกคลาส เพื่อปรับน้ำหนักคลาสทีหลังได้
                # โดยไม่ต้องยิงโมเดลซ้ำ (neutral recall ต่ำมาก น่าจะแก้ได้ด้วยวิธีนี้)
                "sent_prob": {x["label"]: x["score"] for x in s},
                "clauses": clause_by.get(rid, []),
            }
            for rid, c, s in zip(ids, cw, sw)
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    p(f"บันทึก {CACHE.relative_to(ROOT)} ({CACHE.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
