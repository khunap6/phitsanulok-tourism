"""
fix_dirty_keywords.py — ล้างหมวด pain point ของรีวิวที่ให้ดาวอย่างเดียว

ปัญหาที่แก้ (วัดเมื่อ 2026-09-26):
  nlp/pipeline.py เคยดึง r.text (ข้อความดิบ) มาวิเคราะห์ ไม่ใช่ r.text_clean
  ข้อความดิบมีขยะปน: ชื่อคนรีวิว, "Local Guide · 536 รีวิว · 2,957 รูปภาพ",
  วันที่สัมพัทธ์, ปุ่ม "ชอบ"/"แชร์", "คำตอบจากเจ้าของ" และป้ายคะแนนย่อยของ Google
  ("อาหาร: 5  บริการ: 5  บรรยากาศ: 5")

  ผลคือ **รีวิวที่ให้ดาวอย่างเดียว ไม่ได้เขียนข้อความเลย** ถูกติดป้าย pain point
  จากคำในป้าย UI — เช่น "บริการ: 1" ทำให้ถูกจัดเป็นปัญหาเรื่องการบริการ

  ตัวอย่างจริง:
    review_id=126307  ดาว 1  ป้าย "การบริการและเจ้าหน้าที่"  sentiment=positive
      ข้อความดิบ: '\\ue838...2 สัปดาห์ที่แล้ว\\nใหม่\\nบริการ: 1\\nชอบ\\nแชร์'
      text_clean: '' (ว่าง — ผู้รีวิวไม่ได้เขียนอะไร)

⚠️ สคริปต์นี้แก้ **เฉพาะรีวิวที่ text_clean ว่าง** เท่านั้น (3,494 แถว)
   ตั้ง pain_point_category / pain_point_thai = NULL และ keywords = '{}'
   เพราะไม่มีข้อความก็ไม่มีทางรู้ว่าผู้รีวิวติเรื่องอะไร

   **ไม่แตะแถวที่ติดป้าย 'ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)'** (15,128 แถว)
   เพราะป้ายนั้นถูกต้องอยู่แล้วสำหรับรีวิวที่ไม่ได้ระบุปัญหา

⚠️ ไม่แตะ sentiment / severity — มาจากดาวซึ่งเป็นข้อมูลจริงที่ผู้รีวิวให้มา
⚠️ ไม่แตะ claude_* — เก็บไว้เทียบในวิทยานิพนธ์

── ส่วนของรีวิวที่ "มีข้อความ" ต้องใช้สคริปต์อื่น ──

รีวิว 53,475 อันที่มีข้อความก็ถูกวิเคราะห์จากข้อความสกปรกเหมือนกัน (keywords 32%
มีคำ "ชอบ" · 29% มีคำ "แชร์" · 49% มีคำ "ปี" ทั้งที่ไม่มีใน text_clean)

**ห้ามแก้ด้วย rule_based_categorize** — หมวดที่มีอยู่มาจาก WangchanBERTa
การคำนวณใหม่ด้วยตัวจับคำคือการแทนที่ผลของโมเดลที่ฝึกแล้วด้วยตัวที่อ่อนกว่า
ทดลองแล้วได้ผลแย่ลงชัดเจน เช่น
  'ตึกสีส้มเด่นตรงถนนคนเดิน มีทั้งเครื่องดื่มและขนม'
    WangchanBERTa -> ความคิดเห็นทั่วไป (ถูก)
    rule-based    -> การเดินทางและที่จอดรถ (ผิด — จับคำว่า "ถนน")

ใช้ scripts/reanalyze_all.py --apply แทน — มันใช้ text_clean + WangchanBERTa
ตัวเดียวกันอยู่แล้ว จึงแก้ keywords + category + pain_point_thai + sentiment
ได้พร้อมกันโดยไม่เปลี่ยนโมเดล

รัน:
  uv run python scripts/fix_dirty_keywords.py           # DRY-RUN
  uv run python scripts/fix_dirty_keywords.py --apply   # แก้จริง
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal

# ป้ายที่ถูกต้องสำหรับรีวิวที่ไม่ได้ระบุปัญหา — ห้ามล้าง
GENERAL_CATEGORY = "ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)"


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


# เงื่อนไข: ไม่มีข้อความ แต่ถูกติดป้ายหมวด "เฉพาะ" (ไม่ใช่ทั่วไป ไม่ใช่ NULL)
_WHERE = f"""
    COALESCE(r.text_clean, '') = ''
    AND a.pain_point_category IS NOT NULL
    AND a.pain_point_category <> '{GENERAL_CATEGORY}'
