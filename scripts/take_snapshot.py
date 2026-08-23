"""
take_snapshot.py — บันทึก "ภาพนิ่ง" ของสถิติทั้งระบบลงฐานข้อมูล

ทำไมต้องมี: เพื่อเทียบย้อนหลังได้ว่าอะไรเปลี่ยนไป
  - ปัญหาหมวดไหนเพิ่มขึ้น (ระบบแจ้งเตือน)
  - เพิ่มทั้งภาพรวม หรือกระจุกอยู่ร้านเดียว (ตาราง snapshot_places)
  - เก็บสะสมไปเรื่อยๆ = ฐานข้อมูลสถิติร้านอาหาร/สถานที่ในพิษณุโลก

รัน:
  uv run python scripts/take_snapshot.py                      # เก็บ ณ ตอนนี้
  uv run python scripts/take_snapshot.py --label 2026-W34     # ตั้งชื่อช่วง
  uv run python scripts/take_snapshot.py --as-of 2026-01-31   # ย้อนอดีต (นับเฉพาะรีวิวถึงวันนั้น)
  uv run python scripts/take_snapshot.py --list               # ดูรายการที่เก็บไว้
"""
import argparse
import asyncio
from datetime import date

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal


def safe_print(t: str) -> None:
    try:
        print(t)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"))


def _parse_date(s: str | None):
    if not s:
        return None
    y, m, d = s.split("-")
    return date(int(y), int(m), int(d))


async def list_snapshots(session) -> None:
    r = await session.execute(
        text("""
            SELECT s.id, s.taken_at, s.period_label, s.total_reviews, s.total_analyzed,
                   (SELECT COUNT(*) FROM snapshot_categories c WHERE c.snapshot_id = s.id) AS n_cat,
                   (SELECT COUNT(*) FROM snapshot_places p WHERE p.snapshot_id = s.id)     AS n_place
            FROM stat_snapshots s ORDER BY s.taken_at DESC LIMIT 20
        """)
    )
    rows = r.fetchall()
    if not rows:
        safe_print("ยังไม่มี snapshot — รัน `uv run python scripts/take_snapshot.py` เพื่อเก็บครั้งแรก")
        return
    safe_print(f"{'id':>4} | {'เก็บเมื่อ':19} | {'ช่วง':12} | {'รีวิว':>7} | {'หมวด':>5} | {'ร้าน×หมวด':>9}")
    safe_print("-" * 74)
    for x in rows:
        when = x.taken_at.strftime("%Y-%m-%d %H:%M") if x.taken_at else "-"
        safe_print(f"{x.id:>4} | {when:19} | {(x.period_label or '-'):12} | "
                   f"{(x.total_reviews or 0):>7,} | {x.n_cat:>5} | {x.n_place:>9,}")


async def take_snapshot(session, label: str | None, as_of: date | None, note: str | None) -> int:
    # กรองตามวันที่รีวิว (ใช้ตอนสร้าง snapshot ย้อนอดีตจากข้อมูลจริง)
    date_sql = "AND r.review_date_approx <= :as_of" if as_of else ""
    params: dict = {}
    if as_of:
        params["as_of"] = as_of

    # ── 1) หัวข้อ snapshot ──
    r = await session.execute(
        text(f"""
            INSERT INTO stat_snapshots (period_label, total_places, total_reviews, total_analyzed, note)
            SELECT :label,
                   (SELECT COUNT(*) FROM places),
                   (SELECT COUNT(*) FROM reviews r WHERE TRUE {date_sql}),
                   (SELECT COUNT(*) FROM analyzed_reviews ar
                      JOIN reviews r ON r.id = ar.review_id WHERE TRUE {date_sql}),
                   :note
            RETURNING id
        """),
        {**params, "label": label, "note": note},
    )
    snap_id = r.scalar_one()

    # ── 2) สถิติระดับหมวด — ภาพรวม (zone=NULL) + แยกโซน ในคิวรีเดียว ──
    # GROUPING SETS ทำให้ได้ทั้ง 2 ระดับพร้อมกัน แถวภาพรวมจะมี zone = NULL
    await session.execute(
        text(f"""
            INSERT INTO snapshot_categories
                (snapshot_id, zone, category, complaint_count, praise_count,
                 high_count, medium_count, low_count)
            SELECT :sid,
                   COALESCE(p.zone, 'other') AS zone,
                   ar.pain_point_category    AS category,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'negative') AS complaint_count,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'positive') AS praise_count,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'negative' AND ar.severity = 'high')   AS high_count,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'negative' AND ar.severity = 'medium') AS medium_count,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'negative' AND ar.severity = 'low')    AS low_count
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places  p ON p.id = r.place_id
            WHERE ar.pain_point_category IS NOT NULL
              AND r.text_clean <> ''
              {date_sql}
            GROUP BY GROUPING SETS (
                (ar.pain_point_category),                          -- ภาพรวมทั้งจังหวัด
                (COALESCE(p.zone, 'other'), ar.pain_point_category) -- แยกโซน
            )
        """),
        {**params, "sid": snap_id},
    )

    # ── 3) สถิติระดับร้าน × หมวด (เก็บเฉพาะคู่ที่มีข้อมูลจริง) ──
    await session.execute(
        text(f"""
            INSERT INTO snapshot_places
                (snapshot_id, place_id, category, complaint_count, praise_count, high_count)
            SELECT :sid,
                   r.place_id,
                   ar.pain_point_category,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'negative') AS complaint_count,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'positive') AS praise_count,
                   COUNT(*) FILTER (WHERE ar.sentiment = 'negative' AND ar.severity = 'high') AS high_count
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            WHERE ar.pain_point_category IS NOT NULL
              AND r.text_clean <> ''
              {date_sql}
            GROUP BY r.place_id, ar.pain_point_category
        """),
        {**params, "sid": snap_id},
    )

    await session.commit()
    return snap_id


