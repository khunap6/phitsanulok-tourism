"""human_check_v3.py — ชุดให้คนตรวจป้าย gold v3.2 แล้วคำนวณความสอดคล้อง

⚠️ ทำไมต้องมี
  ป้ายในชุด gold v3.2 ทั้ง 199 แถวติดโดย Claude และการตรวจทีละบรรทัดก็ทำโดย Claude
  ตัวเลขทุกตัวที่คำนวณจากชุดนี้จึงวัด "ความเหมือน Claude" ไม่ใช่ความถูกต้อง
  รอบ v2 เคยให้คนตรวจแล้วได้ kappa อารมณ์รวม 0.8156 และหมวด micro-F1 0.8101
  ซึ่งต่ำกว่าที่โมเดลทำได้ (0.8771) แปลว่าโมเดลเหมือน Claude มากกว่าที่คนเหมือน Claude
  รอบนี้ต้องวัดซ้ำบนชุดหมวดใหม่ เพราะหมวดเปลี่ยนไป 4 หมวดและกติกาเพิ่ม 7 ข้อ

⚠️ สุ่มแบบถ่วงน้ำหนัก ไม่ใช่สุ่มล้วน
  ชุดนี้บังคับให้มีกลุ่มที่ "ป้ายของ Claude อ่อนที่สุด" ครบ
    1. 6 แถวที่กติกาตอบไม่ได้จริง (needs_human)
    2. 27 แถวที่เพิ่งแก้ในรอบ v3.1 — ป้ายใหม่สุด ผ่านการตรวจน้อยสุด
    3. แถวที่ใช้หมวดใหม่ 9/10/11/12 — เป็นเหตุผลทั้งหมดของการทำ v3
    4. แถวที่มี metadata ของ Google ปน — ทดสอบว่าคนอ่านข้ามได้ไหม
    5. แถวธรรมดาที่ไม่ได้แก้ — เป็นฐานเทียบ
  ⚠️ ค่าที่ได้จึงเป็นความสอดคล้องบน "เคสที่ยากกว่าค่าเฉลี่ย" ต้องระบุในเล่ม

⚠️ กันปัญหาไฟล์เสียหายที่เกิดขึ้นจริงในรอบ v2
  รอบนั้นไฟล์ที่กรอกกลับมาหายไป 1 แถว (ข้อความมีอัญประกาศโค้ง "...")
  และอีก 1 แถวข้อความเพี้ยน จึงรอบนี้
    - เทียบด้วย review_id ไม่ใช่ลำดับแถว
    - เก็บ sha1 ของข้อความไว้ในไฟล์ ถ้าข้อความเปลี่ยนจะรู้ทันที
    - --score รายงานแถวหาย แถวเกิน และแถวที่ข้อความเพี้ยน แล้วข้ามเฉพาะแถวนั้น
      ไม่ล้มทั้งไฟล์และไม่เงียบ

⚠️ ห้ามเปิดไฟล์ gold_v3_2_labeled.csv ก่อนกรอกเสร็จ
  ถ้าเห็นป้ายของ Claude ก่อน ค่าที่ได้ใช้อ้างอิงไม่ได้เลย

รัน
  uv run python scripts/human_check_v3.py --make
  (กรอกไฟล์ human_check_v3_blank.csv แล้วค่อยรัน)
  uv run python scripts/human_check_v3.py --score
"""
import argparse
import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.human_check import kappa, kappa_word  # noqa: E402

OUT = ROOT / "reports" / "evaluation"
# ⚠️ ใช้ชุดที่ตัดรีวิวนอกขอบเขตออกแล้ว (gold_v3_2) ไม่ใช่ v3_1
#   v3_1 มีรีวิวร้านกล้อง สตูดิโอ ร้านเฟอร์นิเจอร์ ปนอยู่ 15 แถว
#   ซึ่งอยู่นอกขอบเขตตาม shared/scope.json
GOLD = OUT / "gold_v3_2_labeled.csv"
CHANGELOG = OUT / "gold_v3_1_changelog.csv"
NEEDS = OUT / "gold_v3_1_needs_human.csv"   # ยังใช้ได้ id ไม่เปลี่ยน
BLANK = OUT / "human_check_v3_blank.csv"
# ผลการให้คะแนนในรูป JSON ให้ scripts/measure_everything.py อ่านไปรวมในเล่ม
RESULT = OUT / "human_check_v3_result.json"
GUIDE = OUT / "human_check_v3_guide.md"

