"""sample_gold_v3.py — สุ่มชุด gold รอบใหม่ แบบแบ่งชั้นตามประเภทสถานที่

⚠️ ทำไมต้องแบ่งชั้น ไม่สุ่มล้วน
  จาก 762 สถานที่ เป็นร้านอาหาร/คาเฟ่ 637 แห่ง (84%) คิดเป็น 81% ของการกล่าวถึง
  สุ่มล้วนจึงได้ร้านอาหารเกือบทั้งชุด แล้วหมวดของสถานที่ท่องเที่ยว วัด ตลาด
  จะมีตัวอย่างไม่พอวัดผล — ซึ่งเป็นสาเหตุที่ชุด gold เดิมมีตัวอย่าง
    หมวด 10 (สถานที่/กิจกรรม/สินค้า) แค่ 13 ใบ และหมวด 8 แค่ 11 ใบ
  ทั้งสองหมวดจึงวัดผลเชิงสถิติไม่ได้มาตั้งแต่ต้น (sd ของ F1 สูงถึง ±0.21)

⚠️ ชุดนี้ "เพิ่ม" ไม่ใช่ "แทน" ชุด gold เดิม
  gold เดิม 300 ใบ (ใช้ได้ 251) ยังอยู่ครบและห้ามแก้
  ชุดนี้เป็นไฟล์ใหม่ ติดป้ายด้วยชุดหมวด v3
  เวลารายงานผลต้องแยกกันชัดเจนว่าตัวเลขไหนมาจากชุดไหน

⚠️ ตัดรีวิวที่ซ้ำกับชุดเดิมและชุดเทรนออกก่อน
  ถ้าไม่ตัด จะเกิดข้อมูลรั่วแบบเดียวกับที่เคยเจอ 49 ใบในชุด gold เดิม
  ตัดด้วย review_id และด้วยข้อความที่ทำความสะอาดแล้ว (กันรีวิวเดียวกันคนละร้าน)

⚠️ ตัดรีวิวที่ข้อความเป็นช่วงราคา ฿X-Y ล้วน ๆ ออก (48 ใบในฐาน)
  นั่นเป็น metadata ของ Google ไม่ใช่ข้อความรีวิว ติดป้ายไม่ได้
  แต่ "ไม่" ตัดรีวิวที่มีช่วงราคาต่อท้ายข้อความจริง เพราะยังมีเนื้อหาให้อ่าน
  (คนติดป้ายต้องมองข้ามส่วนนั้นตามกติกา google_price_badge_is_not_review_text)

รัน:
  uv run python scripts/sample_gold_v3.py                 # ดูโควตาก่อน
  uv run python scripts/sample_gold_v3.py --write
"""
import argparse
import asyncio
import csv
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from db.database import engine  # noqa: E402

LAB = ROOT / "data" / "labeling"
OUT_DIR = ROOT / "reports" / "evaluation"
BLANK = OUT_DIR / "gold_v3_blank.csv"
META = OUT_DIR / "gold_v3_meta.csv"
GUIDE = OUT_DIR / "gold_v3_guide.md"

SEED = 20261013  # ⚠️ ตรึงไว้ ห้ามเปลี่ยน ไม่งั้นชุดเปลี่ยนและเทียบผลเก่าไม่ได้

# กลุ่มประเภทสถานที่ + โควตา
# ⚠️ โควตานี้ไม่ได้สะท้อนสัดส่วนจริงของสถานที่ และตั้งใจให้ไม่สะท้อน
#   เป้าหมายคือให้ทุกหมวดมีตัวอย่างพอวัดผล ไม่ใช่ให้ชุดเป็นตัวแทนประชากร
#   เวลารายงานต้องระบุข้อนี้ และห้ามเอาสัดส่วนในชุดนี้ไปอ้างเป็นสัดส่วนของจังหวัด
STRATA = [
    ("วัด/ศาสนสถาน", 40,
     "google_category ~ 'วัด|เทวสถาน|มัสยิด|โบสถ์|บูชาทางศาสนา'"),
    ("ธรรมชาติ/สวน", 30,
     "google_category ~ 'อุทยาน|สวน|น้ำตก'"),
    ("พิพิธภัณฑ์/ประวัติศาสตร์", 25,
     "google_category ~ 'พิพิธภัณฑ์|ประวัติศาสตร์|อนุสรณ์'"),
    ("ตลาด", 20, "google_category ~ 'ตลาด'"),
    ("ร้านค้า/บริการ", 20,
     "google_category ~ 'ร้านเฟอร์นิเจอร์|ร้านกล้อง|ร้านกรอบรูป|ซูเปอร์มาร์เก็ต"
     "|ล้างรถ|สตูดิโอ|ร้านอุปกรณ์'"),
    ("ท่องเที่ยวทั่วไป", 20, "google_category = 'สถานที่ท่องเที่ยว'"),
    ("อาหาร/คาเฟ่", 40,
     "google_category ~ 'ร้านอาหาร|ภัตตาคาร|ร้านกาแฟ|ก๋วยเตี๋ยว|เบเกอรี่|ขนม"
     "|ข้าวต้ม|อาหาร|คาเฟ่|ปิ้งย่าง|บาร์บีคิว|พิซซ่า|สเต็ก|ซูชิ|ราเมน|ชาบู|สุกี้|ติ่มซำ'"),
]

