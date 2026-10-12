"""relabel_gold_v3_1.py — ติดป้ายชุด gold v3 ใหม่ตามคู่มือ v3.1

⚠️ ป้ายทุกแถวยังติดโดย Claude ไม่ใช่คน
  v3.1 แก้ตามผลการตรวจทีละบรรทัด (gold_v3_review.csv) ซึ่งก็ตรวจโดย Claude
  ข้อจำกัดเรื่อง "ป้ายมาจากแหล่งเดียว" จึงยังอยู่ครบและต้องระบุในเล่ม

⚠️ สองชั้นของการแก้ และห้ามปนกัน
  ชั้น 1 FORCED — คำตัดสินที่สั่งมาในโจทย์ ใส่ตรงตามนั้นห้ามคิดเอง
  ชั้น 2 SWEEP  — กวาดแถวที่เหลือตามกติกาที่เขียนไว้ใน categories_v3.json
                  แก้เฉพาะที่กติกาสั่งชัด ถ้ายังกำกวมให้ส่งเข้า needs_human
  ถ้าชั้น 2 จะทับชั้น 1 ให้ชั้น 1 ชนะเสมอ และสคริปต์จะเตือน

⚠️ ห้ามใช้ข้อความ metadata เป็นหลักฐาน
  ลอกเฉพาะ "ส่วนท้าย" ของข้อความ ห้ามจับคำที่ตำแหน่งใดก็ได้
  เพราะคำบอกวันเดียวกันเป็นเนื้อความจริงได้ (4784 'รถแน่นวันธรรมดา')

รัน:
  uv run python scripts/relabel_gold_v3_1.py
  uv run python scripts/relabel_gold_v3_1.py --write
"""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "evaluation"
SRC = OUT / "gold_v3_labeled.csv"
DST = OUT / "gold_v3_1_labeled.csv"
CHANGELOG = OUT / "gold_v3_1_changelog.csv"
NEEDS = OUT / "gold_v3_1_needs_human.csv"

OLD_SRC = "claude_guided_v3"
NEW_SRC = "claude_guided_v3_1"

DROP = {"63356": "ข้อความซ้ำกับ 55824 ทุกตัวอักษร"}

# ── ชั้น 1: คำตัดสินที่สั่งมา (review_id -> overall, aspects, no_specific, เหตุผล)
FORCED: dict[str, tuple[str, str, str, str]] = {
    "108313": ("positive", "3+", "", "4+ มาจากช่องประเมินราคาของ Google ไม่ใช่คำผู้รีวิว"),
    "79816":  ("neutral", "7n", "", "'วันธรรมดา' เป็นเนื้อความจริงเรื่องวันที่เปิด"),
    "3630":   ("positive", "3+", "", "'ผู้คนน่ารัก' ระบุประเด็นแล้ว จึงไม่ใช่ไม่ระบุประเด็น"),
    "104111": ("positive", "1+", "", "ชมเป็นหลัก ติผ่าน ๆ ตามกติกาอารมณ์รวมและกติกา A"),
    "101747": ("neutral", "1+,4-,5+", "", "'ให้ผ่าน' คือชมเบา ๆ · คิดเงินเพิ่มคือติราคา"),
    "1425":   ("positive", "3+,5+,6+,7n,9+", "",
               "เพิ่ม 9+ (น้ำกำลังดี) · ปิดตามฤดู -> 7 · ตัด 11n · ห้องน้ำสะอาด -> 5"),
    "1430":   ("positive", "1+,2+,5+,6+,9+", "", "ความสะอาดห้องน้ำอยู่หมวด 5 เท่านั้น"),
    "79775":  ("positive", "8+", "", "การคัดกรองโรค -> หมวด 8"),
    "125956": ("positive", "10+", "", "โทนเดียวกับ 239678"),
    "153718": ("neutral", "2+,6-,9n", "",
               "'วัดเก่าแก่' เป็นข้อเท็จจริง -> 9n · ชมเบาพอกับติ -> neutral"),
    "26607":  ("negative", "2+,3-", "", "เป็นเรื่องสั่งผิดและความรู้พนักงาน ไม่ใช่รสชาติ"),
    "112749": ("positive", "2+", "", "การจัดสถานที่ -> หมวด 2"),
    "47507":  ("positive", "2+,11+", "", "การปรับแต่งพื้นที่ -> หมวด 2"),
    "3318":   ("positive", "8-,9+,11+", "", "'เปลี่ยว' -> หมวด 8"),
    "226197": ("negative", "7-,9-", "", "'วัดหลักปิดอยู่' -> 7- · คำติหมวด 9 เป็นหลัก"),
    "38758":  ("positive", "", "1", "ลูกค้าประจำหลายสิบปี = คำชมโดยนัย ไม่ระบุประเด็น"),
    "70346":  ("positive", "2+,6n", "", "การบอกที่ตั้ง -> 6n แบบเดียวกับ 686 และ 2032"),
    "54342":  ("positive", "6+,12n", "", "'ใกล้ มน. มากที่สุด' -> 6+ · มีแต่ชม -> positive"),
    "24108":  ("positive", "2+,4+,11+,12+", "", "ร้านขายอาหารปลา -> หมวด 12"),
    "4784":   ("neutral", "1+,6-", "", "หมวด 1 ชมเป็นหลัก ตามกติกา A"),
    "3153":   ("neutral", "12n", "", "ข้อความบอกว่าร้านรับทำอะไร ตามกติกา B"),
    "114275": ("neutral", "12n", "", "ข้อความบอกว่าร้านรับทำอะไร ตามกติกา B"),
    "108171": ("neutral", "12n", "", "ข้อความบรรยายว่าร้านเป็นอะไร ตามกติกา B"),
}

