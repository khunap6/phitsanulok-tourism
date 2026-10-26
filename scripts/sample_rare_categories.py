"""sample_rare_categories.py — สุ่มเจาะจงรีวิวจริงให้หมวดที่ตัวอย่างไม่ถึงเกณฑ์

ปัญหา: ชุด gold v3.2 มี 199 แถว แต่หมวด 5, 7, 8, 10, 13, 14 มีตัวอย่างไม่ถึง 20
  จึงวัด precision/recall รายหมวดของหมวดพวกนั้นไม่ได้

ทางที่ไม่เลือก: แต่งข้อความขึ้นมาเอง
  ชุด gold มีหน้าที่วัดผลบน *ข้อมูลจริง* ข้อความที่แต่งขึ้นจะไม่มีคำพิมพ์ผิด
  (l; · เเก้ไข) ไม่มี metadata ปน (฿1-200 · ประเภทก) ไม่มีรีวิวที่แปลด้วยเครื่อง
  ซึ่งทั้งสามอย่างวัดได้ว่ามีอยู่จริงในข้อมูล โมเดลที่ทำคะแนนดีบนข้อความสะอาด
  ที่เราแต่งเอง ไม่ได้บอกอะไรเลยว่ามันจะทำงานกับข้อมูลจริงได้ไหม

ทางที่เลือก: สุ่มเจาะจงจากรีวิวจริง เพราะของจริงมีเหลือเฟือ (วัดเมื่อ 2026-10-13)
  หมวด 5 มี 4,374 ใบ · 7 มี 5,674 · 8 มี 3,403 · 10 มี 6,069 · 13 มี 664
  ความขาดแคลนเป็นผลของวิธีสุ่ม ไม่ใช่ข้อมูลไม่มี

⚠️ ชุดที่ได้จากสคริปต์นี้ **มีอคติ** และต้องประกาศทุกครั้งที่รายงาน
  กอง A เลือกจากรีวิวที่โมเดล v2 ทำนายหมวดนั้นไว้แล้ว = เป็นเคสที่หาง่าย
  recall รายหมวดที่วัดจากกอง A จึงสูงกว่าความจริง และสืบทอดจุดบอดของ v2 มาด้วย
  กอง B จึงมีไว้ถ่วง — เลือกจากรีวิวที่ v2 **ไม่ได้** ทำนายหมวดนั้น
  ที่สถานที่ประเภทที่หมวดนั้นควรโผล่ เพื่อดูว่า v2 พลาดเคสแบบไหนไป

⚠️ ไฟล์ที่ให้คนกรอกต้องไม่บอกว่าแถวไหนเล็งหมวดอะไร
  ถ้าบอก ผู้ติดป้ายจะถูกชี้นำให้ใส่หมวดนั้น แล้วตัวเลขจะวัดการชี้นำ ไม่ใช่การอ่าน
  ที่มาของแต่ละแถวเก็บแยกไว้ใน manifest ซึ่งห้ามเปิดก่อนกรอกเสร็จ

⚠️ ไม่สุ่มแถวที่อยู่ในชุด gold แล้ว
  (ชุดตรวจคน 96 แถวเป็นสับเซตของ gold จึงถูกกันออกไปด้วยโดยปริยาย)

⚠️ จำกัด 1 แถวต่อสถานที่
  ไม่งั้นหมวด 10 จะได้วัดเดียว 6 ใบ แล้ววัดผลได้แต่กับวัดนั้น

รัน:
  uv run python scripts/sample_rare_categories.py
  uv run python scripts/sample_rare_categories.py --write
"""
import argparse
import asyncio
import csv
import hashlib
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from db.database import engine  # noqa: E402
from nlp.text_cleaner import clean_review_text  # noqa: E402

OUT = ROOT / "reports" / "evaluation"
GOLD = OUT / "gold_v3_2_labeled.csv"
BLANK = OUT / "gold_v3_2_rare_to_label.csv"
MANIFEST = OUT / "gold_v3_2_rare_manifest.csv"
TARGET = 20          # เกณฑ์จำนวนตัวอย่างต่อหมวดที่ถือว่าวัดผลได้
POOL_A_SHARE = 0.70  # สัดส่วนที่มาจากกองที่ v2 ทำนายหมวดนั้นไว้
SEED = 20261013

# คำสักการะ — ต้องตรงกับ labeling_rules.worship_has_its_own_category
# ถ้ากติกานั้นเปลี่ยน ให้แก้ที่นี่ด้วย สคริปต์จะตรวจให้ว่ายังตรงกันอยู่
WORSHIP = ["กราบ", "สักการะ", "ไหว้พระ", "ขอพร", "ทำบุญ", "อิ่มบุญ", "นมัสการ",
           "แก้บน", "ใส่บาตร", "ทอดกฐิน", "สวดมนต์", "ทำสมาธิ", "พิธีกรรม",
           "ศักดิ์สิทธิ์", "ขลัง", "ศรัทธา", "ประดิษฐาน", "หลวงพ่อ"]

