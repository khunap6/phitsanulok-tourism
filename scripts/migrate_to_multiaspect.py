"""migrate_to_multiaspect.py — Phase 3: ย้ายข้อมูลเดิมเข้าโครงสร้างใหม่

ทำ 3 ส่วนตามลำดับ (ลำดับสำคัญ ส่วนหลังทับส่วนหน้า)

  A. ย้ายผลของโมเดลเดิมทั้งหมด                    label_source = 'model'
     overall_sentiment = sentiment เดิม (ค่าเดียวกัน ไม่ได้คำนวณใหม่)
     primary_category_id = map ชื่อหมวดเดิม -> id หมวดใหม่ (map ด้วยชื่อเท่านั้น)
     review_aspects 1 แถว/รีวิว (is_primary = true) ให้โค้ดใหม่อ่านได้ทันที

  B. ทับด้วยป้ายชุด gold 300 รีวิว                 label_source = 'claude_guided'
  C. ทับด้วยป้ายชุด silver 996 รีวิว               label_source = 'claude_silver'

⚠️ ไม่แตะคอลัมน์เดิมสักตัว
  sentiment และ pain_point_category ยังมีค่าเดิมครบทุกแถว
  endpoint และรายงานที่อ่านสองคอลัมน์นั้นจึงทำงานต่อได้โดยไม่ต้องแก้

⚠️ หมวด "อื่นๆ" เดิมแยกได้สองทาง (10 สถานที่/กิจกรรม หรือ 11 นอกเรื่อง)
  ผู้ใช้สั่งให้ตั้งเป็น 10 ไว้ก่อนแล้ว mark needs_review = true

⚠️ แถวที่ไม่มีหมวดเดิม (rating-only / rule-based / claude ที่ category เป็น NULL)
  ได้ overall_sentiment แต่ไม่มี primary_category_id และไม่มีแถวใน review_aspects
  เพราะเราไม่รู้ว่าเป็นหมวดอะไร การเดาจะทำให้สถิติหมวดเพี้ยน
  รอ Phase 4 re-analyse ด้วยโมเดลใหม่จึงจะได้หมวดจริง

⚠️ Phase 4 ต้องข้ามแถวที่ label_source เป็น claude_guided / claude_silver /
  human_verified ไม่งั้นผลโมเดลจะทับป้ายที่ใช้เป็นชุดประเมินและชุดเทรน

รัน:
  uv run python scripts/migrate_to_multiaspect.py            # DRY-RUN
  uv run python scripts/migrate_to_multiaspect.py --apply
"""
import argparse
import asyncio
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal, engine

LAB = ROOT / "data" / "labeling"
SENTS = ("positive", "neutral", "negative")


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def load_map():
    doc = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    old2new, needs = {}, set()
    for c in doc["categories"]:
        for o in c["old_names"]:
            old2new[o] = c["id"]
    for o in doc.get("needs_review_from_old", []):
        needs.add(o)
    return old2new, needs


def load_label_set(rev_file: str, asp_file: str, source: str):
    """อ่านชุดป้ายจาก CSV -> (reviews, aspects)"""
    revs, asps = {}, defaultdict(list)
    for r in csv.DictReader(open(LAB / rev_file, encoding="utf-8-sig")):
        rid = int(r["review_id"])
        prim = r.get("primary_category_id") or r.get("primary_category", "")
        # ไฟล์ gold เก็บหมวดหลักเป็น "3.บรรยากาศ ..." ต้องตัดเลขหน้าจุดออก
        if prim and not prim.isdigit():
            prim = prim.split(".", 1)[0]
        revs[rid] = {
            "overall": r["overall_sentiment"].strip(),
            "primary": int(prim) if prim and prim.isdigit() else None,
            "needs": bool(r.get("needs_review", "").strip()),
            "source": source,
        }
    for r in csv.DictReader(open(LAB / asp_file, encoding="utf-8-sig")):
        rid = int(r["review_id"])
        if rid in revs:
            asps[rid].append({
                "cat": int(r["category_id"]),
                "sent": r["aspect_sentiment"].strip(),
                "primary": r["is_primary"] == "1",
            })
    return revs, asps


