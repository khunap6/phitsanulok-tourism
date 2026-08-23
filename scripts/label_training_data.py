"""
label_training_data.py — ให้ Claude ติดป้ายรีวิวเพิ่ม เพื่อแก้อคติในชุดข้อมูลฝึก

ปัญหาที่แก้:
  สคริปต์เดิม (classify_other_llm.py) ส่งให้ Claude เฉพาะรีวิวที่ตัวจับคำตอบ "อื่นๆ"
  → หมวดที่คำสำคัญจับได้ (จอดรถ/ราคา/บริการ) ไม่เคยถูกส่งไปเลย
  → Claude เห็นหมวด "การเดินทางและที่จอดรถ" แค่ 53 จาก 2,701 อัน (1%)
  → โมเดลที่ฝึกจากข้อมูลนี้จึงจับ pain point หลักไม่ได้

สคริปต์นี้สุ่มรีวิวจากหมวดที่ Claude ยังเห็นน้อย มาให้ติดป้ายเพิ่มแบบสมดุล

รัน:
  uv run python scripts/label_training_data.py                 # ดูก่อนว่าจะส่งกี่อัน ราคาเท่าไหร่ (ไม่ยิง API)
  uv run python scripts/label_training_data.py --limit 100     # ทดสอบ 100 อันก่อน
  uv run python scripts/label_training_data.py --apply         # ยิงจริงเต็มจำนวน
"""
import argparse
import asyncio
import json
import os
from collections import Counter

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal

BATCH_SIZE = 20
MODEL = "claude-haiku-4-5"
# ป้ายกำกับที่บันทึกลง model_used — ต้องแยกจาก 'claude-haiku-4-5' เดิม!
#
# ⚠️ บทเรียนสำคัญ: classify_other_llm.py เดิมอัปเดตแค่ "หมวดหมู่" แต่เปลี่ยน
# model_used เป็น 'claude-haiku-4-5' ทำให้ดูเหมือน Claude วิเคราะห์ทั้งหมด
# ทั้งที่ sentiment ยังเป็นค่าเดิมจากกฎดูดาว → พอเอาไปฝึกโมเดล
# โมเดลเลยเรียนรู้แค่การเลียนแบบกฎดูดาว และการวัดผลกลายเป็นวัดกฎกับตัวเอง
#
# ป้ายนี้บอกชัดว่า "Claude อ่านเนื้อความและให้ทั้งหมวดหมู่+อารมณ์"
MODEL_TAG = "claude-haiku-4-5-full"
# จำนวนตัวอย่างเป้าหมายต่อหมวด (พอสำหรับให้โมเดลเรียนรู้)
TARGET_PER_CATEGORY = 500
# ราคาโดยประมาณ อ้างอิงจากที่เคยรันจริง (~$1 ต่อ 4,500 รีวิว)
COST_PER_REVIEW = 1.0 / 4500

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
    "รสชาติและคุณภาพอาหาร/เครื่องดื่ม",
    "บรรยากาศและการตกแต่งร้าน",
    "ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)",
]

SYSTEM_PROMPT = f"""คุณเป็นผู้เชี่ยวชาญวิเคราะห์รีวิวสถานที่ท่องเที่ยว/ร้านค้าในจังหวัดพิษณุโลก

หน้าที่: วิเคราะห์แต่ละรีวิว 2 อย่าง
1) หมวดหมู่หลักที่รีวิวพูดถึง — เลือก 1 หมวดจาก:
{chr(10).join(f'- {c}' for c in CATEGORIES)}

2) ความรู้สึกของผู้รีวิว — เลือก 1 จาก: positive / neutral / negative
   - negative = มีการบ่น ตำหนิ หรือไม่พอใจ (แม้จะให้ดาวสูงก็ตาม)
   - positive = ชื่นชม พอใจ
   - neutral  = เล่าข้อมูลเฉยๆ ไม่ชมไม่บ่น

หลักการ:
- เลือกหมวดที่ตรงกับสิ่งที่รีวิว "พูดถึงมากที่สุด"
- ถ้าเป็นการชม/ให้ข้อมูลทั่วไป/ไม่มีประเด็นชัดเจน → "ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)"
- รีวิวเรื่องรสชาติ ความสด คุณภาพอาหาร/เครื่องดื่ม → "รสชาติและคุณภาพอาหาร/เครื่องดื่ม"
- รีวิวเรื่องการตกแต่ง มุมถ่ายรูป อุณหภูมิ เสียง บรรยากาศ → "บรรยากาศและการตกแต่งร้าน"

ตอบเป็น JSON array เท่านั้น:
[{{"id": <review_id>, "category": "<ชื่อหมวด>", "sentiment": "<positive|neutral|negative>"}}, ...]
ห้ามมีข้อความอื่นนอกจาก JSON"""


def safe_print(t: str) -> None:
    try:
        print(t, flush=True)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"), flush=True)


