"""check_gold_v3_1.py — ตรวจชุด gold v3.1 ตามเงื่อนไขที่โจทย์กำหนด + ออกไฟล์ที่ต้องให้คนตัดสิน

⚠️ สคริปต์นี้ต้องล้มเหลวเสียงดังถ้าเงื่อนไขใดไม่ผ่าน
  ไม่ใช่เตือนแล้วปล่อยผ่าน เพราะไฟล์นี้จะถูกใช้เป็นชุดวัดผล
  ถ้ามีแถวผิดรูปหลุดไป ตัวเลขทุกตัวที่คำนวณจากมันจะเชื่อไม่ได้

เงื่อนไขที่ตรวจ (ตามโจทย์)
  1. ทุกโทเคนใน aspects ตรงรูปแบบ ^(1[0-3]|[1-9])[+n-]$
  2. ไม่มีหมวดซ้ำในแถวเดียว
  3. แถวที่ no_specific_topic=1 ต้องมี aspects ว่าง
  4. แถว positive ห้ามมีแต่หมวดเครื่องหมายลบ · negative ห้ามมีแต่บวก (ยกเว้นแถวติดธง)
  5. แถว neutral ห้ามมีแต่หมวดเครื่องหมายบวก
  6. จำนวนแถวเท่ากับ 194 และ review_id ไม่ซ้ำ
  7. ทุก review_id ในตารางคำตัดสินที่สั่งมา มีป้ายตรงตามที่สั่งเป๊ะ

รัน:
  uv run python scripts/check_gold_v3_1.py
  uv run python scripts/check_gold_v3_1.py --write-needs-human
"""
import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.relabel_gold_v3_1 import FORCED, norm  # noqa: E402

OUT = ROOT / "reports" / "evaluation"
SRC = OUT / "gold_v3_1_labeled.csv"
NEEDS = OUT / "gold_v3_1_needs_human.csv"
EXPECT_ROWS = 194
TOKEN = re.compile(r"^(1[0-3]|[1-9])[+n-]$")

