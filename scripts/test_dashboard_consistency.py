"""test_dashboard_consistency.py — ทดสอบหัวข้อ 3.5.2 ความถูกต้องของตัวเลขบนแดชบอร์ด

เทียบ "ค่าที่หน้าเว็บได้รับจาก API" กับ "ค่าที่นับจากฐานข้อมูลโดยตรง"
ทั้งสองฝั่งใช้ตัวกรองชุดเดียวกัน คือ เปิดกิจการ + อยู่ในขอบเขตการศึกษา (กฎข้อ 1)

⚠️ ฝั่งฐานข้อมูลเขียน SQL ขึ้นใหม่จากนิยามในแบบจำลองข้อมูล ไม่ได้คัดลอก SQL
  ของ endpoint มาใช้ ถ้าคัดลอกมาก็เท่ากับเอา endpoint มาเทียบกับตัวเอง
  ซึ่งผ่านเสมอและไม่ได้ทดสอบอะไรเลย

เกณฑ์ผ่าน ผลต่างเท่ากับ 0 ทุกรายการ และลำดับหมวดตรงกันทุกอันดับ

ต้องเปิด API ที่ localhost:8000 ไว้ก่อน

รัน:
  uv run python scripts/test_dashboard_consistency.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from api.filters import NON_PROBLEM_CATEGORY_IDS, scope_filter, status_filter  # noqa: E402
from db.database import AsyncSessionLocal  # noqa: E402

API = "http://localhost:8000/api"
FILT = f"{status_filter('operational')} {scope_filter()}"
NONPROB = ", ".join(str(i) for i in NON_PROBLEM_CATEGORY_IDS) or "-1"


async def db_scalars() -> dict:
    """นับจากฐานข้อมูลโดยตรง ด้วย SQL ที่เขียนขึ้นใหม่"""
    q = {
        # จำนวนสถานที่ที่เข้าเกณฑ์
        "total_places": f"""
            SELECT COUNT(*) FROM places p WHERE TRUE {FILT}
        """,
        # รีวิวทั้งหมดของสถานที่เหล่านั้น
        "total_reviews": f"""
            SELECT COUNT(*) FROM reviews r JOIN places p ON p.id = r.place_id
            WHERE TRUE {FILT}
        """,
        # รีวิวที่ผ่านการวิเคราะห์แล้ว
        "total_analyzed": f"""
            SELECT COUNT(*) FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places  p ON p.id = r.place_id
            WHERE TRUE {FILT}
        """,
        # รีวิวที่มีข้อความให้วิเคราะห์
        "with_text": f"""
            SELECT COUNT(*) FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places  p ON p.id = r.place_id
            WHERE r.text_clean <> '' {FILT}
        """,
        # จำนวนการกล่าวถึง (1 แถว = 1 หมวดของ 1 รีวิว)
        "aspect_mentions": f"""
            SELECT COUNT(*) FROM review_aspects ra
            JOIN reviews r ON r.id = ra.review_id
            JOIN places  p ON p.id = r.place_id
            WHERE r.text_clean <> '' {FILT}
        """,
        # รีวิวที่อารมณ์รวมเป็นลบ (ตัวตั้งของอัตราการบ่น)
        "negative_reviews": f"""
            SELECT COUNT(*) FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places  p ON p.id = r.place_id
            WHERE r.text_clean <> '' AND ar.overall_sentiment = 'negative' {FILT}
        """,
    }
    out = {}
    async with AsyncSessionLocal() as db:
        for k, sql in q.items():
            out[k] = (await db.execute(text(sql))).scalar_one()
    return out


async def db_ranking() -> list[tuple[str, int]]:
    """ลำดับหมวดที่ถูกติมากสุด หน่วย 'รีวิว' (หมวดหลักเท่านั้น)"""
    sql = f"""
        SELECT c.name AS name, COUNT(*) AS n
        FROM analyzed_reviews ar
        JOIN reviews r    ON r.id = ar.review_id
        JOIN places  p    ON p.id = r.place_id
        JOIN categories c ON c.id = ar.primary_category_id
        WHERE r.text_clean <> ''
          AND ar.overall_sentiment = 'negative'
          AND ar.primary_category_id NOT IN ({NONPROB})
          {FILT}
        GROUP BY c.name
        ORDER BY n DESC, c.name
    """
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text(sql))).fetchall()
    return [(r.name, r.n) for r in rows]


async def main() -> int:
    async with httpx.AsyncClient(timeout=60) as cx:
        summary = (await cx.get(f"{API}/insights/summary")).json()
        overview = (await cx.get(f"{API}/aspects/overview")).json()

    dbv = await db_scalars()
    dbrank = await db_ranking()

    # ── ค่าที่หน้าเว็บได้รับ ──
    api_vals = {
        "total_places": summary.get("total_places"),
        "total_reviews": summary.get("total_reviews"),
        "total_analyzed": summary.get("total_analyzed"),
        "with_text": overview.get("total_reviews"),
        "aspect_mentions": overview.get("total_mentions"),
        "negative_reviews": overview.get("reviews_negative"),
    }

    label = {
        "total_places": "จำนวนสถานที่",
        "total_reviews": "จำนวนรีวิวทั้งหมด",
        "total_analyzed": "จำนวนรีวิวที่วิเคราะห์แล้ว",
        "with_text": "จำนวนรีวิวที่มีข้อความ",
        "aspect_mentions": "จำนวนการกล่าวถึง",
        "negative_reviews": "จำนวนรีวิวเชิงลบ",
    }

    print("ตารางที่ 4.x ผลการทดสอบความถูกต้องของตัวเลขบนแดชบอร์ด")
    print(f"ตัวกรอง: เปิดกิจการ + อยู่ในขอบเขตการศึกษา")
    print()
    print(f"{'รายการ':<28}{'หน้าเว็บ':>12}{'ฐานข้อมูล':>12}{'ผลต่าง':>9}  ผล")
    fails = 0
    for k, lab in label.items():
        a, d = api_vals.get(k), dbv.get(k)
        if a is None:
            print(f"{lab:<28}{'(ไม่พบคีย์)':>12}{d:>12,}{'-':>9}  ตรวจไม่ได้")
            fails += 1
            continue
        diff = a - d
        ok = diff == 0
        fails += 0 if ok else 1
        print(f"{lab:<28}{a:>12,}{d:>12,}{diff:>9,}  {'ผ่าน' if ok else 'ไม่ผ่าน'}")

    # ── ลำดับหมวด ──
    apirank = [(c["category"], c["count"]) for c in summary.get("top_pain_point_categories", [])]
    n = min(len(apirank), len(dbrank))
    print()
    print("ลำดับหมวดที่ถูกติมากที่สุด (หน่วย: รีวิว)")
    print(f"{'อันดับ':<8}{'หมวด (หน้าเว็บ)':<42}{'หน้าเว็บ':>10}{'ฐานข้อมูล':>11}  ผล")
    rank_fail = 0
    for i in range(n):
        an, ac = apirank[i]
        dn, dc = dbrank[i]
        ok = (an == dn) and (ac == dc)
        rank_fail += 0 if ok else 1
        print(f"{i + 1:<8}{an[:40]:<42}{ac:>10,}{dc:>11,}  {'ผ่าน' if ok else 'ไม่ผ่าน'}")
    if len(apirank) != len(dbrank):
        print(f"  (หน้าเว็บมี {len(apirank)} หมวด · ฐานข้อมูลมี {len(dbrank)} หมวด)")
        rank_fail += 1

    print()
    total_fail = fails + rank_fail
    if total_fail == 0:
        print("สรุป ผ่านทุกรายการ ผลต่างเท่ากับ 0 และลำดับหมวดตรงกันทุกอันดับ")
    else:
        print(f"สรุป ไม่ผ่าน {total_fail} รายการ")
    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
