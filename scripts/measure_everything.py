"""measure_everything.py — เก็บตัววัดทุกตัวที่วัดได้ในโปรเจกต์นี้ไว้ที่เดียว

⚠️ ทำไมต้องมี
  ตัวเลขในโปรเจกต์นี้กระจายอยู่หลายที่ (ฐานข้อมูล · about.json ของโมเดล ·
  รายงานการประเมิน · ไฟล์ชุดติดป้าย) และเคยเกิดปัญหาว่าเอกสารอ้างตัวเลข
  ที่ย้อนตรวจไม่ได้ สคริปต์นี้ดึงทุกอย่างจากแหล่งจริงในรอบเดียว
  แล้วเขียนออกเป็นไฟล์ที่ลง git ได้ เพื่อให้ตัวเลขในเล่มมีที่มาเสมอ

⚠️ สคริปต์นี้ "อ่านอย่างเดียว" ไม่แก้ฐานข้อมูลและไม่แตะไฟล์ชุดติดป้าย

⚠️ กฎข้อ 1 ของโปรเจกต์ — ตัวเศษกับตัวส่วนต้องผ่านตัวกรองชุดเดียวกัน
  ในสคริปต์นี้ทุกสัดส่วนจึงคำนวณจากคิวรีเดียวที่นับทั้งตัวเศษและตัวส่วน
  ไม่ใช่สองคิวรีแยกกัน

รัน:
  uv run python scripts/measure_everything.py
"""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from db.database import engine  # noqa: E402

OUT_JSON = ROOT / "reports" / "measurements.json"
OUT_MD = ROOT / "reports" / "measurements.md"


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


async def one(c, sql: str, **kw) -> dict:
    return dict((await c.execute(text(sql), kw)).mappings().one())


async def many(c, sql: str, **kw) -> list[dict]:
    return [dict(r) for r in (await c.execute(text(sql), kw)).mappings()]


