"""
compare_models.py — เทียบโมเดลแบบยุติธรรมบนชุดข้อมูลเดียวกัน

ทำไมต้องมี:
  accuracy หลอกตาได้เมื่อข้อมูลไม่สมดุล (ข้อมูลเรามี positive 89%
  → เดา "บวก" ตลอดก็ได้ 89% แล้ว แต่จับคำบ่นไม่ได้เลย)
  ต้องวัดด้วยชุด "สมดุล" + macro-F1 ถึงจะเห็นความจริง

เทียบ 3 ทาง:
  1. rule-based เดิม        (ดูจากดาว / จับคำ)
  2. โมเดลสาธารณะ           (poom-sci — ไม่ได้ฝึกกับข้อมูลเรา)
  3. โมเดลที่เราฝึกเอง       (models/wangchanberta-*)

รัน:
  uv run python nlp/train/compare_models.py --task sentiment
  uv run python nlp/train/compare_models.py --task category
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from sqlalchemy import text

from db.database import AsyncSessionLocal

SENT_MAP = {"pos": "positive", "neg": "negative", "neu": "neutral", "q": "neutral"}


def safe_print(t: str) -> None:
    try:
        print(t, flush=True)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"), flush=True)


async def balanced_sample(task: str, per_class: int) -> list[tuple[str, str, int]]:
    """ดึงตัวอย่างเท่าๆ กันทุกคลาส จากชุด test (โมเดลไม่เคยเห็น)"""
    ds = json.loads(Path(f"data/training/{task}_dataset.json").read_text(encoding="utf-8"))
    by_label: dict[str, list[dict]] = {}
    for r in ds["test"]:
        by_label.setdefault(r["label"], []).append(r)

    # ต้องดึง rating มาด้วยเพื่อทดสอบ rule-based
    texts = [r["text"] for items in by_label.values() for r in items[:per_class]]
    async with AsyncSessionLocal() as s:
        # ใช้ชื่อ alias ยาวๆ — 't' ชนกับ attribute ภายในของ SQLAlchemy Row
        res = await s.execute(
            text("SELECT text_clean AS review_text, rating FROM reviews WHERE text_clean = ANY(:ts)"),
            {"ts": texts},
        )
        rating_of = {x.review_text: x.rating for x in res.fetchall()}

    out = []
    for lab, items in by_label.items():
        for r in items[:per_class]:
            out.append((r["text"], lab, rating_of.get(r["text"]) or 0))
    return out


def predict_rule_based(task: str, samples) -> list[str]:
    if task == "sentiment":
        def f(rating):
            if not rating:
                return "neutral"
            return "positive" if rating >= 4 else ("neutral" if rating == 3 else "negative")
        return [f(r) for _, _, r in samples]
    from nlp.topic_model import rule_based_categorize
    return [rule_based_categorize(t)[0] for t, _, _ in samples]


def predict_model(model_path: str, samples, task: str) -> list[str] | None:
    from transformers import pipeline
    try:
        clf = pipeline("text-classification", model=model_path, truncation=True, max_length=128)
    except Exception as e:
        safe_print(f"    (ข้าม {model_path}: {str(e)[:60]})")
        return None
    raw = clf([t for t, _, _ in samples], batch_size=16)
    if task == "sentiment":
        return [SENT_MAP.get(r["label"], r["label"]) for r in raw]
    return [r["label"] for r in raw]


def report(name: str, gold: list[str], pred: list[str], labels: list[str]) -> dict:
    from sklearn.metrics import accuracy_score, f1_score
    acc = accuracy_score(gold, pred)
    f1 = f1_score(gold, pred, average="macro", labels=labels, zero_division=0)
    safe_print(f"  {name:34} accuracy={acc:.3f}  macro-F1={f1:.3f}")
    return {"name": name, "accuracy": acc, "macro_f1": f1}


async def main(task: str, per_class: int) -> None:
    samples = await balanced_sample(task, per_class)
    gold = [g for _, g, _ in samples]
    labels = sorted(set(gold))

    safe_print("=" * 68)
    safe_print(f"เทียบโมเดล — งาน: {task}")
    safe_print("=" * 68)
    safe_print(f"  ชุดทดสอบ: {len(samples):,} รีวิว ({len(labels)} คลาส "
               f"ละ ~{per_class} — สมดุล ไม่เอนเอียง)\n")

    results = [report("1) ระบบเดิม (rule-based)", gold, predict_rule_based(task, samples), labels)]

    if task == "sentiment":
        p = predict_model("poom-sci/WangchanBERTa-finetuned-sentiment", samples, task)
        if p:
            results.append(report("2) โมเดลสาธารณะ (ไม่ได้ฝึกกับข้อมูลเรา)", gold, p, labels))

    ours = f"models/wangchanberta-{task}"
    if Path(ours).exists():
        p = predict_model(ours, samples, task)
        if p:
            results.append(report("3) โมเดลที่เราฝึกเอง ⭐", gold, p, labels))
            from sklearn.metrics import classification_report
            safe_print("\n  รายละเอียดโมเดลที่เราฝึกเอง:")
            safe_print(classification_report(gold, p, labels=labels, zero_division=0, digits=3))
    else:
        safe_print(f"  (ยังไม่มี {ours} — ฝึกก่อนด้วย train.py)")

    if len(results) >= 2:
        best, base = max(results, key=lambda r: r["macro_f1"]), results[0]
        gain = (best["macro_f1"] - base["macro_f1"]) / max(base["macro_f1"], 0.001)
        safe_print("=" * 68)
        safe_print(f"🏆 ดีที่สุด: {best['name']} (macro-F1={best['macro_f1']:.3f})")
        safe_print(f"   ดีขึ้นจากระบบเดิม {gain * 100:.0f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["sentiment", "category"], required=True)
    ap.add_argument("--per-class", type=int, default=100)
    a = ap.parse_args()
    asyncio.run(main(a.task, a.per_class))