# ⚠️ รายการนี้ต้องสั้นและซื่อสัตย์ ห้ามใส่เพิ่มเพื่อให้ดูรอบคอบ
#   เกณฑ์: กติกาที่เขียนไว้ตอบไม่ได้จริง ไม่ใช่แค่ "ตัดสินยาก"
NEEDS_HUMAN = [
    ("157064", "หมวด 1 มีทั้งชม (อร่อย) และติ (ได้น้อย) น้ำหนักใกล้เคียง "
               "กติกา A บอกให้ใส่ n แต่ 'ไม่ค่อยอิ่ม' อาจหนักพอให้เป็น 1-"),
    ("110130", "อร่อยเมื่อเจ้าของทำ ไม่อร่อยเมื่อลูกน้องทำ "
               "เป็นเงื่อนไขเรื่องคน ไม่ใช่ความเห็นเดียว กติกา A ตอบไม่ตรง"),
    ("143310", "ให้ 1 ดาวแต่ข้อความชมล้วน กฎ 7 บอกให้ยึดข้อความ "
               "แต่ส่วนต่างนี้มากพอที่คนควรยืนยัน"),
    ("3316", "'ก็โอเคนะ แต่แนะนำให้แวะเฉพาะถ้าผ่านมาพอดี' "
             "เป็นการแนะนำแบบมีเงื่อนไข ถือเป็นติหรือไม่ กติกาไม่ได้เขียน"),
    ("47509", "'เพราะ ฉัน อยู่ ใน หมู่ บ้าน นี้ ดีที่สุด' เป็นข้อความที่แปลด้วยเครื่อง "
              "ตีความได้หลายทาง"),
    ("26934", "ข้อความอ่านไม่ออก เว้น overall_sentiment ว่างไว้ "
              "ต้องให้คนยืนยันว่าควรตัดออกจากชุดหรือเก็บไว้เป็นกรณีศึกษา"),
]


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-needs-human", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    fail: list[str] = []

    p("=" * 70)
    p("ตรวจชุด gold v3.1")
    p("=" * 70)

    # 6. จำนวนแถว + id ไม่ซ้ำ
    dup = [k for k, v in Counter(r["review_id"] for r in rows).items() if v > 1]
    ok6 = len(rows) == EXPECT_ROWS and not dup
    p(f"  [{'ผ่าน' if ok6 else 'ตก'}] จำนวนแถว {len(rows)} (ต้องเป็น {EXPECT_ROWS}) "
      f"· id ซ้ำ {len(dup)}")
    if not ok6:
        fail.append(f"จำนวนแถว {len(rows)} หรือมี id ซ้ำ {dup[:5]}")

    bad_tok, dup_cat, flag_bad, sign_bad, neu_bad = [], [], [], [], []
    for r in rows:
        rid = r["review_id"]
        toks = [t.strip() for t in r["aspects"].split(",") if t.strip()]
        for t in toks:
            if not TOKEN.match(t):
                bad_tok.append(f"{rid}:{t}")
        cids = [t[:-1] for t in toks]
        if len(cids) != len(set(cids)):
            dup_cat.append(rid)
        flag = (r["no_specific_topic"] or "").strip() == "1"
        if flag and toks:
            flag_bad.append(rid)
        signs = {t[-1] for t in toks}
        ov = r["overall_sentiment"]
        if toks and not flag:
            if ov == "positive" and signs == {"-"}:
                sign_bad.append(f"{rid} positive แต่มีแต่ลบ")
            if ov == "negative" and signs == {"+"}:
                sign_bad.append(f"{rid} negative แต่มีแต่บวก")
            if ov == "neutral" and signs == {"+"}:
                neu_bad.append(rid)

    for name, bad, num in (
        ("ทุกโทเคนตรงรูปแบบ", bad_tok, 1),
        ("ไม่มีหมวดซ้ำในแถวเดียว", dup_cat, 2),
        ("แถวติดธงต้องไม่มีหมวด", flag_bad, 3),
        ("อารมณ์รวมไม่ขัดกับเครื่องหมายหมวด", sign_bad, 4),
        ("แถว neutral ไม่มีแต่หมวดบวก", neu_bad, 5),
    ):
        p(f"  [{'ผ่าน' if not bad else 'ตก'}] {num}. {name}"
          + (f" — ผิด {len(bad)}: {bad[:6]}" if bad else ""))
        if bad:
            fail.append(f"{name}: {bad[:6]}")

    # 7. คำตัดสินที่สั่งมาต้องตรงเป๊ะ
    byid = {r["review_id"]: r for r in rows}
    mism = []
    for rid, (ov, spec, flag, _why) in FORCED.items():
        r = byid.get(rid)
        if r is None:
            mism.append(f"{rid} ไม่อยู่ในไฟล์")
            continue
        if (r["overall_sentiment"] != ov or norm(r["aspects"]) != norm(spec)
                or (r["no_specific_topic"] or "") != flag):
            mism.append(f"{rid} ได้ [{r['overall_sentiment']}] {r['aspects']}"
                        f" ควรเป็น [{ov}] {spec}")
    p(f"  [{'ผ่าน' if not mism else 'ตก'}] 7. คำตัดสินที่สั่งมา {len(FORCED)} แถวตรงเป๊ะ"
      + (f" — ไม่ตรง {mism[:4]}" if mism else ""))
    if mism:
        fail.append(f"คำตัดสินที่สั่งมาไม่ตรง: {mism[:4]}")

    p("")
    d = Counter(r["overall_sentiment"] or "(ว่าง)" for r in rows)
    p("อารมณ์รวม: " + " · ".join(f"{k} {v}" for k, v in d.most_common()))
    agg = Counter()
    for r in rows:
        for t in (x.strip() for x in r["aspects"].split(",") if x.strip()):
            agg[int(t[:-1])] += 1
    p("คู่ (หมวด, อารมณ์) รวม " + str(sum(agg.values())))
    p("ติดธงไม่ระบุประเด็น " + str(sum(1 for r in rows
                                       if (r["no_specific_topic"] or "").strip() == "1")))
    p("label_source: " + " · ".join(
        f"{k} {v}" for k, v in Counter(r["label_source"] for r in rows).most_common()))

    if a.write_needs_human:
        with open(NEEDS, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["review_id", "text", "overall_sentiment", "aspects", "reason"])
            for rid, why in NEEDS_HUMAN:
                r = byid.get(rid, {})
                w.writerow([rid, r.get("text", ""), r.get("overall_sentiment", ""),
                            r.get("aspects", ""), why])
        p("")
        p(f"เขียน {NEEDS.relative_to(ROOT)} ({len(NEEDS_HUMAN)} แถว)")

    p("")
    p("=" * 70)
    if fail:
        p(f"ไม่ผ่าน {len(fail)} ข้อ")
        for x in fail:
            p(f"  {x}")
        sys.exit(1)
    p("ผ่านทุกข้อ")


if __name__ == "__main__":
    main()