BAHT_ONLY = r"^฿[0-9][0-9,]*(-[0-9][0-9,]*)?$"


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def norm(s: str) -> str:
    """คีย์เทียบข้อความแบบหยาบ ใช้กันรีวิวเดียวกันคนละร้าน"""
    return re.sub(r"\s+", "", (s or "")).lower()


def load_used() -> tuple[set[int], set[str]]:
    """review_id และข้อความที่ถูกใช้ไปแล้วในชุด gold เดิมและชุดเทรน"""
    ids: set[int] = set()
    texts: set[str] = set()
    for fn in ("reviews_labeled.csv", "silver_reviews.csv"):
        f = LAB / fn
        if not f.exists():
            continue
        for r in csv.DictReader(open(f, encoding="utf-8-sig")):
            try:
                ids.add(int(r["review_id"]))
            except (KeyError, ValueError):
                pass
            t = r.get("text") or r.get("text_clean") or ""
            if t.strip():
                texts.add(norm(t))
    return ids, texts


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    used_ids, used_texts = load_used()
    p(f"ตัดออกก่อน: review_id ที่ใช้แล้ว {len(used_ids):,} · "
      f"ข้อความที่ใช้แล้ว {len(used_texts):,}")

    rnd = random.Random(SEED)
    picked: list[dict] = []
    seen_text: set[str] = set()
    report: list[tuple] = []

    async with engine.connect() as c:
        for name, quota, cond in STRATA:
            rows = (await c.execute(text(f"""
                SELECT r.id, r.rating, r.text_clean,
                       p.name AS place_name, p.google_category,
                       COALESCE(p.zone,'other') AS zone
                FROM reviews r JOIN places p ON p.id = r.place_id
                WHERE r.text_clean <> ''
                  AND LENGTH(r.text_clean) >= 15
                  AND r.text_clean !~ '{BAHT_ONLY}'
                  AND {cond}
                ORDER BY r.id"""))).mappings().all()
            pool = []
            for x in rows:
                if x["id"] in used_ids:
                    continue
                k = norm(x["text_clean"])
                if k in used_texts or k in seen_text:
                    continue
                pool.append(dict(x))
            rnd.shuffle(pool)
            # กระจายให้ครบหลายสถานที่ก่อน ไม่ให้กระจุกร้านเดียว
            by_place = defaultdict(list)
            for x in pool:
                by_place[x["place_name"]].append(x)
            take: list[dict] = []
            places = list(by_place)
            rnd.shuffle(places)
            while len(take) < quota and any(by_place[q] for q in places):
                for q in places:
                    if len(take) >= quota:
                        break
                    if by_place[q]:
                        take.append(by_place[q].pop())
            for x in take:
                x["stratum"] = name
                seen_text.add(norm(x["text_clean"]))
            picked += take
            report.append((name, quota, len(pool), len(take),
                           len({x["place_name"] for x in take})))

    await engine.dispose()

    p("")
    p(f"{'กลุ่ม':<26} {'โควตา':>6} {'มีให้เลือก':>10} {'ได้':>5} {'สถานที่':>8}")
    p("-" * 62)
    for name, quota, npool, ntake, nplace in report:
        warn = "" if ntake >= quota else "  <- ไม่ครบโควตา"
        p(f"{name:<26} {quota:>6} {npool:>10,} {ntake:>5} {nplace:>8}{warn}")
    p("-" * 62)
    p(f"{'รวม':<26} {sum(r[1] for r in report):>6} "
      f"{sum(r[2] for r in report):>10,} {len(picked):>5} "
      f"{len({x['place_name'] for x in picked}):>8}")

    if not a.write:
        p("")
        p("นี่คือ DRY-RUN — ยังไม่เขียนไฟล์  ลงมือจริงด้วย --write")
        return

    rnd.shuffle(picked)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(BLANK, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "ข้อความรีวิว", "อารมณ์รวม", "หมวด+อารมณ์",
                    "ไม่ระบุประเด็น"])
        for x in picked:
            w.writerow([x["id"], x["text_clean"], "", "", ""])

    # ⚠️ meta แยกไฟล์ ไม่ปนในไฟล์ที่ใช้ติดป้าย
    #   ถ้าคนติดป้ายเห็นประเภทสถานที่ จะเดาหมวดจากประเภท ไม่ได้อ่านข้อความ
    with open(META, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "stratum", "google_category", "place_name",
                    "zone", "rating"])
        for x in picked:
            w.writerow([x["id"], x["stratum"], x["google_category"],
                        x["place_name"], x["zone"], x["rating"]])

    v3 = json.loads((ROOT / "shared" / "categories_v3.json").read_text(encoding="utf-8"))
    g = [f"# คู่มือติดป้ายชุด gold v3 ({len(picked)} รายการ)", "",
         f"ไฟล์ที่ต้องกรอก: `{BLANK.name}`", "",
         "## ชุดนี้คืออะไร", "",
         "ชุด gold เดิม 300 ใบสุ่มมาแบบไม่แบ่งชั้น จึงเป็นร้านอาหารเกือบทั้งชุด",
         "ทำให้หมวดของสถานที่ท่องเที่ยว วัด ตลาด มีตัวอย่างไม่พอวัดผล",
         "ชุดนี้บังคับโควตาตามประเภทสถานที่ เพื่อให้ทุกหมวดวัดผลได้", "",
         "⚠️ **ชุดนี้ไม่เป็นตัวแทนประชากร** สัดส่วนประเภทสถานที่ถูกบิดโดยเจตนา",
         "ห้ามเอาสัดส่วนในชุดนี้ไปอ้างเป็นสัดส่วนของจังหวัด", "",
         "⚠️ ติดป้ายด้วย **ชุดหมวด v3 (13 หมวด)** ไม่ใช่ v2 ที่ระบบใช้อยู่", "",
         "## วิธีกรอก", "",
         "| ช่อง | กรอกอะไร |", "|---|---|",
         "| อารมณ์รวม | `p` = ชม · `n` = กลางๆ · `g` = ติ |",
         "| หมวด+อารมณ์ | `<เลขหมวด><เครื่องหมาย>` คั่นจุลภาค · `+` ชม `n` กลางๆ `-` ติ |",
         "| ไม่ระบุประเด็น | ใส่ `1` ถ้าชมหรือติแบบไม่บอกว่าเรื่องอะไร แล้วเว้นช่องหมวดว่าง |",
         "", "ตัวอย่าง `3-,1+` = ติบริการ ชมอาหาร", "",
         "ไม่แน่ใจจริง ๆ ให้เว้นว่าง ดีกว่าเดา (ช่องว่างถูกข้าม ไม่นับผิด)", "",
         "## หมวดทั้งหมด", "",
         "| เลข | ชื่อหมวด | ใช้กับ | ครอบคลุมอะไร |", "|---|---|---|---|"]
    scope_th = {"all": "ทุกที่", "food": "ร้านอาหาร/คาเฟ่", "place": "สถานที่ท่องเที่ยว"}
    for c in v3["categories"]:
        g.append(f"| {c['id']} | {c['name']} | {scope_th.get(c['scope'], c['scope'])} "
                 f"| {c['covers']} |")
    g += ["", "## หัวข้อที่ไม่มีหมวดของตัวเอง — ส่งเข้าหมวดไหน", "",
          "หัวข้อพวกนี้พบในข้อมูลจริงแต่น้อยเกินกว่าจะตั้งเป็นหมวด", "",
          "| ถ้ารีวิวพูดถึง | ใช้หมวด |", "|---|---|"]
    for k, v in v3["routing"].items():
        if not k.startswith("_"):
            g.append(f"| {k} | {v} |")
    g += ["", "## กติกาที่ต้องใช้", ""]
    for key, r in v3["labeling_rules"].items():
        if key.startswith("_") or not isinstance(r, dict):
            continue
        g += [f"### {r.get('title', key)}", ""]
        rule = r.get("rule")
        if isinstance(rule, list):
            g += rule + [""]
        elif rule:
            g += [f"**{rule}**", ""]
        if r.get("aspect_level_note"):
            g += [f"⚠️ {r['aspect_level_note']}", ""]
        if r.get("why"):
            g += ["ที่มา:"] + [f"- {w}" for w in r["why"]] + [""]
    g += ["## การกระจายของชุดนี้", "",
          "| กลุ่มประเภทสถานที่ | จำนวน | สถานที่ |", "|---|---|---|"]
    cnt = Counter(x["stratum"] for x in picked)
    for name, _, _, ntake, nplace in report:
        g.append(f"| {name} | {cnt[name]} | {nplace} |")
    g += ["", f"รวม **{len(picked)}** รายการ จาก "
          f"**{len({x['place_name'] for x in picked})}** สถานที่", ""]
    GUIDE.write_text("\n".join(g) + "\n", encoding="utf-8")

    p("")
    p(f"เขียนไฟล์ให้กรอก : {BLANK.relative_to(ROOT)}  ({len(picked)} แถว)")
    p(f"เขียนข้อมูลกำกับ : {META.relative_to(ROOT)}  (ไม่ให้คนติดป้ายดู)")
    p(f"เขียนคู่มือ      : {GUIDE.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