# ── ชั้น 2: กวาดตามกติกา
# ⚠️ ทุกข้อต้องอ้างกติกาได้ ห้ามใส่เพราะ "รู้สึกว่าน่าจะดีกว่า"
SWEEP: dict[str, tuple[str, str, str, str]] = {
    # routing: ร่มรื่น/อากาศ/ความเงียบ -> หมวด 2
    "1542":  ("positive", "2+,8-,9+", "", "'ร่มรื่น' -> หมวด 2 ตาม routing"),
    "153761": ("positive", "2+,5+,6+", "", "'สะดวก' -> 6 · 'ร่มรื่น' -> 2 ตาม routing"),
    # routing: เวลารอ -> หมวด 7
    "27152": ("positive", "3+,7+", "", "'ไม่ต้องรอนาน' -> หมวด 7 ตาม routing"),
    "149160": ("positive", "1+,7-", "", "'รอนาน' -> หมวด 7 (เดิมถูกแล้ว ยืนยัน)"),
    # กติกาอารมณ์รวมข้อ 2: มีแต่ชม ไม่มีติ -> positive
    "32718": ("neutral", "8n", "", "บรรยายว่ามีสนามเด็กเล่น ไม่ได้ประเมิน ตามกติกา B"),
    "82042": ("neutral", "11n", "", "บรรยายว่าเป็นที่ออกกำลังกาย ไม่ได้ประเมิน ตามกติกา B"),
    # กติกา B: บรรยายอย่างเดียว ไม่ใช่หมวด 13
    "252315": ("neutral", "6n", "", "บรรยายว่าเป็นที่รับส่งผู้โดยสาร ตามกติกา B"),
    "24211": ("neutral", "11n", "", "บรรยายกิจกรรมปลูกต้นไม้ ตามกติกา B"),
    # routing: สัตว์ที่ไม่ใช่การพาสัตว์เลี้ยง -> 13
    "10711": ("neutral", "13n", "", "แจกลูกแมว -> หมวด 13 ตาม routing (ยืนยันของเดิม)"),
    # หมวด 10 คำที่เข้าข่ายกว้างขึ้น
    "179372": ("positive", "10+", "", "'อิ่มบุญ' เข้าข่ายหมวด 10 (ยืนยันของเดิม)"),
    "68972": ("neutral", "7n,10n", "", "'ใส่บาตร' -> 10 · เวลาเริ่ม -> 7 (ยืนยันของเดิม)"),
    "108155": ("neutral", "10n", "", "'ทอดกฐิน' เข้าข่ายหมวด 10 (ยืนยันของเดิม)"),
    "125960": ("positive", "9+", "", "ชมความสวยของสถานที่ ไม่มีคำทางศาสนา"),
    # routing: คุณภาพงานร้านบริการ -> 3
    "108308": ("positive", "3+", "", "คุณภาพงานล้างรถ -> หมวด 3 (ยืนยันของเดิม)"),
    "112082": ("positive", "2+,3+", "", "คุณภาพงานล้างรถ -> หมวด 3 (ยืนยันของเดิม)"),
    # routing: ที่พัก -> 8
    "27437": ("negative", "3-,8-", "", "'ที่พักไม่ดี' -> หมวด 8 (ยืนยันของเดิม)"),
    # routing: รายการสินค้าที่อาหารเป็นรายการหนึ่ง -> 12
    "79683": ("neutral", "12n", "", "ไล่รายการสินค้าโดยอาหารเป็นรายการหนึ่ง -> 12"),
    "180810": ("positive", "1+", "", "ประเมินอาหารตรง ๆ -> หมวด 1 (ยืนยันของเดิม)"),
    # routing: เทศกาลไม่ใช่ศาสนา -> 11 + 7 ถ้ามีความแออัด
    "31873": ("neutral", "7n,11n", "", "เทศกาลอาหาร -> 11 · คนเยอะ -> 7 (ยืนยันของเดิม)"),
    "112745": ("neutral", "11n", "", "งานลอยกระทง -> 11 (ยืนยันของเดิม)"),
    "584":   ("positive", "2+,9+,10n", "", "งานประจำปีของวัด -> 10 (ยืนยันของเดิม)"),
}

