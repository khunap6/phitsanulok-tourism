"""
evaluate.py — รายงานผลการวัดสำหรับเขียนลงเล่มวิทยานิพนธ์

ทำไมต้องมีไฟล์นี้ แยกจาก train.py:
  train.py พิมพ์แค่ accuracy กับ macro-F1 รวม ซึ่งไม่พอสำหรับงานวิจัย
  ค่ารวมตัวเดียวตอบไม่ได้ว่า "หมวดไหนแม่น หมวดไหนไม่แม่น" และซ่อนปัญหา
  ข้อมูลไม่สมดุลไว้ — ชุดเทรน category มี 'ความคิดเห็นทั่วไป' 3,139 ตัวอย่าง
  แต่ 'อื่นๆ' มีแค่ 22 ตัว โมเดลจึงดูแม่นทั้งที่จับหมวดเล็กไม่ได้เลย

  ไฟล์นี้ออกตัวเลขที่ก๊อปลงเล่มได้ตรง ๆ และบันทึกเป็น CSV/JSON ไว้อ้างอิง

สิ่งที่ออกให้
  1. ตารางรายคลาส  precision / recall / F1 / support  (ทั้ง 2 โมเดล)
  2. confusion matrix                                  (CSV + ตารางในหน้าจอ)
  3. ความครบของข้อมูลแยกโซน                            (จากฐานข้อมูลจริง)
  4. คุณภาพข้อมูล — รีวิวที่ให้ดาวอย่างเดียว            (ตัวเลขที่ตรวจพบ)

⚠️ วัดบน test split เท่านั้น — ชุดที่โมเดลไม่เคยเห็นตอนเทรน
  category 1,600 ตัวอย่าง · sentiment 404 ตัวอย่าง
  ห้ามรายงานตัวเลขจาก train/val ลงเล่มเด็ดขาด

⚠️ ตัวเลขพวกนี้วัด "เทียบกับชุดข้อมูลที่ติดป้ายไว้" ไม่ใช่เทียบกับความจริง
  ชุดป้ายมาจาก Claude + กฎ ไม่ใช่จากคนอ่านทุกอัน จึงเป็นเพดานบนของความถูกต้อง
  ถ้าต้องการหลักฐานที่หนักกว่านี้ ต้องให้คนสุ่มอ่านแล้วติดป้ายเทียบ (ดู --sample)

ใช้งาน
  uv run python nlp/train/evaluate.py                 # ทั้งสองโมเดล
  uv run python nlp/train/evaluate.py --task category
  uv run python nlp/train/evaluate.py --sample 300    # สุ่มชุดให้คนติดป้ายเทียบ
"""
import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "reports" / "evaluation"
BATCH = 64


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def _predict(model_dir: Path, texts: list[str]) -> list[str]:
    """ทำนายทั้งชุด คืนเป็นชื่อคลาส"""
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(model_dir))
    mdl = AutoModelForSequenceClassification.from_pretrained(str(model_dir)).eval()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    mdl.to(dev)
    id2label = {int(k): v for k, v in mdl.config.id2label.items()}

    out: list[str] = []
    with torch.no_grad():
        for i in range(0, len(texts), BATCH):
            enc = tok(texts[i:i + BATCH], return_tensors="pt", padding=True,
                      truncation=True, max_length=128).to(dev)
            out += [id2label[int(j)] for j in mdl(**enc).logits.argmax(-1).cpu()]
    return out


def _print_table(rows: list[list], headers: list[str], widths: list[int]) -> None:
    line = "  ".join(h[:w].ljust(w) for h, w in zip(headers, widths))
    p("  " + line)
    p("  " + "-" * len(line))
    for r in rows:
        p("  " + "  ".join(str(c)[:w].ljust(w) for c, w in zip(r, widths)))


