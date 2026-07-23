"""
classify_other_llm.py — จัดหมวด pain point ของรีวิว "อื่นๆ" ใหม่ ด้วย Claude Haiku 4.5

- อ่านรีวิวที่ pain_point_category = 'อื่นๆ' และมีเนื้อความ (text_clean)
- ส่งเป็น batch ทีละ 20 อัน ให้ Claude จัดหมวด
- อัพเดต pain_point_category + model_used ใน DB
- resume ได้ (รันซ้ำจะทำเฉพาะที่ยังเป็น 'อื่นๆ')

ต้องตั้ง ANTHROPIC_API_KEY ใน .env ก่อน

รัน: uv run python scripts/classify_other_llm.py --limit 40   # ทดสอบ 40 อันก่อน
     uv run python scripts/classify_other_llm.py              # ทำทั้งหมด
"""
import argparse
import asyncio
import json
import os

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from db.database import AsyncSessionLocal

BATCH_SIZE = 20
MODEL = "claude-haiku-4-5"

# หมวดหมู่ทั้งหมด (เดิม 10 + ใหม่ 3) — Claude ต้องเลือก 1 หมวดต่อรีวิว
CATEGORIES = [
    "การเดินทางและที่จอดรถ",
    "ความสะอาดและสิ่งแวดล้อม",
    "ราคาและความคุ้มค่า",
    "การบริการและเจ้าหน้าที่",
    "ความปลอดภัย",
    "สิ่งอำนวยความสะดวก",
    "ข้อมูลและป้ายบอกทาง",
    "ความแออัดและการจัดการ",
    "พ่อค้าแม่ค้าและการรบกวน",
    "รสชาติและคุณภาพอาหาร/เครื่องดื่ม",   # ใหม่
    "บรรยากาศและการตกแต่งร้าน",           # ใหม่
    "ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)",     # ใหม่ — สำหรับรีวิวที่ไม่ใช่คำบ่น
]

SYSTEM_PROMPT = f"""คุณเป็นผู้เชี่ยวชาญวิเคราะห์รีวิวสถานที่ท่องเที่ยว/ร้านค้าในจังหวัดพิษณุโลก

หน้าที่: จัดหมวดหมู่ "ปัญหาหลัก (pain point)" ของแต่ละรีวิว โดยเลือกเพียง 1 หมวดจากรายการนี้:
{chr(10).join(f'- {c}' for c in CATEGORIES)}

หลักการ:
- เลือกหมวดที่ตรงกับ "ปัญหาหลัก" ที่รีวิวพูดถึงมากที่สุด
- ถ้ารีวิวเป็นการชม/ให้ข้อมูลทั่วไป/ไม่มีคำบ่นชัดเจน → เลือก "ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)"
- รีวิวเรื่องรสชาติ ความสด คุณภาพอาหาร/กาแฟ/เครื่องดื่ม → "รสชาติและคุณภาพอาหาร/เครื่องดื่ม"
- รีวิวเรื่องการตกแต่ง มุมถ่ายรูป ความร้อน/เย็น เสียงดัง บรรยากาศในร้าน → "บรรยากาศและการตกแต่งร้าน"

ตอบเป็น JSON array เท่านั้น รูปแบบ:
[{{"id": <review_id>, "category": "<ชื่อหมวด>"}}, ...]
ห้ามมีข้อความอื่นนอกจาก JSON"""


def safe_print(text_val: str) -> None:
    try:
        print(text_val)
    except UnicodeEncodeError:
        print(text_val.encode("ascii", errors="replace").decode("ascii"))


async def load_batch(session, limit_remaining):
    n = min(BATCH_SIZE, limit_remaining) if limit_remaining else BATCH_SIZE
    result = await session.execute(
        text("""
            SELECT ar.review_id, r.text_clean
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            WHERE ar.pain_point_category = 'อื่นๆ'
              AND r.text_clean <> ''
            ORDER BY ar.review_id
            LIMIT :n
        """),
        {"n": n},
    )
    return [{"id": row.review_id, "text": row.text_clean} for row in result.fetchall()]


def classify_batch(client, reviews: list[dict]) -> dict[int, str]:
    """ส่ง batch ให้ Claude คืน {review_id: category}"""
    reviews_text = "\n".join(
        f'{{"id": {r["id"]}, "text": "{r["text"][:300].replace(chr(34), "")}"}}'
        for r in reviews
    )
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},  # cache หมวดหมู่ ลดค่าใช้จ่าย
        }],
        messages=[{
            "role": "user",
            "content": f"จัดหมวดรีวิวต่อไปนี้:\n{reviews_text}",
        }],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    data = json.loads(raw.strip())
    valid = set(CATEGORIES)
    out = {}
    for item in data:
        cat = item.get("category", "").strip()
        if cat in valid:
            out[int(item["id"])] = cat
    return out


async def main(limit: int | None = None):
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your_anthropic_key_here":
        print("❌ ยังไม่ได้ตั้ง ANTHROPIC_API_KEY ใน .env")
        print("   เอา key จาก https://console.anthropic.com → Settings → API Keys")
        return

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    async with AsyncSessionLocal() as session:
        # นับงานทั้งหมด
        total_q = await session.execute(
            text("""SELECT COUNT(*) FROM analyzed_reviews ar
                    JOIN reviews r ON r.id = ar.review_id
                    WHERE ar.pain_point_category = 'อื่นๆ' AND r.text_clean <> ''""")
        )
        total = total_q.scalar()
        target = min(total, limit) if limit else total
        print(f"รีวิว 'อื่นๆ' ที่มีเนื้อความ: {total} | จะจัดหมวด: {target}\n")

        done = 0
        cat_counts: dict[str, int] = {}
        while done < target:
            remaining = target - done
            batch = await load_batch(session, remaining)
            if not batch:
                break

            try:
                results = classify_batch(client, batch)
            except Exception as e:
                print(f"  ⚠️  batch ล้มเหลว: {e} — ข้าม")
                # กันวนไม่รู้จบ: ทำ id พวกนี้เป็น marker ชั่วคราวไม่ได้
                # จึงหยุดเพื่อให้ผู้ใช้ตรวจสอบ
                break

            for rid, cat in results.items():
                await session.execute(
                    text("""UPDATE analyzed_reviews
                            SET pain_point_category = :cat, model_used = :model
                            WHERE review_id = :rid"""),
                    {"cat": cat, "model": MODEL, "rid": rid},
                )
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
            await session.commit()

            done += len(batch)
            safe_print(f"  [{done}/{target}] จัดแล้ว (batch นี้ {len(results)}/{len(batch)})")

        print(f"\n✅ เสร็จ — จัดหมวดใหม่ {done} รีวิว")
        print("\n📊 หมวดที่ได้:")
        for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
            safe_print(f"  {cat:<40} {cnt}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="จำกัดจำนวน (ทดสอบ)")
    args = parser.parse_args()
    asyncio.run(main(args.limit))