SEED = 20261013
N_DEFAULT = 100
NEW_CATS = {9, 10, 11, 12}
SENTS = ["positive", "neutral", "negative"]
OVERALL = {"p": "positive", "n": "neutral", "g": "negative",
           "positive": "positive", "neutral": "neutral", "negative": "negative"}
SIGN = {"+": "positive", "n": "neutral", "-": "negative"}
META_PAT = re.compile(
    r"฿[0-9]|[0-9]+:[0-9][0-9]|^[0-9]+ (ปี|เดือน|สัปดาห์|วัน|ชั่วโมง|นาที)ที่ผ่านมา"
    r"|(วันธรรมดา|วันหยุด|สุดสัปดาห์|วันเสาร์-อาทิตย์|รับประทานที่ร)")


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def h(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def parse_spec(spec: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for tok in (t.strip() for t in (spec or "").split(",") if t.strip()):
        if len(tok) >= 2 and tok[:-1].isdigit() and tok[-1] in SIGN:
            out[int(tok[:-1])] = SIGN[tok[-1]]
    return out


def load_gold() -> list[dict]:
    return list(csv.DictReader(open(GOLD, encoding="utf-8-sig")))


def groups_of(rows: list[dict]) -> dict[str, list[str]]:
    changed = {r["review_id"] for r in csv.DictReader(
        open(CHANGELOG, encoding="utf-8-sig")) if r["new_overall"] != "(ลบแถว)"}
    needs = {r["review_id"] for r in csv.DictReader(
        open(NEEDS, encoding="utf-8-sig"))}
    g: dict[str, list[str]] = defaultdict(list)
    for r in rows:
        rid = r["review_id"]
        cats = set(parse_spec(r["aspects"]))
        if rid in needs:
            g["กติกาตอบไม่ได้"].append(rid)
        elif r.get("label_source") == "claude_guided_v3_2":
            g["ติดป้ายรอบแก้ขอบเขต"].append(rid)
        elif rid in changed:
            g["เพิ่งแก้ใน v3.1"].append(rid)
        elif cats & NEW_CATS:
            g["ใช้หมวดใหม่ 9/10/11/12"].append(rid)
        elif META_PAT.search(r["text"]):
            g["มี metadata ปน"].append(rid)
        else:
            g["แถวธรรมดา"].append(rid)
    return g


def make(n: int) -> None:
    rows = load_gold()
    byid = {r["review_id"]: r for r in rows}
    g = groups_of(rows)
    rnd = random.Random(SEED)

    # เอาสองกลุ่มแรกทั้งหมด แล้วเติมที่เหลือตามสัดส่วน
    picked: list[str] = []
    picked += g["กติกาตอบไม่ได้"]
    picked += g["ติดป้ายรอบแก้ขอบเขต"]
    picked += g["เพิ่งแก้ใน v3.1"]
    quota = {"ใช้หมวดใหม่ 9/10/11/12": 0.45, "มี metadata ปน": 0.20,
             "แถวธรรมดา": 0.35}
    left = max(0, n - len(picked))
    for name, frac in quota.items():
        pool = [x for x in g[name] if x not in picked]
        rnd.shuffle(pool)
        picked += pool[:round(left * frac)]
    rnd.shuffle(picked)

    OUT.mkdir(parents=True, exist_ok=True)
    with open(BLANK, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(["review_id", "text_hash", "ข้อความรีวิว",
                    "อารมณ์รวม(คนกรอก)", "หมวด+อารมณ์(คนกรอก)", "ไม่ระบุประเด็น"])
        for rid in picked:
            w.writerow([rid, h(byid[rid]["text"]), byid[rid]["text"], "", "", ""])

    v3 = json.loads((ROOT / "shared" / "categories_v3.json").read_text(encoding="utf-8"))
    cnt = Counter()
    rev = {rid: name for name, ids in g.items() for rid in ids}
    for rid in picked:
        cnt[rev[rid]] += 1

    L = [f"# ชุดให้คนตรวจป้าย gold v3.2 ({len(picked)} รายการ)", "",
         "⚠️ **ไฟล์นี้ generate อัตโนมัติ** แก้ที่ `scripts/human_check_v3.py`", "",
         f"ไฟล์ที่ต้องกรอก: `{BLANK.name}`", "",
         "## ทำไมต้องกรอก", "",
         f"ป้ายในชุด gold v3.2 ทั้ง {len(rows)} แถวติดโดย Claude "
         "และการตรวจทีละบรรทัด",
         "ก็ทำโดย Claude ตัวเลขทุกตัวที่คำนวณจากชุดนี้จึงวัด **ความเหมือน Claude**",
         "ไม่ใช่ความถูกต้อง", "",
         "รอบ v2 เคยวัดแล้วได้ kappa อารมณ์รวม **0.8156** และหมวด micro-F1 **0.8101**",
         "ซึ่ง**ต่ำกว่า**ที่โมเดลทำได้ (0.8771) แปลว่าโมเดลเหมือน Claude",
         "มากกว่าที่คนเหมือน Claude — ตัวเลขของโมเดลจึงไม่ใช่ความถูกต้อง",
         "และรอบนั้นคุณจับผิด gold ได้ 3 ใน 3 ใบที่มีช่วงราคา `฿` ต่อท้าย", "",
         "รอบนี้ต้องวัดซ้ำ เพราะหมวดเปลี่ยนไป 4 หมวดและกติกาเพิ่ม 7 ข้อ", "",
         "## กติกาการกรอก", "",
         "1. **ห้ามเปิด `gold_v3_2_labeled.csv` ก่อนกรอกเสร็จ** ถ้าเห็นป้ายของ Claude",
         "   ก่อน ค่าที่ได้ใช้อ้างอิงไม่ได้เลย",
         "2. ช่อง `อารมณ์รวม(คนกรอก)` กรอก **p** = ชม · **n** = กลางๆ · **g** = ติ",
         "   (พิมพ์เต็มว่า positive/neutral/negative ก็ได้)",
         "3. ช่อง `หมวด+อารมณ์(คนกรอก)` กรอกทุกหมวดที่รีวิวประเมิน คั่นด้วยจุลภาค",
         "   รูปแบบ `<เลขหมวด><เครื่องหมาย>` โดย `+` ชม · `n` กลางๆ · `-` ติ",
         "   ตัวอย่าง `3-,1+` = ติบริการ ชมอาหาร",
         "4. ช่อง `ไม่ระบุประเด็น` ใส่ `1` ถ้าชมหรือติแบบไม่บอกว่าเรื่องอะไร",
         "   แล้วเว้นช่องหมวดว่างไว้",
         "5. ไม่แน่ใจจริง ๆ ให้เว้นว่าง ดีกว่าเดา (ช่องว่างถูกข้าม ไม่นับผิด)",
         "6. กรอกไม่ครบก็ส่งได้ สคริปต์รายงานให้ว่าครอบคลุมกลุ่มไหนไปแล้วบ้าง",
         "7. กรอกเสร็จรัน `uv run python scripts/human_check_v3.py --score`", "",
         "## ⚠️ เรื่องการบันทึกไฟล์ (รอบก่อนไฟล์เสียหาย)", "",
         "รอบ v2 ไฟล์ที่กรอกกลับมา **หายไป 1 แถว** (ข้อความมีอัญประกาศโค้ง)",
         "และอีก 1 แถวข้อความเพี้ยน รอบนี้จึงมีคอลัมน์ `text_hash` กำกับไว้", "",
         "- **ห้ามแก้คอลัมน์ `review_id`, `text_hash`, `ข้อความรีวิว`** กรอกแค่ 3 ช่องขวา",
         "- ถ้าใช้ Excel ให้บันทึกเป็น **CSV UTF-8 (Comma delimited)**",
         "- ถ้าแถวหายหรือข้อความเพี้ยน สคริปต์จะบอกว่าแถวไหน แล้วข้ามเฉพาะแถวนั้น",
         "  ไม่ล้มทั้งไฟล์และไม่เงียบ", "",
         "## หมวดทั้งหมด", "",
         "| เลข | ชื่อหมวด | ครอบคลุมอะไร |", "|---|---|---|"]
    for c in v3["categories"]:
        L.append(f"| {c['id']} | {c['name']} | {c['covers']} |")
    L += ["", "⚠️ หมวดใดใช้กับสถานที่ประเภทใดก็ได้ ไม่มีข้อจำกัด", "",
          "## กติกาและ routing", "",
          f"อ่านฉบับเต็มที่ `reports/evaluation/gold_v3_guide.md` "
          f"({len([k for k in v3['routing'] if not k.startswith('_')])} เรื่อง routing · "
          f"{len([k for k in v3['labeling_rules'] if not k.startswith('_')])} กติกา)",
          "",
          "สรุปข้อที่ใช้บ่อย", "",
          "- **อารมณ์รวม** มีแต่ติ→ติ · มีแต่ชม→ชม · มีทั้งคู่ให้ชั่งน้ำหนัก",
          "  (ติเป็นหลัก→ติ · ชมเป็นหลักติผ่านๆ→ชม · พอกัน→กลางๆ) · ไม่มีทั้งคู่→กลางๆ",
          "- **หมวดเดียวมีทั้งชมและติ** ชั่งน้ำหนักในหมวดนั้น พอกันใส่ `n`",
          "  ห้ามใส่หมวดเดียวกันสองครั้ง",
          "- **บรรยายอย่างเดียวไม่ได้ประเมิน** ใส่หมวดที่บรรยายถึงด้วย `n`",
          "  หมวด 13 ใช้เฉพาะที่ไม่เกี่ยวกับสถานที่เลย",
          "- **ความสะอาดห้องน้ำ** → หมวด 5 เท่านั้น",
          "- **ร่มรื่น อากาศ ความเงียบ การจัดพื้นที่** → หมวด 2",
          "- **วิว ธรรมชาติในฐานะสิ่งที่มาชม** → หมวด 9",
          "- **เวลารอ คิว ปิดร้าน เวลาทำการ** → หมวด 7",
          "- **คุณภาพงานร้านบริการ ความเป็นมิตรของคน** → หมวด 3", "",
          "⚠️ **ข้อความที่เป็น metadata ของ Google ห้ามใช้เป็นหลักฐาน**",
          "ช่วงราคา `฿200-300` · `การประเมินราคา ...` · `วันธรรมดา` ท้ายข้อความ ·",
          "`รับประทานที่ร้าน` · `0:08` · วันที่นำหน้า",
          "แต่ถ้าคำบอกวันอยู่กลางประโยคมันเป็นเนื้อความจริง เช่น 'รถแน่นวันธรรมดา'", "",
          "## การกระจายของชุดนี้", "",
          "⚠️ ชุดนี้ **ถ่วงน้ำหนักให้มีเคสยาก** ไม่ใช่สุ่มล้วน",
          "ค่าที่ได้จึงเป็นความสอดคล้องบนเคสที่ยากกว่าค่าเฉลี่ย ต้องระบุในเล่ม", "",
          "| กลุ่ม | จำนวน | ทำไมอยู่ในชุด |", "|---|---|---|"]
    why = {"กติกาตอบไม่ได้": "กติกาที่เขียนไว้ตอบไม่ได้จริง เอามาทั้งหมด",
           "ติดป้ายรอบแก้ขอบเขต": "เพิ่งติดป้ายสดใหม่ ยังไม่เคยมีใครตรวจ เอามาทั้งหมด",
           "เพิ่งแก้ใน v3.1": "ป้ายใหม่สุด ผ่านการตรวจน้อยสุด เอามาทั้งหมด",
           "ใช้หมวดใหม่ 9/10/11/12": "เป็นเหตุผลทั้งหมดของการทำ v3",
           "มี metadata ปน": "ทดสอบว่าคนอ่านข้าม metadata ได้ไหม",
           "แถวธรรมดา": "ฐานเทียบ"}
    for name in why:
        if cnt[name]:
            L.append(f"| {name} | {cnt[name]} | {why[name]} |")
    L += ["", f"รวม **{len(picked)}** รายการ จาก {len(rows)} แถวในชุด gold v3.2", ""]
    GUIDE.write_text("\n".join(L) + "\n", encoding="utf-8")

    p(f"สร้างชุดให้คนตรวจ {len(picked)} รายการ")
    p(f"  ไฟล์ให้กรอก : {BLANK.relative_to(ROOT)}")
    p(f"  คู่มือ      : {GUIDE.relative_to(ROOT)}")
    p("")
    for name in why:
        if cnt[name]:
            p(f"  {name:<26} {cnt[name]:>3}")


def score() -> None:
    if not BLANK.exists():
        p(f"ไม่พบ {BLANK} — รัน --make ก่อน")
        return
    gold = {r["review_id"]: r for r in load_gold()}
    rows = list(csv.DictReader(open(BLANK, encoding="utf-8-sig")))
    g = groups_of(load_gold())
    rev = {rid: name for name, ids in g.items() for rid in ids}

    # ── ตรวจความสมบูรณ์ของไฟล์ก่อน ──
    seen, broken, missing_g = set(), [], []
    for r in rows:
        rid = r.get("review_id", "").strip()
        if rid not in gold:
            missing_g.append(rid)
            continue
        seen.add(rid)
        if r.get("text_hash", "").strip() and r["text_hash"].strip() != h(r["ข้อความรีวิว"]):
            broken.append(rid)
    p("=" * 70)
    p("  ความสอดคล้องระหว่างคนกับป้าย gold v3.2")
    p("=" * 70)
    p(f"ไฟล์มี {len(rows)} แถว · ตรงกับชุด gold {len(seen)}")
    if missing_g:
        p(f"⚠️ review_id ที่ไม่อยู่ในชุด gold {len(missing_g)}: {missing_g[:6]}")
    if broken:
        p(f"⚠️ ข้อความเพี้ยนจากต้นฉบับ {len(broken)} แถว (ข้ามแถวนี้): {broken[:6]}")
    p("")

    ov_h, ov_g, used = [], [], []
    tp = fp = fn = 0
    sh, sg = [], []
    n_asp = 0
    flag_tp = flag_fp = flag_fn = 0
    # ⚠️ ช่วงเลขหมวดมาจาก shared/categories_v3.json แหล่งเดียว
    #   เดิมฝัง range(1, 14) ไว้ พอเพิ่มหมวด 14 แล้วหมวดนั้นหายจากรายงาน
    #   โดยไม่มีข้อความเตือนใด ๆ (นับถูกแต่ไม่พิมพ์ออกมา)
    _cv3 = json.loads(
        (ROOT / "shared" / "categories_v3.json").read_text(encoding="utf-8"))
    CAT_IDS = sorted(c["id"] for c in _cv3["categories"])
    per_cat = {c: Counter() for c in CAT_IDS}
    for r in rows:
        rid = r.get("review_id", "").strip()
        if rid not in gold or rid in broken:
            continue
        G = gold[rid]
        v = (r.get("อารมณ์รวม(คนกรอก)") or "").strip().lower()
        hv = OVERALL.get(v)
        if hv and G["overall_sentiment"]:
            ov_h.append(hv)
            ov_g.append(G["overall_sentiment"])
            used.append(rid)
        hflag = (r.get("ไม่ระบุประเด็น") or "").strip() == "1"
        gflag = (G["no_specific_topic"] or "").strip() == "1"
        if hflag or gflag:
            flag_tp += hflag and gflag
            flag_fp += hflag and not gflag
            flag_fn += gflag and not hflag
        spec = (r.get("หมวด+อารมณ์(คนกรอก)") or "").strip()
        if not spec and not hflag:
            continue
        n_asp += 1
        H, Gm = parse_spec(spec), parse_spec(G["aspects"])
        tp += len(set(H) & set(Gm))
        fp += len(set(H) - set(Gm))
        fn += len(set(Gm) - set(H))
        for c in set(H) & set(Gm):
            sh.append(H[c])
            sg.append(Gm[c])
            per_cat[c]["agree" if H[c] == Gm[c] else "differ"] += 1
        for c in set(H) - set(Gm):
            per_cat[c]["คนใส่เกิน"] += 1
        for c in set(Gm) - set(H):
            per_cat[c]["คนไม่ใส่"] += 1

    if not ov_h:
        p("ยังไม่ได้กรอกช่องอารมณ์รวมเลย")
        return
    cov = Counter(rev.get(x, "?") for x in used)
    p(f"กรอกอารมณ์รวมแล้ว {len(ov_h)} จาก {len(rows)} แถว")
    p("  ครอบคลุมกลุ่ม: " + " · ".join(f"{k} {v}" for k, v in cov.most_common()))
    p("")
    agree = sum(1 for a, b in zip(ov_h, ov_g) if a == b) / len(ov_h)
    k = kappa(ov_h, ov_g, SENTS)
    p(f"[1] อารมณ์รวม  ตรงกัน {agree * 100:.1f}%  |  kappa {k:.4f} ({kappa_word(k)})")
    p("    ที่ไม่ตรงกัน (คน -> gold):")
    for rid, a, b in zip(used, ov_h, ov_g):
        if a != b:
            p(f"      id={rid} [{rev.get(rid,'?')}]: {a} -> {b}")
            p(f"        {gold[rid]['text'][:80]}")
    if n_asp:
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
        p("")
        p(f"[2] หมวด (กรอกแล้ว {n_asp} แถว)")
        p(f"    precision {pr:.3f} | recall {rc:.3f} | micro-F1 {f1:.4f}")
        p(f"    tp {tp} · คนใส่เกิน {fp} · คนไม่ใส่ {fn}")
        p("")
        p("    รายหมวด (เฉพาะที่มีข้อมูล)")
        nm = {c["id"]: c["name"] for c in _cv3["categories"]}
        for c in CAT_IDS:
            t = per_cat[c]
            if not sum(t.values()):
                continue
            p(f"      {c:>2} {nm[c][:34]:<35} ตรง {t['agree']:>3} "
              f"ต่างอารมณ์ {t['differ']:>3} คนใส่เกิน {t['คนใส่เกิน']:>3} "
              f"คนไม่ใส่ {t['คนไม่ใส่']:>3}")
    if sh:
        ak = kappa(sh, sg, SENTS)
        aa = sum(1 for a, b in zip(sh, sg) if a == b) / len(sh)
        p("")
        p(f"[3] อารมณ์รายหมวด (เฉพาะหมวดที่เลือกตรงกัน {len(sh)} คู่)")
        p(f"    ตรงกัน {aa * 100:.1f}% | kappa {ak:.4f} ({kappa_word(ak)})")
    if flag_tp + flag_fp + flag_fn:
        p("")
        p(f"[4] ธงไม่ระบุประเด็น  ตรงกัน {flag_tp} · คนติดเกิน {flag_fp} · "
          f"คนไม่ติด {flag_fn}")
    p("")
    p("วิธีอ่านค่านี้")
    p("  kappa คือเพดานความแม่นที่เป็นไปได้ของโมเดลบนชุดหมวดนี้")
    p("  ถ้าโมเดลได้สูงกว่าค่านี้ แปลว่าโมเดลเหมือน Claude มากกว่าที่คนเหมือน Claude")
    p("  ซึ่งไม่ใช่ความถูกต้อง แต่เป็นการเรียนธรรมเนียมของผู้ติดป้าย")

    # ⚠️ เขียนผลเป็น JSON ให้ scripts/measure_everything.py อ่านไปรวมในเล่ม
    #   ใช้แพตเทิร์นเดียวกับ seed_sweep — ตัวรวมไม่คำนวณ kappa เองซ้ำ
    #   เพื่อไม่ให้สูตรแตกเป็นสองชุดแล้วให้ค่าต่างกันโดยไม่มีใครเห็น
    #
    # ⚠️ ค่า หมวด_micro_f1 ที่ได้ตรงนี้วัดกับ gold **รุ่นปัจจุบัน**
    #   แต่ผู้ตรวจกรอกไฟล์ตอน gold ยังเป็น v3.1 (ยังไม่มีหมวด 14)
    #   ค่าที่อ้างในเล่มได้คือค่าของรอบ v3.1 ซึ่งบันทึกไว้ในคีย์ ค่าที่อ้างได้ด้านล่าง
    #   ดู docs/limitations.md ข้อ 2.8
    res = {
        "สร้างเมื่อ": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "ชุดตรวจ": {"แถวในไฟล์": len(rows), "จับคู่กับ gold ได้": len(used)},
        "อารมณ์รวม": {"ตรงกัน": round(agree, 4), "kappa": round(k, 4),
                      "n": len(ov_h)},
        "หมวด": ({"precision": round(pr, 4), "recall": round(rc, 4),
                  "micro_f1": round(f1, 4), "tp": tp, "คนใส่เกิน": fp,
                  "คนไม่ใส่": fn} if n_asp else {}),
        "อารมณ์รายหมวด": ({"ตรงกัน": round(aa, 4), "kappa": round(ak, 4),
                           "คู่ที่เทียบได้": len(sh)} if sh else {}),
        "ธงไม่ระบุประเด็น": {"ตรงกัน": flag_tp, "คนติดเกิน": flag_fp,
                             "คนไม่ติด": flag_fn},
        "ค่าที่อ้างในเล่มได้": {
            "อารมณ์รวม_kappa": 0.7790,
            "อารมณ์รายหมวด_kappa": 0.8117,
            "หมวด_micro_f1": 0.8000,
            "จำนวนแถว": 95,
            "เทียบกับ": ("gold รุ่นที่ผู้ตรวจเห็นตอนกรอก (ก่อนเพิ่มหมวด 14) "
                         "และตัดรีวิวของสถานที่นอกขอบเขตออกแล้ว"),
            "หมายเหตุ": ("ค่า หมวด_micro_f1 ที่คำนวณสด ๆ ด้านบนคือ 0.7872 ซึ่ง "
                         "**ห้ามใช้** เพราะวัดกับ gold ปัจจุบันที่มีหมวด 14 "
                         "อันเป็นหมวดที่ผู้ตรวจไม่เคยมีให้เลือกตอนกรอก "
                         "ส่วน kappa ทั้งสองตัวเท่ากันทั้งสองแบบ เพราะหมวด 14 "
                         "กระทบเฉพาะการเทียบหมวด ไม่กระทบการเทียบอารมณ์ "
                         "ดู docs/limitations.md ข้อ 2.8"),
        },
    }
    RESULT.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    p("")
    p(f"เขียนผลเป็น {RESULT.relative_to(ROOT)} ให้ measure_everything.py อ่านต่อ")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--make", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--n", type=int, default=N_DEFAULT)
    a = ap.parse_args()
    if a.make:
        make(a.n)
    elif a.score:
        score()
    else:
        ap.print_help()
