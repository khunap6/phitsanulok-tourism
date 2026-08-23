"""
train.py — Fine-tune WangchanBERTa ด้วยป้ายกำกับจาก Claude (Knowledge Distillation)

ออกแบบมาสำหรับ CPU โดยเฉพาะ:
  - dynamic padding: เติมความยาวเท่าประโยคที่ยาวสุดในแต่ละ batch (ไม่ใช่ 128 เสมอ)
    รีวิวเราเฉลี่ยแค่ ~30 token → เร็วขึ้นหลายเท่า
  - class weight แบบ sqrt: ชดเชยคลาสที่ตัวอย่างน้อย แต่ไม่รุนแรงเกินจนโมเดลเอนเอียง
  - เลือกโมเดลที่ดีที่สุดจาก macro-F1 บนชุด val (ไม่ใช่ accuracy ซึ่งหลอกตาเมื่อข้อมูลไม่สมดุล)

รัน:
  uv run python nlp/train/train.py --task sentiment
  uv run python nlp/train/train.py --task category
"""
import argparse
import json
import math
import os
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

DATA_DIR = Path("data/training")
MODEL_DIR = Path("models")

# โมเดลตั้งต้นของแต่ละงาน
BASE_MODEL = {
    # อารมณ์: ต่อยอดจากตัวที่ fine-tune ภาษาไทยมาแล้ว (รู้จักอารมณ์อยู่บ้าง)
    "sentiment": "poom-sci/WangchanBERTa-finetuned-sentiment",
    # หมวดหมู่: ไม่มีใครทำมาก่อน → เริ่มจาก WangchanBERTa ตัวฐาน
    "category": "airesearch/wangchanberta-base-att-spm-uncased",
}


def safe_print(t: str) -> None:
    try:
        print(t, flush=True)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"), flush=True)


class ReviewDataset(Dataset):
    def __init__(self, rows: list[dict], label2id: dict[str, int]):
        self.texts = [r["text"] for r in rows]
        self.labels = [label2id[r["label"]] for r in rows]

    def __len__(self) -> int:
        return len(self.texts)

    def __getitem__(self, i: int):
        return self.texts[i], self.labels[i]


def make_collate(tokenizer, max_length: int):
    """เติมความยาวตามประโยคยาวสุดใน batch นั้น (dynamic padding) → เร็วกว่าเติมเต็มเสมอ"""
    def collate(batch):
        texts, labels = zip(*batch)
        enc = tokenizer(list(texts), padding=True, truncation=True,
                        max_length=max_length, return_tensors="pt")
        enc["labels"] = torch.tensor(labels, dtype=torch.long)
        return enc
    return collate


def class_weights(labels: list[int], n_classes: int) -> torch.Tensor:
    """
    น้ำหนักแบบ 1/sqrt(count) — ชดเชยคลาสน้อยแบบพอดี
    ('balanced' เต็มสูตรจะให้น้ำหนักคลาสที่มี 27 ตัวอย่างสูงเกินไปจนโมเดลเดามั่ว)
    """
    counts = np.bincount(labels, minlength=n_classes).astype(float)
    counts[counts == 0] = 1.0
    w = 1.0 / np.sqrt(counts)
    w = w / w.mean()
    return torch.tensor(w, dtype=torch.float)


@torch.no_grad()
def evaluate(model, loader, device) -> tuple[float, float, list[int], list[int]]:
    from sklearn.metrics import f1_score, accuracy_score
    model.eval()
    preds, golds = [], []
    for batch in loader:
        labels = batch.pop("labels")
        batch = {k: v.to(device) for k, v in batch.items()}
        logits = model(**batch).logits
        preds += logits.argmax(-1).cpu().tolist()
        golds += labels.tolist()
    return (accuracy_score(golds, preds),
            f1_score(golds, preds, average="macro", zero_division=0),
            golds, preds)