# ---------------------------------------------------------------- ฐานข้อมูล
async def collect_db() -> dict:
    d: dict = {}
    async with engine.connect() as c:
        d["สถานที่"] = await one(c, """
            SELECT COUNT(*) AS total,
                   -- ⚠️ ค่าในฐานข้อมูลเป็นตัวพิมพ์เล็ก และ NULL ให้นับเป็นเปิด
                   --   ต้องตรงกับ api/filters.status_filter() เป๊ะ ไม่งั้นตัวเลข
                   --   ในรายงานนี้จะไม่ตรงกับที่หน้าเว็บแสดง
                   COUNT(*) FILTER (WHERE COALESCE(business_status,'operational')
                                        = 'operational') AS operational,
                   COUNT(*) FILTER (WHERE COALESCE(business_status,'operational')
                                        IN ('closed_permanently','closed_temporarily'))
                       AS closed,
                   COUNT(*) FILTER (WHERE zone IS NOT NULL) AS has_zone,
                   COUNT(DISTINCT zone) AS n_zones
            FROM places""")

        # ⚠️ text_clean <> '' คือตัวกรองที่ทุกสัดส่วนต้องใช้ร่วมกัน
        #   รีวิวที่ให้ดาวอย่างเดียวไม่มีข้อความให้วิเคราะห์ ถ้าปนในตัวส่วน
        #   สัดส่วนทุกตัวจะต่ำกว่าความจริง (ปัญหาที่เคยเจอจริง)
        d["รีวิว"] = await one(c, """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE text_clean IS NOT NULL AND text_clean <> '')
                       AS with_text,
                   COUNT(*) FILTER (WHERE text_clean IS NULL OR text_clean = '')
                       AS rating_only,
                   COUNT(*) FILTER (WHERE review_date_approx IS NOT NULL) AS has_date,
                   MIN(review_date_approx)::text AS date_min,
                   MAX(review_date_approx)::text AS date_max,
                   COUNT(DISTINCT text_hash) AS distinct_hash
            FROM reviews""")

        # ⚠️ รีวิว 1-3 ดาวมีน้อย = ข้อจำกัดสำคัญ เพราะคำบ่นส่วนใหญ่อยู่ในกลุ่มนี้
        d["การกระจายดาว"] = await many(c, """
            SELECT rating,
                   COUNT(*) AS n,
                   COUNT(*) FILTER (WHERE text_clean IS NOT NULL AND text_clean <> '')
                       AS with_text
            FROM reviews GROUP BY rating ORDER BY rating""")

        d["วิเคราะห์แล้ว"] = await one(c, """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE pain_point_category IS NOT NULL) AS legacy_cat,
                   COUNT(*) FILTER (WHERE sentiment IS NOT NULL)           AS legacy_senti,
                   COUNT(*) FILTER (WHERE severity IS NOT NULL)            AS legacy_sev,
                   COUNT(*) FILTER (WHERE primary_category_id IS NOT NULL) AS primary_cat,
                   COUNT(*) FILTER (WHERE overall_sentiment IS NOT NULL)   AS overall_senti,
                   COUNT(*) FILTER (WHERE needs_review)                    AS needs_review
            FROM analyzed_reviews""")

        d["สถานะร้าน"] = await many(c, """
            SELECT COALESCE(business_status,'(null)') AS v, COUNT(*) AS n
            FROM places GROUP BY 1 ORDER BY 2 DESC""")

        # ⚠️ severity ยังไม่ถูกย้ายมาชั้น aspect — วัดไว้ให้เห็นว่าย้ายไม่ได้
        d["severity"] = {
            "analyzed_reviews (เดิม)": await many(c, """
                SELECT COALESCE(severity,'(null)') AS v, COUNT(*) AS n
                FROM analyzed_reviews GROUP BY 1 ORDER BY 2 DESC"""),
            "review_aspects (ใหม่)": await many(c, """
                SELECT COALESCE(severity,'(null)') AS v, COUNT(*) AS n
                FROM review_aspects GROUP BY 1 ORDER BY 2 DESC"""),
        }

        # ⚠️ ข้อความซ้ำข้ามสถานที่ — รีวิวเดียวกันโผล่ในหลายร้านได้
        #   เพราะคีย์กันซ้ำผูกกับ (place_id, text_hash) ไม่ใช่ text_hash เดียว
        d["ข้อความซ้ำ"] = await one(c, """
            SELECT COUNT(*) AS rows_in_dup_groups,
                   COUNT(DISTINCT text_hash) AS dup_hash_groups
            FROM reviews WHERE text_hash IN (
              SELECT text_hash FROM reviews GROUP BY text_hash HAVING COUNT(*) > 1)""")

        # ⚠️ ช่องว่างระหว่างสองชั้น — รีวิวที่มีข้อความแต่ยังไม่มีแถว aspect
        d["ช่องว่างสองชั้น"] = await one(c, """
            SELECT
              (SELECT COUNT(*) FROM reviews r
               WHERE r.text_clean IS NOT NULL AND r.text_clean <> ''
                 AND NOT EXISTS (SELECT 1 FROM review_aspects ra
                                 WHERE ra.review_id = r.id)) AS text_without_aspect,
              (SELECT COUNT(*) FROM analyzed_reviews ar
               WHERE ar.primary_category_id IS NULL
                 AND ar.pain_point_category IS NOT NULL) AS legacy_cat_without_primary,
              (SELECT COUNT(*) FROM analyzed_reviews ar
               WHERE ar.overall_sentiment IS NULL
                 AND ar.sentiment IS NOT NULL) AS legacy_senti_without_overall""")

        d["ชั้น aspect"] = await one(c, """
            SELECT COUNT(*) AS rows,
                   COUNT(DISTINCT review_id) AS reviews,
                   COUNT(*) FILTER (WHERE is_primary) AS primary_rows,
                   COUNT(*) FILTER (WHERE severity IS NOT NULL) AS has_severity,
                   ROUND(AVG(confidence)::numeric, 4)::float AS avg_confidence,
                   ROUND((COUNT(*)::numeric / NULLIF(COUNT(DISTINCT review_id), 0)), 4)::float
                       AS aspects_per_review
            FROM review_aspects""")

        d["label_source"] = {
            "analyzed_reviews": await many(c, """
                SELECT COALESCE(label_source, '(null)') AS src, COUNT(*) AS n
                FROM analyzed_reviews GROUP BY 1 ORDER BY 2 DESC"""),
            "review_aspects": await many(c, """
                SELECT COALESCE(label_source, '(null)') AS src, COUNT(*) AS n
                FROM review_aspects GROUP BY 1 ORDER BY 2 DESC"""),
        }

        # ⚠️ สองหน่วยนับนี้ตอบคำถามคนละข้อ ห้ามเอามาบวกหรือเทียบกันตรง ๆ
        #   mention = ทุกหมวดที่รีวิวพูดถึง  -> ผลรวมเกินจำนวนรีวิว
        #   primary = หมวดหลักของรีวิว       -> ผลรวมเท่าจำนวนรีวิวพอดี
        d["หมวด หน่วยการกล่าวถึง"] = await many(c, """
            SELECT ra.category_id AS id, cat.name,
                   COUNT(*) AS n_reviews,
                   COUNT(*) FILTER (WHERE ra.aspect_sentiment = 'positive') AS pos,
                   COUNT(*) FILTER (WHERE ra.aspect_sentiment = 'neutral')  AS neu,
                   COUNT(*) FILTER (WHERE ra.aspect_sentiment = 'negative') AS neg
            FROM review_aspects ra
            JOIN categories cat ON cat.id = ra.category_id
            GROUP BY 1, 2 ORDER BY 3 DESC""")

        d["หมวด หน่วยหมวดหลัก"] = await many(c, """
            SELECT ra.category_id AS id, cat.name, COUNT(*) AS n_reviews
            FROM review_aspects ra
            JOIN categories cat ON cat.id = ra.category_id
            WHERE ra.is_primary
            GROUP BY 1, 2 ORDER BY 3 DESC""")

        d["หมวดเดิม v1"] = await many(c, """
            SELECT pain_point_category AS name, COUNT(*) AS n
            FROM analyzed_reviews
            WHERE pain_point_category IS NOT NULL
            GROUP BY 1 ORDER BY 2 DESC""")

        d["อารมณ์"] = {
            "เดิม (sentiment)": await many(c, """
                SELECT COALESCE(sentiment, '(null)') AS v, COUNT(*) AS n
                FROM analyzed_reviews GROUP BY 1 ORDER BY 2 DESC"""),
            "ใหม่ (overall_sentiment)": await many(c, """
                SELECT COALESCE(overall_sentiment, '(null)') AS v, COUNT(*) AS n
                FROM analyzed_reviews GROUP BY 1 ORDER BY 2 DESC"""),
            "รายหมวด (aspect_sentiment)": await many(c, """
                SELECT aspect_sentiment AS v, COUNT(*) AS n
                FROM review_aspects GROUP BY 1 ORDER BY 2 DESC"""),
        }

        # ⚠️ ปัญหาคุณภาพข้อมูลที่รู้แล้วแต่แก้ไม่ได้ ต้องวัดไว้ให้เห็นขนาด
        #   text_clean บางแถวยังมีคำนำหน้าแบบ "6 ปีที่แล้ว" ติดมา
        #   แก้ไม่ได้เพราะ text_hash คำนวณจาก clean_review_text(text)
        #   ถ้าแก้ฟังก์ชันนั้น hash ทุกแถวจะเปลี่ยน -> insert ซ้ำทั้งตาราง
        d["คุณภาพข้อความ"] = await one(c, """
            SELECT COUNT(*) AS with_text,
                   COUNT(*) FILTER (WHERE text_clean ~ '^[0-9]+ (ปี|เดือน|สัปดาห์|วัน|ชั่วโมง|นาที)ที่แล้ว')
                       AS date_prefix_left,
                   COUNT(*) FILTER (WHERE LENGTH(text_clean) < 10) AS very_short
            FROM reviews
            WHERE text_clean IS NOT NULL AND text_clean <> ''""")

        d["โซน"] = await many(c, """
            SELECT COALESCE(p.zone, '(ไม่มีโซน)') AS zone,
                   COUNT(DISTINCT p.id) AS places,
                   COUNT(r.id) AS reviews,
                   COUNT(r.id) FILTER (WHERE r.text_clean IS NOT NULL
                                         AND r.text_clean <> '') AS with_text
            FROM places p LEFT JOIN reviews r ON r.place_id = p.id
            GROUP BY 1 ORDER BY 3 DESC""")

        d["สแนปช็อต"] = await one(c, """
            SELECT (SELECT COUNT(*) FROM stat_snapshots)      AS stat_snapshots,
                   (SELECT COUNT(*) FROM snapshot_categories) AS snapshot_categories,
                   (SELECT COUNT(*) FROM snapshot_places)     AS snapshot_places,
                   (SELECT COUNT(DISTINCT category_version) FROM snapshot_categories)
                       AS cat_versions""")
        d["สแนปช็อต รายรุ่นหมวด"] = await many(c, """
            SELECT COALESCE(category_version, '(null)') AS version, COUNT(*) AS n
            FROM snapshot_categories GROUP BY 1 ORDER BY 1""")
        d["งาน scrape"] = await many(c, """
            SELECT status, COUNT(*) AS n FROM scrape_jobs GROUP BY 1 ORDER BY 2 DESC""")
        d["การค้นหาสถานที่"] = await one(c, """
            SELECT (SELECT COUNT(*) FROM discover_cells)    AS discover_cells,
                   (SELECT COUNT(*) FROM place_candidates)  AS place_candidates""")
    await engine.dispose()
    return d


