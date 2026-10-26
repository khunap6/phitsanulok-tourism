"""convert_gold_v2_to_v3.py — แปลงชุด gold v2 (300 แถวในฐาน) มาเป็นหมวดชุด v3

ชุด gold v2 คือแถวที่ `analyzed_reviews.label_source = 'claude_guided'` 300 แถว
ไม่ซ้ำกับชุด gold v3.2 เลยแม้แถวเดียว (วัดแล้ว) จึงเอามาเพิ่มได้เต็มจำนวน

⚠️ แปลงเครื่องได้ไม่หมด และ "แปลงได้" ไม่เท่ากับ "เชื่อได้"
  หมวด v2 แปด หมวดแมปตัวต่อตัว (CLEAN) ส่วนหมวด 2, 3, 10 ของ v2 ถูกแยก
  เป็นหลายหมวดใน v3 ตามเนื้อหา จึงต้องอ่านข้อความ ไม่มีสูตร

⚠️ และแถวที่แมปตัวต่อตัวได้ก็ยังเชื่อไม่ได้ทุกแถว
  ป้าย v2 ติดด้วยคู่มือที่มีข้อขัดแย้งที่บันทึกไว้แล้ว (limitations 2.4)
  กติกาสามข้อที่เปลี่ยนใน v3 ต้องเอามาตรวจย้อน ไม่ใช่แปลงแล้วจบ
    1. ป้ายราคาของ Google — gold v2 เคยให้หมวดราคาเป็นบวกจาก metadata
       ('อร่อยครับ ฿200-300' ได้ 5+ ทั้งที่ผู้รีวิวไม่ได้พูดเรื่องราคา)
    2. กติกาชั่งน้ำหนักอารมณ์รวม — กฎ v2 ข้อ 1 เขียนว่า "มีการติ = negative"
       ซึ่งทำให้ positive และ neutral เกิดขึ้นไม่ได้เลย แถวที่มีทั้งบวกและลบ
       จึงต้องตัดสินอารมณ์รวมใหม่
    3. กติกาสักการะ — v2 บังคับให้ไปหมวด 2 ซึ่ง v3 แยกเป็นหมวด 10
  แถวที่เข้าข่ายข้อใดข้อหนึ่งถูกส่งไปกองที่ต้องอ่าน ไม่แปลงอัตโนมัติ

⚠️ ตัดแถวนอกขอบเขตออก ตาม shared/scope.json
  เพื่อให้เงื่อนไขเดียวกับชุด v3.2 ที่ตัดไปแล้ว 15 แถว

⚠️ ไฟล์ที่ให้คนอ่าน **ไม่ลบป้ายส่วนที่ไม่กำกวม**
  เหตุผล: ถ้าให้อ่านใหม่หมดทั้ง 142 แถว เป็นงานเท่ากับติดป้ายชุดใหม่ทั้งชุด
  จึงเก็บป้ายส่วนที่แมปตัวต่อตัวได้ไว้ แล้วเว้นเฉพาะส่วนที่กำกวมจริง
  พร้อมเขียนคำถามเจาะจงให้ว่าต้องตัดสินอะไร
  ข้อแลก: ผู้อ่านถูกยึดโยงกับป้าย v2 ในส่วนที่ไม่ได้เว้น — ต้องบันทึกเป็นข้อจำกัด

รัน:
  uv run python scripts/convert_gold_v2_to_v3.py
  uv run python scripts/convert_gold_v2_to_v3.py --write
"""
import argparse
import asyncio
import csv
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from db.database import engine  # noqa: E402

OUT = ROOT / "reports" / "evaluation"
GOLD = OUT / "gold_v3_2_labeled.csv"
TODO = OUT / "gold_v3_3_to_label.csv"
DROPPED = OUT / "gold_v3_3_dropped.csv"
BACKUP_DIR = ROOT / "backup"
SRC_LABEL = "claude_guided"
NEW_SOURCE = "converted_v2_to_v3"

