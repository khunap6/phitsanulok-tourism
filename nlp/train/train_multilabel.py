"""train_multilabel.py — เทรนหัวจำแนกหมวดแบบ multi-label (1 รีวิวได้หลายหมวด)

ต่างจาก train.py เดิมตรงไหน
  เดิม  softmax 12 คลาส เลือกได้หมวดเดียว  -> recall แค่ 0.41 เพราะ gold มี 1.96 หมวด/รีวิว
  นี่   sigmoid 11 คลาส + BCEWithLogitsLoss ตัดสินทีละหมวดอิสระกัน

⚠️ เริ่มจากโมเดลเดิมไม่ใช่จาก base
  models/wangchanberta-category ถูก fine-tune ด้วยรีวิวไทย 10,690 รายการของงานนี้แล้ว
  ตัว encoder จึงรู้จักภาษาและโดเมนนี้ดีอยู่แล้ว เราเปลี่ยนแค่หัวจำแนก
  ถ้าเริ่มจาก base ใหม่ ชุดเทรน silver 500 รายการน้อยเกินกว่าจะเรียนได้ดี

⚠️ ทำไมไม่เอาชุดเทรนเดิม 10,690 มารวม
  ป้ายเดิมเป็น single-label ถ้าแปลงเป็น multi-hot ที่มี 1 ตัว แล้วถือว่าหมวดอื่น
  เป็น "ไม่ใช่" ทั้งหมด จะเป็นการสอนผิด เพราะรีวิวเหล่านั้นอาจพูดถึงหมวดอื่นจริง
  แต่ผู้ติดป้ายตอนนั้นเลือกได้แค่หมวดเดียว -> false negative เต็มไปหมด
  การถ่ายทอดผ่าน encoder ที่เทรนมาแล้วจึงปลอดภัยกว่า

⚠️ ข้อมูลไม่สมดุล
  ใช้ pos_weight รายคลาส = (จำนวนที่ไม่ใช่ / จำนวนที่ใช่) ตามที่ผู้ใช้สั่งให้ใช้ class weight
  และแบ่ง train/val แบบ stratified ตามจำนวนหมวดของรีวิว

⚠️ กันข้อมูลรั่ว
  ชุด silver ถูกสุ่มโดยกัน review_id และ "ข้อความ" ของ gold 300 ออกแล้ว
  (ดู scripts/sample_for_labeling.py) สคริปต์นี้ตรวจซ้ำอีกชั้นก่อนเทรน

รัน:
  uv run python nlp/train/train_multilabel.py --epochs 8
"""
import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
LAB = ROOT / "data" / "labeling"
OUT_DIR = ROOT / "models" / "wangchanberta-category-multilabel"
START_FROM = ROOT / "models" / "wangchanberta-category"
SEED = 20261012


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


class MLDataset(Dataset):
    def __init__(self, rows):
        self.rows = rows

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, i):
        return self.rows[i]


def make_collate(tok, max_length):
    def collate(batch):
        enc = tok([b["text"] for b in batch], padding=True, truncation=True,
                  max_length=max_length, return_tensors="pt")
        enc["labels"] = torch.tensor([b["y"] for b in batch], dtype=torch.float)
        return enc
    return collate


def prf(tp, fp, fn):
    pr = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return pr, rc, (2 * pr * rc / (pr + rc) if pr + rc else 0.0)


@torch.no_grad()
def collect_probs(model, loader, device):
    model.eval()
    P, Y = [], []
    for b in loader:
        y = b.pop("labels")
        b = {k: v.to(device) for k, v in b.items()}
        P.append(torch.sigmoid(model(**b).logits).cpu())
        Y.append(y)
    return torch.cat(P), torch.cat(Y)


def score(P, Y, th):
    pred = (P >= th).float()
    tp = (pred * Y).sum().item()
    fp = (pred * (1 - Y)).sum().item()
    fn = ((1 - pred) * Y).sum().item()
    micro = prf(tp, fp, fn)
    f1s = []
    for c in range(Y.shape[1]):
        f1s.append(prf((pred[:, c] * Y[:, c]).sum().item(),
                       (pred[:, c] * (1 - Y[:, c])).sum().item(),
                       ((1 - pred[:, c]) * Y[:, c]).sum().item())[2])
    return micro, sum(f1s) / len(f1s), f1s