# หมวด v3 ที่ขาด -> หมวด v2 ที่เนื้อหานี้เคยอยู่ + วิธีคัดพูลให้แคบลง
#   หมวด 10 กับ 14 แมปไปหมวด 2 ของ v2 ตัวเดียวกัน (ถุงที่รวมสักการะกับคำชมลอย)
#   จึงต้องแยกด้วยเงื่อนไขข้อความ ไม่ใช่แยกด้วยเลขหมวด v2
PLAN = {
    5:  {"v2": 6, "why": "ความสะอาด แมป 1:1"},
    7:  {"v2": 8, "why": "ความแออัด แมป 1:1"},
    8:  {"v2": 9, "why": "สิ่งอำนวยความสะดวก แมป 1:1"},
    10: {"v2": 2, "why": "สักการะ เคยอยู่ v2 หมวด 2+10 — คัดด้วยคำสักการะ",
         "require_worship": True, "place_like": "วัด|ศาสนสถาน|โบสถ์|มัสยิด|เจ้าพ่อ|ศาลเจ้า"},
    14: {"v2": 2, "why": "คำชม/ติลอย เคยอยู่ v2 หมวด 2 — คัดข้อความสั้นที่ไม่มีคำสักการะ",
         "exclude_worship": True, "max_len": 30},
}
# หมวด 13 ไม่อยู่ในแผนนี้โดยเจตนา — เป็นหมวดเศษเหลือ 0.92% ของฐาน
#   ตัวเลขรายหมวดของหมวดเศษเหลือไม่มีความหมาย และการสุ่มเจาะจงจะยิ่งทำให้เอียง
#   รายงานเป็น "วัดไม่ได้" ตรง ๆ ดีกว่า (ตกลงกับผู้ใช้เมื่อ 2026-10-13)


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def h(t: str) -> str:
    return hashlib.md5(clean_review_text(t).encode("utf-8")).hexdigest()[:10]


