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


def _category_list() -> str:
    """รายการหมวดสำหรับใส่ในพรอมป์ — อ่านจาก shared/category_labels.json

    ⚠️ ห้ามพิมพ์รายการหมวดลงในพรอมป์ตรง ๆ (เคยทำแล้วเพี้ยน)
      ลิสต์เดิมที่ฝังไว้มี 10 หมวด ต่างจากโมเดล 12 หมวดจริง —
      มี "พ่อค้าแม่ค้าและการรบกวน" ที่โมเดลไม่รู้จัก และขาด
      "รสชาติและคุณภาพอาหาร/เครื่องดื่ม" กับ "บรรยากาศและการตกแต่งร้าน"
      ซึ่งเป็นสองหมวดที่มีข้อมูลมากที่สุด
      ถ้าเส้นทางนี้เคยถูกใช้เขียนหมวดลง DB ข้อมูลจะปนหมวดที่หน้าเว็บไม่รู้จัก
      (ตรวจแล้วยังไม่เคยเกิด — 671 แถวจากเส้นทางนี้มี category เป็น NULL ทั้งหมด)
    """
    from api.filters import CATEGORY_KEYS
    return ", ".join(CATEGORY_KEYS)


def _category_rules() -> str:
    """กติกาเลือกหมวดเมื่อรีวิวพูดถึงหลายเรื่อง — จาก shared/category_labels.json

    ⚠️ พรอมป์เดิมให้แต่ลิสต์หมวด ไม่ได้บอกว่าถ้ารีวิวพูดถึงหลายเรื่องให้เลือกอันไหน
      เส้นทางนี้จึงอาจเลือกหมวดของ "สิ่งที่ชม" แทน "สิ่งที่ถูกติ" ซึ่งตรงข้าม
      กับที่โมเดลหลักทำ (วัดแล้ว: "อาหารอร่อยแต่ที่จอดรถน้อย" -> ที่จอดรถ 95.6%)
      แล้วสถิติหมวดจะปนกันสองกติกา
    """
    from api.filters import category_guideline_text
    return category_guideline_text()


def _sentiment_guide() -> str:
    """นิยามอารมณ์สำหรับใส่ในพรอมป์ — อ่านจาก shared/sentiment_labels.json

    ⚠️ ด้วยเหตุผลเดียวกับ _category_list() ข้างบน
      พรอมป์เดิมบอกแค่ว่าตอบได้ 3 ค่า แต่ไม่ได้นิยามว่าแต่ละค่าหมายถึงอะไร
      การตีความจึงเลื่อนได้ตามรอบที่รัน และเวลาเอาคนมาประเมินเทียบ
      ถ้าคนใช้กติกาคนละชุดกับที่โมเดลใช้ ค่า kappa จะต่ำเพราะกติกาไม่ตรงกัน
      ไม่ใช่เพราะโมเดลแย่ แล้วจะสรุปผลงานวิจัยผิด
      ไฟล์เดียวกันนี้เป็นคู่มือให้คนติดป้ายและเป็นนิยามที่อ้างในเล่ม
    """
    from api.filters import sentiment_guideline_text
    return sentiment_guideline_text()


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

นิยามของ sentiment ที่ต้องใช้ตัดสิน (ห้ามใช้เกณฑ์อื่น):
{_sentiment_guide()}

หมวดหมู่ที่ใช้ได้: {_category_list()}

กติกาเลือกหมวด (รีวิวหนึ่งได้หมวดเดียว):
{_category_rules()}

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