async def show_snapshot(session, snap_id: int) -> None:
    r = await session.execute(
        text("""SELECT taken_at, period_label, total_places, total_reviews, total_analyzed
                FROM stat_snapshots WHERE id = :id"""),
        {"id": snap_id},
    )
    s = r.fetchone()
    safe_print(f"\n✅ เก็บ snapshot #{snap_id} สำเร็จ")
    safe_print(f"   ช่วง: {s.period_label or '(ไม่ระบุ)'} | สถานที่ {s.total_places} | "
               f"รีวิว {s.total_reviews:,} | วิเคราะห์แล้ว {s.total_analyzed:,}")

    r = await session.execute(
        text("""SELECT COUNT(*) FILTER (WHERE zone IS NULL) AS overall,
                       COUNT(*) FILTER (WHERE zone IS NOT NULL) AS by_zone
                FROM snapshot_categories WHERE snapshot_id = :id"""),
        {"id": snap_id},
    )
    c = r.fetchone()
    r2 = await session.execute(
        text("SELECT COUNT(*) FROM snapshot_places WHERE snapshot_id = :id"), {"id": snap_id}
    )
    safe_print(f"   บันทึก: หมวดภาพรวม {c.overall} | หมวดแยกโซน {c.by_zone} | ร้าน×หมวด {r2.scalar():,}")

    r = await session.execute(
        text("""SELECT category, complaint_count FROM snapshot_categories
                WHERE snapshot_id = :id AND zone IS NULL
                  AND category NOT IN ('ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)','อื่นๆ','ไม่มี')
                ORDER BY complaint_count DESC LIMIT 5"""),
        {"id": snap_id},
    )
    safe_print("\n   Top 5 ปัญหา (คำบ่น) ณ snapshot นี้:")
    for x in r.fetchall():
        safe_print(f"     {x.complaint_count:>5} | {x.category}")


async def main(label, as_of, note, do_list):
    async with AsyncSessionLocal() as session:
        if do_list:
            await list_snapshots(session)
            return
        if as_of and not label:
            label = as_of.isoformat()
        snap_id = await take_snapshot(session, label, as_of, note)
        await show_snapshot(session, snap_id)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default=None, help="ชื่อช่วง เช่น 2026-W34 หรือ 2026-08")
    ap.add_argument("--as-of", dest="as_of", default=None,
                    help="สร้าง snapshot ย้อนอดีต — นับเฉพาะรีวิวถึงวันนี้ (YYYY-MM-DD)")
    ap.add_argument("--note", default=None, help="หมายเหตุ")
    ap.add_argument("--list", action="store_true", dest="do_list", help="ดูรายการ snapshot")
    a = ap.parse_args()
    asyncio.run(main(a.label, _parse_date(a.as_of), a.note, a.do_list))