"""


async def run(apply: bool) -> None:
    async with AsyncSessionLocal() as s:
        p("=" * 78)
        p(f"  {'ทำจริง' if apply else 'DRY-RUN'} — ล้างหมวดของรีวิวที่ให้ดาวอย่างเดียว")
        p("=" * 78)

        rows = (await s.execute(text(f"""
            SELECT a.pain_point_category AS cat, count(*) AS n
            FROM analyzed_reviews a JOIN reviews r ON r.id = a.review_id
            WHERE {_WHERE}
            GROUP BY 1 ORDER BY 2 DESC
        """))).fetchall()
        total = sum(x.n for x in rows)

        keep = (await s.execute(text(f"""
            SELECT count(*) FROM analyzed_reviews a JOIN reviews r ON r.id = a.review_id
            WHERE COALESCE(r.text_clean, '') = ''
              AND a.pain_point_category = '{GENERAL_CATEGORY}'
        """))).scalar()

        if not total:
            p("\n  ✅ ไม่มีแถวที่ต้องแก้")
            p("=" * 78)
            return

        p(f"\n  รีวิวดาวเปล่าที่ถูกติดป้ายหมวดเฉพาะ: {total:,} แถว")
        for x in rows:
            p(f"    {x.cat[:46]:<48}{x.n:>7,}")
        p(f"\n  ไม่แตะ: ติดป้าย '{GENERAL_CATEGORY}' {keep:,} แถว (ถูกต้องอยู่แล้ว)")

        ex = (await s.execute(text(f"""
            SELECT a.review_id AS rid, r.rating, a.pain_point_category AS cat,
                   a.sentiment, a.keywords AS kw, left(COALESCE(r.text, ''), 64) AS raw
            FROM analyzed_reviews a JOIN reviews r ON r.id = a.review_id
            WHERE {_WHERE} ORDER BY a.review_id DESC LIMIT 3
        """))).fetchall()
        p(f"\n  ตัวอย่าง 3 แถว:")
        for x in ex:
            p(f"    review_id={x.rid}  ดาว={x.rating}  [{x.sentiment}]  {x.cat}")
            p(f"      ข้อความดิบ : {x.raw!r}")
            p(f"      text_clean : '' (ว่าง)")
            p(f"      keywords   : {list(x.kw or [])[:8]}")

        if not apply:
            p(f"\n  ยังไม่แก้อะไร — เติม --apply เพื่อทำจริง")
            p(f"\n  สิ่งที่จะทำกับ {total:,} แถว:")
            p(f"    pain_point_category -> NULL")
            p(f"    pain_point_thai     -> NULL")
            p(f"    keywords            -> {{}}")
            p(f"    ไม่แตะ sentiment · severity · claude_*")
            p(f"\n  ⚠️ รีวิว 53,475 อันที่มีข้อความยังต้องวิเคราะห์ใหม่แยก:")
            p(f"     uv run python scripts/reanalyze_all.py --apply")
            p("=" * 78)
            return

        res = await s.execute(text(f"""
            UPDATE analyzed_reviews a SET
                pain_point_category = NULL,
                pain_point_thai     = NULL,
                keywords            = '{{}}'
            FROM reviews r
            WHERE r.id = a.review_id AND {_WHERE}
        """))
        await s.commit()
        p(f"\n  ✅ แก้แล้ว {res.rowcount:,} แถว")

        left = (await s.execute(text(f"""
            SELECT count(*) FROM analyzed_reviews a JOIN reviews r ON r.id = a.review_id
            WHERE {_WHERE}
        """))).scalar()
        still = (await s.execute(text(f"""
            SELECT count(*) FROM analyzed_reviews a JOIN reviews r ON r.id = a.review_id
            WHERE COALESCE(r.text_clean, '') = ''
              AND a.pain_point_category = '{GENERAL_CATEGORY}'
        """))).scalar()
        p(f"  ตรวจผล — เหลือแถวที่ผิด {left} | ป้าย 'ทั่วไป' ที่ไม่แตะ {still:,} (เท่าเดิม)")
        p(f"\n  ขั้นต่อไป — รีวิวที่มีข้อความ 53,475 อัน:")
        p(f"    uv run python scripts/reanalyze_all.py            # ดูก่อน")
        p(f"    uv run python scripts/reanalyze_all.py --apply    # วิเคราะห์ใหม่จาก text_clean")
        p("=" * 78)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="ล้างหมวด pain point ของรีวิวที่ให้ดาวอย่างเดียว")
    ap.add_argument("--apply", action="store_true", help="แก้จริง (ไม่ใส่ = DRY-RUN)")
    asyncio.run(run(ap.parse_args().apply))
