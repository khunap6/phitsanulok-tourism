"""
fix_place_category.py — ซ่อม places.google_category ที่เก็บข้อความปุ่ม UI มาผิด

ปัญหาที่แก้ (พบจริง 27 ก.ย. 2026):
  ร้านที่เจ้าของยังไม่ได้ยืนยันข้อมูลกับ Google จะไม่มีหมวดหมู่แสดงในหน้าร้าน
  แต่ Google เอา**ปุ่มชวนแก้ไขข้อมูล** มาวางที่ตำแหน่งเดียวกัน ตัวอ่านหมวดใน
  scraper_core จึงเก็บข้อความปุ่มมาเป็นหมวด

  เจอ 4 ร้าน:
    id=664  Nature Park Resort              'เพิ่มเว็บไซต์'   (จริง ๆ เป็นที่พัก)
    id=651  พีพี การ์เด้น                    'เพิ่มเวลาทำการ'
    id=827  ทศวรรณ เกสต์เฮ้าส์               'เพิ่มเว็บไซต์'   (จริง ๆ เป็นที่พัก)
    id=3596 โจ๊กอัมรินทร์นคร (เจ้าเก่า)       'เพิ่มเว็บไซต์'

  ต้นเหตุถูกปิดแล้วใน scraper_core._is_ui_button_text() — รอบต่อไปจะไม่เกิดอีก
  สคริปต์นี้แก้ข้อมูลที่ค้างอยู่

หลักการ: เชื่อ google_types จาก Places API ไม่เชื่อหน้าเว็บ
  google_types มาจาก API ตรง ๆ แม่นกว่าการอ่าน DOM ที่เปลี่ยนรูปแบบได้

⚠️ แตะเฉพาะแถวที่หมวด "ผิดชัดเจน" เท่านั้น
  คือเป็นข้อความปุ่ม UI หรือเป็น NULL — **ไม่ทับหมวดที่ดีอยู่แล้ว**
  เพราะหมวดที่ scrape มาถูกต้องละเอียดกว่า types เยอะ ('ร้านอาหารญี่ปุ่น'
  ละเอียดกว่า 'restaurant' · 'รีสอร์ท' ละเอียดกว่า 'lodging')
  ทับทิ้งคือทำให้ข้อมูลหยาบลง ไม่ใช่การซ่อม

⚠️ types ตัวแรกที่แมปได้ชนะ ไม่ใช่ตัวแรกในสตริง
  Google เรียง types ไม่คงที่ — บางร้านขึ้นต้นด้วย 'establishment' ซึ่งเป็น
  ประเภทกว้างไร้ความหมาย จึงต้องไล่ตามลำดับความเฉพาะเจาะจงที่เรากำหนด
  (ดู TYPE_TO_THAI) ไม่ใช่ลำดับที่ Google ส่งมา

รัน:
  uv run python scripts/fix_place_category.py            # DRY-RUN
  uv run python scripts/fix_place_category.py --apply    # ทำจริง
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from scraper.scraper_core import UI_BUTTON_PREFIXES, _is_ui_button_text

# แมป google_type -> หมวดภาษาไทย
#
# เรียงจาก "เฉพาะเจาะจงที่สุด" ลงมา — ตัวที่เจอก่อนชนะ
# ค่าภาษาไทยเลือกให้ตรงกับค่าที่มีอยู่ในฐานแล้ว เพื่อไม่สร้างหมวดซ้ำซ้อน
# (เช่น 'ที่พัก' มีอยู่แล้วที่ id=649 · 'ร้านกาแฟ' ใช้อยู่หลายร้าน)
TYPE_TO_THAI: list[tuple[str, str]] = [
    ("bakery", "ร้านเบเกอรี่"),
    ("cafe", "ร้านกาแฟ"),
    ("restaurant", "ร้านอาหาร"),
    ("museum", "พิพิธภัณฑ์"),
    ("park", "สวนสาธารณะ"),
    ("university", "มหาวิทยาลัย"),
    ("place_of_worship", "ศาสนสถาน"),
    ("tourist_attraction", "สถานที่ท่องเที่ยว"),
    ("campground", "ลานกางเต็นท์"),
    ("lodging", "ที่พัก"),
    ("library", "ห้องสมุด"),
    ("stadium", "สนามกีฬา"),
    ("travel_agency", "บริษัทนำเที่ยว"),
    ("store", "ร้านค้า"),
    # 'food' อยู่ท้ายสุดเพราะกว้าง — ขึ้นเฉพาะเมื่อไม่มี restaurant/cafe/bakery
    # (Shareloma Outdoor x Grill ได้ types แค่ establishment,food แต่เป็นร้านอาหารจริง)
    ("food", "ร้านอาหาร"),
    # ไม่แมปโดยเจตนา:
    #   establishment, point_of_interest, business — กว้างเกินจะบอกอะไรได้
    #   school, secondary_school, local_government_office, general_contractor —
    #     Google ติด type พวกนี้ผิดบ่อย (ศาลสมเด็จพระนเรศวรฯ ได้ secondary_school ·
    #     จุดเล่นน้ำท้ายเขื่อนได้ local_government_office) แมปแล้วจะผิดกว่าเดิม
    #   locality, political, administrative_area_level_* — ไม่ใช่ร้าน เป็นเขตปกครอง
    #     ดู exclude_places.py --admin-areas
]


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def category_from_types(google_types: str | None) -> str | None:
    """หาหมวดภาษาไทยจาก google_types — คืน None ถ้าบอกอะไรไม่ได้"""
    if not google_types:
        return None
    parts = {t.strip() for t in google_types.split(",") if t.strip()}
    for gtype, thai in TYPE_TO_THAI:
        if gtype in parts:
            return thai
    return None


async def load_dirty(session) -> list:
    """แถวที่หมวดผิดชัดเจน: เป็นข้อความปุ่ม UI หรือเป็น NULL

    กรองข้อความปุ่มด้วย Python ไม่ใช่ SQL IN (...) เพื่อใช้ UI_BUTTON_PREFIXES
    ชุดเดียวกับ scraper_core — ถ้าเขียนรายการซ้ำใน SQL สองที่จะเพี้ยนกันภายหลัง
    """
    rows = (await session.execute(text("""
        SELECT p.id, p.name, p.google_category AS gc, p.google_types AS gt,
               p.google_reviews_total AS g, p.discovered_by AS db,
               (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS sc
        FROM places p
        WHERE p.google_category IS NULL
           OR p.google_category = ''
           OR p.google_category LIKE 'เพิ่ม%'
           OR p.google_category LIKE 'อ้างสิทธิ์%'
           OR p.google_category LIKE 'แนะนำ%'
           OR p.google_category LIKE 'ยืนยัน%'
           OR p.google_category LIKE 'Add %'
           OR p.google_category LIKE 'Claim %'
           OR p.google_category LIKE 'Suggest %'
        ORDER BY p.google_reviews_total DESC NULLS LAST
    """))).fetchall()

    out = []
    for r in rows:
        gc = (r.gc or "").strip()
        if gc and not _is_ui_button_text(gc):
            continue           # หมวดจริงที่เผอิญขึ้นต้นเหมือนปุ่ม — ไม่แตะ
        out.append(r)
    return out


async def report(session, apply: bool) -> None:
    rows = await load_dirty(session)

    # ข้อความปุ่ม UI ต้องถูกล้างทิ้งทุกกรณี แม้เดาหมวดใหม่ไม่ได้ —
    # ค่าผิดแย่กว่าค่าว่าง เพราะ zone_breakdown จะนับ 'เพิ่มเว็บไซต์'
    # เป็นหมวดหนึ่งในกราฟ ส่วนแถวที่เป็น NULL อยู่แล้วและเดาไม่ได้ ไม่ต้องแตะ
    plan: list[tuple] = []     # (row, ค่าใหม่ — None = ล้างทิ้ง)
    no_guess: list = []        # NULL อยู่แล้วและ types บอกอะไรไม่ได้
    for r in rows:
        new = category_from_types(r.gt)
        is_junk = bool((r.gc or "").strip())
        if new:
            plan.append((r, new))
        elif is_junk:
            plan.append((r, None))
        else:
            no_guess.append(r)

    junk = [r for r in rows if (r.gc or "").strip()]

    p("=" * 78)
    p(f"  {'ทำจริง' if apply else 'DRY-RUN'} — ซ่อม google_category จาก google_types")
    p("=" * 78)
    p(f"  หมวดผิดชัดเจนทั้งหมด {len(rows)} ร้าน")
    p(f"    เป็นข้อความปุ่ม UI {len(junk)} ร้าน · เป็น NULL/ว่าง {len(rows) - len(junk)} ร้าน")
    p(f"  เดาหมวดได้จาก types {len(plan)} ร้าน · เดาไม่ได้ {len(no_guess)} ร้าน")

    if junk:
        p()
        p("  --- ข้อความปุ่ม UI ที่ต้องล้าง ---")
        for r in junk:
            new = category_from_types(r.gt)
            p(f"    id={r.id:<5} {r.name[:34]:<36} {r.gc!r} -> {new!r}")

    if plan:
        p()
        p(f"  --- จะเปลี่ยนเป็น ({len(plan)} ร้าน) ---")
        by_new: dict[str, int] = {}
        for _, new in plan:
            key = new if new else "(ล้างเป็นค่าว่าง)"
            by_new[key] = by_new.get(key, 0) + 1
        for new, n in sorted(by_new.items(), key=lambda kv: -kv[1]):
            p(f"    {new:<22} {n:>4} ร้าน")
        p()
        for r, new in plan[:25]:
            p(f"    id={r.id:<5} Google {str(r.g or '-'):>5} เก็บ {r.sc:>4}  "
              f"{r.name[:30]:<32} {r.gc!r} -> {new!r}")
        if len(plan) > 25:
            p(f"    ... และอีก {len(plan) - 25} ร้าน")

    if no_guess:
        p()
        p(f"  --- หมวดว่างอยู่แล้วและเดาไม่ได้ ไม่ต้องแตะ ({len(no_guess)} ร้าน) ---")
        p(f"      (types กว้างเกินจะบอกอะไร หรือไม่มี types เลย)")
        for r in no_guess[:10]:
            p(f"    id={r.id:<5} {r.name[:32]:<34} types={(r.gt or '(ไม่มี)')[:40]}")
        if len(no_guess) > 10:
            p(f"    ... และอีก {len(no_guess) - 10} ร้าน")

    if not apply:
        p()
        p("  ยังไม่ได้แก้อะไร — เติม --apply เพื่อทำจริง")
        p("  ⚠️ ไม่ทับหมวดที่ดีอยู่แล้ว · ไม่แตะรีวิว · ไม่แตะ scraped_at")
        p("=" * 78)
        return

    if not plan:
        p("\n  ไม่มีอะไรต้องแก้")
        p("=" * 78)
        return

    for r, new in plan:
        await session.execute(text("""
            UPDATE places SET google_category = :gc WHERE id = :id
        """), {"gc": new, "id": r.id})
    await session.commit()

    left = await load_dirty(session)
    p()
    p(f"  ✅ แก้หมวดแล้ว {len(plan)} ร้าน")
    p(f"  เหลือหมวดที่ยังบอกไม่ได้ {len(left)} ร้าน (types กว้างเกิน)")
    p(f"  รีวิวในระบบ {(await session.execute(text('SELECT count(*) FROM reviews'))).scalar():,} อัน (ไม่ถูกแตะ)")
    p("=" * 78)


async def run(args) -> int:
    async with AsyncSessionLocal() as session:
        await report(session, args.apply)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="ซ่อม google_category ที่เก็บข้อความปุ่ม UI มาผิด")
    ap.add_argument("--apply", action="store_true",
                    help="ทำจริง (ไม่ใส่ = DRY-RUN ดูเฉย ๆ)")
    sys.exit(asyncio.run(run(ap.parse_args())))