def gold_counts() -> tuple[dict[int, int], set[str]]:
    rows = list(csv.DictReader(open(GOLD, encoding="utf-8-sig")))
    cnt: dict[int, int] = {}
    for r in rows:
        for t in (x.strip() for x in r["aspects"].split(",") if x.strip()):
            cnt[int(t[:-1])] = cnt.get(int(t[:-1]), 0) + 1
    return cnt, {r["review_id"] for r in rows}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    v3 = json.loads((ROOT / "shared" / "categories_v3.json").read_text(encoding="utf-8"))
    names = {c["id"]: c["name"] for c in v3["categories"]}
    rule = json.dumps(v3["labeling_rules"]["worship_has_its_own_category"],
                      ensure_ascii=False)
    drift = [w for w in ("สักการะ", "ไหว้พระ", "ใส่บาตร", "หลวงพ่อ") if w not in rule]
    if drift:
        p(f"หยุด: รายการคำสักการะในสคริปต์ไม่ตรงกับกติกาใน categories_v3.json ({drift})")
        p("   ให้ตรวจ labeling_rules.worship_has_its_own_category แล้วแก้ WORSHIP")
        sys.exit(1)

    cnt, used = gold_counts()
    rnd = random.Random(SEED)
    wor = "|".join(WORSHIP)

    p(f"ชุด gold {len(used)} แถว · เกณฑ์ {TARGET} ตัวอย่างต่อหมวด")
    p("")
    p(f"{'id':>3} {'หมวด':<34} {'มี':>4} {'ขาด':>4} {'จะสุ่ม':>7} {'กอง A':>6} {'กอง B':>6}")

    want: dict[int, tuple[int, int]] = {}
    for cid in sorted(PLAN):
        have = cnt.get(cid, 0)
        need = max(0, TARGET - have)
        n = max(2 * need, 6) if need else 0
        na = round(n * POOL_A_SHARE)
        want[cid] = (na, n - na)
        p(f"{cid:>3} {names[cid][:33]:<34} {have:>4} {need:>4} {n:>7} {na:>6} {n - na:>6}")

    picked: list[dict] = []
    seen_place: set[int] = set()
    seen_rid: set[str] = set()

    async with engine.connect() as c:
        for cid in sorted(PLAN):
            na, nb = want[cid]
            if na + nb == 0:
                continue
            cfg = PLAN[cid]
            conds = ["r.text_clean <> ''", "p.in_scope"]
            params: dict = {"v2": cfg["v2"], "wor": wor}
            if cfg.get("require_worship"):
                conds.append("r.text_clean ~ :wor")
            if cfg.get("exclude_worship"):
                conds.append("r.text_clean !~ :wor")
            if cfg.get("max_len"):
                conds.append("LENGTH(r.text_clean) <= :mx")
                params["mx"] = cfg["max_len"]
            base = " AND ".join(conds)

            for pool, extra in (("A", "EXISTS"), ("B", "NOT EXISTS")):
                k = na if pool == "A" else nb
                if k == 0:
                    continue
                cond = base
                pr = dict(params)
                if pool == "B" and cfg.get("place_like"):
                    cond += " AND p.name ~ :plike"
                    pr["plike"] = cfg["place_like"]
                rows = (await c.execute(text(f"""
                    SELECT r.id, r.text_clean, r.rating, p.id AS pid, p.name,
                           p.google_category
                    FROM reviews r JOIN places p ON p.id = r.place_id
                    WHERE {cond}
                      AND {extra} (SELECT 1 FROM review_aspects ra
                                   WHERE ra.review_id = r.id AND ra.category_id = :v2)
                    ORDER BY r.id"""), pr)).mappings().all()
                cand = [x for x in rows
                        if str(x["id"]) not in used and str(x["id"]) not in seen_rid]
                rnd.shuffle(cand)
                got = 0
                for x in cand:
                    if got >= k:
                        break
                    if x["pid"] in seen_place:
                        continue
                    seen_place.add(x["pid"])
                    seen_rid.add(str(x["id"]))
                    picked.append({
                        "review_id": str(x["id"]),
                        "ข้อความรีวิว": x["text_clean"],
                        "stratum": x["google_category"] or "(ไม่ทราบ)",
                        "google_category": x["google_category"] or "",
                        "place_name": x["name"],
                        "rating": x["rating"],
                        "_target": cid,
                        "_pool": pool,
                        "_place_id": x["pid"],
                    })
                    got += 1
                if got < k:
                    p(f"  ⚠️ หมวด {cid} กอง {pool} ต้องการ {k} ได้ {got} "
                      f"(พูลเหลือ {len(cand)} หลังกันซ้ำสถานที่)")

    await engine.dispose()
    rnd.shuffle(picked)

    p("")
    p(f"สุ่มได้ {len(picked)} แถว · สถานที่ไม่ซ้ำ {len({x['_place_id'] for x in picked})}")
    pa = sum(1 for x in picked if x["_pool"] == "A")
    p(f"  กอง A (v2 ทำนายหมวดนั้น) {pa} · กอง B (v2 ไม่ทำนาย) {len(picked) - pa}")
    p("")
    p("ตัวอย่าง 8 แถวแรก (เรียงสุ่มแล้ว ไม่เรียงตามหมวดเป้าหมาย)")
    for x in picked[:8]:
        p(f"  {x['review_id']:<9} {x['place_name'][:26]:<27} {x['ข้อความรีวิว'][:44]!r}")

    if not a.write:
        p("")
        p("DRY-RUN — ยังไม่เขียนไฟล์  ลงมือจริงด้วย --write")
        return

    # ⚠️ ต้องมีช่องกรอกในไฟล์เลย ให้ merge_gold_v3_2.py อ่าน CSV ได้ตรง ๆ
    #   รอบก่อนไม่มีช่องพวกนี้ ผู้กรอกต้องไปพิมพ์เป็นบรรทัด review_id|อารมณ์|หมวด
    #   ซึ่งเป็นงานซ้ำและพิมพ์พลาดง่าย
    #   เว้นว่างทั้งสองช่อง — ช่องหมวดเป็นตัวบอกว่าแถวนี้กรอกแล้วหรือยัง
    cols = ["review_id", "ข้อความรีวิว", "stratum", "google_category",
            "place_name", "rating", "อารมณ์รวม(กรอก)", "หมวด+อารมณ์(กรอก)",
            "หมายเหตุ"]
    for x in picked:
        x.setdefault("อารมณ์รวม(กรอก)", "")
        x.setdefault("หมวด+อารมณ์(กรอก)", "")
        x.setdefault("หมายเหตุ", "")
    with open(BLANK, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore",
                           quoting=csv.QUOTE_ALL)
        w.writeheader()
        w.writerows(picked)
    with open(MANIFEST, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "text_hash", "หมวดเป้าหมาย", "กอง",
                    "place_id", "place_name"])
        for x in picked:
            w.writerow([x["review_id"], h(x["ข้อความรีวิว"]), x["_target"],
                        x["_pool"], x["_place_id"], x["place_name"]])
    p("")
    p(f"เขียน {BLANK.relative_to(ROOT)} ({len(picked)} แถว) — ไฟล์ที่ต้องกรอก")
    p(f"เขียน {MANIFEST.relative_to(ROOT)} — ที่มาของแต่ละแถว ห้ามเปิดก่อนกรอกเสร็จ")
    p("")
    p("กรอกเสร็จแล้วรวมเข้าชุด gold ด้วย")
    p(f"  uv run python scripts/merge_gold_v3_2.py <ไฟล์ป้าย> "
      f"--todo {BLANK.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
