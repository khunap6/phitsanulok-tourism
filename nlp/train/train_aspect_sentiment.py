"""train_aspect_sentiment.py — เทรนโมเดลอารมณ์ "รายหมวด" (อีกครึ่งของ ABSA)

ปัญหาที่แก้
  โมเดลอารมณ์เดิมให้ค่าเดียวต่อรีวิว พอรีวิวหนึ่งมีหลายหมวด เช่น
  "อาหารอร่อยแต่ที่จอดรถน้อย" ถ้าใช้ค่าเดียวกับทุกหมวด หมวดอาหารจะถูกนับเป็นคำบ่น
  ทั้งที่ผู้รีวิวชม -> ข้อมูลเพี้ยน

วิธี (รูปแบบมาตรฐานของงาน ABSA)
  ป้อนเป็นคู่ประโยค  (ชื่อหมวด, ข้อความรีวิว)  แล้วทำนายอารมณ์ของ "หมวดนั้น"
  โมเดลจึงตอบต่างกันได้สำหรับคนละหมวดในรีวิวเดียวกัน

⚠️ เริ่มจาก models/wangchanberta-sentiment ที่ fine-tune มาแล้ว
  encoder รู้จักภาษาและโดเมนนี้อยู่แล้ว เปลี่ยนแค่วิธีป้อนกับหัวจำแนก

⚠️ ข้อมูลไม่สมดุล -> ใช้ class weight ตามที่ผู้ใช้สั่ง
  และแบ่ง train/val แบบ stratified ตามคู่ (หมวด, อารมณ์)

⚠️ ชุด silver เป็น negative 50% ส่วน gold เป็น positive 88%
  การวัดบน gold จึงเป็นการวัดข้ามการกระจาย ซึ่งเข้มกว่าการวัดบน val ของตัวเอง

รัน:
  uv run python nlp/train/train_aspect_sentiment.py --epochs 12
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
OUT_DIR = ROOT / "models" / "wangchanberta-aspect-sentiment"
START_FROM = ROOT / "models" / "wangchanberta-sentiment"
SENTS = ["positive", "neutral", "negative"]
SEED = 20261012

# ⚠️ SEED ด้านบนใช้ตรึง "ส่วนแบ่ง train/val" เท่านั้น และต้องคงที่ตลอดไป
#    ถ้าเปลี่ยน ส่วนแบ่งจะขยับ ตัวเลขทุกรอบที่เคยรายงานไว้จะเทียบกันไม่ได้
#
# run_seed ด้านล่างเป็นของคนละอย่าง — ตรึงการสุ่มค่าเริ่มต้นของหัวจำแนก
# ลำดับ batch และ dropout ซึ่งเดิมไม่ได้ตรึงไว้เลย
#
# ⚠️ ทำไมต้องมี วัดได้จริงในโปรเจกต์นี้
#    เทรนโมเดลอารมณ์รายหมวดสองรอบด้วยข้อมูลชุดเดียวกันทุกประการ
#    ได้ macro-F1 0.5933 กับ 0.7322 ห่างกัน 0.139 (ทั้งระบบ 0.8056 กับ 0.8479)
#    เกือบสรุปผิดว่าการแก้ป้ายรอบนั้นทำให้โมเดลแย่ลง
#    ที่จริงเป็นความผันผวนของการเทรนล้วน ๆ
#
#    ผลที่ตามมา บนชุดประเมินขนาดนี้ห้ามสรุปว่าวิธีไหนดีกว่าจากการรันครั้งเดียว
#    ต้องรันหลาย run_seed แล้วรายงานค่าเฉลี่ยกับส่วนเบี่ยงเบน
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


def main(epochs: int, lr: float, batch_size: int, max_length: int,
         run_seed: int = SEED) -> None:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    doc = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    names = {c["id"]: c["name"] for c in doc["categories"]}
    rows = load_rows(names)

    rnd = random.Random(SEED)
    by = defaultdict(list)
    for r in rows:
        by[(r["cid"], r["y"])].append(r)
    train, val = [], []
    for k in sorted(by):
        g = by[k]
        rnd.shuffle(g)
        cut = max(1, int(len(g) * 0.2)) if len(g) >= 3 else 0
        val += g[:cut]
        train += g[cut:]
    rnd.shuffle(train)

    p("=" * 72)
    p("  เทรนโมเดลอารมณ์รายหมวด (aspect-based)")
    p("=" * 72)
    c = Counter(SENTS[r["y"]] for r in rows)
    p(f"ชุด silver {len(rows)} คู่ (หมวด, รีวิว) : " +
      " | ".join(f"{s} {c[s]}" for s in SENTS))
    p(f"train {len(train)} | val {len(val)}")
    p(f"เริ่มจาก {START_FROM.name}")
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

    coll = make_collate(tok, max_length)
    tl = DataLoader(DS(train), batch_size=batch_size, shuffle=True,
                    collate_fn=coll, generator=gen)
    vl = DataLoader(DS(val), batch_size=batch_size * 2, collate_fn=coll)

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
        G, P = predict(model, vl, device)
        macro, acc, _ = report(G, P)
        p(f"epoch {ep}  loss {tot / len(tl):.4f} | val macro-F1 {macro:.4f} acc {acc:.4f}")
        if macro > best:
            best = macro
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    if best_state:
        model.load_state_dict(best_state)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(OUT_DIR))
    tok.save_pretrained(str(OUT_DIR))
    (OUT_DIR / "about.json").write_text(json.dumps({
        "_readme": ["โมเดลอารมณ์รายหมวด — ป้อนเป็นคู่ (ชื่อหมวด, ข้อความรีวิว)",
                    "ชื่อหมวดต้องตรงกับ shared/categories.json",
                    "เทรนจาก data/labeling/silver_aspects.csv (claude_silver)"],
        "labels": SENTS, "n_train": len(train), "n_val": len(val),
        "run_seed": run_seed,
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