async def pick_targets(session, limit: int | None) -> list[dict]:
    """
    เลือกรีวิวที่ควรให้ Claude ติดป้าย — เน้นหมวดที่ Claude ยังเห็นน้อย
    เลือกจากรีวิวที่ตอนนี้ติดป้ายโดย rule-based (ซึ่งเชื่อถือไม่ได้)
    """
    # นับว่าแต่ละหมวด Claude เห็นไปแล้วกี่อัน
    r = await session.execute(
        text("""
            SELECT ar.pain_point_category AS cat, COUNT(*) AS n
            FROM analyzed_reviews ar JOIN reviews rv ON rv.id = ar.review_id
            WHERE ar.model_used LIKE 'claude%' AND rv.text_clean <> ''
            GROUP BY 1
        """)
    )
    seen = {x.cat: x.n for x in r.fetchall()}

    picks: list[dict] = []
    for cat in CATEGORIES:
        need = max(0, TARGET_PER_CATEGORY - seen.get(cat, 0))
        if need == 0:
            continue
        r = await session.execute(
            text("""
                SELECT rv.id, rv.text_clean AS review_text, rv.rating
                FROM analyzed_reviews ar JOIN reviews rv ON rv.id = ar.review_id
                WHERE ar.model_used = 'rule-based'
                  AND ar.pain_point_category = :cat
                  AND rv.text_clean <> ''
                  AND LENGTH(rv.text_clean) >= 15
                ORDER BY random() LIMIT :n
            """),
            {"cat": cat, "n": need},
        )
        rows = [{"id": x.id, "text": x.review_text, "rating": x.rating, "want": cat}
                for x in r.fetchall()]
        picks += rows

    if limit:
        picks = picks[:limit]
    return picks


def call_claude(client, batch: list[dict]) -> list[dict]:
    body = "\n".join(
        f"[id:{b['id']}] ★{b.get('rating', '?')} | {b['text'][:250]}" for b in batch
    )
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=[{"type": "text", "text": SYSTEM_PROMPT,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": body}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip()), msg.usage


async def main(apply: bool, limit: int | None) -> None:
    async with AsyncSessionLocal() as session:
        picks = await pick_targets(session, limit)

        by_cat = Counter(p["want"] for p in picks)
        safe_print("=" * 64)
        safe_print("รีวิวที่จะส่งให้ Claude ติดป้าย (เน้นหมวดที่ข้อมูลฝึกยังขาด)")
        safe_print("=" * 64)
        for cat, n in by_cat.most_common():
            safe_print(f"  {n:5,} | {cat}")
        safe_print(f"\n  รวม {len(picks):,} รีวิว")
        safe_print(f"  ประมาณการค่าใช้จ่าย: ~${len(picks) * COST_PER_REVIEW:.2f} "
                   f"(~{len(picks) * COST_PER_REVIEW * 35:.0f} บาท)")
        safe_print(f"  ใช้เครดิต: ANTHROPIC_API_KEY (บัญชี console.anthropic.com)")

        if not apply and not limit:
            safe_print("\n⚠️  โหมดดูอย่างเดียว — ยังไม่ยิง API")
            safe_print("   ทดสอบก่อน : uv run python scripts/label_training_data.py --limit 100")
            safe_print("   ยิงเต็ม   : uv run python scripts/label_training_data.py --apply")
            return

        if not os.getenv("ANTHROPIC_API_KEY"):
            safe_print("\n❌ ไม่พบ ANTHROPIC_API_KEY ใน .env")
            return

        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

        updated = failed = 0
        in_tok = out_tok = 0
        safe_print(f"\nเริ่มติดป้าย ({len(picks):,} รีวิว, ครั้งละ {BATCH_SIZE})...\n")

        for i in range(0, len(picks), BATCH_SIZE):
            batch = picks[i:i + BATCH_SIZE]
            try:
                results, usage = call_claude(client, batch)
                in_tok += usage.input_tokens
                out_tok += usage.output_tokens
            except Exception as e:
                safe_print(f"  ⚠️  batch {i // BATCH_SIZE + 1} ผิดพลาด: {str(e)[:80]}")
                failed += len(batch)
                continue

            valid = set(CATEGORIES)
            ids_in_batch = {b["id"] for b in batch}
            for item in results:
                if not isinstance(item, dict):
                    continue
                cat = item.get("category")
                sen = item.get("sentiment")
                # Claude บางครั้งส่ง id กลับมาเป็นข้อความ ("43760") แทนตัวเลข → ต้องแปลงก่อน
                try:
                    rid = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                # กันกรณี Claude สร้าง id มั่วที่ไม่ได้อยู่ใน batch นี้
                if rid not in ids_in_batch:
                    continue
                if cat not in valid or sen not in ("positive", "neutral", "negative"):
                    continue
                try:
                    await session.execute(
                        text("""
                            UPDATE analyzed_reviews
                            SET pain_point_category = :cat,
                                sentiment           = :sen,
                                model_used          = :model,
                                -- เก็บผลของ Claude ไว้เทียบกับโมเดลที่เราฝึกเอง (ไม่ถูกเขียนทับ)
                                claude_category     = :cat,
                                claude_sentiment    = :sen,
                                claude_source       = :model
                            WHERE review_id = :rid
                        """),
                        {"cat": cat, "sen": sen, "model": MODEL_TAG, "rid": rid},
                    )
                    updated += 1
                except Exception as e:
                    # แถวเดียวพังไม่ควรล้มทั้งงาน
                    await session.rollback()
                    failed += 1
                    safe_print(f"  ⚠️  บันทึก id={rid} ไม่ได้: {str(e)[:60]}")
                    continue
            await session.commit()

            done = min(i + BATCH_SIZE, len(picks))
            safe_print(f"  [{done:,}/{len(picks):,}] ติดป้ายแล้ว {updated:,} "
                       f"| token เข้า {in_tok:,} ออก {out_tok:,}")

        safe_print("\n" + "=" * 64)
        safe_print(f"✅ ติดป้ายสำเร็จ {updated:,} รีวิว | ล้มเหลว {failed:,}")
        safe_print(f"   token: เข้า {in_tok:,} / ออก {out_tok:,}")
        safe_print(f"   ค่าใช้จ่ายจริงดูได้ที่ console.anthropic.com → Usage")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="ยิง API จริง")
    ap.add_argument("--limit", type=int, default=None, help="จำกัดจำนวน (ทดสอบ)")
    a = ap.parse_args()
    asyncio.run(main(a.apply, a.limit))
