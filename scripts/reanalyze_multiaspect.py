"""reanalyze_multiaspect.py — Phase 4: วิเคราะห์รีวิวทั้งฐานใหม่ด้วยโมเดลชุดใหม่

เขียนอะไรบ้าง
  analyzed_reviews.overall_sentiment    อารมณ์รวมของรีวิว
  analyzed_reviews.primary_category_id  หมวดหลัก (ใช้ทำกราฟที่ต้องรวมได้ 100%)
  review_aspects                        1 แถวต่อ 1 หมวดที่รีวิวพูดถึง พร้อมอารมณ์ของหมวดนั้น

⚠️ ข้ามแถวที่ label_source เป็น claude_guided / claude_silver / human_verified
  นั่นคือชุดประเมิน (gold 300) และชุดเทรน (silver 996)
  ถ้าเขียนทับ ชุดประเมินจะกลายเป็นผลของโมเดลเอง แล้ววัดอะไรไม่ได้อีกเลย

⚠️ ไม่แตะคอลัมน์เดิม
  sentiment / pain_point_category / severity / keywords ยังมีค่าเดิมครบ
  endpoint และรายงานที่อ่านคอลัมน์เดิมจึงทำงานต่อได้ระหว่างที่ยังไม่ได้แก้

⚠️ กฎการเลือกหมวดหลัก (ตามคู่มือข้อ "หมวดหลัก")
  ถ้าอารมณ์รวมเป็น negative/neutral -> หมวดแรกที่ถูกติ (เลือกหมวดที่อารมณ์เป็นลบ
    และความน่าจะเป็นสูงสุด) ถ้าไม่มีหมวดไหนเป็นลบเลยจึงใช้หมวดที่ความน่าจะเป็นสูงสุด
  ถ้าอารมณ์รวมเป็น positive -> หมวดที่ความน่าจะเป็นสูงสุด

⚠️ รันซ้ำได้ ทำทีละก้อนและ commit ทีละก้อน ถ้าหยุดกลางทางรันต่อได้เลย
  เพราะเลือกเฉพาะแถวที่ยังไม่ได้ทำ (model_used ยังไม่ใช่ค่ารุ่นใหม่)

รัน:
  uv run python scripts/reanalyze_multiaspect.py --limit 200     # ลองก่อน
  uv run python scripts/reanalyze_multiaspect.py --apply
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

import torch
from sqlalchemy import text

from db.database import AsyncSessionLocal, engine

M_CAT = ROOT / "models" / "wangchanberta-category-multilabel"
M_ASP = ROOT / "models" / "wangchanberta-aspect-sentiment"
# ⚠️ ป้ายรุ่นของผลทำนาย — ใช้เป็นตัวบอกว่าแถวไหนทำด้วยโมเดลรุ่นไหนแล้ว
#   สคริปต์ข้ามแถวที่ model_used ตรงกับค่านี้ ดังนั้น **ต้องเปลี่ยนค่านี้ทุกครั้ง
#   ที่เทรนโมเดลใหม่** ไม่งั้นจะข้ามทั้งฐานแล้วผลเก่าค้างอยู่โดยไม่มีใครเห็น
#
#   multiaspect-v1  2026-10-11  โมเดลชุดแรก (ชุดเทรนยังมีสถานที่นอกขอบเขตปน)
#   multiaspect-v2  2026-10-13  หลังตัดสถานที่นอกจังหวัดออกแล้วเทรนใหม่
#                               ดู docs/limitations.md ข้อ 2.11
MODEL_TAG = "multiaspect-v2"
PROTECTED = ("claude_guided", "claude_silver", "human_verified")
SENTS = ["positive", "neutral", "negative"]
CHUNK = 2000
BATCH = 64


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


class Models:
    def __init__(self, overall_dir: Path):
        from transformers import (AutoModelForSequenceClassification,
                                  AutoTokenizer)
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"

        def load(path):
            return (AutoTokenizer.from_pretrained(str(path)),
                    AutoModelForSequenceClassification
                    .from_pretrained(str(path)).to(self.dev).eval())

        self.tok_c, self.cat = load(M_CAT)
        self.tok_a, self.asp = load(M_ASP)
        self.tok_o, self.ovr = load(overall_dir)
        doc = json.loads((M_CAT / "thresholds.json").read_text(encoding="utf-8"))
        self.cat_ids = doc["category_ids"]
        self.th = {int(k): v for k, v in doc["thresholds"].items()}
        cats = json.loads(
            (ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
        self.names = {c["id"]: c["name"] for c in cats["categories"]}
        self.overall_dir = overall_dir

    @torch.no_grad()
    def predict(self, texts: list[str]):
        """คืน [(overall, [(cat_id, sentiment, prob), ...]), ...]"""
        # อารมณ์รวม
        overall = []
        for i in range(0, len(texts), BATCH):
            enc = self.tok_o(texts[i:i + BATCH], padding=True, truncation=True,
                             max_length=256, return_tensors="pt").to(self.dev)
            lg = self.ovr(**enc).logits.argmax(-1).cpu().tolist()
            overall += [self.ovr.config.id2label[j] for j in lg]

        # หมวด (multi-label)
        cats = []
        for i in range(0, len(texts), BATCH):
            enc = self.tok_c(texts[i:i + BATCH], padding=True, truncation=True,
                             max_length=256, return_tensors="pt").to(self.dev)
            pr = torch.sigmoid(self.cat(**enc).logits).cpu()
            for j in range(pr.shape[0]):
                picked = [(self.cat_ids[k], pr[j][k].item())
                          for k in range(len(self.cat_ids))
                          if pr[j][k].item() >= self.th[self.cat_ids[k]]]
                if not picked:
                    k = int(pr[j].argmax())
                    picked = [(self.cat_ids[k], pr[j][k].item())]
                cats.append(picked)

        # อารมณ์รายหมวด — ยิงเป็นคู่ (ชื่อหมวด, ข้อความ)
        pairs, owner = [], []
        for idx, picked in enumerate(cats):
            for cid, _ in picked:
                pairs.append((self.names[cid], texts[idx]))
                owner.append(idx)
        sents = []
        for i in range(0, len(pairs), BATCH):
            ch = pairs[i:i + BATCH]
            enc = self.tok_a([x[0] for x in ch], [x[1] for x in ch],
                             padding=True, truncation=True, max_length=256,
                             return_tensors="pt").to(self.dev)
            sents += [SENTS[j] for j in
                      self.asp(**enc).logits.argmax(-1).cpu().tolist()]

        out, k = [], 0
        for idx, picked in enumerate(cats):
            asp = []
            for cid, prob in picked:
                asp.append((cid, sents[k], prob))
                k += 1
            out.append((overall[idx], asp))
        return out


def pick_primary(overall: str, aspects: list) -> int:
    """หมวดหลักตามกฎในคู่มือ"""
    if overall in ("negative", "neutral"):
        neg = [a for a in aspects if a[1] == "negative"]
        if neg:
            return max(neg, key=lambda a: a[2])[0]
    return max(aspects, key=lambda a: a[2])[0]


async def main(apply: bool, limit: int | None, overall_dir: Path) -> None:
    async with AsyncSessionLocal() as s:
        todo = (await s.execute(text(f"""
            SELECT count(*) FROM reviews r
             WHERE r.text_clean <> '' AND length(r.text_clean) >= 5
               AND NOT EXISTS (SELECT 1 FROM analyzed_reviews a
                                WHERE a.review_id = r.id
                                  AND (a.label_source = ANY(:prot)
                                       OR a.model_used = :tag))
        """), {"prot": list(PROTECTED), "tag": MODEL_TAG})).scalar()
        prot = (await s.execute(text(
            "SELECT count(*) FROM analyzed_reviews WHERE label_source = ANY(:p)"),
            {"p": list(PROTECTED)})).scalar()

    p("=" * 72)
    p("  Phase 4 — วิเคราะห์ใหม่ด้วยโมเดลชุด Multi-Aspect")
    p("=" * 72)
    p(f"โมเดลอารมณ์รวมที่ใช้ : {overall_dir.name}")
    p(f"รีวิวที่ต้องทำ        : {todo:,}")
    p(f"แถวที่กันไว้ไม่แตะ    : {prot:,} (gold + silver)")
    if not apply and limit is None:
        p("")
        p("นี่คือ DRY-RUN — ลองจริงด้วย --limit 200 หรือ --apply")
        await engine.dispose()
        return

    # ── ล้าง aspect ที่ค้างจากรีวิว "ให้ดาวอย่างเดียว" ──
    # รีวิวพวกนี้ text_clean ถูกตั้งเป็นค่าว่างไปแล้วโดย
    # scripts/clear_rating_only_text.py เพราะผู้รีวิวไม่ได้เขียนอะไรจริง
    # แต่โมเดลเดิมเคยให้หมวดไว้ และ Phase 3 คัดลอกตามมาด้วย
    # ถ้าไม่ลบ ตัวส่วนของสถิติรายหมวดจะปนรีวิวที่ไม่มีข้อความ
    # ซึ่งเป็นบั๊กเดียวกับที่เคยทำให้หมวด "ความคิดเห็นทั่วไป" พองขึ้น 3,944 แถว
    async with AsyncSessionLocal() as s:
        res = await s.execute(text("""
            DELETE FROM review_aspects a
             USING reviews r
             WHERE r.id = a.review_id AND r.text_clean = ''
        """))
        await s.commit()
        if res.rowcount:
            p(f"ล้าง aspect ของรีวิวที่ไม่มีข้อความ {res.rowcount:,} แถว")

    mdl = Models(overall_dir)
    done, t0, n_asp = 0, time.time(), 0
    while True:
        async with AsyncSessionLocal() as s:
            take = CHUNK if limit is None else min(CHUNK, limit - done)
            if take <= 0:
                break
            rows = (await s.execute(text(f"""
                SELECT r.id, r.text_clean AS txt FROM reviews r
                 WHERE r.text_clean <> '' AND length(r.text_clean) >= 5
                   AND NOT EXISTS (SELECT 1 FROM analyzed_reviews a
                                    WHERE a.review_id = r.id
                                      AND (a.label_source = ANY(:prot)
                                           OR a.model_used = :tag))
                 ORDER BY r.id LIMIT :n
            """), {"prot": list(PROTECTED), "tag": MODEL_TAG,
                   "n": take})).fetchall()
            if not rows:
                break
            ids = [r.id for r in rows]
            preds = mdl.predict([r.txt for r in rows])

            # มีรีวิวที่ยังไม่มีแถว analyzed_reviews -> สร้างก่อน
            await s.execute(text("""
                INSERT INTO analyzed_reviews (review_id) SELECT UNNEST(CAST(:i AS int[]))
                ON CONFLICT (review_id) DO NOTHING
            """), {"i": ids})
            await s.execute(text("""
                UPDATE analyzed_reviews AS ar
                   SET overall_sentiment = v.ov, primary_category_id = v.pc,
                       label_source = 'model', model_used = :tag
                  FROM (SELECT UNNEST(CAST(:i AS int[]))  AS rid,
                               UNNEST(CAST(:o AS text[])) AS ov,
                               UNNEST(CAST(:c AS int[]))  AS pc) AS v
                 WHERE ar.review_id = v.rid
            """), {"tag": MODEL_TAG, "i": ids,
                   "o": [x[0] for x in preds],
                   "c": [pick_primary(*x) for x in preds]})
            await s.execute(text(
                "DELETE FROM review_aspects WHERE review_id = ANY(:i)"),
                {"i": ids})
            flat = [(rid, cid, sn, prob, cid == pick_primary(ov, asp))
                    for rid, (ov, asp) in zip(ids, preds)
                    for cid, sn, prob in asp]
            await s.execute(text("""
                INSERT INTO review_aspects
                       (review_id, category_id, aspect_sentiment, is_primary,
                        confidence, label_source)
                SELECT UNNEST(CAST(:r AS int[])), UNNEST(CAST(:c AS int[])),
                       UNNEST(CAST(:s AS text[])), UNNEST(CAST(:p AS bool[])),
                       UNNEST(CAST(:f AS float8[])), 'model'
                ON CONFLICT (review_id, category_id) DO NOTHING
            """), {"r": [x[0] for x in flat], "c": [x[1] for x in flat],
                   "s": [x[2] for x in flat], "p": [x[4] for x in flat],
                   "f": [x[3] for x in flat]})
            await s.commit()
            done += len(rows)
            n_asp += len(flat)
            el = time.time() - t0
            p(f"  ทำแล้ว {done:,}/{todo:,} | aspect {n_asp:,} "
              f"({n_asp / done:.2f}/รีวิว) | {done / el:.0f} รีวิว/วิ "
              f"| เหลือ ~{(todo - done) / max(done / el, 1) / 60:.0f} นาที")
            if limit is not None and done >= limit:
                break

    p("")
    p(f"เสร็จ {done:,} รีวิว / {n_asp:,} aspect ใน {(time.time() - t0) / 60:.1f} นาที")
    await engine.dispose()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--overall-model", default="wangchanberta-overall-sentiment")
    a = ap.parse_args()
    asyncio.run(main(a.apply, a.limit, ROOT / "models" / a.overall_model))