# ------------------------------------------------------------------ โมเดล
def collect_models() -> dict:
    out = {}
    for name, rel in (
        ("หมวด (multi-label)", "models/wangchanberta-category-multilabel/thresholds.json"),
        ("อารมณ์รายหมวด (ABSA)", "models/wangchanberta-aspect-sentiment/about.json"),
        ("อารมณ์รวม", "models/wangchanberta-overall-sentiment/about.json"),
        ("อารมณ์ (รุ่นเดิม)", "models/wangchanberta-sentiment/about.json"),
        ("หมวด (รุ่นเดิม single-label)", "models/wangchanberta-category/about.json"),
    ):
        f = ROOT / rel
        if not f.exists():
            out[name] = {"สถานะ": "ไม่มีไฟล์ about/thresholds", "path": rel}
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        out[name] = {
            "path": rel,
            "run_seed": d.get("run_seed"),
            "epochs": d.get("epochs"),
            "lr": d.get("lr"),
            "batch_size": d.get("batch_size"),
            "max_length": d.get("max_length"),
            "n_train": d.get("n_train"),
            "n_val": d.get("n_val"),
            "val_macro_f1": d.get("val_macro_f1") or d.get("val_macro_f1"),
            "val_micro_f1": d.get("val_micro_f1"),
            # ⚠️ ถ้า run_seed/epochs เป็น null แปลว่าโมเดลตัวนั้นเทรนก่อนที่จะ
            #   เพิ่มการบันทึก config จึง "ย้อนทำซ้ำไม่ได้" และตัวเลขจากมัน
            #   ใช้อ้างอิงในเล่มไม่ได้
            "ทำซ้ำได้": d.get("run_seed") is not None and d.get("epochs") is not None,
        }
    return out


