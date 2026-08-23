"""
wangchan_classifier.py — ใช้โมเดล WangchanBERTa ที่ fine-tune เองแล้ว
(ทั้งจัดอารมณ์ + จัดหมวดหมู่ปัญหา) รันบน GPU ถ้ามี ไม่มีก็ CPU

ต่างจาก nlp/sentiment.py เดิม:
  - ตัวเดิมใช้โมเดล base ที่ไม่มีหัวจำแนก (พังเงียบมาตลอด)
  - ตัวนี้โหลดโมเดลจาก models/wangchanberta-* ที่เราฝึกเอง
  - มีการตรวจสอบว่าโมเดลมีหัวจำแนกจริง ไม่งั้นปฏิเสธการโหลด (กันบั๊กพังเงียบ)
"""
import os
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

MODEL_DIR = Path(__file__).parent.parent / "models"
SENTIMENT_MODEL = MODEL_DIR / "wangchanberta-sentiment"
CATEGORY_MODEL = MODEL_DIR / "wangchanberta-category"

_pipes: dict[str, object] = {}
_device = None


def _get_device() -> int:
    """คืน device id สำหรับ transformers pipeline (-1 = CPU, 0 = GPU ตัวแรก)"""
    global _device
    if _device is None:
        try:
            import torch
            _device = 0 if torch.cuda.is_available() else -1
        except Exception:
            _device = -1
    return _device


def _load(kind: str):
    """
    โหลด pipeline ครั้งเดียวแล้ว cache ไว้
    kind = 'sentiment' | 'category'
    คืน None ถ้าโหลดไม่ได้ (โมเดลไม่มี / ไม่มีหัวจำแนก) — ให้ผู้เรียกไป fallback
    """
    if kind in _pipes:
        return _pipes[kind]

    path = SENTIMENT_MODEL if kind == "sentiment" else CATEGORY_MODEL
    if not path.exists():
        print(f"[nlp] ไม่พบโมเดล {kind} ที่ {path} — ต้องฝึกก่อน (nlp/train/train.py)")
        _pipes[kind] = None
        return None

    try:
        from transformers import (AutoConfig, AutoModelForSequenceClassification,
                                   AutoTokenizer, pipeline)
        # ── ตรวจว่าเป็นโมเดลจำแนกจริง (มี id2label หลายคลาส) กันโหลดโมเดลผิดตัว ──
        cfg = AutoConfig.from_pretrained(str(path))
        if not getattr(cfg, "id2label", None) or len(cfg.id2label) < 2:
            print(f"[nlp] ⚠️  {kind}: โมเดลไม่มีหัวจำแนก (id2label) — ปฏิเสธการใช้งาน")
            _pipes[kind] = None
            return None

        tok = AutoTokenizer.from_pretrained(str(path))
        mdl = AutoModelForSequenceClassification.from_pretrained(str(path))
        clf = pipeline("text-classification", model=mdl, tokenizer=tok,
                       truncation=True, max_length=256, device=_get_device())
        dev = "GPU" if _get_device() == 0 else "CPU"
        print(f"[nlp] โหลดโมเดล {kind} สำเร็จ ({len(cfg.id2label)} คลาส, {dev})")
        _pipes[kind] = clf
        return clf
    except Exception as e:
        print(f"[nlp] โหลดโมเดล {kind} ไม่ได้: {str(e)[:100]}")
        _pipes[kind] = None
        return None


def is_available() -> bool:
    """โมเดลทั้งสองพร้อมใช้งานไหม"""
    return _load("sentiment") is not None and _load("category") is not None


def classify(texts: list[str]) -> list[dict] | None:
    """
    จัดทั้งอารมณ์ + หมวดหมู่ให้รายการข้อความ (batch เดียว)
    คืน [{"sentiment": ..., "category": ...}, ...] หรือ None ถ้าโมเดลไม่พร้อม
    """
    sen_clf = _load("sentiment")
    cat_clf = _load("category")
    if sen_clf is None or cat_clf is None:
        return None
    if not texts:
        return []

    sen = sen_clf(texts, batch_size=32)
    cat = cat_clf(texts, batch_size=32)
    return [
        {"sentiment": s["label"], "sentiment_score": s["score"],
         "category": c["label"], "category_score": c["score"]}
        for s, c in zip(sen, cat)
    ]
