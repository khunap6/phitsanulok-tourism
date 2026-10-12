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

# ⚠️ SEED ด้านบนใช้ตรึง "ส่วนแบ่ง train/val" เท่านั้น และต้องคงที่ตลอดไป
#    ถ้าเปลี่ยน ส่วนแบ่งจะขยับ ตัวเลขทุกรอบที่เคยรายงานไว้จะเทียบกันไม่ได้
#
# run_seed ด้านล่างเป็นของคนละอย่าง — ตรึงการสุ่มค่าเริ่มต้นของหัวจำแนก
# ลำดับ batch และ dropout ซึ่งเดิมไม่ได้ตรึงไว้เลย
#
# ⚠️ ทำไมต้องมี — เรื่องจริงที่เกิดในโปรเจกต์นี้
#    เคยเทรนโมเดลอารมณ์รายหมวดสองรอบแล้วได้ macro-F1 0.5933 กับ 0.7322
#    ตอนนั้นสรุปว่าเป็นความผันผวนของ seed เพราะข้อมูลไม่ได้เปลี่ยน
#
#    พอมาวัดจริงด้วย run_seed_sweep.py พบว่า **สรุปผิด**
#      ตรึง config แล้วรัน 3 seed  12 epoch -> 0.6721 ± 0.0107
#                                 16 epoch -> 0.6814 ± 0.0355
#      ความผันผวนของ seed เล็กกว่า 0.139 มาก และ epoch ก็ไม่ใช่สาเหตุ
#      (ต่างกัน +0.009 ซึ่งอยู่ในช่วง sd)
#
#    สาเหตุจริงของ 0.5933 กับ 0.7322 สรุปไม่ได้ เพราะสองรอบนั้น
#    **ไม่ได้บันทึกทั้ง seed และ hyperparameter ไว้** จึงย้อนทำซ้ำไม่ได้เลย
#    นี่คือเหตุผลที่ about.json ต้องเก็บ run_seed คู่กับ epochs/lr/batch_size
#
# ⚠️ ความผันผวนที่วัดได้จริงอยู่ที่โมเดลหมวด ไม่ใช่โมเดลอารมณ์
#    หมวด micro-F1 0.8449 ± 0.0310 · macro-F1 0.7139 ± 0.0502
#    หมวด 7 แกว่งถึง ±0.2074 (gold มีแค่ 17 รายการ)
#    ผลต่างระดับ 0.01 จึงอ่านเป็นการปรับปรุงไม่ได้
#    ต้องรันหลาย run_seed แล้วรายงานค่าเฉลี่ยกับส่วนเบี่ยงเบนเสมอ
def set_run_seed(run_seed: int):
    """ตรึงการสุ่มทุกแหล่งของรอบการเทรน แล้วคืน generator ให้ DataLoader

    ต้องเรียก *ก่อน* สร้างโมเดล ไม่งั้นหัวจำแนกถูกสุ่มไปแล้ว
    """
    random.seed(run_seed)
    torch.manual_seed(run_seed)
    torch.cuda.manual_seed_all(run_seed)
    try:
        import numpy as np
        np.random.seed(run_seed)
    except ImportError:
        pass
    g = torch.Generator()
    g.manual_seed(run_seed)
    return g



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


def make_collate(tok, max_length):
    def collate(batch):
        enc = tok([b["cat"] for b in batch], [b["text"] for b in batch],
                  padding=True, truncation=True, max_length=max_length,
                  return_tensors="pt")
        enc["labels"] = torch.tensor([b["y"] for b in batch])
        return enc
    return collate


def prf(tp, fp, fn):
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return pr, rc, (2 * pr * rc / (pr + rc) if pr + rc else 0.0)


def report(gold, pred):
    out = {}
    for i, s in enumerate(SENTS):
        out[s] = prf(sum(1 for g, q in zip(gold, pred) if g == i and q == i),
                     sum(1 for g, q in zip(gold, pred) if g != i and q == i),
                     sum(1 for g, q in zip(gold, pred) if g == i and q != i))
    macro = sum(v[2] for v in out.values()) / len(SENTS)
    acc = sum(1 for g, q in zip(gold, pred) if g == q) / len(gold)
    return macro, acc, out


@torch.no_grad()
def predict(model, loader, device):
    model.eval()
    G, P = [], []
    for b in loader:
        y = b.pop("labels")
        b = {k: v.to(device) for k, v in b.items()}
        P += model(**b).logits.argmax(-1).cpu().tolist()
        G += y.tolist()
    return G, P


def load_rows(names):
    texts = {int(r["review_id"]): r["text"] for r in
             csv.DictReader(open(LAB / "silver_reviews.csv", encoding="utf-8-sig"))}
    rows = []
    for r in csv.DictReader(open(LAB / "silver_aspects.csv", encoding="utf-8-sig")):
        rid = int(r["review_id"])
        if rid in texts:
            rows.append({"cat": names[int(r["category_id"])], "text": texts[rid],
                         "y": SENTS.index(r["aspect_sentiment"]),
                         "cid": int(r["category_id"])})
    return rows




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


def main(epochs: int, lr: float, batch_size: int, max_length: int,
         run_seed: int = SEED) -> None:
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

    # ⚠️ ต้องอยู่ก่อน from_pretrained เสมอ หัวจำแนกถูกสุ่มตอนนั้น
    gen = set_run_seed(run_seed)
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

    tl = DataLoader(DS(train), batch_size=batch_size, shuffle=True,
                    collate_fn=collate, generator=gen)
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
        # ⚠️ ต้องบันทึก hyperparameter คู่กับ seed เสมอ
        #   ไม่งั้นเทียบผลสองรอบแล้วแยกไม่ออกว่าต่างเพราะ seed หรือเพราะ config
        "run_seed": run_seed, "epochs": epochs, "lr": lr,
        "batch_size": batch_size, "max_length": max_length,
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
    ap.add_argument("--seed", type=int, default=SEED,
                    help="ตรึงรอบการเทรน (ไม่ใช่ส่วนแบ่ง train/val)")
    a = ap.parse_args()
    main(a.epochs, a.lr, a.batch_size, a.max_length, a.seed)