# หมวด v2 ที่แมปตัวต่อตัว — ย้อนจากคอลัมน์ from_v2 ของ data/labeling/categories_v3.csv
# ไม่มีสองตัวที่ชี้ไปหมวด v3 เดียวกัน จึงไม่มีทางเกิดหมวดซ้ำในแถวเดียว
CLEAN = {1: 1, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7, 9: 8, 11: 13}
# หมวด v2 ที่ v3 แยกออกเป็นหลายหมวด -> ต้องอ่านข้อความ
AMBIG = {
    2: ("10 หรือ 14", "หมวด 2 ของ v2 รวมคำสักการะกับคำชมลอยไว้ด้วยกัน "
                      "ถ้าพูดถึงการสักการะ -> 10 · ถ้าชม/ติโดยรวมไม่ระบุประเด็น -> 14"),
    3: ("2 หรือ 9", "หมวด 3 ของ v2 รวมบรรยากาศกับทัศนียภาพไว้ด้วยกัน "
                    "ถ้าเป็นบรรยากาศ/การตกแต่ง -> 2 · ถ้าเป็นวิว/สิ่งที่มาชม -> 9"),
    10: ("9 หรือ 11 หรือ 12", "หมวด 10 ของ v2 เป็นถุงรวมสามเรื่อง "
                              "สิ่งที่มาชม -> 9 · กิจกรรมที่ทำ -> 11 · สินค้า/บริการ -> 12"),
}
SG = {"positive": "+", "neutral": "n", "negative": "-"}
BAHT = re.compile("฿\\s*\\d")
TAILS = re.compile(r"(วันธรรมดา|วันหยุด|วันเสาร์-อาทิตย์|สุดสัปดาห์|วันธรร|วันเส|"
                   r"รับประทานที่ร|ประเภทการ|ประเภทก|การประเมินราคา|\d+:\d{2})\s*$")