async def main(apply: bool) -> None:
    old2new, needs_from = load_map()
    gold_r, gold_a = load_label_set("reviews_labeled.csv", "review_aspects.csv",
                                    "claude_guided")
    silv_r, silv_a = load_label_set("silver_reviews.csv", "silver_aspects.csv",
                                    "claude_silver")

    p("=" * 72)
    p("  Phase 3 — ย้ายข้อมูลเข้าโครงสร้าง Multi-Aspect")
    p("=" * 72)
    p(f"map ชื่อหมวดเดิม -> id ใหม่ : {len(old2new)} ชื่อ")
    p(f"ชุด gold   {len(gold_r)} รีวิว / {sum(len(v) for v in gold_a.values())} aspect")
    p(f"ชุด silver {len(silv_r)} รีวิว / {sum(len(v) for v in silv_a.values())} aspect")
    p("")

    async with AsyncSessionLocal() as s:
        before = (await s.execute(text(
            "SELECT count(*) FROM analyzed_reviews"))).scalar()
        if not apply:
            n_cat = (await s.execute(text(
                "SELECT count(*) FROM analyzed_reviews "
                "WHERE pain_point_category IS NOT NULL"))).scalar()
            n_other = (await s.execute(text(
                "SELECT count(*) FROM analyzed_reviews "
                "WHERE pain_point_category = 'อื่นๆ'"))).scalar()
            p("[A] จะย้ายผลโมเดลเดิม")
            p(f"    overall_sentiment ทุกแถว            : {before:,}")
            p(f"    primary_category_id จากชื่อหมวดเดิม : {n_cat:,}")
            p(f"    ในนั้นมาจาก 'อื่นๆ' -> หมวด 10 + needs_review : {n_other:,}")
            p(f"    review_aspects (1 แถว/รีวิว)        : {n_cat:,}")
            p(f"[B] จะทับด้วย gold   : {len(gold_r)} รีวิว")
            p(f"[C] จะทับด้วย silver : {len(silv_r)} รีวิว")
            p("")
            p("นี่คือ DRY-RUN — ยังไม่เขียนอะไร  ลงมือจริงด้วย --apply")
            await engine.dispose()
            return

        # ---------- A. ผลของโมเดลเดิม ----------
        await s.execute(text("""
            UPDATE analyzed_reviews
               SET overall_sentiment = sentiment,
                   label_source = 'model'
        """))
        pairs = sorted({(o, n) for o, n in old2new.items()})
        await s.execute(text("""
            UPDATE analyzed_reviews AS ar
               SET primary_category_id = m.new_id,
                   needs_review = m.needs
              FROM (SELECT UNNEST(CAST(:names AS text[]))  AS nm,
                           UNNEST(CAST(:ids   AS int[]))   AS new_id,
                           UNNEST(CAST(:needs AS bool[]))  AS needs) AS m
             WHERE ar.pain_point_category = m.nm
        """), {"names": [o for o, _ in pairs],
               "ids": [n for _, n in pairs],
               "needs": [o in needs_from for o, _ in pairs]})
        res = await s.execute(text("""
            INSERT INTO review_aspects
                   (review_id, category_id, aspect_sentiment, is_primary, label_source)
            SELECT ar.review_id, ar.primary_category_id, ar.sentiment, true, 'model'
              FROM analyzed_reviews ar
             WHERE ar.primary_category_id IS NOT NULL
               AND ar.sentiment IN ('positive','neutral','negative')
            ON CONFLICT (review_id, category_id) DO NOTHING
        """))
        await s.commit()
        p(f"[A] เขียน review_aspects จากโมเดลเดิม {res.rowcount:,} แถว")

        # ---------- B, C. ชุดป้ายที่ติดเอง ----------
        for tag, revs, asps in (("gold", gold_r, gold_a),
                                ("silver", silv_r, silv_a)):
            ids = list(revs)
            # บางรีวิวยังไม่มีแถว analyzed_reviews -> สร้างให้ก่อน
            made = await s.execute(text("""
                INSERT INTO analyzed_reviews (review_id, model_used)
                SELECT r.id, 'label-import' FROM reviews r
                 WHERE r.id = ANY(:ids)
                   AND NOT EXISTS (SELECT 1 FROM analyzed_reviews a
                                    WHERE a.review_id = r.id)
            """), {"ids": ids})
            await s.execute(text("""
                UPDATE analyzed_reviews AS ar
                   SET overall_sentiment    = v.ov,
                       primary_category_id  = v.pc,
                       needs_review         = v.nr,
                       label_source         = v.src
                  FROM (SELECT UNNEST(CAST(:ids AS int[]))   AS rid,
                               UNNEST(CAST(:ov  AS text[]))  AS ov,
                               UNNEST(CAST(:pc  AS int[]))   AS pc,
                               UNNEST(CAST(:nr  AS bool[]))  AS nr,
                               UNNEST(CAST(:src AS text[]))  AS src) AS v
                 WHERE ar.review_id = v.rid
            """), {"ids": ids,
                   "ov": [revs[i]["overall"] for i in ids],
                   "pc": [revs[i]["primary"] for i in ids],
                   "nr": [revs[i]["needs"] for i in ids],
                   "src": [revs[i]["source"] for i in ids]})
            # แทนที่ aspect ของรีวิวเหล่านี้ทั้งชุด (ของเดิมมาจากโมเดล)
            await s.execute(text(
                "DELETE FROM review_aspects WHERE review_id = ANY(:ids)"),
                {"ids": ids})
            flat = [(i, a) for i in ids for a in asps.get(i, [])]
            await s.execute(text("""
                INSERT INTO review_aspects
                       (review_id, category_id, aspect_sentiment, is_primary, label_source)
                SELECT UNNEST(CAST(:rid AS int[])),
                       UNNEST(CAST(:cat AS int[])),
                       UNNEST(CAST(:sen AS text[])),
                       UNNEST(CAST(:pri AS bool[])),
                       UNNEST(CAST(:src AS text[]))
                ON CONFLICT (review_id, category_id) DO NOTHING
            """), {"rid": [i for i, _ in flat],
                   "cat": [a["cat"] for _, a in flat],
                   "sen": [a["sent"] for _, a in flat],
                   "pri": [a["primary"] for _, a in flat],
                   "src": [revs[i]["source"] for i, _ in flat]})
            await s.commit()
            p(f"[{tag}] สร้างแถวใหม่ {made.rowcount} | เขียน aspect {len(flat):,} แถว")

        # ---------- ตรวจผลจากฐานจริง ----------
        p("")
        p("ตรวจจากฐานข้อมูลจริง")
        after = (await s.execute(text(
            "SELECT count(*) FROM analyzed_reviews"))).scalar()
        p(f"  analyzed_reviews {before:,} -> {after:,}")
        for q, lbl in (
            ("SELECT count(*) FROM analyzed_reviews WHERE sentiment IS NOT NULL",
             "sentiment เดิมยังมีค่า"),
            ("SELECT count(*) FROM analyzed_reviews WHERE pain_point_category IS NOT NULL",
             "pain_point_category เดิมยังมีค่า"),
            ("SELECT count(*) FROM analyzed_reviews WHERE overall_sentiment IS NOT NULL",
             "overall_sentiment ใหม่"),
            ("SELECT count(*) FROM analyzed_reviews WHERE primary_category_id IS NOT NULL",
             "primary_category_id ใหม่"),
            ("SELECT count(*) FROM analyzed_reviews WHERE needs_review", "needs_review"),
            ("SELECT count(*) FROM review_aspects", "review_aspects ทั้งหมด"),
        ):
            p(f"  {lbl:<32} {(await s.execute(text(q))).scalar():>8,}")
        p("")
        p("  แยกตาม label_source")
        for r in (await s.execute(text("""
            SELECT label_source, count(*) n FROM analyzed_reviews
             GROUP BY 1 ORDER BY 2 DESC"""))).fetchall():
            p(f"    {str(r.label_source):<16} {r.n:>8,}")
        p("")
        p("  review_aspects แยกตามแหล่งป้าย")
        for r in (await s.execute(text("""
            SELECT label_source, count(*) n,
                   round(count(*)::numeric / count(DISTINCT review_id), 2) per
              FROM review_aspects GROUP BY 1 ORDER BY 2 DESC"""))).fetchall():
            p(f"    {str(r.label_source):<16} {r.n:>8,}  ({r.per} หมวด/รีวิว)")

    await engine.dispose()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.apply))
