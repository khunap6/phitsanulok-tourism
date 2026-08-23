"""
prepare_data.py — เตรียมชุดข้อมูลฝึกจากป้ายกำกับที่ Claude สร้างไว้

แนวคิด (Knowledge Distillation):
  Claude ติดป้ายรีวิวไว้แล้ว 9,125 รายการ → ใช้เป็น "ครู"
  เอาไปสอน WangchanBERTa ให้ทำงานเองได้ฟรีโดยไม่ต้องเรียก API อีก

รัน:
  uv run python nlp/train/prepare_data.py --task category
  uv run python nlp/train/prepare_data.py --task sentiment
"""
import argparse
import asyncio
import json
import random
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal

OUT_DIR = Path("data/training")

# หมวดที่ไม่ใช่ปัญหาจริง — รวมเข้า "อื่นๆ" ตอนฝึก
MERGE_INTO_OTHER = {"ไม่มี"}
# ต้องมีตัวอย่างอย่างน้อยเท่านี้ถึงจะเป็นคลาสของตัวเอง (น้อยกว่านี้โมเดลเรียนไม่ได้)
MIN_SAMPLES = 40


def safe_print(t: str) -> None:
    try:
        print(t)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"))


# ⚠️ แหล่งข้อมูลที่เชื่อถือได้ "ต่างกันตามงาน" — จุดนี้เคยพลาดมาแล้ว
#
# classify_other_llm.py อัปเดตเฉพาะ "หมวดหมู่" แต่ตั้ง model_used='claude-haiku-4-5'
# ทำให้ sentiment ของแถวเหล่านั้นยังเป็นค่าเดิมจากกฎดูดาว (ตรงกับดาว 99%)
# ถ้าเอาไปฝึกโมเดลอารมณ์ = สอนให้เลียนแบบกฎดูดาว ไม่ได้เรียนรู้ภาษา
TRUSTED_SOURCES = {
    # หมวดหมู่: Claude ติดป้ายจริงทุกแหล่ง
    "category": ["claude-haiku-4-5", "claude-haiku-4-5-20251001", "claude-haiku-4-5-full"],
    # อารมณ์: เฉพาะแหล่งที่ Claude อ่านเนื้อความจริงเท่านั้น
    "sentiment": ["claude-haiku-4-5-20251001", "claude-haiku-4-5-full"],
}


async def fetch(task: str) -> list[dict]:
    """ดึงเฉพาะรีวิวที่ป้ายกำกับ 'เชื่อถือได้สำหรับงานนั้น' (ดูคำอธิบาย TRUSTED_SOURCES)"""
    col = "ar.pain_point_category" if task == "category" else "ar.sentiment"
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            text(f"""
                SELECT rv.text_clean AS review_text, {col} AS label
                FROM analyzed_reviews ar
                JOIN reviews rv ON rv.id = ar.review_id
                WHERE ar.model_used = ANY(:sources)
                  AND rv.text_clean <> ''
                  AND LENGTH(rv.text_clean) >= 10
                  AND {col} IS NOT NULL
            """),
            {"sources": TRUSTED_SOURCES[task]},
        )
        return [{"text": x.review_text, "label": x.label} for x in r.fetchall()]


def clean_labels(rows: list[dict], task: str) -> tuple[list[dict], list[str]]:
    """รวมคลาสที่ตัวอย่างน้อยเกินไป + ตัดคลาสขยะ"""
    counts = Counter(r["label"] for r in rows)

    if task == "category":
        keep = {lab for lab, c in counts.items()
                if c >= MIN_SAMPLES and lab not in MERGE_INTO_OTHER}
        keep.add("อื่นๆ")
        for r in rows:
            if r["label"] not in keep:
                r["label"] = "อื่นๆ"
    else:
        # sentiment: เก็บแค่ 3 คลาสหลัก ('mixed' มีอันเดียว → รวมเป็น negative)
        for r in rows:
            if r["label"] == "mixed":
                r["label"] = "negative"
        rows = [r for r in rows if r["label"] in ("positive", "neutral", "negative")]

    labels = sorted({r["label"] for r in rows})
    return rows, labels


def split(rows: list[dict], seed: int = 42) -> dict[str, list[dict]]:
    """
    แบ่ง train/val/test แบบ stratified (แต่ละคลาสกระจายเท่ากันทุกชุด)
    ถ้าแบ่งมั่วๆ คลาสที่มีน้อยอาจไม่โผล่ในชุดทดสอบเลย → วัดผลไม่ได้
    """
    rng = random.Random(seed)
    by_label: dict[str, list[dict]] = {}
    for r in rows:
        by_label.setdefault(r["label"], []).append(r)

    out = {"train": [], "val": [], "test": []}
    for lab, items in by_label.items():
        rng.shuffle(items)
        n = len(items)
        n_test = max(1, int(n * 0.15))
        n_val = max(1, int(n * 0.15))
        out["test"] += items[:n_test]
        out["val"] += items[n_test:n_test + n_val]
        out["train"] += items[n_test + n_val:]

    for k in out:
        rng.shuffle(out[k])
    return out


async def main(task: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = await fetch(task)
    safe_print(f"ดึงข้อมูลที่ Claude ติดป้ายไว้: {len(rows):,} รีวิว")

    rows, labels = clean_labels(rows, task)
    counts = Counter(r["label"] for r in rows)

    safe_print(f"\nคลาสที่จะฝึก ({len(labels)} คลาส):")
    for lab in sorted(labels, key=lambda l: -counts[l]):
        bar = "#" * min(40, counts[lab] // 50 + 1)
        safe_print(f"  {counts[lab]:5,} | {lab[:38]:40} {bar}")

    parts = split(rows)
    safe_print(f"\nแบ่งชุดข้อมูล:")
    for k, v in parts.items():
        safe_print(f"  {k:6} {len(v):5,} รายการ")

    out = {
        "task": task,
        "labels": labels,
        "counts": dict(counts),
        **{k: v for k, v in parts.items()},
    }
    path = OUT_DIR / f"{task}_dataset.json"
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    safe_print(f"\n✅ บันทึกที่ {path} ({path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["category", "sentiment"], required=True)
    a = ap.parse_args()
    asyncio.run(main(a.task))