def main(epochs: int, lr: float, batch_size: int, max_length: int) -> None:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    cats = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    ids = [c["id"] for c in cats["categories"]]
    names = {c["id"]: c["name"] for c in cats["categories"]}
    idx = {cid: i for i, cid in enumerate(ids)}

    texts = {}
    for r in csv.DictReader(open(LAB / "silver_reviews.csv", encoding="utf-8-sig")):
        texts[int(r["review_id"])] = r["text"]
    y = defaultdict(lambda: [0.0] * len(ids))
    for r in csv.DictReader(open(LAB / "silver_aspects.csv", encoding="utf-8-sig")):
        y[int(r["review_id"])][idx[int(r["category_id"])]] = 1.0

    gold_texts = {r["text"].strip() for r in
                  csv.DictReader(open(LAB / "reviews_labeled.csv", encoding="utf-8-sig"))}
    rows = [{"text": t, "y": y[rid]} for rid, t in texts.items()
            if t.strip() not in gold_texts]
    leaked = len(texts) - len(rows)

    rnd = random.Random(SEED)
    # stratify ตามจำนวนหมวดของรีวิว เพื่อให้ val มีทั้งรีวิวหมวดเดียวและหลายหมวด
    by_n = defaultdict(list)
    for r in rows:
        by_n[int(sum(r["y"]))].append(r)
    train, val = [], []
    for k in sorted(by_n):
        g = by_n[k]
        rnd.shuffle(g)
        cut = max(1, int(len(g) * 0.2))
        val += g[:cut]
        train += g[cut:]
    rnd.shuffle(train)

    p("=" * 72)
    p("  เทรนหัวจำแนกหมวดแบบ multi-label")
    p("=" * 72)
    p(f"ชุด silver {len(texts)} รีวิว | ตัดที่ซ้ำกับ gold ออก {leaked}")
    p(f"train {len(train)} | val {len(val)} | {len(ids)} หมวด")
    p(f"เริ่มจาก {START_FROM.name} (เปลี่ยนเฉพาะหัวจำแนก)")
    p("")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = AutoTokenizer.from_pretrained(str(START_FROM))
    model = AutoModelForSequenceClassification.from_pretrained(
        str(START_FROM), num_labels=len(ids),
        problem_type="multi_label_classification",
        id2label={i: names[c] for i, c in enumerate(ids)},
        label2id={names[c]: i for i, c in enumerate(ids)},
        ignore_mismatched_sizes=True).to(device)

    pos = torch.tensor([sum(r["y"][i] for r in train) for i in range(len(ids))])
    pos_weight = ((len(train) - pos) / pos.clamp(min=1)).clamp(max=20.0).to(device)
    p("pos_weight รายหมวด (ชดเชยคลาสที่พบน้อย):")
    for i, cid in enumerate(ids):
        p(f"   {cid:>2} {names[cid][:34]:<35} พบ {int(pos[i]):>4} | w={pos_weight[i]:.2f}")
    p("")

    coll = make_collate(tok, max_length)
    tl = DataLoader(MLDataset(train), batch_size=batch_size, shuffle=True, collate_fn=coll)
    vl = DataLoader(MLDataset(val), batch_size=batch_size * 2, collate_fn=coll)

    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    lossf = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
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
        P, Y = collect_probs(model, vl, device)
        micro, macro, _ = score(P, Y, 0.5)
        p(f"epoch {ep}  loss {tot / len(tl):.4f} | val micro-F1 {micro[2]:.4f} "
          f"(P {micro[0]:.3f} R {micro[1]:.3f}) macro-F1 {macro:.4f}")
        if micro[2] > best:
            best = micro[2]
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    if best_state:
        model.load_state_dict(best_state)
    model.to(device)

    # จูน threshold รายหมวดบน val
    P, Y = collect_probs(model, vl, device)
    th = torch.full((len(ids),), 0.5)
    grid = [i / 100 for i in range(5, 95, 5)]
    for _ in range(3):
        for c in range(len(ids)):
            cur, bestv = th[c].item(), score(P, Y, th)[0][2]
            for t in grid:
                th[c] = t
                v = score(P, Y, th)[0][2]
                if v > bestv + 1e-9:
                    cur, bestv = t, v
            th[c] = cur
    micro, macro, f1s = score(P, Y, th)
    p("")
    p(f"หลังจูน threshold บน val : micro-F1 {micro[2]:.4f} "
      f"(P {micro[0]:.3f} R {micro[1]:.3f}) macro-F1 {macro:.4f}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(OUT_DIR))
    tok.save_pretrained(str(OUT_DIR))
    (OUT_DIR / "thresholds.json").write_text(json.dumps({
        "_readme": ["เกณฑ์ตัดสินรายหมวด จูนบน val ของชุด silver",
                    "ใช้คู่กับ sigmoid ของโมเดลนี้เท่านั้น",
                    "ถ้าเทรนใหม่ต้องจูนใหม่"],
        "category_ids": ids,
        "thresholds": {str(cid): round(th[i].item(), 3) for i, cid in enumerate(ids)},
        "val_micro_f1": micro[2], "val_macro_f1": macro,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    p(f"บันทึกโมเดลที่ {OUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--max-length", type=int, default=256)
    a = ap.parse_args()
    main(a.epochs, a.lr, a.batch_size, a.max_length)
