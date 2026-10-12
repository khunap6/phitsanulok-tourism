"""fix_gold_v3_scope.py — ตัดรีวิวนอกขอบเขตออกจากชุด gold v3.1 แล้วสุ่มเติมให้ครบ

⚠️ ทำไมต้องทำ
  ชุด gold v3.1 สุ่มมาก่อนที่จะมีนิยามขอบเขต (shared/scope.json)
  ตัวสุ่มเดิมตั้งโควตา "ร้านค้า/บริการ 20" ไว้เอง โดยไม่ได้ตรวจก่อนว่า
  ร้านพวกนั้นอยู่ในขอบเขตของโจทย์ไหม ผลคือมีรีวิวร้านกล้อง สตูดิโอถ่ายภาพ
  ร้านกรอบรูป ร้านเฟอร์นิเจอร์ หลุดเข้ามา 15 แถว

⚠️ กลุ่ม "ร้านค้า/บริการ" ถูกยุบทิ้ง ไม่ใช่เติมใหม่
  หลังใช้นิยามขอบเขต กลุ่มนี้เหลือสถานที่ในขอบเขตแค่ 2 แห่ง
  (ร้านดอยคำ กับ วิษณุคาร์แคร์ ซึ่งทั้งคู่เป็น override_in เพราะมี type cafe)
  การเติมโควตา 20 จากสองแห่งจะได้รีวิวกระจุกร้านเดียว ซึ่งแย่กว่าไม่มีกลุ่มนี้เลย
  จึงกระจายโควตาไปกลุ่มอื่น โดยเพิ่มให้ตลาดและท่องเที่ยวทั่วไปเป็นหลัก
  (ผู้ใช้ยืนยันแล้วว่าตลาดอยู่ในขอบเขต)

⚠️ แถวที่เหลือไม่ถูกแตะเลย
  179 แถวที่อยู่ในขอบเขตคงป้ายเดิมทุกตัวอักษร รวมถึง label_source
  แถวใหม่ที่สุ่มมาจะยังไม่มีป้าย ต้องติดป้ายแยกแล้วรวมเข้าด้วย
  apply_gold_v3_labels.py

รัน:
  uv run python scripts/fix_gold_v3_scope.py
  uv run python scripts/fix_gold_v3_scope.py --write
"""
import argparse
import asyncio
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from db.database import engine  # noqa: E402

LAB = ROOT / "data" / "labeling"
OUT = ROOT / "reports" / "evaluation"
SRC = OUT / "gold_v3_1_labeled.csv"
META = OUT / "gold_v3_meta.csv"
KEPT = OUT / "gold_v3_2_labeled.csv"
TODO = OUT / "gold_v3_2_to_label.csv"
DROPPED = OUT / "gold_v3_2_dropped.csv"
SCOPE_CSV = ROOT / "reports" / "scope_classification.csv"

SEED = 20261013