def eval_task(task: str) -> dict | None:
    """วัดโมเดลหนึ่งตัวบน test split แล้วคืนผลเป็น dict"""
    from sklearn.metrics import (classification_report, confusion_matrix,
                                 accuracy_score, f1_score)

    ds_path = ROOT / "data" / "training" / f"{task}_dataset.json"
    model_dir = ROOT / "models" / f"wangchanberta-{task}"
    if not ds_path.exists() or not model_dir.exists():
        p(f"  ข้าม {task} — ไม่พบชุดข้อมูลหรือโมเดล")
        return None

    data = json.loads(ds_path.read_text(encoding="utf-8"))
    test = data["test"]
    labels = data["labels"]
    gold = [r["label"] for r in test]
    pred = _predict(model_dir, [r["text"] for r in test])

    acc = accuracy_score(gold, pred)
    macro = f1_score(gold, pred, average="macro", zero_division=0)
    weighted = f1_score(gold, pred, average="weighted", zero_division=0)
    rep = classification_report(gold, pred, labels=labels, output_dict=True,
                                zero_division=0)

    p("")
    p(f"── โมเดล {task} · ชุดทดสอบ {len(test):,} ตัวอย่าง ──")
    p(f"   accuracy {acc:.4f} · macro-F1 {macro:.4f} · weighted-F1 {weighted:.4f}")
    p("")
    rows = []
    for lab in labels:
        m = rep.get(lab, {})
        rows.append([lab, f"{m.get('precision', 0):.3f}", f"{m.get('recall', 0):.3f}",
                     f"{m.get('f1-score', 0):.3f}", int(m.get("support", 0))])
    rows.sort(key=lambda r: -r[4])
    _print_table(rows, ["คลาส", "precision", "recall", "F1", "support"],
                 [34, 9, 6, 6, 7])

    # ── บันทึกไฟล์ ──
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / f"{task}_per_class.csv", "w", encoding="utf-8-sig",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["class", "precision", "recall", "f1", "support"])
        w.writerows(rows)

    cm = confusion_matrix(gold, pred, labels=labels)
    with open(OUT_DIR / f"{task}_confusion_matrix.csv", "w", encoding="utf-8-sig",
              newline="") as f:
        w = csv.writer(f)
        w.writerow(["จริง \\ ทำนาย"] + labels)
        for lab, row in zip(labels, cm):
            w.writerow([lab] + [int(v) for v in row])

    # ── คู่ที่สับสนกันมากสุด — เขียนลงเล่มได้ว่าโมเดลพลาดตรงไหน ──
    pairs = [(labels[i], labels[j], int(cm[i][j]))
             for i in range(len(labels)) for j in range(len(labels))
             if i != j and cm[i][j] > 0]
    pairs.sort(key=lambda x: -x[2])
    if pairs:
        p("")
        p("   คู่ที่โมเดลสับสนมากที่สุด 5 อันดับ")
        for a, b, n in pairs[:5]:
            p(f"      {n:>4} ครั้ง : จริงเป็น '{a[:26]}' แต่ทายเป็น '{b[:26]}'")

    return {"task": task, "n_test": len(test), "accuracy": acc,
            "macro_f1": macro, "weighted_f1": weighted,
            "per_class": {r[0]: {"precision": float(r[1]), "recall": float(r[2]),
                                 "f1": float(r[3]), "support": r[4]} for r in rows}}


