"""
eval_sentiment_model.py — ทดสอบโมเดล sentiment ภาษาไทยกับข้อมูลจริงของเรา

ทำไมต้องทดสอบก่อนใช้:
  ข้อมูลที่ Claude ติดป้ายไว้ไม่สมดุล (บวก 89% / ลบ 4%)
  ถ้าเอาไป fine-tune ตรงๆ จะได้โมเดลที่ทายว่า "บวก" ตลอดแล้วดูเหมือนแม่น 89%
  → ต้องวัดด้วย F1 ของแต่ละคลาส ไม่ใช่ accuracy รวม

รัน:
  uv run python nlp/train/eval_sentiment_model.py
  uv run python nlp/train/eval_sentiment_model.py --model poom-sci/WangchanBERTa-finetuned-sentiment
"""
import argparse
import asyncio
import os

from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from sqlalchemy import text

from db.database import AsyncSessionLocal

DEFAULT_MODEL = "poom-sci/WangchanBERTa-finetuned-sentiment"

# label ของโมเดล → label มาตรฐานของเรา
LABEL_MAP = {
    "pos": "positive", "neg": "negative", "neu": "neutral", "q": "neutral",
    "POSITIVE": "positive", "NEGATIVE": "negative", "NEUTRAL": "neutral",
    "LABEL_0": "positive", "LABEL_1": "neutral", "LABEL_2": "negative",
}


def safe_print(t: str) -> None:
    try:
        print(t)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"))


async def load_samples(limit: int) -> list[tuple[str, str]]:
    """
    ดึงตัวอย่างแบบ "สมดุล" — เอาแต่ละคลาสเท่าๆ กัน
    ไม่งั้นจะวัดไม่ออกว่าโมเดลจับ negative ได้จริงไหม
    """
    per_class = max(1, limit // 3)
    out: list[tuple[str, str]] = []
    async with AsyncSessionLocal() as s:
        for label in ("positive", "neutral", "negative"):
            r = await s.execute(
                text("""
                    SELECT rv.text_clean AS review_text
                    FROM analyzed_reviews ar JOIN reviews rv ON rv.id = ar.review_id
                    WHERE ar.model_used LIKE 'claude%'
                      AND ar.sentiment = :lab
                      AND rv.text_clean <> ''
                      AND LENGTH(rv.text_clean) BETWEEN 15 AND 300
                    ORDER BY random() LIMIT :n
                """),
                {"lab": label, "n": per_class},
            )
            out += [(x.review_text, label) for x in r.fetchall()]
    return out


def evaluate(model_name: str, samples: list[tuple[str, str]]) -> None:
    from transformers import pipeline
    from sklearn.metrics import classification_report, confusion_matrix

    safe_print(f"กำลังโหลดโมเดล: {model_name}")
    clf = pipeline("text-classification", model=model_name, truncation=True, max_length=256)
    safe_print("  โหลดสำเร็จ\n")

    texts = [t for t, _ in samples]
    gold = [g for _, g in samples]

    raw = clf(texts, batch_size=16)
    pred = [LABEL_MAP.get(r["label"], "neutral") for r in raw]

    labels = ["negative", "neutral", "positive"]
    safe_print("=" * 62)
    safe_print(f"ผลทดสอบ — {len(samples)} รีวิว (ใช้ผล Claude เป็นเฉลย)")
    safe_print("=" * 62)
    safe_print(classification_report(gold, pred, labels=labels, zero_division=0, digits=3))

    safe_print("Confusion matrix (แถว=เฉลยจริง, คอลัมน์=โมเดลทาย)")
    cm = confusion_matrix(gold, pred, labels=labels)
    safe_print(f"{'':10} " + " ".join(f"{l[:8]:>9}" for l in labels))
    for i, l in enumerate(labels):
        safe_print(f"{l:10} " + " ".join(f"{v:>9}" for v in cm[i]))

    # ตัวชี้วัดที่สำคัญที่สุดสำหรับงานเรา: จับคำบ่นได้ไหม
    neg_i = labels.index("negative")
    tp = cm[neg_i][neg_i]
    total_neg = cm[neg_i].sum()
    safe_print(f"\n🎯 จับ 'คำบ่น' ได้ {tp}/{total_neg} = {tp / max(total_neg, 1) * 100:.0f}%"
               "   ← ตัวชี้วัดสำคัญสุด (ระบบเราเน้นหา pain point)")


async def main(model: str, limit: int) -> None:
    samples = await load_samples(limit)
    safe_print(f"ดึงตัวอย่างมา {len(samples)} รีวิว (สมดุลทุกคลาส)\n")
    evaluate(model, samples)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--limit", type=int, default=900)
    a = ap.parse_args()
    asyncio.run(main(a.model, a.limit))
