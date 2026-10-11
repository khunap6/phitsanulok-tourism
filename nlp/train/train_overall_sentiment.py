"""train_overall_sentiment.py — เทรนโมเดลอารมณ์รวมของรีวิวใหม่บนชุด silver

ทำไมต้องเทรนใหม่ ทั้งที่มี models/wangchanberta-sentiment อยู่แล้ว
  ตัวเดิมเทรนบนข้อมูลที่ positive ~88% จึงเอนไปทางบวกจนคลาสน้อยถูกกลืน
  วัดบน gold ได้ macro-F1 0.6802 โดย neutral recall เหลือแค่ 0.235
  ลองปรับน้ำหนักคลาสหลังบ้านแล้วขึ้นได้แค่ 0.7029 และ neutral ไม่ขยับเลย
  = ปัญหาอยู่ที่ตัวโมเดลแยกคลาสไม่ออก ไม่ใช่ที่เกณฑ์ตัดสิน

  ชุด silver มี บวก 436 / ลบ 423 / กลาง 137 ซึ่งสมดุลกว่ามาก
  น่าจะสอนให้แยก negative กับ neutral ได้ดีกว่า

⚠️ เทียบกับตัวเดิมบน gold ก่อนเอาไปใช้จริง ถ้าไม่ดีกว่าก็ใช้ตัวเดิมต่อ
  (ดู nlp/train/compare_overall_sentiment.py ที่รันต่อจากนี้)

⚠️ ชุด silver ถูกกัน review_id และข้อความของ gold ออกตั้งแต่ตอนสุ่มแล้ว
  สคริปต์นี้ตรวจซ้ำอีกชั้นก่อนเทรน

รัน:
  uv run python nlp/train/train_overall_sentiment.py --epochs 12
"""
import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
LAB = ROOT / "data" / "labeling"
OUT_DIR = ROOT / "models" / "wangchanberta-overall-sentiment"
START_FROM = ROOT / "models" / "wangchanberta-sentiment"
SENTS = ["positive", "neutral", "negative"]
SEED = 20261012


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


class DS(Dataset):
    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


def prf(tp, fp, fn):
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return pr, rc, (2 * pr * rc / (pr + rc) if pr + rc else 0.0)


def report(gold, pred):
    out = {s: prf(sum(1 for g, q in zip(gold, pred) if g == i and q == i),
                  sum(1 for g, q in zip(gold, pred) if g != i and q == i),
                  sum(1 for g, q in zip(gold, pred) if g == i and q != i))
           for i, s in enumerate(SENTS)}
    return (sum(v[2] for v in out.values()) / 3,
            sum(1 for g, q in zip(gold, pred) if g == q) / len(gold), out)


def main(epochs: int, lr: float, batch_size: int, max_length: int) -> None:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    gold_txt = {r["text"].strip() for r in
                csv.DictReader(open(LAB / "reviews_labeled.csv", encoding="utf-8-sig"))}
    rows = []
    for r in csv.DictReader(open(LAB / "silver_reviews.csv", encoding="utf-8-sig")):
        if r["text"].strip() in gold_txt:
            continue
        rows.append({"text": r["text"], "y": SENTS.index(r["overall_sentiment"])})

    rnd = random.Random(SEED)
    by = defaultdict(list)
    for r in rows:
        by[r["y"]].append(r)
    train, val = [], []
    for k in sorted(by):
        g = by[k]
        rnd.shuffle(g)
        cut = max(1, int(len(g) * 0.2))
        val += g[:cut]
        train += g[cut:]
    rnd.shuffle(train)

    c = Counter(SENTS[r["y"]] for r in rows)
    p("=" * 70)
    p("  เทรนโมเดลอารมณ์รวมของรีวิวใหม่")
    p("=" * 70)
    p(f"ชุด silver {len(rows)} รีวิว : " + " | ".join(f"{s} {c[s]}" for s in SENTS))
    p(f"train {len(train)} | val {len(val)}")
    p("")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(str(START_FROM))
    model = AutoModelForSequenceClassification.from_pretrained(
        str(START_FROM), num_labels=3,
        id2label={i: s for i, s in enumerate(SENTS)},
        label2id={s: i for i, s in enumerate(SENTS)},
        ignore_mismatched_sizes=True).to(device)

    cnt = Counter(r["y"] for r in train)
    w = torch.tensor([len(train) / (3 * max(cnt[i], 1)) for i in range(3)],
                     dtype=torch.float).to(device)
    p("class weight: " + " | ".join(f"{SENTS[i]} {w[i]:.2f}" for i in range(3)))
    p("")

    def collate(batch):
        enc = tok([b["text"] for b in batch], padding=True, truncation=True,
                  max_length=max_length, return_tensors="pt")
        enc["labels"] = torch.tensor([b["y"] for b in batch])
        return enc

    tl = DataLoader(DS(train), batch_size=batch_size, shuffle=True, collate_fn=collate)
    vl = DataLoader(DS(val), batch_size=batch_size * 2, collate_fn=collate)
    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    lossf = nn.CrossEntropyLoss(weight=w)
    best, best_state = -1.0, None
    for ep in range(1, epochs + 1):
        model.train()
        tot = 0.0
        for b in tl:
            lab = b.pop("labels").to(device)
            b = {k: v.to(device) for k, v in b.items()}
            loss = lossf(model(**b).logits, lab)
            loss.backward()
            opt.step()
            opt.zero_grad()
            tot += loss.item()
        model.eval()
        G, P = [], []
        with torch.no_grad():
            for b in vl:
                y = b.pop("labels")
                b = {k: v.to(device) for k, v in b.items()}
                P += model(**b).logits.argmax(-1).cpu().tolist()
                G += y.tolist()
        m, a, _ = report(G, P)
        p(f"epoch {ep}  loss {tot / len(tl):.4f} | val macro-F1 {m:.4f} acc {a:.4f}")
        if m > best:
            best = m
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    if best_state:
        model.load_state_dict(best_state)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(OUT_DIR))
    tok.save_pretrained(str(OUT_DIR))
    (OUT_DIR / "about.json").write_text(json.dumps({
        "_readme": ["อารมณ์รวมของรีวิว เทรนบน data/labeling/silver_reviews.csv",
                    "ต้องเทียบกับ models/wangchanberta-sentiment บน gold ก่อนใช้จริง"],
        "labels": SENTS, "n_train": len(train), "n_val": len(val),
        "val_macro_f1": best,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    p("")
    p(f"บันทึกที่ {OUT_DIR.relative_to(ROOT)} | val macro-F1 ดีสุด {best:.4f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--max-length", type=int, default=256)
    a = ap.parse_args()
    main(a.epochs, a.lr, a.batch_size, a.max_length)