async def data_report() -> dict:
    """ความครบของข้อมูลและคุณภาพข้อมูล — ดึงจากฐานข้อมูลจริง"""
    from sqlalchemy import text as sql

    from db.database import engine

    async with engine.connect() as c:
        zones = (await c.execute(sql("""
            WITH t AS (
              SELECT COALESCE(p.zone,'other') z,
                     LEAST(p.google_reviews_total, 850) ceil,
                     (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) sc
              FROM places p
              WHERE NOT p.scrape_excluded AND p.google_reviews_total IS NOT NULL)
            SELECT z, count(*) places, sum(ceil) ceil, sum(sc) sc
            FROM t GROUP BY 1 ORDER BY sum(ceil) DESC"""))).fetchall()
        tot = (await c.execute(sql("""
            SELECT (SELECT count(*) FROM reviews) reviews,
                   (SELECT count(*) FROM places WHERE NOT scrape_excluded) places,
                   (SELECT count(*) FROM reviews WHERE text_clean <> '') with_text,
                   (SELECT count(*) FROM analyzed_reviews) analyzed"""))).first()

    p("")
    p("── ความครบของข้อมูลแยกโซน ──")
    rows = [[z.z, z.places, f"{z.sc:,}", f"{z.ceil:,}", f"{z.sc / z.ceil * 100:.1f}%"]
            for z in zones]
    s_sc = sum(z.sc for z in zones)
    s_ce = sum(z.ceil for z in zones)
    rows.append(["รวม", sum(z.places for z in zones), f"{s_sc:,}", f"{s_ce:,}",
                 f"{s_sc / s_ce * 100:.1f}%"])
    _print_table(rows, ["โซน", "ร้าน", "เก็บได้", "เพดาน", "ครบ"],
                 [14, 6, 10, 10, 7])
    p("")
    p(f"   รีวิวทั้งหมด {tot.reviews:,} · วิเคราะห์แล้ว {tot.analyzed:,}")
    p(f"   มีข้อความให้วิเคราะห์ {tot.with_text:,} "
      f"({tot.with_text / tot.reviews * 100:.1f}% ของรีวิวทั้งหมด)")
    p(f"   ที่เหลือคือรีวิวที่ให้ดาวอย่างเดียว ไม่มีข้อความ")

    # SUM() ของ Postgres คืน Decimal ซึ่ง json.dumps ไม่รู้จัก -> แปลงเป็น int
    return {"zones": [{k: (int(v) if isinstance(v, (int, float)) or hasattr(v, "to_integral_value") else v)
                      for k, v in z._mapping.items()} for z in zones],
            "reviews": tot.reviews, "places": tot.places,
            "with_text": tot.with_text, "analyzed": tot.analyzed,
            "coverage_pct": round(s_sc / s_ce * 100, 2)}


async def make_sample(n: int) -> None:
    """สุ่มรีวิวให้คนอ่านแล้วติดป้ายเอง — ใช้วัดความถูกต้องเทียบกับคนตัดสิน

    ⚠️ ปิดคำตอบของระบบไว้ในไฟล์แยก ไม่ให้คนติดป้ายเห็นก่อน
      ถ้าเห็นคำตอบของระบบก่อน จะมีอคติตามไปโดยไม่รู้ตัว (anchoring)
    """
    from sqlalchemy import text as sql

    from db.database import engine

    async with engine.connect() as c:
        rows = (await c.execute(sql("""
            -- ⚠️ ห้ามตั้ง alias เป็น t / s — ชนกับ attribute ของ Row ใน SQLAlchemy
            --    แล้ว r.t จะคืนทั้งแถวแทนที่จะเป็นคอลัมน์ (เจอมาแล้ว ไฟล์เสียทั้งไฟล์)
            SELECT r.id, r.text_clean AS txt, ar.sentiment AS senti,
                   ar.pain_point_category AS cat
            FROM reviews r JOIN analyzed_reviews ar ON ar.review_id = r.id
            WHERE r.text_clean <> '' AND length(r.text_clean) >= 10
              -- ⚠️ ตัดรีวิวที่ถูกยกเป็นตัวอย่างในคู่มือออก
              --    คู่มือเฉลยป้ายของรีวิวพวกนั้นไว้ ถ้าหลุดเข้าชุดให้คนกรอก
              --    คนจะลอกคำตอบได้ แล้ว kappa จะสูงเกินจริง
              AND r.id <> ALL(CAST(:skip AS int[]))
            ORDER BY random() LIMIT :n"""),
            {"n": n, "skip": _guideline_ids()})).fetchall()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    blind = OUT_DIR / f"human_eval_{n}_blank.csv"
    key = OUT_DIR / f"human_eval_{n}_system_answer.csv"
    with open(blind, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "ข้อความรีวิว", "อารมณ์(คนกรอก)", "หมวด(คนกรอก)"])
        for r in rows:
            w.writerow([r.id, r.txt, "", ""])
    with open(key, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["review_id", "อารมณ์(ระบบ)", "หมวด(ระบบ)"])
        for r in rows:
            w.writerow([r.id, r.senti, r.cat])
    p("")
    p(f"สร้างชุดให้คนติดป้ายแล้ว {len(rows)} รายการ")
    p(f"   ไฟล์ให้คนกรอก : {blind}")
    p(f"   คำตอบของระบบ  : {key}  (อย่าเปิดก่อนกรอกเสร็จ)")
    p("   กรอกเสร็จแล้วเทียบด้วย Cohen's kappa หรืออัตราตรงกัน")
    p(f"   คู่มือสำหรับผู้ตรวจ : {write_guideline()}")