WORSHIP = re.compile("กราบ|สักการะ|ไหว้พระ|ขอพร|ทำบุญ|อิ่มบุญ|นมัสการ|แก้บน|ใส่บาตร|"
                     "ทอดกฐิน|สวดมนต์|ทำสมาธิ|พิธีกรรม|ศักดิ์สิทธิ์|ขลัง|ศรัทธา|"
                     "ประดิษฐาน|หลวงพ่อ")


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def reasons(r, aspects) -> list[str]:
    """เหตุที่แถวนี้แปลงอัตโนมัติไม่ได้ — คืนลิสต์ว่างถ้าแปลงได้"""
    out = []
    amb = sorted({x["category_id"] for x in aspects} & set(AMBIG))
    if amb:
        out.append("หมวด v2 " + "/".join(map(str, amb)) + " กำกวม")
    signs = {x["aspect_sentiment"] for x in aspects}
    if {"positive", "negative"} <= signs:
        out.append("มีทั้งหมวดบวกและลบ ต้องชั่งน้ำหนักอารมณ์รวมใหม่")
    t = (r["text_clean"] or "").strip()
    if BAHT.search(t):
        out.append("มีป้ายราคาของ Google ในข้อความ")
    if TAILS.search(t):
        out.append("ลงท้ายด้วย metadata ของ Google")
    if WORSHIP.search(t):
        out.append("มีคำสักการะ กติกาเปลี่ยนเป็นหมวด 10")
    if len(t) < 10:
        out.append("ข้อความสั้นกว่า 10 อักขระ")
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    v3 = json.loads((ROOT / "shared" / "categories_v3.json").read_text(encoding="utf-8"))
    valid = {c["id"] for c in v3["categories"]}
    n3 = {c["id"]: c["name"] for c in v3["categories"]}
    missing = sorted(set(CLEAN.values()) - valid)
    if missing:
        p(f"หยุด: CLEAN ชี้ไปหมวดที่ไม่มีใน categories_v3.json {missing}")
        sys.exit(1)

    gold = list(csv.DictReader(open(GOLD, encoding="utf-8-sig")))
    fields = list(gold[0])
    have = {r["review_id"] for r in gold}

    async with engine.connect() as c:
        rows = (await c.execute(text("""
            SELECT a.review_id, a.overall_sentiment, r.text_clean,
                   p.in_scope, p.name AS place_name, p.google_category
            FROM analyzed_reviews a
            JOIN reviews r ON r.id = a.review_id
            JOIN places p ON p.id = r.place_id
            WHERE a.label_source = :src ORDER BY a.review_id"""),
            {"src": SRC_LABEL})).mappings().all()
        asp = (await c.execute(text("""
            SELECT ra.review_id, ra.category_id, ra.aspect_sentiment
            FROM review_aspects ra
            JOIN analyzed_reviews a ON a.review_id = ra.review_id
            WHERE a.label_source = :src
            ORDER BY ra.review_id, ra.category_id"""), {"src": SRC_LABEL})).mappings().all()
    await engine.dispose()

    by: dict[int, list] = {}
    for x in asp:
        by.setdefault(x["review_id"], []).append(x)

    p(f"ชุด gold v2 {len(rows)} แถว · คู่ (หมวด, อารมณ์) {len(asp)}")
    dup = [str(r["review_id"]) for r in rows if str(r["review_id"]) in have]
    p(f"ซ้ำกับชุด v3.2 ที่มีอยู่ {len(dup)} แถว")
    p("")

    conv, todo, dropped, errs = [], [], [], []
    for r in rows:
        rid = str(r["review_id"])
        aspects = by.get(r["review_id"], [])
        if rid in have:
            continue
        if not r["in_scope"]:
            dropped.append({"review_id": rid, "text": r["text_clean"],
                            "place_name": r["place_name"],
                            "reason": "นอกขอบเขตตาม shared/scope.json"})
            continue
        if not aspects:
            todo.append((r, aspects, ["ไม่มีแถวใน review_aspects"]))
            continue
        why = reasons(r, aspects)
        if why:
            todo.append((r, aspects, why))
            continue
        toks = [f"{CLEAN[x['category_id']]}{SG[x['aspect_sentiment']]}" for x in aspects]
        cids = [t[:-1] for t in toks]
        if len(cids) != len(set(cids)):
            errs.append(f"id={rid} แปลงแล้วได้หมวดซ้ำ {toks}")
            continue
        ov = r["overall_sentiment"]
        signs = {t[-1] for t in toks}
        if ov == "positive" and signs == {"-"}:
            errs.append(f"id={rid} positive แต่มีแต่หมวดลบ {toks}")
            continue
        if ov == "negative" and signs == {"+"}:
            errs.append(f"id={rid} negative แต่มีแต่หมวดบวก {toks}")
            continue
        if ov == "neutral" and signs == {"+"}:
            errs.append(f"id={rid} neutral แต่มีแต่หมวดบวก {toks}")
            continue
        old = ",".join(f"{x['category_id']}{SG[x['aspect_sentiment']]}" for x in aspects)
        conv.append({
            "review_id": rid, "text": r["text_clean"],
            "overall_sentiment": ov, "aspects": ",".join(toks),
            "no_specific_topic": "",
            "note": f"แปลงจากหมวด v2 {old} ด้วย convert_gold_v2_to_v3.py "
                    f"(แมปตัวต่อตัว ไม่มีการตีความใหม่)",
            "label_source": NEW_SOURCE,
        })

    p(f"{'แปลงอัตโนมัติได้':<40} {len(conv):>4} แถว")
    p(f"{'ต้องให้คนอ่าน':<40} {len(todo):>4} แถว")
    p(f"{'ตัดออกเพราะนอกขอบเขต':<40} {len(dropped):>4} แถว")
    if errs:
        p("")
        p(f"หยุด: {len(errs)} แถวแปลงแล้วขัดกับกติกา")
        for e in errs[:10]:
            p("  " + e)
        sys.exit(1)

    cnt = Counter()
    for r in gold:
        for t in (x.strip() for x in r["aspects"].split(",") if x.strip()):
            cnt[int(t[:-1])] += 1
    for r in conv:
        for t in r["aspects"].split(","):
            cnt[int(t[:-1])] += 1
    p("")
    p(f"ชุดใหม่จะมี {len(gold)} + {len(conv)} = {len(gold) + len(conv)} แถว")
    p("")
    p(f"{'id':>3} {'หมวด':<34} {'รวม':>5}  สถานะ")
    for cid in sorted(valid):
        tot = cnt.get(cid, 0)
        p(f"{cid:>3} {n3[cid][:33]:<34} {tot:>5}  "
          f"{'วัดได้' if tot >= 20 else f'ยังขาด {20 - tot}'}")

    p("")
    p("เหตุที่ต้องให้คนอ่าน (นับซ้ำได้ แถวเดียวมีได้หลายเหตุ)")
    rc: Counter = Counter()
    for _, _, why in todo:
        for w in why:
            rc[w] += 1
    for w, k in rc.most_common():
        p(f"  {k:>4}  {w}")

    if not a.write:
        p("")
        p("DRY-RUN — ยังไม่เขียนไฟล์  ลงมือจริงด้วย --write")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"gold_before_v2convert_{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(GOLD, dest / GOLD.name)

    with open(GOLD, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(gold + conv)

    # ⚠️ แยกคอลัมน์ "อ่านเท่านั้น" ออกจาก "ช่องกรอก" อย่างเด็ดขาด
    #   เคยลองเติมค่าลงช่องกรอกไว้ล่วงหน้าแล้วพัง เพราะแยกไม่ออกว่าแถวไหน
    #   ถูกกรอกแล้วจริง — merge นับเป็นกรอกแล้ว 107 แถวทั้งที่กรอกจริง 2 แถว
    #
    #   หมวดที่แมปได้แล้ว  = อ่านเท่านั้น merge จะเอาไปรวมกับที่กรอกให้เอง
    #                        ผู้อ่านจึงพิมพ์แค่หมวดที่กำกวม ไม่ต้องพิมพ์ซ้ำ
    #   หมวด+อารมณ์(กรอก) = เว้นว่างทุกแถว ใช้เป็นตัวบอกว่าแถวนี้กรอกแล้วหรือยัง
    #   อารมณ์รวม(กรอก)   = เติมค่าเดิมของ v2 ไว้ได้ เพราะไม่ได้ใช้ตัดสินว่ากรอกแล้ว
    #                        **ยกเว้น** แถวที่มีทั้งหมวดบวกและลบ ต้องเว้นว่าง
    #                        เพราะค่าเดิมมาจากกฎ v2 ข้อ 1 ที่ขัดกันเอง
    #                        ("มีการติ = negative" ทำให้ positive/neutral เกิดไม่ได้เลย)
    #                        ถ้าเติมไว้ ผู้อ่านจะถูกยึดโยงกับค่าที่รู้แล้วว่าเชื่อไม่ได้
    MIX = "มีทั้งหมวดบวกและลบ ต้องชั่งน้ำหนักอารมณ์รวมใหม่"
    with open(TODO, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["review_id", "ข้อความรีวิว", "place_name", "google_category",
                    "ต้องตัดสินอะไร", "หมวดที่แมปได้แล้ว", "อารมณ์รวมเดิม(v2)",
                    "อารมณ์รวม(กรอก)", "หมวด+อารมณ์(กรอก)", "หมายเหตุ"])
        for r, aspects, why in todo:
            keep = [f"{CLEAN[x['category_id']]}{SG[x['aspect_sentiment']]}"
                    for x in aspects if x["category_id"] in CLEAN]
            ask = []
            for x in aspects:
                if x["category_id"] in AMBIG:
                    tgt, expl = AMBIG[x["category_id"]]
                    ask.append(f"v2 {x['category_id']}{SG[x['aspect_sentiment']]} "
                               f"-> {tgt} ({expl})")
            ask += [w2 for w2 in why if not w2.startswith("หมวด v2 ")]
            ov_old = r["overall_sentiment"] or ""
            prefill_ov = "" if MIX in why else {"positive": "p", "neutral": "n",
                                                "negative": "g"}.get(ov_old, "")
            w.writerow([r["review_id"], r["text_clean"], r["place_name"],
                        r["google_category"] or "", " | ".join(ask),
                        ",".join(keep), ov_old, prefill_ov, "", ""])

    with open(DROPPED, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["review_id", "text", "place_name", "reason"])
        w.writeheader()
        w.writerows(dropped)

    p("")
    p(f"สำรองชุดเดิมไว้ที่ {(dest / GOLD.name).relative_to(ROOT)}")
    p(f"เขียน {GOLD.relative_to(ROOT)} ({len(gold) + len(conv)} แถว)")
    p(f"เขียน {TODO.relative_to(ROOT)} ({len(todo)} แถว) — ไฟล์ที่ต้องให้คนอ่าน")
    p(f"เขียน {DROPPED.relative_to(ROOT)} ({len(dropped)} แถว) — ที่ตัดออก")
    p("")
    p("กรอกเสร็จแล้วรวมด้วย")
    p(f"  uv run python scripts/merge_gold_v3_2.py <ไฟล์ป้าย> "
      f"--todo {TODO.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