OVERRIDE_NOTE = "แก้ตามคู่มือ v3.1"


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def norm(spec: str) -> str:
    """เรียงหมวดตามเลข เพื่อให้เทียบสองสเปกได้โดยไม่ติดลำดับ"""
    toks = [t.strip() for t in (spec or "").split(",") if t.strip()]
    return ",".join(sorted(toks, key=lambda t: int(t[:-1])))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    v3 = json.loads((ROOT / "shared" / "categories_v3.json").read_text(encoding="utf-8"))
    valid = {c["id"] for c in v3["categories"]}

    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    fields = list(rows[0])

    clash = set(FORCED) & set(SWEEP)
    if clash:
        p(f"⚠️ มีแถวที่อยู่ทั้งใน FORCED และ SWEEP: {sorted(clash)} — ใช้ FORCED")

    changes: list[dict] = []
    out: list[dict] = []
    rule_count: Counter = Counter()

    for r in rows:
        rid = r["review_id"]
        if rid in DROP:
            changes.append({
                "review_id": rid,
                "old_overall": r["overall_sentiment"], "new_overall": "(ลบแถว)",
                "old_aspects": r["aspects"], "new_aspects": "(ลบแถว)",
                "old_no_specific": r["no_specific_topic"], "new_no_specific": "(ลบแถว)",
                "rule": "แถวซ้ำ", "reason": DROP[rid]})
            rule_count["ลบแถวซ้ำ"] += 1
            continue

        dec = FORCED.get(rid)
        layer = "คำตัดสินที่สั่งมา"
        if dec is None:
            dec = SWEEP.get(rid)
            layer = "กวาดตามกติกา"
        if dec is None:
            out.append(r)
            continue

        ov, spec, flag, why = dec
        bad = [t for t in (x.strip() for x in spec.split(",") if x.strip())
               if not re.fullmatch(r"(1[0-3]|[1-9])[+n-]", t) or int(t[:-1]) not in valid]
        if bad:
            p(f"หยุด: แถว {rid} มีโทเคนผิดรูป {bad}")
            raise SystemExit(1)
        if flag and spec:
            p(f"หยุด: แถว {rid} ติดธงไม่ระบุประเด็นแต่ยังมีหมวด")
            raise SystemExit(1)

        same = (r["overall_sentiment"] == ov
                and norm(r["aspects"]) == norm(spec)
                and (r["no_specific_topic"] or "") == flag)
        new = dict(r)
        if not same:
            changes.append({
                "review_id": rid,
                "old_overall": r["overall_sentiment"], "new_overall": ov,
                "old_aspects": r["aspects"], "new_aspects": spec,
                "old_no_specific": r["no_specific_topic"], "new_no_specific": flag,
                "rule": layer, "reason": why})
            rule_count[layer] += 1
            new["overall_sentiment"] = ov
            new["aspects"] = spec
            new["no_specific_topic"] = flag
            new["note"] = f"{OVERRIDE_NOTE}: {why}"
            new["label_source"] = NEW_SRC
        out.append(new)

    p(f"แถวต้นทาง {len(rows)} · ลบ {len(DROP)} · เหลือ {len(out)}")
    p(f"เปลี่ยนจริง {sum(v for k, v in rule_count.items() if k != 'ลบแถวซ้ำ')} แถว")
    for k, v in rule_count.most_common():
        p(f"  {k}: {v}")
    p("")
    d = Counter(r["overall_sentiment"] or "(ว่าง)" for r in out)
    p("อารมณ์รวม: " + " · ".join(f"{k} {v}" for k, v in d.most_common()))
    agg: Counter = Counter()
    sign: dict[int, Counter] = {c: Counter() for c in sorted(valid)}
    for r in out:
        for t in (x.strip() for x in r["aspects"].split(",") if x.strip()):
            cid = int(t[:-1])
            agg[cid] += 1
            sign[cid][t[-1]] += 1
    names = {c["id"]: c["name"] for c in v3["categories"]}
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

    with open(DST, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out)
    with open(CHANGELOG, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "review_id", "old_overall", "new_overall", "old_aspects", "new_aspects",
            "old_no_specific", "new_no_specific", "rule", "reason"])
        w.writeheader()
        w.writerows(changes)
    p("")
    p(f"เขียน {DST.relative_to(ROOT)} ({len(out)} แถว)")
    p(f"เขียน {CHANGELOG.relative_to(ROOT)} ({len(changes)} แถว)")


if __name__ == "__main__":
    main()