# ------------------------------------------------------- ชุดติดป้าย + ผลวัด
def collect_labelsets() -> dict:
    import csv
    out = {}
    for name, rel in (("silver_reviews", "data/labeling/silver_reviews.csv"),
                      ("silver_aspects", "data/labeling/silver_aspects.csv")):
        f = ROOT / rel
        if not f.exists():
            out[name] = {"สถานะ": "ไม่มีไฟล์"}
            continue
        rows = list(csv.DictReader(open(f, encoding="utf-8-sig")))
        rec = {"path": rel, "n_rows": len(rows)}
        if "review_id" in (rows[0] if rows else {}):
            rec["n_reviews"] = len({r["review_id"] for r in rows})
        if rows and "category_id" in rows[0]:
            from collections import Counter
            rec["ต่อหมวด"] = dict(sorted(
                Counter(int(r["category_id"]) for r in rows).items()))
            rec["อารมณ์"] = dict(Counter(r["aspect_sentiment"] for r in rows))
        out[name] = rec
    return out


def collect_eval() -> dict:
    out = {}
    f = ROOT / "reports" / "evaluation" / "seed_sweep_final.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        out["sweep ปิดท้าย"] = {
            "n_runs": d["n_runs"], "seeds": d["seeds"],
            "epochs_cat": d.get("epochs_cat"), "epochs_asp": d.get("epochs_asp"),
            "epochs_overall": d.get("epochs_overall"),
            "ตัวชี้วัด": {k: {"label": v["label"], "mean": v["mean"], "sd": v["sd"],
                            "min": v["min"], "max": v["max"]}
                        for k, v in d["summary"].items()},
            "f1_รายหมวด": d.get("per_category_f1", {}),
        }
    f = ROOT / "reports" / "evaluation" / "multiaspect_summary.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        out["ชุดประเมิน gold"] = d.get("eval_set", {})
        out["รอบเดียว (โมเดลบนดิสก์)"] = {
            "หมวด micro_f1": d["category_multilabel"]["micro_f1"],
            "หมวด macro_f1": d["category_multilabel"]["macro_f1"],
            "f1_รายหมวด": {k: v["f1"] for k, v in
                           d["category_multilabel"]["per_category"].items()},
        }
    # ชุด sweep อื่น ๆ ที่เก็บไว้เทียบ config
    sweeps = {}
    for f in sorted((ROOT / "reports" / "evaluation").glob("seed_sweep_*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        sweeps[f.stem] = {
            "epochs_cat": d.get("epochs_cat"), "epochs_asp": d.get("epochs_asp"),
            "seeds": d["seeds"],
            "cat_micro_f1": d["summary"]["cat_micro_f1"]["mean"],
            "cat_micro_sd": d["summary"]["cat_micro_f1"]["sd"],
            "asp_macro_f1": d["summary"]["asp_macro_f1"]["mean"],
            "asp_macro_sd": d["summary"]["asp_macro_f1"]["sd"],
            "e2e_micro_f1": d["summary"]["e2e_micro_f1"]["mean"],
            "e2e_micro_sd": d["summary"]["e2e_micro_f1"]["sd"],
        }
    if sweeps:
        out["sweep ทุกชุดที่เก็บไว้"] = sweeps
    return out


# ------------------------------------------------------------------- เขียน
def fmt(n) -> str:
    if isinstance(n, float):
        return f"{n:,.4f}"
    if isinstance(n, int):
        return f"{n:,}"
    return str(n)


def table(rows: list[dict], cols: list[str] | None = None) -> list[str]:
    if not rows:
        return ["(ไม่มีข้อมูล)", ""]
    cols = cols or list(rows[0])
    L = ["| " + " | ".join(cols) + " |", "|---" * len(cols) + "|"]
    for r in rows:
        L.append("| " + " | ".join(fmt(r.get(c)) for c in cols) + " |")
    L.append("")
    return L


def kv(d: dict) -> list[str]:
    L = ["| ตัว | ค่า |", "|---|---|"]
    for k, v in d.items():
        L.append(f"| {k} | {fmt(v)} |")
    L.append("")
    return L


def main() -> None:
    p("กำลังอ่านฐานข้อมูล...")
    db = asyncio.run(collect_db())
    p("กำลังอ่าน about.json ของโมเดล...")
    models = collect_models()
    p("กำลังอ่านชุดติดป้าย...")
    labels = collect_labelsets()
    p("กำลังอ่านผลการประเมิน...")
    ev = collect_eval()

    doc = {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
           "ฐานข้อมูล": db, "โมเดล": models, "ชุดติดป้าย": labels, "ผลการวัด": ev}
    OUT_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")

    L = [f"# ตัววัดทั้งหมดของโปรเจกต์ (สร้างอัตโนมัติ {doc['generated_at']})", "",
         "สร้างด้วย `scripts/measure_everything.py` ซึ่งอ่านอย่างเดียว ไม่แก้อะไร",
         "ทุกตัวเลขในเล่มควรอ้างไฟล์นี้หรือ `reports/measurements.json` เป็นที่มา", "",
         "⚠️ ไฟล์นี้บอก **ขนาดและการกระจายของข้อมูล** ไม่ใช่คุณภาพของโมเดล",
         "ตัวเลขคุณภาพโมเดลอยู่ในหัวข้อ 8 และต้องอ่านคู่กับ "
         "`reports/evaluation/seed_sweep_final.md`", "",
         "---", "", "## 1. สถานที่และรีวิว", ""]
    L += kv(db["สถานที่"])
    L += kv(db["รีวิว"])
    L += ["### การกระจายดาว", "",
          "⚠️ **ข้อจำกัดสำคัญ** คำบ่นส่วนใหญ่อยู่ในรีวิว 1-3 ดาว "
          "ถ้ากลุ่มนี้มีน้อย ระบบจะเห็นปัญหาน้อยกว่าความจริง", ""]
    tot = sum(r["n"] for r in db["การกระจายดาว"])
    rows = [{**r, "ร้อยละ": f"{r['n'] / tot * 100:.2f}%"} for r in db["การกระจายดาว"]]
    L += table(rows, ["rating", "n", "with_text", "ร้อยละ"])
    low = sum(r["n"] for r in db["การกระจายดาว"] if r["rating"] and r["rating"] <= 3)
    L += [f"รีวิว 1-3 ดาวมี **{low:,}** จาก {tot:,} = "
          f"**{low / tot * 100:.2f}%** ของรีวิวทั้งหมด", ""]

    L += ["---", "", "## 2. สภาพการวิเคราะห์", ""]
    L += kv(db["วิเคราะห์แล้ว"])
    L += ["### ชั้น aspect (`review_aspects`)", ""]
    L += kv(db["ชั้น aspect"])
    L += ["### ช่องว่างระหว่างชั้นเดิมกับชั้น aspect", "",
          "ตัวเลขพวกนี้ต้องเป็น 0 หรือใกล้ 0 ถ้าไม่ใช่ แปลว่ามีรีวิวที่หายไป"
          "จากชั้นใหม่และตัวเลขสองชั้นจะไม่สอดคล้องกัน", ""]
    L += kv(db["ช่องว่างสองชั้น"])
    L += ["### severity", "",
          "⚠️ **`review_aspects.severity` ยังว่างทั้งตาราง** "
          "ความรุนแรงจึงยังอ่านได้จากคอลัมน์เดิม `analyzed_reviews.severity` เท่านั้น "
          "endpoint และกราฟที่ใช้ severity จึง**ย้ายมาชั้น aspect ไม่ได้** "
          "ต้องคงไว้ที่ชั้นเดิมและติดป้ายกำกับ", ""]
    for k, v in db["severity"].items():
        L += [f"**{k}**", ""] + table(v, ["v", "n"])
    L += ["### ข้อความซ้ำ", "",
          "รีวิวข้อความเดียวกันโผล่ได้หลายสถานที่ เพราะคีย์กันซ้ำผูกกับ "
          "`(place_id, text_hash)` ไม่ใช่ `text_hash` เดียว", ""]
    L += kv(db["ข้อความซ้ำ"])
    L += ["### สถานะร้าน", ""] + table(db["สถานะร้าน"], ["v", "n"])
    L += ["### ที่มาของป้าย", ""]
    for k, v in db["label_source"].items():
        L += [f"**{k}**", ""] + table(v, ["src", "n"])

    L += ["---", "", "## 3. การกระจายรายหมวด", "",
          "⚠️ **สองหน่วยนับนี้ตอบคำถามคนละข้อ ห้ามบวกหรือเทียบกันตรง ๆ**",
          "- *การกล่าวถึง* = ทุกหมวดที่รีวิวพูดถึง ผลรวมเกินจำนวนรีวิว",
          "- *หมวดหลัก* = หมวดเดียวต่อรีวิว ผลรวมเท่าจำนวนรีวิวพอดี", "",
          "### หน่วย: การกล่าวถึง (1 รีวิวนับได้หลายหมวด)", ""]
    L += table(db["หมวด หน่วยการกล่าวถึง"], ["id", "name", "n_reviews", "pos", "neu", "neg"])
    L += ["### หน่วย: หมวดหลัก (1 รีวิว 1 หมวด)", ""]
    L += table(db["หมวด หน่วยหมวดหลัก"], ["id", "name", "n_reviews"])
    L += ["### หมวดเดิม v1 (คอลัมน์ `pain_point_category` — legacy ไม่ลบทิ้ง)", ""]
    L += table(db["หมวดเดิม v1"], ["name", "n"])

    L += ["---", "", "## 4. การกระจายอารมณ์", ""]
    for k, v in db["อารมณ์"].items():
        L += [f"**{k}**", ""] + table(v, ["v", "n"])

    L += ["---", "", "## 5. คุณภาพข้อความ", ""]
    L += kv(db["คุณภาพข้อความ"])
    cq = db["คุณภาพข้อความ"]
    if cq["date_prefix_left"]:
        L += [f"⚠️ ยังมี **{cq['date_prefix_left']:,}** แถว "
              f"({cq['date_prefix_left'] / cq['with_text'] * 100:.2f}%) "
              "ที่ `text_clean` มีคำนำหน้าแบบ \"6 ปีที่แล้ว\" ติดมา",
              "",
              "**แก้ไม่ได้** เพราะ `text_hash = md5(clean_review_text(text))` "
              "ถ้าแก้ `clean_review_text()` แล้ว hash ทุกแถวจะเปลี่ยน "
              "ทำให้ตัวกันซ้ำพังและ insert ซ้ำทั้งตาราง (เคยเกิดจริง 3,453 แถว)", ""]

    L += ["---", "", "## 6. โซน", ""]
    L += table(db["โซน"], ["zone", "places", "reviews", "with_text"])

    L += ["---", "", "## 6.1 สแนปช็อตและงานเบื้องหลัง", "",
          "⚠️ `category_version` บนสแนปช็อตมีไว้เพื่อไม่ต้องแก้สแนปช็อตเก่า"
          "ย้อนหลัง แถวเก่าเป็น v1 (12 หมวด) แถวใหม่เป็น v2 (11 หมวด) "
          "ต้อง map ตอนอ่าน ไม่ใช่ตอนเขียน", ""]
    L += kv(db["สแนปช็อต"])
    L += table(db["สแนปช็อต รายรุ่นหมวด"], ["version", "n"])
    L += kv(db["การค้นหาสถานที่"])
    L += ["**งาน scrape**", ""] + table(db["งาน scrape"], ["status", "n"])

    L += ["---", "", "## 7. config ของโมเดลที่อยู่บนดิสก์", "",
          "⚠️ ถ้าคอลัมน์ `ทำซ้ำได้` เป็น False แปลว่าโมเดลตัวนั้นเทรนก่อนที่จะ"
          "เพิ่มการบันทึก config ตัวเลขจากมันจึง**ย้อนทำซ้ำไม่ได้** "
          "และใช้อ้างอิงในเล่มไม่ได้", ""]
    mrows = [{"โมเดล": k, **{kk: vv for kk, vv in v.items() if kk != "path"}}
             for k, v in models.items()]
    L += table(mrows, ["โมเดล", "run_seed", "epochs", "lr", "batch_size",
                       "n_train", "n_val", "val_macro_f1", "ทำซ้ำได้"])

    L += ["---", "", "## 8. ผลการวัดคุณภาพ", ""]
    if "ชุดประเมิน gold" in ev:
        L += ["### ชุดประเมิน", ""] + kv(ev["ชุดประเมิน gold"])
    if "sweep ปิดท้าย" in ev:
        sw = ev["sweep ปิดท้าย"]
        L += [f"### ตัวชี้วัดหลัก — mean ± sd จาก {sw['n_runs']} seed "
              f"(config: หมวด {sw['epochs_cat']} ep · อารมณ์รายหมวด "
              f"{sw['epochs_asp']} ep · อารมณ์รวม {sw['epochs_overall']} ep)", "",
              "| ตัวชี้วัด | mean | sd | ต่ำสุด | สูงสุด |", "|---|---|---|---|---|"]
        for v in sw["ตัวชี้วัด"].values():
            L.append(f"| {v['label']} | **{v['mean']:.4f}** | ±{v['sd']:.4f} | "
                     f"{v['min']:.4f} | {v['max']:.4f} |")
        L += ["", "### F1 รายหมวด (mean ± sd)", "",
              "⚠️ หมวดที่มีตัวอย่างใน gold น้อยกว่า 20 รายการ **ห้ามสรุปเชิงสถิติ**", "",
              "| หมวด | mean | sd | ช่วงกว้าง |", "|---|---|---|---|"]
        for cid, v in sw["f1_รายหมวด"].items():
            L.append(f"| {cid} | {v['mean']:.4f} | ±{v['sd']:.4f} | "
                     f"{v['max'] - v['min']:.4f} |")
        L.append("")
    if "sweep ทุกชุดที่เก็บไว้" in ev:
        L += ["### sweep ทุกชุดที่รันไว้ (ใช้เลือก config)", "",
              "| ชุด | หมวด ep | อารมณ์ ep | หมวด micro | อารมณ์รายหมวด | ทั้งระบบ |",
              "|---|---|---|---|---|---|"]
        for k, v in ev["sweep ทุกชุดที่เก็บไว้"].items():
            L.append(f"| `{k}` | {v['epochs_cat']} | {v['epochs_asp']} | "
                     f"{v['cat_micro_f1']:.4f} ±{v['cat_micro_sd']:.4f} | "
                     f"{v['asp_macro_f1']:.4f} ±{v['asp_macro_sd']:.4f} | "
                     f"{v['e2e_micro_f1']:.4f} ±{v['e2e_micro_sd']:.4f} |")
        L.append("")

    L += ["---", "", "## 9. ชุดติดป้าย", ""]
    for k, v in labels.items():
        L += [f"**{k}** — `{v.get('path', '?')}`", ""]
        L += kv({kk: vv for kk, vv in v.items()
                 if kk not in ("path", "ต่อหมวด", "อารมณ์")})
        if "ต่อหมวด" in v:
            L += ["ต่อหมวด: " + " · ".join(f"{a}={b}" for a, b in v["ต่อหมวด"].items()), ""]
        if "อารมณ์" in v:
            L += ["อารมณ์: " + " · ".join(f"{a}={b}" for a, b in v["อารมณ์"].items()), ""]

    L += ["---", "",
          "## 10. สิ่งที่ไฟล์นี้ยังวัดไม่ได้", "",
          "1. **ความถูกต้องสัมบูรณ์ของป้าย** ชุด gold ติดโดย Claude ยังไม่ผ่าน",
          "   การตรวจโดยคน ตัวเลขทุกตัวในหัวข้อ 8 จึงวัด *ความสอดคล้องกับป้ายชุดนั้น*",
          "   ไม่ใช่ความถูกต้อง ต้องให้คนตรวจแล้วคำนวณ Cohen's kappa",
          "   (ชุดเตรียมไว้แล้วที่ `reports/evaluation/human_check_blank.csv`)",
          "2. **ความครบถ้วนของการเก็บรีวิว** ไม่ทราบว่ารีวิวที่เก็บมาเป็นกี่ % ของที่มีจริง",
          "   เพราะ Google ไม่บอกจำนวนรีวิวทั้งหมดที่เชื่อถือได้",
          "3. **อัตราการเก็บไม่ได้ของรีวิว 1-3 ดาว** ไม่ทราบว่าสัดส่วนดาวที่เห็น",
          "   สะท้อนความจริงหรือเป็นผลของวิธีเก็บ",
          "4. **ความผันผวนจากการแบ่งข้อมูล** วัดได้แต่ความผันผวนของการเทรน",
          "   ส่วนแบ่ง train/val คงที่ตลอด ต้องทำ cross-validation จึงจะวัดได้",
          "5. **ประสิทธิภาพในโลกจริง** ไม่มีข้อมูลว่าผู้ใช้จริงเห็นด้วยกับหมวด",
          "   และอารมณ์ที่ระบบจัดให้หรือไม่", ""]

    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    p("")
    p(f"เขียนที่ {OUT_MD.relative_to(ROOT)} และ {OUT_JSON.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
