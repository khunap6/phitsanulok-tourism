"""apply_scope_to_db.py — เขียนผลการจัดขอบเขตลง places.in_scope

⚠️ อ่านเกณฑ์จาก shared/scope.json ทุกครั้ง ไม่ฝังเกณฑ์ไว้ที่นี่
  ถ้าเกณฑ์เปลี่ยน ให้แก้ scripts/build_scope.py แล้วรัน
    build_scope.py -> classify_scope.py --write -> apply_scope_to_db.py --write

⚠️ ไม่ลบข้อมูลใด ๆ แค่ตั้งธง สถานที่ที่ in_scope=false ยังอยู่ครบพร้อมรีวิว
  ถอนกลับได้ด้วย UPDATE places SET in_scope = true

⚠️ รายงานก่อน-หลังทุกครั้ง เพราะธงนี้เปลี่ยนตัวส่วนของทุกสัดส่วนบนแดชบอร์ด
  ถ้าไม่เห็นตัวเลขก่อน-หลัง จะไม่รู้ว่าเปลี่ยนไปเท่าไร

รัน:
  uv run python scripts/apply_scope_to_db.py
  uv run python scripts/apply_scope_to_db.py --write
"""
import argparse
import asyncio
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from db.database import AsyncSessionLocal, engine  # noqa: E402

SRC = ROOT / "reports" / "scope_classification.csv"


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


async def stats(c) -> dict:
    return dict((await c.execute(text("""
        SELECT COUNT(*) AS places,
               COUNT(*) FILTER (WHERE in_scope) AS places_in,
               (SELECT COUNT(*) FROM reviews r JOIN places p ON p.id=r.place_id
                  WHERE r.text_clean <> '') AS rev,
               (SELECT COUNT(*) FROM reviews r JOIN places p ON p.id=r.place_id
                  WHERE r.text_clean <> '' AND p.in_scope) AS rev_in,
               (SELECT COUNT(*) FROM review_aspects ra
                  JOIN reviews r ON r.id=ra.review_id
                  JOIN places p ON p.id=r.place_id WHERE p.in_scope) AS asp_in,
               (SELECT COUNT(*) FROM review_aspects) AS asp
        FROM places"""))).mappings().one())


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()

    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))
    want = {int(r["id"]): (r["in_scope"] == "True", r["reason"]) for r in rows}
    p(f"อ่านผลการจัด {len(want)} แห่ง จาก {SRC.relative_to(ROOT)}")

    async with engine.connect() as c:
        before = await stats(c)
        cur = {r[0]: r[1] for r in (await c.execute(text(
            "SELECT id, in_scope FROM places"))).all()}
    missing = [i for i in cur if i not in want]
    extra = [i for i in want if i not in cur]
    if missing or extra:
        p(f"⚠️ ไม่ตรงกัน: ในฐานแต่ไม่มีในไฟล์ {len(missing)} · "
          f"ในไฟล์แต่ไม่มีในฐาน {len(extra)}")
        p("   ให้รัน classify_scope.py --write ใหม่ก่อน")
        if missing:
            raise SystemExit(1)
    change = [i for i, v in cur.items() if i in want and v != want[i][0]]
    p(f"ต้องเปลี่ยน {len(change)} แห่ง")
    p("")
    p(f"{'':<22} {'ก่อน':>12} {'หลัง (คาด)':>14}")
    exp_in = sum(1 for v in want.values() if v[0])
    p(f"{'สถานที่ในขอบเขต':<22} {before['places_in']:>12,} {exp_in:>14,}")
    p(f"{'รีวิวที่มีข้อความ':<22} {before['rev_in']:>12,} {'จะวัดหลังเขียน':>14}")

    if not a.write:
        p("")
        p("DRY-RUN — ยังไม่เขียน  ลงมือจริงด้วย --write")
        await engine.dispose()
        return

    async with AsyncSessionLocal() as s:
        await s.execute(text("""
            UPDATE places SET in_scope = v.ok, in_scope_reason = v.why
            FROM (SELECT UNNEST(CAST(:ids AS int[])) AS id,
                         UNNEST(CAST(:oks AS boolean[])) AS ok,
                         UNNEST(CAST(:whys AS text[])) AS why) v
            WHERE places.id = v.id"""),
            {"ids": [int(r["id"]) for r in rows],
             "oks": [r["in_scope"] == "True" for r in rows],
             "whys": [r["reason"] for r in rows]})
        await s.commit()

    async with engine.connect() as c:
        after = await stats(c)
    await engine.dispose()

    p("")
    p(f"{'':<24} {'ก่อน':>12} {'หลัง':>12} {'ต่าง':>10}")
    for k, lab in (("places_in", "สถานที่ในขอบเขต"),
                   ("rev_in", "รีวิวที่มีข้อความ"),
                   ("asp_in", "การกล่าวถึงรายหมวด")):
        d = after[k] - before[k]
        p(f"{lab:<24} {before[k]:>12,} {after[k]:>12,} {d:>+10,}")
    p("")
    p(f"รีวิวที่หลุดออกจากสถิติ {after['rev']- after['rev_in']:,} "
      f"= {(after['rev'] - after['rev_in']) / after['rev'] * 100:.2f}% ของรีวิวที่มีข้อความ")
    p(f"การกล่าวถึงที่หลุดออก {after['asp'] - after['asp_in']:,} "
      f"= {(after['asp'] - after['asp_in']) / after['asp'] * 100:.2f}%")


if __name__ == "__main__":
    asyncio.run(main())
