"""merge_gold_v3_2.py — รวมแถวที่ติดป้ายใหม่เข้ากับชุด gold v3.2 แล้วตรวจ

⚠️ แถวเดิม 179 แถวไม่ถูกแตะเลย รวมถึง label_source
  แถวใหม่ได้ label_source = claude_guided_v3_2 เพื่อให้แยกออกว่ามาจากรอบไหน
  ถ้าภายหลังพบว่ารอบใดติดป้ายคลาดเคลื่อน จะย้อนดูได้ว่ากระทบแถวไหนบ้าง

⚠️ ตรวจเงื่อนไขเดียวกับ check_gold_v3_1.py ก่อนเขียนเสมอ
  ถ้าไม่ตรวจ แถวผิดรูปจะหลุดเข้าชุดวัดผล แล้วตัวเลขทุกตัวที่คำนวณจากมันเชื่อไม่ได้

รัน:
  uv run python scripts/merge_gold_v3_2.py <ไฟล์ป้าย> [--write]
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "evaluation"
KEPT = OUT / "gold_v3_2_labeled.csv"
TODO = OUT / "gold_v3_2_to_label.csv"
# ⚠️ ไม่ฝังช่วงเลขหมวดในรูปแบบนี้ — ความถูกต้องของเลขตรวจด้วย valid
#   ซึ่งอ่านจาก shared/categories_v3.json เพื่อให้มีแหล่งความจริงเดียว
#   (เดิมเขียน 1[0-3] ไว้ พอเพิ่มหมวด 14 ป้ายที่ถูกต้องจะถูกตีตกว่าผิดรูป)
TOKEN = re.compile(r"^([1-9][0-9]?)[+n-]$")

# หมวดที่ห้ามใส่ควบกับหมวดอื่น ตามกติกา overall_impression_is_a_category
#   หมวด 14 ใช้ได้เฉพาะเมื่อไม่มีหมวด 1-12 ใดใช้ได้เลย ถ้าใส่ควบได้
#   มันจะกลายเป็นถังขยะที่แปะกับทุกรีวิว แล้ววัดผลหมวดนี้ไม่ได้
EXCLUSIVE_IDS = {"14"}
# รับทั้งอักษรย่อและคำเต็ม
#   ไฟล์ที่ให้กรอกมีคอลัมน์ อารมณ์รวมเดิม(v2) ที่แสดงคำเต็ม (positive/neutral/negative)
#   อยู่ติดกับช่องกรอกที่เติม p/n/g ไว้ ผู้กรอกจึงพิมพ์คำเต็มตามที่เห็นข้างๆ เป็นธรรมดา
#   เคยตีตกทั้ง 142 แถวเพราะเหตุนี้ — เป็นข้อบกพร่องของไฟล์ ไม่ใช่ของผู้กรอก
OVERALL = {"p": "positive", "n": "neutral", "g": "negative",
           "positive": "positive", "neutral": "neutral", "negative": "negative"}
NEW_SRC = "claude_guided_v3_2"


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--write", action="store_true")
    # ⚠️ ไฟล์ "รอติดป้าย" เปลี่ยนได้ตามรอบการสุ่ม
    #   รอบแก้ขอบเขตใช้ gold_v3_2_to_label.csv (20 แถว ใช้หมดแล้ว)
    #   รอบเติมหมวดที่ขาดใช้ gold_v3_2_rare_to_label.csv จาก sample_rare_categories.py
    #   ต้องอ้างไฟล์ให้ตรงรอบ ไม่งั้น review_id จะถูกตีตกว่า "ไม่อยู่ในรายการที่รอติดป้าย"
    ap.add_argument("--todo", default=None,
                    help="ไฟล์รายการที่รอติดป้าย (ค่าเริ่มต้น reports/evaluation/"
                         "gold_v3_2_to_label.csv)")
    a = ap.parse_args()

    v3 = json.loads((ROOT / "shared" / "categories_v3.json").read_text(encoding="utf-8"))
    valid = {c["id"] for c in v3["categories"]}
    names = {c["id"]: c["name"] for c in v3["categories"]}

    kept = list(csv.DictReader(open(KEPT, encoding="utf-8-sig")))
    fields = list(kept[0])
    todo_path = Path(a.todo) if a.todo else TODO
    if not todo_path.is_absolute() and not todo_path.exists():
        todo_path = ROOT / a.todo
    if not todo_path.exists():
        p(f"หยุด: ไม่พบไฟล์รายการที่รอติดป้าย {todo_path}")
        sys.exit(1)
    todo = {r["review_id"]: r
            for r in csv.DictReader(open(todo_path, encoding="utf-8-sig"))}
    p(f"รายการที่รอติดป้ายอ่านจาก {todo_path.name}")

    new: list[dict] = []
    errs: list[str] = []
    seen: set[str] = set()
    for fn in a.files:
        f = Path(fn)
        if not f.is_absolute() and not f.exists():
            f = ROOT / fn
        # ⚠️ รับสองรูปแบบ
        #   .csv  = กรอกในตารางตรง ๆ ใช้คอลัมน์ อารมณ์รวม(กรอก) + หมวด+อารมณ์(กรอก)
        #   อื่น  = ไฟล์ข้อความบรรทัดละ review_id|อารมณ์|หมวด|หมายเหตุ
        # มี .csv เพราะชุด 142 แถวที่แปลงจาก v2 ต้องให้คนกรอกทีละแถว
        #   ถ้าบังคับให้พิมพ์เป็นบรรทัด ผู้กรอกต้องพิมพ์ส่วนที่แมปไว้แล้วซ้ำทุกแถว
        #   ซึ่งเป็นงานซ้ำซ้อนและเป็นจุดที่พิมพ์พลาดได้ง่าย
        if f.suffix.lower() == ".csv":
            lines = []
            n_rows = 0
            for i, row in enumerate(csv.DictReader(open(f, encoding="utf-8-sig")), 2):
                need = ("review_id", "อารมณ์รวม(กรอก)", "หมวด+อารมณ์(กรอก)")
                miss = [k for k in need if k not in row]
                if miss:
                    p(f"หยุด: {f.name} ไม่มีคอลัมน์ {miss}")
                    sys.exit(1)
                n_rows += 1
                rid = (row["review_id"] or "").strip()
                typed = (row["หมวด+อารมณ์(กรอก)"] or "").strip()
                # ⚠️ ตัวบอกว่า "กรอกแล้ว" คือช่องหมวดที่กรอกเท่านั้น
                #   ไม่ใช้อารมณ์รวม เพราะช่องนั้นมีค่าเติมไว้ล่วงหน้าอยู่แล้ว
                if not rid or not typed:
                    continue
                ov = (row["อารมณ์รวม(กรอก)"] or "").strip()
                # ⚠️ ช่อง "หมวด+อารมณ์(กรอก)" คือ **รายการเต็ม** ไม่ใช่ส่วนที่เพิ่มเข้ามา
                #   คอลัมน์ "หมวดที่แมปได้แล้ว" เป็นข้อมูลให้อ่านประกอบเท่านั้น
                #
                #   เดิมออกแบบให้เอาสองช่องมารวมกัน แล้วใช้ = นำหน้าเพื่อสั่งไม่ให้รวม
                #   แต่พอผู้ใช้กรอกจริง 142 แถว ไม่มีใครใช้ = เลย และหลักฐานชี้ชัดว่า
                #   เขาถือว่าช่องนี้เป็นรายการเต็ม:
                #     - 89 แถวพิมพ์ครอบคลุมหมวดที่แมปไว้ครบ
                #     - 12 แถวที่มีป้ายราคาของ Google เขาตัดหมวดราคาออกถูกทุกแถว
                #       (102674 'อร่อยครับ ฿200-300' แมป 1+,4+ -> กรอก 1+ เท่านั้น)
                #     - 7 แถวที่ไม่ทับกันเลย อ่านแล้วเป็นการตัด/ย้ายหมวดโดยตั้งใจทุกแถว
                #   ถ้าเอามารวมกันจะได้หมวดซ้ำ 100 แถว และจะใส่หมวดราคาที่ผิดกลับเข้าไป
                #   = ที่นำหน้ายังรับอยู่ เพื่อไม่ให้ไฟล์ที่เขียนตามกติกาเดิมพัง
                spec = typed[1:].strip() if typed.startswith("=") else typed
                note = (row.get("หมายเหตุ") or "").strip()
                lines.append((i, f"{rid}|{ov}|{spec}|{note}"))
            p(f"  {f.name} มี {n_rows} แถว กรอกแล้ว {len(lines)} แถว")
        else:
            lines = list(enumerate(f.read_text(encoding="utf-8").splitlines(), 1))
        for ln, raw in lines:
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            parts = (raw.split("|") + ["", "", ""])[:4]
            rid, ov, spec, note = (x.strip() for x in parts)
            if rid not in todo:
                errs.append(f"{f.name}:{ln} review_id {rid} ไม่อยู่ในรายการที่รอติดป้าย")
                continue
            if rid in seen:
                errs.append(f"{f.name}:{ln} review_id {rid} ซ้ำ")
                continue
            seen.add(rid)
            ov = ov.lower()
            if ov and ov not in OVERALL:
                errs.append(f"{f.name}:{ln} อารมณ์รวม '{ov}' ต้องเป็น p/n/g")
                continue
            toks = [t.strip() for t in spec.split(",") if t.strip()]
            bad = [t for t in toks if not TOKEN.match(t) or int(t[:-1]) not in valid]
            if bad:
                errs.append(f"{f.name}:{ln} โทเคนผิดรูป {bad}")
                continue
            cids = [t[:-1] for t in toks]
            if len(cids) != len(set(cids)):
                errs.append(f"{f.name}:{ln} มีหมวดซ้ำในแถวเดียว")
                continue
            excl = EXCLUSIVE_IDS & set(cids)
            if excl and len(cids) > 1:
                errs.append(f"{f.name}:{ln} หมวด {sorted(excl)} ต้องอยู่เดี่ยว "
                            f"แต่ใส่มากับ {sorted(set(cids) - excl)}")
                continue
            flag = "ไม่ระบุประเด็น" in note
            if flag and toks:
                errs.append(f"{f.name}:{ln} ติดธงแต่ยังมีหมวด")
                continue
            if ov and not toks and not flag:
                errs.append(f"{f.name}:{ln} มีอารมณ์รวมแต่ไม่มีหมวดและไม่ติดธง")
                continue
            signs = {t[-1] for t in toks}
            o = OVERALL.get(ov, "")
            if toks and not flag:
                if o == "positive" and signs == {"-"}:
                    errs.append(f"{f.name}:{ln} positive แต่มีแต่หมวดลบ")
                    continue
                if o == "negative" and signs == {"+"}:
                    errs.append(f"{f.name}:{ln} negative แต่มีแต่หมวดบวก")
                    continue
                if o == "neutral" and signs == {"+"}:
                    errs.append(f"{f.name}:{ln} neutral แต่มีแต่หมวดบวก")
                    continue
            new.append({"review_id": rid, "text": todo[rid]["ข้อความรีวิว"],
                        "overall_sentiment": o, "aspects": ",".join(toks),
                        "no_specific_topic": "1" if flag else "",
                        "note": note, "label_source": NEW_SRC})

    miss = [k for k in todo if k not in seen]
    p(f"รอติดป้าย {len(todo)} · ติดแล้ว {len(new)} · ยังไม่ติด {len(miss)}")
    if miss:
        p(f"  {miss}")
    if errs:
        p("")
        p(f"พบข้อผิดพลาด {len(errs)} จุด — ไม่เขียนไฟล์")
        for e in errs[:20]:
            p(f"  {e}")
        sys.exit(1)

    allrows = kept + new
    ids = [r["review_id"] for r in allrows]
    dup = [k for k, v in Counter(ids).items() if v > 1]
    if dup:
        p(f"หยุด: review_id ซ้ำ {dup[:6]}")
        sys.exit(1)

    p("")
    p(f"ชุดใหม่ {len(allrows)} แถว (เดิม {len(kept)} + ใหม่ {len(new)})")
    d = Counter(r["overall_sentiment"] or "(ว่าง)" for r in allrows)
    p("อารมณ์รวม: " + " · ".join(f"{k} {v}" for k, v in d.most_common()))
    agg: Counter = Counter()
    sign: dict[int, Counter] = {c: Counter() for c in sorted(valid)}
    for r in allrows:
        for t in (x.strip() for x in r["aspects"].split(",") if x.strip()):
            cid = int(t[:-1])
            agg[cid] += 1
            sign[cid][t[-1]] += 1
    p(f"คู่ (หมวด, อารมณ์) {sum(agg.values())} · ติดธง "
      f"{sum(1 for r in allrows if r['no_specific_topic'])}")
    p("")
    p(f"{'id':>3} {'หมวด':<40} {'รวม':>5} {'+':>4} {'n':>4} {'-':>4}  วัดได้ไหม")
    for cid in sorted(valid):
        tot = agg[cid]
        p(f"{cid:>3} {names[cid][:39]:<40} {tot:>5} {sign[cid]['+']:>4} "
          f"{sign[cid]['n']:>4} {sign[cid]['-']:>4}  "
          f"{'วัดได้' if tot >= 20 else 'ข้อมูลน้อย'}")

    if not a.write:
        p("")
        p("DRY-RUN — ยังไม่เขียนไฟล์  ลงมือจริงด้วย --write")
        return

    with open(KEPT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(allrows)
    p("")
    p(f"เขียน {KEPT.relative_to(ROOT)} ({len(allrows)} แถว)")


if __name__ == "__main__":
    main()
