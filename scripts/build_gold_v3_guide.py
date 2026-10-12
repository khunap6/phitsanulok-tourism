"""build_gold_v3_guide.py — สร้าง reports/evaluation/gold_v3_guide.md

⚠️ ทำไมแยกสคริปต์ออกจาก sample_gold_v3.py
  เดิม sampler เป็นคนเขียนคู่มือ ซึ่งหมายความว่าทุกครั้งที่รัน --write
  คู่มือจะถูกเขียนทับ ถ้ามีใครแก้คู่มือด้วยมือ งานนั้นจะหายเงียบ ๆ
  (เป็นบั๊กแบบเดียวกับที่ labeling_rules หายจาก shared/categories.json
   เพราะถูกเติมมือหลัง generate)
  ตอนนี้ sampler ทำหน้าที่สุ่มอย่างเดียว คู่มือมีผู้เขียนคนเดียวคือสคริปต์นี้

⚠️ คู่มือ generate จากแหล่งจริงทั้งหมด ห้ามแก้ไฟล์ .md ตรง ๆ
  นิยามหมวด + routing + กติกา  <- shared/categories_v3.json
  การกระจายของชุด               <- reports/evaluation/gold_v3_meta.csv
                                   + ชุดที่ติดป้ายแล้ว (ถ้ามี)
  ถ้าต้องแก้กติกา ให้แก้ scripts/build_categories_v3.py แล้ว generate ใหม่สองชั้น

รัน:
  uv run python scripts/build_categories_v3.py
  uv run python scripts/build_gold_v3_guide.py
"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "reports" / "evaluation"
GUIDE = OUT_DIR / "gold_v3_guide.md"
META = OUT_DIR / "gold_v3_meta.csv"
# ใช้ชุดที่ติดป้ายแล้วรุ่นใหม่สุดที่มี เพื่อให้จำนวนในคู่มือตรงกับไฟล์จริง
LABELED = [OUT_DIR / "gold_v3_1_labeled.csv", OUT_DIR / "gold_v3_labeled.csv"]

SCOPE_TH = {"all": "ทุกที่", "food": "ร้านอาหาร/คาเฟ่", "place": "สถานที่ท่องเที่ยว"}


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def main() -> None:
    v3 = json.loads((ROOT / "shared" / "categories_v3.json").read_text(encoding="utf-8"))
    ver = v3.get("version", "v3")

    meta = {r["review_id"]: r for r in csv.DictReader(open(META, encoding="utf-8-sig"))}
    src = next((f for f in LABELED if f.exists()), None)
    if src:
        ids = [r["review_id"] for r in csv.DictReader(open(src, encoding="utf-8-sig"))]
    else:
        ids = list(meta)
    n = len(ids)
    strata = Counter(meta[i]["stratum"] for i in ids if i in meta)
    unknown = sum(1 for i in ids if i not in meta)

    L = [f"# คู่มือติดป้ายชุด gold {ver} ({n} รายการ)", "",
         "⚠️ **ไฟล์นี้ generate อัตโนมัติ ห้ามแก้ตรง ๆ**",
         "แก้กติกาที่ `scripts/build_categories_v3.py` แล้วรัน",
         "`build_categories_v3.py` ตามด้วย `build_gold_v3_guide.py`", "",
         f"ไฟล์ที่ต้องกรอก: `{(src or (OUT_DIR / 'gold_v3_blank.csv')).name}`", "",
         "## ชุดนี้คืออะไร", "",
         "ชุด gold เดิม 300 ใบสุ่มมาแบบไม่แบ่งชั้น จึงเป็นร้านอาหารเกือบทั้งชุด",
         "ทำให้หมวดของสถานที่ท่องเที่ยว วัด ตลาด มีตัวอย่างไม่พอวัดผล",
         "ชุดนี้บังคับโควตาตามประเภทสถานที่ เพื่อให้ทุกหมวดวัดผลได้", "",
         "⚠️ **ชุดนี้ไม่เป็นตัวแทนประชากร** สัดส่วนประเภทสถานที่ถูกบิดโดยเจตนา",
         "ห้ามเอาสัดส่วนในชุดนี้ไปอ้างเป็นสัดส่วนของจังหวัด", "",
         f"⚠️ ติดป้ายด้วย **ชุดหมวด {ver} ({len(v3['categories'])} หมวด)** "
         "ไม่ใช่ v2 ที่ระบบใช้อยู่", "",
         "## วิธีกรอก", "",
         "| ช่อง | กรอกอะไร |", "|---|---|",
         "| `overall_sentiment` | `positive` · `neutral` · `negative` |",
         "| `aspects` | `<เลขหมวด><เครื่องหมาย>` คั่นจุลภาค · "
         "`+` ชม `n` กลางๆ `-` ติ · เช่น `1+,3-` |",
         "| `no_specific_topic` | ใส่ `1` ถ้าชมหรือติแบบไม่บอกว่าเรื่องอะไร "
         "แล้ว `aspects` ต้องว่าง |",
         "",
         "⚠️ ห้ามใส่หมวดเดียวกันสองครั้งในรีวิวเดียว", "",
         "⚠️ ข้อความที่อ่านไม่เข้าใจ ให้เว้น `overall_sentiment` ว่างไว้",
         "แถวนั้นจะถูกตัดออกจากการคิดคะแนน ไม่นับว่าผิด", "",
         "ไม่แน่ใจจริง ๆ ให้เว้นว่าง ดีกว่าเดา", "",
         "## หมวดทั้งหมด", "",
         "| เลข | ชื่อหมวด | ใช้กับ | ครอบคลุมอะไร |", "|---|---|---|---|"]
    for c in v3["categories"]:
        L.append(f"| {c['id']} | {c['name']} | {SCOPE_TH.get(c['scope'], c['scope'])} "
                 f"| {c['covers']} |")
    L += ["",
          "⚠️ คอลัมน์ **ใช้กับ** เป็นเพียงคำใบ้ว่าหมวดนั้นมักโผล่ที่สถานที่แบบไหน",
          "**ไม่ใช่ข้อบังคับ** หมวดใดก็ใช้กับสถานที่ประเภทใดก็ได้",
          "(เช่น หมวด 1 รสชาติ ใช้กับตลาดหรือวัดที่มีร้านอาหารได้)", ""]

    L += ["## หัวข้อที่ไม่มีหมวดของตัวเอง — ส่งเข้าหมวดไหน", "",
          "หัวข้อพวกนี้พบในข้อมูลจริงแต่น้อยเกินกว่าจะตั้งเป็นหมวด", "",
          "| ถ้ารีวิวพูดถึง | ใช้หมวด |", "|---|---|"]
    for k, v in v3["routing"].items():
        if not k.startswith("_"):
            L.append(f"| {k} | {v} |")
    L.append("")

    L += ["## กติกาที่ต้องใช้", ""]
    for key, r in v3["labeling_rules"].items():
        if key.startswith("_") or not isinstance(r, dict):
            continue
        L += [f"### {r.get('title', key)}", ""]
        rule = r.get("rule")
        if isinstance(rule, list):
            L += [f"{i}. {x}" if not x.startswith(("   ", "-")) else x
                  for i, x in enumerate(rule, 1)] + [""]
        elif rule:
            L += [f"**{rule}**", ""]
        if r.get("exception"):
            L += [f"ข้อยกเว้น: {r['exception']}", ""]
        if r.get("hard_constraint"):
            L += [f"⚠️ {r['hard_constraint']}", ""]
        if isinstance(r.get("mapping"), dict):
            L += ["| ถ้ารีวิวพูดถึง | ให้ใช้หมวด |", "|---|---|"]
            L += [f"| {k} | {v} |" for k, v in r["mapping"].items()] + [""]
        if r.get("patterns"):
            L += ["| รูปแบบ metadata | จำนวนรีวิว |", "|---|---|"]
            L += [f"| {k} | {v:,} |" for k, v in r["patterns"].items()] + [""]
        if r.get("patterns_v31"):
            L += ["รูปแบบที่ต้องอ่านข้ามทั้งหมด", ""]
            L += [f"- {x}" for x in r["patterns_v31"]] + [""]
        if r.get("warning"):
            L += [f"⚠️ {r['warning']}", ""]
        if r.get("warning_v31"):
            L += [f"{r['warning_v31']}", ""]
        if r.get("correction_note"):
            L += [f"หมายเหตุ: {r['correction_note']}", ""]
        if r.get("why"):
            L += ["ที่มา:"] + [f"- {w}" for w in r["why"]] + [""]
        if r.get("ที่มา"):
            L += ["ที่มา (review_id ที่ทำให้ต้องเขียนกติกานี้):"]
            L += [f"- {w}" for w in r["ที่มา"]] + [""]

    L += ["## การกระจายของชุดนี้", "",
          "| กลุ่มประเภทสถานที่ | จำนวน |", "|---|---|"]
    for name, k in strata.most_common():
        L.append(f"| {name} | {k} |")
    if unknown:
        L.append(f"| (ไม่ทราบกลุ่ม) | {unknown} |")
    L += ["", f"รวม **{n}** รายการ"]
    if src and src.name.startswith("gold_v3_1"):
        L += ["",
              "⚠️ จำนวนลดจาก 195 เหลือ 194 เพราะลบแถว 63356 ที่เป็นข้อความซ้ำกับ 55824",
              "ตัวเลขด้านบนนับจากไฟล์ที่ติดป้ายแล้วจริง ไม่ใช่จากโควตาที่ตั้งไว้ตอนสุ่ม"]
    L.append("")

    GUIDE.write_text("\n".join(L) + "\n", encoding="utf-8")
    p(f"เขียน {GUIDE.relative_to(ROOT)} แล้ว — {ver}")
    p(f"  อ้างจำนวนจาก {src.name if src else 'gold_v3_meta.csv'} = {n} รายการ")
    p(f"  หมวด {len(v3['categories'])} · routing "
      f"{len([k for k in v3['routing'] if not k.startswith('_')])} · "
      f"กติกา {len([k for k in v3['labeling_rules'] if not k.startswith('_')])}")


if __name__ == "__main__":
    main()
