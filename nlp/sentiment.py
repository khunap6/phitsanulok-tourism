"""
sentiment.py — Sentiment analysis wrapper
Primary: WangchanBERTa (HuggingFace)
Fallback: Claude API (claude-haiku-4-5-20251001)
"""

import json
import os
from typing import Literal

SentimentLabel = Literal["positive", "negative", "neutral"]

# WangchanBERTa label → standard label
_WANGCHAN_LABEL_MAP: dict[str, SentimentLabel] = {
    "pos": "positive",
    "neg": "negative",
    "neu": "neutral",
    "q": "neutral",        # question label → treat as neutral
    "POSITIVE": "positive",
    "NEGATIVE": "negative",
    "NEUTRAL": "neutral",
    "LABEL_0": "negative",  # some fine-tuned variants
    "LABEL_1": "neutral",
    "LABEL_2": "positive",
}

_wangchan_pipeline = None
_wangchan_loaded = False


def _load_wangchan() -> bool:
    """Load WangchanBERTa pipeline once; returns True on success."""
    global _wangchan_pipeline, _wangchan_loaded
    if _wangchan_loaded:
        return _wangchan_pipeline is not None

    _wangchan_loaded = True
    try:
        from transformers import pipeline as hf_pipeline
        _wangchan_pipeline = hf_pipeline(
            "text-classification",
            model="airesearch/wangchanberta-base-att-spm-uncased",
            truncation=True,
            max_length=512,
        )
        print("[nlp] WangchanBERTa loaded")
        return True
    except Exception as e:
        print(f"[nlp] WangchanBERTa unavailable ({e}) — will use Claude fallback")
        return False


def _map_label(raw_label: str) -> SentimentLabel:
    return _WANGCHAN_LABEL_MAP.get(raw_label, "neutral")


def analyze_wangchan(texts: list[str]) -> list[SentimentLabel]:
    """
    Run WangchanBERTa on a list of texts.
    Returns a list of SentimentLabel; raises RuntimeError if model not loaded.
    """
    if not _load_wangchan() or _wangchan_pipeline is None:
        raise RuntimeError("WangchanBERTa not available")

    results = _wangchan_pipeline(texts)  # type: ignore[call-arg]
    return [_map_label(r["label"]) for r in results]


def analyze_claude(reviews: list[dict], place_name: str) -> list[dict]:
    """
    Analyze a batch (≤5) of reviews with Claude.
    Returns list of dicts with keys: sentiment, pain_point_category,
    pain_point_thai, severity, keywords.
    Falls back to empty list on error.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your_anthropic_key_here":
        return []

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
    except ImportError:
        return []

    reviews_text = "\n".join(
        f"[รีวิว {i+1}] ★{r.get('rating', '?')} | {r.get('text', '')[:200]}"
        for i, r in enumerate(reviews)
    )

    prompt = f"""คุณเป็นผู้เชี่ยวชาญด้านการวิเคราะห์รีวิวการท่องเที่ยวในประเทศไทย

สถานที่: {place_name}

รีวิวที่ต้องวิเคราะห์:
{reviews_text}

สำหรับรีวิวแต่ละอัน ตอบในรูปแบบ JSON array:
[
  {{
    "review_index": 1,
    "sentiment": "negative" หรือ "neutral" หรือ "positive",
    "pain_point_category": "หมวดหมู่หลัก 1 อัน",
    "pain_point_thai": "อธิบาย pain point สั้นๆ ภาษาไทย",
    "severity": "high" หรือ "medium" หรือ "low",
    "keywords": ["คำสำคัญ1", "คำสำคัญ2"]
  }}
]

หมวดหมู่ที่ใช้ได้: การเดินทางและที่จอดรถ, ความสะอาดและสิ่งแวดล้อม, ราคาและความคุ้มค่า, การบริการและเจ้าหน้าที่, ความปลอดภัย, สิ่งอำนวยความสะดวก, ข้อมูลและป้ายบอกทาง, ความแออัดและการจัดการ, พ่อค้าแม่ค้าและการรบกวน, อื่นๆ

ตอบเฉพาะ JSON array เท่านั้น"""

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        print(f"[nlp] Claude API error: {e}")
        return []