# โควตาใหม่ รวม 195 เท่าเดิม แต่ไม่มีกลุ่มร้านค้า/บริการ
STRATA = [
    ("วัด/ศาสนสถาน", 40,
     "google_category ~ 'วัด|เทวสถาน|มัสยิด|โบสถ์|บูชาทางศาสนา'"),
    ("ธรรมชาติ/สวน", 30, "google_category ~ 'อุทยาน|สวน|น้ำตก'"),
    ("พิพิธภัณฑ์/ประวัติศาสตร์", 25,
     "google_category ~ 'พิพิธภัณฑ์|ประวัติศาสตร์|อนุสรณ์'"),
    ("ตลาด", 25, "google_category ~ 'ตลาด'"),
    ("ท่องเที่ยวทั่วไป", 25, "google_category = 'สถานที่ท่องเที่ยว'"),
    ("อาหาร/คาเฟ่", 50,
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
    return re.sub(r"\s+", "", (s or "")).lower()


def load_used() -> tuple[set[int], set[str]]:
    """ทุก review_id และข้อความที่เคยถูกใช้ ไม่ว่าในชุดไหน — กันข้อมูลรั่ว"""
    ids: set[int] = set()
    texts: set[str] = set()
    files = [LAB / "reviews_labeled.csv", LAB / "silver_reviews.csv", SRC]
    for f in files:
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

    in_scope = {int(r["id"]): r["in_scope"] == "True"
                for r in csv.DictReader(open(SCOPE_CSV, encoding="utf-8-sig"))}
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    meta = {r["review_id"]: r for r in csv.DictReader(open(META, encoding="utf-8-sig"))}

    async with engine.connect() as c:
        place_of = {str(r[0]): r[1] for r in (await c.execute(text(
            "SELECT id, place_id FROM reviews WHERE id = ANY(:ids)"),
            {"ids": [int(r["review_id"]) for r in rows]})).all()}

        keep, drop = [], []
        for r in rows:
            pid = place_of.get(r["review_id"])
            (keep if in_scope.get(pid, True) else drop).append(r)

        p(f"ชุดเดิม {len(rows)} แถว -> คงไว้ {len(keep)} · ตัดออก {len(drop)}")
        p("")
        p("ที่ตัดออก")
        for r in drop:
            st = meta.get(r["review_id"], {}).get("stratum", "?")
            p(f"  id={r['review_id']:<8} [{st:<22}] {r['text'][:52]}")

        # กลุ่มที่ยังเหลืออยู่ของแถวที่คงไว้
        have = Counter(meta.get(r["review_id"], {}).get("stratum", "?") for r in keep)
        p("")
        p(f"{'กลุ่ม':<26} {'โควตาใหม่':>10} {'มีแล้ว':>8} {'ต้องเติม':>9}")
        need: dict[str, int] = {}
        for name, quota, _cond in STRATA:
            n = max(0, quota - have.get(name, 0))
            need[name] = n
            p(f"{name:<26} {quota:>10} {have.get(name, 0):>8} {n:>9}")
        gone = sum(v for k, v in have.items() if k not in need)
        if gone:
            p(f"{'(กลุ่มที่ยุบทิ้ง)':<26} {'-':>10} {gone:>8} {'-':>9}")

        import random
        rnd = random.Random(SEED)
        used_ids, used_texts = load_used()
        picked: list[dict] = []
        seen_text: set[str] = set()
        for name, _quota, cond in STRATA:
            k = need[name]
            if not k:
                continue
            cand = (await c.execute(text(f"""
                SELECT r.id, r.rating, r.text_clean, p.id AS pid,
                       p.name AS place_name, p.google_category
                FROM reviews r JOIN places p ON p.id = r.place_id
                WHERE r.text_clean <> '' AND LENGTH(r.text_clean) >= 15
                  AND r.text_clean !~ '{BAHT_ONLY}'
                  AND {cond}
                ORDER BY r.id"""))).mappings().all()
            pool = []
            for x in cand:
                if x["id"] in used_ids or not in_scope.get(x["pid"], True):
                    continue
                t = norm(x["text_clean"])
                if t in used_texts or t in seen_text:
                    continue
                pool.append(dict(x))
            rnd.shuffle(pool)
            by_place = defaultdict(list)
            for x in pool:
                by_place[x["place_name"]].append(x)
            places = list(by_place)
            rnd.shuffle(places)
            take: list[dict] = []
            while len(take) < k and any(by_place[q] for q in places):
                for q in places:
                    if len(take) >= k:
                        break
                    if by_place[q]:
                        take.append(by_place[q].pop())
            for x in take:
                x["stratum"] = name
                seen_text.add(norm(x["text_clean"]))
            if len(take) < k:
                p(f"⚠️ {name}: เติมได้ {len(take)} จาก {k} ที่ต้องการ")
            picked += take
    await engine.dispose()

    p("")
    p(f"สุ่มเติม {len(picked)} แถว จาก {len({x['place_name'] for x in picked})} สถานที่")
    p(f"ชุดใหม่จะมี {len(keep)} + {len(picked)} = {len(keep) + len(picked)} แถว")

    if not a.write:
        p("")
        p("DRY-RUN — ยังไม่เขียนไฟล์  ลงมือจริงด้วย --write")
        return

    with open(KEPT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(keep)
    with open(DROPPED, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) + ["stratum"])
        w.writeheader()
        for r in drop:
            w.writerow({**r, "stratum": meta.get(r["review_id"], {}).get("stratum", "?")})
    with open(TODO, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "ข้อความรีวิว", "stratum", "google_category",
                    "place_name", "rating"])
        for x in picked:
            w.writerow([x["id"], x["text_clean"], x["stratum"],
                        x["google_category"], x["place_name"], x["rating"]])
    p("")
    p(f"เขียน {KEPT.relative_to(ROOT)} ({len(keep)} แถว ป้ายเดิมไม่แตะ)")
    p(f"เขียน {DROPPED.relative_to(ROOT)} ({len(drop)} แถว)")
    p(f"เขียน {TODO.relative_to(ROOT)} ({len(picked)} แถว รอติดป้าย)")


if __name__ == "__main__":
    asyncio.run(main())