def _guideline_ids() -> list[int]:
    """id ของรีวิวที่ถูกยกเป็นตัวอย่างใน shared/sentiment_labels.json

    คู่มือผู้ตรวจเฉลยป้ายของรีวิวพวกนี้ไว้ จึงต้องกันไม่ให้สุ่มเข้าชุดที่ให้คนกรอก
    """
    try:
        spec = json.loads(
            (ROOT / "shared" / "sentiment_labels.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    ids = {ex["id"] for d in spec.get("definitions", {}).values()
           for ex in d.get("ตัวอย่างจริง", [])}
    ids |= {c["id"] for c in spec.get("เคสตัดสินยาก", [])}
    return sorted(ids)


def write_guideline() -> Path:
    """เขียนคู่มือให้คนติดป้าย จาก shared/sentiment_labels.json

    ⚠️ ต้อง generate ไม่ใช่พิมพ์มือ
      ถ้าคนติดป้ายใช้กติกาคนละชุดกับที่ระบบใช้ ค่า kappa จะต่ำเพราะ
      "กติกาไม่ตรงกัน" ไม่ใช่เพราะโมเดลแย่ แล้วจะสรุปผลงานวิจัยผิด
      ไฟล์เดียวกันนี้ยังถูกใส่ลงพรอมป์ใน nlp/sentiment.py ด้วย
    """
    from api.filters import (CATEGORY_KEYS, SENTIMENT_KEYS, SENTIMENT_LABELS,
                             sentiment_guideline_text)

    spec = json.loads(
        (ROOT / "shared" / "sentiment_labels.json").read_text(encoding="utf-8"))
    L = ["# คู่มือติดป้ายรีวิว (สำหรับผู้ตรวจ)", "",
         "สร้างอัตโนมัติจาก shared/sentiment_labels.json — ห้ามแก้ไฟล์นี้ตรง ๆ",
         "แก้ที่ไฟล์ต้นทางแล้วรัน: uv run python nlp/train/evaluate.py --guideline", "",
         "## วิธีกรอก", "",
         "1. เปิด human_eval_300_blank.csv ด้วย Excel หรือ Google Sheets",
         "2. อ่านเฉพาะคอลัมน์ `ข้อความรีวิว` — ห้ามเปิดไฟล์ _system_answer.csv",
         "   เพราะถ้าเห็นคำตอบของระบบก่อน ผลเทียบจะใช้อ้างอิงไม่ได้",
         "3. กรอก `อารมณ์(คนกรอก)` ด้วย positive / neutral / negative",
         "4. กรอก `หมวด(คนกรอก)` ด้วยชื่อหมวดจากรายการท้ายไฟล์นี้",
         "5. ไม่แน่ใจจริง ๆ ให้เว้นว่าง ดีกว่าเดา (ช่องว่างถูกข้าม ไม่นับผิด)",
         "6. กรอกเสร็จแล้วรัน:",
         "   `uv run python nlp/train/evaluate.py --score reports/evaluation/human_eval_300_blank.csv`",
         "", "## หลักการเดียวที่ใช้ตัดสินอารมณ์", "",
         "ดูว่า **ผู้รีวิวแสดงความไม่พอใจหรือไม่** ไม่ใช่ดูรูปประโยคหรือคำที่ใช้",
         "คำว่า 'ควร' หรือ 'ปรับปรุง' ไม่ได้แปลว่า negative เสมอไป", "",
         "## นิยามของอารมณ์ 3 แบบ", "", sentiment_guideline_text(), "",
         "## ตัวอย่างจริงจากฐานข้อมูล", ""]

    for key in SENTIMENT_KEYS:
        d = spec["definitions"].get(key, {})
        L.append(f"### {key} ({SENTIMENT_LABELS.get(key, key)})")
        for ex in d.get("ตัวอย่างจริง", []):
            L.append(f"- id={ex['id']} ({ex['ดาว']} ดาว) \"{ex['text']}\" "
                     f"-> {ex['เพราะ']}")
        L.append("")

    L += ["## เคสที่ตัดสินยาก (อ่านก่อนเริ่มกรอก)", ""]
    for c in spec.get("เคสตัดสินยาก", []):
        L += [f"**id={c['id']} ({c['ดาว']} ดาว) \"{c['text']}\"**",
              f"- ระบบให้: {c['ระบบให้']}",
              f"- ประเด็น: {c['ประเด็น']}",
              f"- กติกาที่ใช้: {c['กติกาที่ใช้']}", ""]

    L += [f"## หมวดหมู่ที่ใช้ได้ ({len(CATEGORY_KEYS)} หมวด)", ""]
    L += [f"{i}. {c}" for i, c in enumerate(CATEGORY_KEYS, 1)]
    L += ["", "หมายเหตุ: ชื่อหมวดในไฟล์นี้คือค่าที่เก็บใน DB",
          "ชื่อที่แสดงบนหน้าเว็บอาจต่างกัน แต่ให้กรอกตามรายการนี้", ""]

    # ── กติกาเลือกหมวด เมื่อรีวิวพูดถึงหลายเรื่อง ──
    cspec = json.loads(
        (ROOT / "shared" / "category_labels.json").read_text(encoding="utf-8"))
    if cspec.get("decision_rules"):
        L += ["## เลือกหมวดยังไงเมื่อรีวิวพูดถึงหลายเรื่อง", ""]
        L += cspec["decision_rules"]
        L.append("")

    beh = cspec.get("พฤติกรรมจริงของโมเดล", {})
    if beh:
        L += ["### โมเดลตัดสินยังไงจริง ๆ (วัดแล้ว)", ""]
        for group, items in beh.items():
            if group.startswith("_"):
                continue
            L.append(f"**{group}**")
            for ex in items:
                line = f"- \"{ex['text']}\" -> {ex['ได้']} ({ex['มั่นใจ']})"
                if ex.get("สรุป"):
                    line += f"  \n  {ex['สรุป']}"
                L.append(line)
            L.append("")

    lim = cspec.get("ข้อจำกัดที่ต้องระบุในเล่ม")
    if lim:
        L += ["### ข้อจำกัดของการเก็บหมวดเดียว", ""] + lim + [""]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "sentiment_guideline.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out


def score_human(blank_path: str) -> None:
    """เทียบป้ายของคนกับของระบบ แล้วรายงานผลแบบที่เขียนลงเล่มได้

    ⚠️ วัด 2 ตัวคู่กันเสมอ ห้ามรายงานแค่ "ตรงกันกี่ %"
      อัตราตรงกันเพียว ๆ หลอกตาเมื่อข้อมูลไม่สมดุล — ถ้า 80% ของรีวิวเป็น
      positive คนกับระบบเดาว่า positive ทั้งคู่ก็ได้ 80% แล้วโดยไม่ต้องเก่ง
      Cohen's kappa หักส่วนที่ "บังเอิญตรงกัน" ออก จึงเป็นตัวที่ต้องรายงาน

    เกณฑ์แปลผล kappa (Landis & Koch, 1977) — อ้างอิงได้ในเล่ม
      < 0.00 แย่กว่าสุ่ม · 0.00-0.20 เล็กน้อย · 0.21-0.40 พอใช้
      0.41-0.60 ปานกลาง · 0.61-0.80 ดี · 0.81-1.00 ดีมาก
    """
    from sklearn.metrics import cohen_kappa_score, classification_report

    blank = Path(blank_path)
    key = Path(str(blank).replace("_blank.csv", "_system_answer.csv"))
    if not key.exists():
        p(f"ไม่พบไฟล์คำตอบของระบบ: {key}")
        return

    def read(path: Path) -> dict[str, list[str]]:
        with open(path, encoding="utf-8-sig") as f:
            return {r[0]: r[1:] for r in list(csv.reader(f))[1:] if r and r[0]}

    human, system = read(blank), read(key)

    # ไฟล์ให้กรอก: [id, ข้อความ, อารมณ์, หมวด] -> ตัด id ออกแล้วเหลือ index 1,2
    # ไฟล์คำตอบระบบ: [id, อารมณ์, หมวด]        -> ตัด id ออกแล้วเหลือ index 0,1
    pairs = {"อารมณ์": (1, 0), "หมวด": (2, 1)}
    out: dict = {}
    for label, (hi, si) in pairs.items():
        rows = [(h[hi].strip(), system[rid][si].strip())
                for rid, h in human.items()
                if rid in system and len(h) > hi and h[hi].strip()]
        p("")
        p(f"── {label} ──")
        if not rows:
            p("   ยังไม่มีใครกรอกช่องนี้ — ข้าม")
            continue
        g = [x[0] for x in rows]
        y = [x[1] for x in rows]
        agree = sum(1 for a, b in rows if a == b)
        kappa = cohen_kappa_score(g, y)
        p(f"   กรอกแล้ว {len(rows)} จาก {len(human)} รายการ")
        p(f"   ตรงกัน {agree}/{len(rows)} = {agree / len(rows) * 100:.1f}%")
        p(f"   Cohen's kappa = {kappa:.3f}  ({_kappa_word(kappa)})")
        p("")
        p(classification_report(g, y, zero_division=0, digits=3))
        out[label] = {"n": len(rows), "agree": agree,
                      "agreement_pct": round(agree / len(rows) * 100, 2),
                      "kappa": round(float(kappa), 4)}
        bad = [(rid, human[rid][hi], system[rid][si])
               for rid in human
               if rid in system and len(human[rid]) > hi
               and human[rid][hi].strip()
               and human[rid][hi].strip() != system[rid][si].strip()]
        if bad:
            p(f"   ตัวอย่างที่ไม่ตรงกัน 5 รายการแรก (คน -> ระบบ)")
            for rid, h, sy in bad[:5]:
                p(f"      id={rid}: {h} -> {sy}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "human_eval_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    p("")
    p(f"บันทึกผลไว้ที่ {OUT_DIR / 'human_eval_result.json'}")


def _kappa_word(k: float) -> str:
    """แปลผลตามเกณฑ์ Landis & Koch (1977)"""
    if k < 0:
        return "แย่กว่าการสุ่ม"
    for lim, word in ((0.20, "สอดคล้องเล็กน้อย"), (0.40, "พอใช้"),
                      (0.60, "ปานกลาง"), (0.80, "ดี")):
        if k <= lim:
            return word
    return "ดีมาก"


async def main(task: str, sample: int | None) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    p("=" * 72)
    p(f"  รายงานผลการวัด — สร้างเมื่อ {stamp}")
    p("=" * 72)

    if sample:
        await make_sample(sample)
        return

    results = {}
    for t in (["category", "sentiment"] if task == "all" else [task]):
        r = eval_task(t)
        if r:
            results[t] = r

    results["data"] = await data_report()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Decimal จาก Postgres ไม่ใช่ชนิดมาตรฐานของ JSON — แปลงตอนเขียนทีเดียว
    (OUT_DIR / "summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, default=float),
        encoding="utf-8")
    p("")
    p(f"บันทึกไฟล์ทั้งหมดไว้ที่ {OUT_DIR}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="รายงานผลการวัดสำหรับเล่ม")
    ap.add_argument("--task", choices=["all", "category", "sentiment"],
                    default="all")
    ap.add_argument("--sample", type=int, default=None, metavar="N",
                    help="สุ่ม N รีวิวให้คนติดป้ายเทียบ (ไม่วัดโมเดล)")
    ap.add_argument("--score", metavar="FILE", default=None,
                    help="คำนวณผลจากไฟล์ที่คนกรอกเสร็จแล้ว (_blank.csv)")
    ap.add_argument("--guideline", action="store_true",
                    help="เขียนคู่มือผู้ตรวจจาก shared/sentiment_labels.json")
    args = ap.parse_args()
    if args.guideline:
        p(f"เขียนคู่มือผู้ตรวจแล้ว -> {write_guideline()}")
    elif args.score:
        score_human(args.score)
    else:
        asyncio.run(main(args.task, args.sample))