def main(task: str, epochs: int, batch_size: int | None, lr: float, max_length: int) -> None:
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    # GPU รับ batch ใหญ่กว่าได้ → เร็วขึ้นอีก (VRAM 8 GB พอสำหรับ BERT-base batch 32)
    if batch_size is None:
        batch_size = 32 if torch.cuda.is_available() else 16

    ds_path = DATA_DIR / f"{task}_dataset.json"
    if not ds_path.exists():
        safe_print(f"❌ ไม่พบ {ds_path} — รัน prepare_data.py ก่อน")
        return
    data = json.loads(ds_path.read_text(encoding="utf-8"))

    labels = data["labels"]
    label2id = {l: i for i, l in enumerate(labels)}
    id2label = {i: l for l, i in label2id.items()}
    base = BASE_MODEL[task]

    safe_print("=" * 64)
    safe_print(f"ฝึกโมเดล: {task}")
    safe_print("=" * 64)
    safe_print(f"  โมเดลตั้งต้น : {base}")
    safe_print(f"  จำนวนคลาส    : {len(labels)}")
    safe_print(f"  train/val/test: {len(data['train']):,} / {len(data['val']):,} / {len(data['test']):,}")
    safe_print(f"  epochs={epochs} batch={batch_size} lr={lr} max_len={max_length}")

    # ใช้ GPU ถ้ามี — เร็วกว่า CPU ราว 10 เท่าสำหรับโมเดลขนาดนี้
    use_cuda = torch.cuda.is_available()
    device = torch.device("cuda" if use_cuda else "cpu")
    if use_cuda:
        name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        safe_print(f"  อุปกรณ์      : 🎮 {name} (VRAM {vram:.0f} GB)")
        torch.backends.cudnn.benchmark = True   # เร่งความเร็วเมื่อขนาด input คงที่
    else:
        torch.set_num_threads(os.cpu_count() or 4)
        safe_print(f"  อุปกรณ์      : CPU ({os.cpu_count()} threads) — ไม่พบ GPU")

    tokenizer = AutoTokenizer.from_pretrained(base)
    model = AutoModelForSequenceClassification.from_pretrained(
        base, num_labels=len(labels), id2label=id2label, label2id=label2id,
        ignore_mismatched_sizes=True,   # หัวจำแนกของโมเดลเดิมมีจำนวนคลาสไม่ตรง → สร้างใหม่
    ).to(device)

    collate = make_collate(tokenizer, max_length)
    pin = use_cuda   # คัดลอกข้อมูลไป GPU ได้เร็วขึ้น
    train_loader = DataLoader(ReviewDataset(data["train"], label2id), batch_size=batch_size,
                              shuffle=True, collate_fn=collate, pin_memory=pin)
    val_loader = DataLoader(ReviewDataset(data["val"], label2id), batch_size=batch_size * 2,
                            collate_fn=collate)
    test_loader = DataLoader(ReviewDataset(data["test"], label2id), batch_size=batch_size * 2,
                             collate_fn=collate)

    w = class_weights([label2id[r["label"]] for r in data["train"]], len(labels)).to(device)
    safe_print(f"  น้ำหนักคลาส  : {', '.join(f'{l[:14]}={w[i]:.2f}' for i, l in enumerate(labels))}")

    loss_fn = torch.nn.CrossEntropyLoss(weight=w)
    optim = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    total_steps = len(train_loader) * epochs
    sched = torch.optim.lr_scheduler.OneCycleLR(optim, max_lr=lr, total_steps=total_steps,
                                                pct_start=0.1)

    out_dir = MODEL_DIR / f"wangchanberta-{task}"
    out_dir.mkdir(parents=True, exist_ok=True)
    best_f1, t_start = -1.0, time.time()

    for ep in range(1, epochs + 1):
        model.train()
        running, t_ep = 0.0, time.time()
        for step, batch in enumerate(train_loader, 1):
            batch = {k: v.to(device) for k, v in batch.items()}
            lbl = batch.pop("labels")
            loss = loss_fn(model(**batch).logits, lbl)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optim.step()
            sched.step()
            optim.zero_grad()
            running += loss.item()

            if step % 50 == 0 or step == len(train_loader):
                done = (ep - 1) * len(train_loader) + step
                eta = (time.time() - t_start) / done * (total_steps - done)
                safe_print(f"  [ep {ep}/{epochs}] step {step}/{len(train_loader)} "
                           f"loss={running / step:.4f} เหลืออีก ~{eta / 60:.0f} นาที")

        acc, f1, _, _ = evaluate(model, val_loader, device)
        safe_print(f"  ✔ epoch {ep} จบใน {(time.time() - t_ep) / 60:.1f} นาที "
                   f"| val accuracy={acc:.3f} macro-F1={f1:.3f}")

        if f1 > best_f1:
            best_f1 = f1
            model.save_pretrained(out_dir)
            tokenizer.save_pretrained(out_dir)
            safe_print(f"    💾 บันทึกโมเดล (ดีที่สุดจนถึงตอนนี้ F1={f1:.3f})")

    # ── ประเมินผลชุดทดสอบด้วยโมเดลที่ดีที่สุด ──
    from sklearn.metrics import classification_report
    from transformers import AutoModelForSequenceClassification as AMSC
    best = AMSC.from_pretrained(out_dir).to(device)
    acc, f1, golds, preds = evaluate(best, test_loader, device)

    safe_print("\n" + "=" * 64)
    safe_print(f"ผลชุดทดสอบ (test set — โมเดลไม่เคยเห็นข้อมูลชุดนี้)")
    safe_print("=" * 64)
    safe_print(f"  accuracy={acc:.3f}  macro-F1={f1:.3f}\n")
    safe_print(classification_report(golds, preds, target_names=labels,
                                     zero_division=0, digits=3))

    (out_dir / "training_info.json").write_text(json.dumps({
        "task": task, "base_model": base, "labels": labels,
        "test_accuracy": round(acc, 4), "test_macro_f1": round(f1, 4),
        "epochs": epochs, "batch_size": batch_size, "lr": lr,
        "train_size": len(data["train"]),
        "trained_minutes": round((time.time() - t_start) / 60, 1),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    safe_print(f"\n✅ เสร็จใน {(time.time() - t_start) / 60:.1f} นาที → {out_dir}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["sentiment", "category"], required=True)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=None,
                    help="ไม่ระบุ = 32 บน GPU, 16 บน CPU")
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max-length", type=int, default=128)
    a = ap.parse_args()
    main(a.task, a.epochs, a.batch_size, a.lr, a.max_length)
