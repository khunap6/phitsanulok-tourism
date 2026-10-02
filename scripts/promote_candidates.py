"""
promote_candidates.py — เลื่อนร้านจากตารางพัก place_candidates เข้าตาราง places

ทำไมต้องมีขั้นนี้:
  ร้าน 8,147 แห่งในตารางพัก **ไม่มีใครในระบบอ่านเลย** — หน้าเว็บ, API, scraper,
  รายงาน ทั้งหมดอ่านจาก places เท่านั้น ตารางพักเป็นบันทึกการสำรวจ ยังไม่ใช่ข้อมูลของระบบ

    place_candidates --[สคริปต์นี้]--> places --> auto_refresh --> reviews --> NLP --> เว็บ

⚠️ เลื่อนเฉพาะร้านที่ผ่านเกณฑ์ ห้ามเลื่อนทั้งหมด
  scraper/scraper.py:65 เลือกคิว refresh ด้วย
      WHERE scraped_at IS NULL ... ORDER BY scraped_at ASC NULLS FIRST
  แถวใหม่ที่ scraped_at เป็น NULL จึง**ขึ้นหัวคิวทันที** ถ้าเลื่อนทั้ง 7,911 ร้าน
  auto_refresh จะไล่ scrape ทั้งหมด = ~31 ชม. ไปกับร้านที่ส่วนใหญ่ไม่มีรีวิว
  และดันร้านที่ควรเก็บไปท้ายคิว
  นอกจากนี้ places ถูกใช้นับสถิติบนหน้าเว็บ เพิ่มจาก 323 เป็น 8,234 แถวโดย 95%
  ไม่มีรีวิว จะทำให้ทุกตัวส่วนเปลี่ยนความหมาย (ผิดหลักเดียวกับกฎข้อ 1)

4 โหมด แยกกันโดยเจตนา:
  (ไม่ใส่ flag)   DRY-RUN  รายชื่อร้าน + ราคา + ตรวจการชนชื่อ           ไม่ยิง API
  --reject-list   ตั้งธง decision='reject' ให้ร้านที่คัดออกด้วยมือ       ไม่ยิง API
  --details       ยิง Places Details เก็บที่อยู่เต็ม + เวลาทำการ         [ใช้เครดิต]
  --promote       เขียนเข้า places                                      ไม่ยิง API

  แยก --details กับ --promote เพราะขั้นแรกเสียเงินและมีกำหนด 31 ต.ค. 2026
  (วันหมดอายุเครดิต Free Trial) ขั้นสองฟรีและย้อนกลับได้ ถ้ารวมเป็นคำสั่งเดียว
  แล้วพังกลางทาง จะไม่รู้ว่าจ่ายไปแล้วแต่ยังไม่เข้า places หรือเปล่า

รัน:
  uv run python scripts/promote_candidates.py                      # DRY-RUN
  uv run python scripts/promote_candidates.py --reject-list        # ตั้งธงคัดออกด้วยมือ
  uv run python scripts/promote_candidates.py --details --limit 5  # ทดสอบ 5 ร้าน (~฿4)
  uv run python scripts/promote_candidates.py --details            # ยิงครบ (~$11)
  uv run python scripts/promote_candidates.py --promote            # เขียนเข้า places
  uv run python scripts/promote_candidates.py --min-reviews 30     # ปรับเกณฑ์
"""
import argparse
import asyncio
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from scraper import places_api
from scraper.places_api import COST_PER_REQUEST_USD, PlacesApiError, place_details
from scraper.scraper_core import is_in_phitsanulok
from scraper.zones import _haversine_km, assign_zone, distance_to_campus_km

MIN_REVIEWS_DEFAULT = 50
REQUEST_DELAY_SEC = 0.15
# sentinel เดียวกับ fetch_hours_api.py — "ดึงแล้วแต่ Google ไม่มีเวลาทำการ"
# ต่างจาก NULL ที่หมายถึง "ยังไม่เคยดึง"
NO_HOURS = "ไม่ระบุ"

# ── ร้านที่คัดออกด้วยมือ (ความรู้ท้องถิ่นที่ google_types บอกไม่ได้) ──
# ใช้ google_place_id ไม่ใช่ชื่อ เพราะชื่อบน Google เปลี่ยนได้
# และ ON CONFLICT ของ discover_api.py ไม่ทับคอลัมน์ decision → ธงนี้อยู่ถาวร
MANUAL_REJECT = {
    "ChIJGxaMbTm93zARQrhTVOd7Im8":
        "The Horizon Groove — เป็นโรงแรม (Google ติด restaurant เพราะมีห้องอาหาร)",
    "ChIJRQJtaQW93zARZDiCNN030oM":
        "PHITSANULOK UNITED — เป็นโรงแรม (Google ติด restaurant เพราะมีห้องอาหาร)",
}

# ── เชน/ห้าง/โรงแรม ที่คัดออกด้วยชื่อ ──
_CHAIN = (r"(starbucks|cafe ?amazon|café ?amazon|อเมซอน|inthanin|อินทนิล|"
          r"pizza company|sukishi|mcdonald|แมคโดนัลด์|kfc|เคเอฟซี|sizzler|"
          r"ซิซซ์เล่อร์|swensen|สเวนเซ่น|dairy queen|7-eleven|เซเว่น|bonchon|"
          r"ชาบูชิ|yayoi|ยาโยอิ|ฟูจิ|mk restaurant|เอ็มเค|texas chicken|"
          r"burger king|โออิชิ|oishi|สุกี้ตี๋น้อย|ตี๋น้อย)")
_PLACE = (r"(โรงแรม|hotel|resort|รีสอร์ท|hostel|โฮสเทล|เกสท์เฮาส์|guest ?house|"
          r"เซ็นทรัล|central ?plaza|central ?phitsanulok|โลตัส|lotus|บิ๊กซี|"
          r"big ?c|makro|แม็คโคร|homepro|โฮมโปร|โกลบอลเฮ้าส์|global ?house|"
          r"ไทวัสดุ|dohome|ดูโฮม|index living|อินเด็กซ์)")

# type ที่ถือว่าเป็นสถานที่ที่วิทยานิพนธ์สนใจ — ดูจาก google_types ของตัวสถานที่เอง
_WANT_TYPES = ["cafe", "restaurant", "bakery", "tourist_attraction",
               "museum", "park", "university", "place_of_worship"]


def keep_sql(alias: str = "c", min_reviews: int = MIN_REVIEWS_DEFAULT) -> str:
    """
    เงื่อนไข SQL ของ "ร้านที่ควรเลื่อนเข้า places"

    ⚠️ ต้องระบุ alias ทุกคอลัมน์ ไม่ใช้ชื่อเปล่า
      place_candidates กับ places มีคอลัมน์ชื่อซ้ำกันหลายตัว (name, google_types,
      google_reviews_total, formatted_address) พอ JOIN สองตารางแล้วใช้ชื่อเปล่า
      Postgres จะตอบ AmbiguousColumnError ทันที — เจอมาแล้วตอนตรวจการชนชื่อ

    3 เงื่อนไข:
      1. ยังไม่ถูกเลื่อน/ไม่ถูกคัดออก (decision = 'new')
      2. มีรีวิวบน Google >= min_reviews
         เหตุผล: คำบ่นมีราว 6% ของรีวิวทั้งหมด (วัดจากข้อมูลจริง 2,405/38,029)
         ร้านที่มี 50 รีวิวจึงให้คำบ่นที่วิเคราะห์ได้ ~3 อัน ต่ำกว่านี้ไม่มีอะไรให้ NLP ทำ
      3. เป็นประเภทที่สนใจจริง และไม่ใช่เชน/ห้าง/โรงแรม

    ⚠️ ข้อ 3 ดูจาก google_types (ตัวตนจริงของสถานที่) **ไม่ใช่** source_type
      (type ที่ค้นเจอ) เพราะการค้นด้วย place_of_worship ถูก Google เพิกเฉย
      แล้วคืนทุกอย่างในรัศมีมาให้ ถ้ากรองด้วย source_type จะทิ้งวัดจริง 4 แห่ง
      (วัดคูหาสวรรค์ 252 รีวิว ฯลฯ) ที่เผอิญถูกคืนจากคำค้นนั้น

    ⚠️ ตัดโรงแรม/ห้างเฉพาะที่เป็น "ล้วน" (ไม่มี restaurant/cafe ใน types)
      ถ้าตัดทุกอย่างที่มี lodging จะตัดร้านอาหารที่อยู่ในโรงแรมทิ้งด้วย
      ส่วนโรงแรมที่มีห้องอาหาร (จึงติด restaurant) ดักด้วยชื่อใน _PLACE
    """
    want = " OR ".join(f"{alias}.google_types LIKE '%{t}%'" for t in _WANT_TYPES)
    pure = (f"(({alias}.google_types LIKE '%lodging%' "
            f"OR {alias}.google_types LIKE '%shopping_mall%' "
            f"OR {alias}.google_types LIKE '%supermarket%' "
            f"OR {alias}.google_types LIKE '%department_store%') "
            f"AND {alias}.google_types NOT LIKE '%restaurant%' "
            f"AND {alias}.google_types NOT LIKE '%cafe%')")
    excl = (f"({alias}.name ~* '{_CHAIN}' OR {alias}.name ~* '{_PLACE}' OR {pure})")
    return (f"{alias}.decision = 'new' "
            f"AND {alias}.google_reviews_total >= {int(min_reviews)} "
            f"AND ({want}) AND NOT {excl}")


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


# ---------------------------------------------------------------------------
# ตรวจการชนชื่อ (places.name เป็น UNIQUE)
# ---------------------------------------------------------------------------

async def coord_collisions(session, min_reviews: int,
                           max_m: float = 40.0) -> dict[str, dict]:
    """
    ผู้สมัครที่พิกัดตรงกับร้านที่มีอยู่แล้ว — คืน {place_id ของผู้สมัคร: ข้อมูลร้านเดิม}

    ⚠️ ทำไมต้องตรวจพิกัด ไม่ใช่แค่ชื่อ (บทเรียนราคา 26 แถวซ้ำ)

    รอบแรกผมตรวจแค่ "ชื่อตรงกันเป๊ะ" เจอ 1 คู่แล้วสรุปว่าปลอดภัย — **ผิดทิศ**
    ปัญหาไม่ใช่ชื่อชนกัน แต่เป็น**ชื่อไม่ชนทั้งที่เป็นร้านเดียวกัน**:

        promote สร้างแถวด้วยชื่อจาก API   -> "Pang Ki Khao Man Kai"
        auto_refresh ค้นชื่อนั้น Google แสดง -> "พังกี่ข้าวมันไก่"
        save_to_db ON CONFLICT (name) ไม่ตรง -> INSERT แถวใหม่

    ผลคือร้านเดียวกันมี 2 แถว · นับร้านเกินจริง · แถว API ค้างในคิว refresh ตลอดไป
    เพราะ refresh สร้างแถวใหม่ทุกครั้งไม่มาเติมแถวเดิม (วน scrape ไม่รู้จบ)

    ชื่ออังกฤษจาก API กับชื่อไทยบนหน้าเว็บเทียบกันด้วยข้อความไม่ได้เลย
    **พิกัดเท่านั้นที่เชื่อได้** — คู่ที่พบจริงทั้ง 26 คู่ห่างกัน 0 เมตร
    """
    cands = (await session.execute(
        text(f"""
            SELECT c.google_place_id AS pid, c.name, c.lat, c.lng
            FROM place_candidates c
            WHERE {keep_sql('c', min_reviews)} AND c.lat IS NOT NULL
        """))).fetchall()
    if not cands:
        return {}

    existing = (await session.execute(text("""
        SELECT p.id, p.name, p.google_place_id AS gpid,
               ST_Y(p.location::geometry) AS lat, ST_X(p.location::geometry) AS lng,
               (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS sc
        FROM places p WHERE p.location IS NOT NULL
    """))).fetchall()

    out: dict[str, dict] = {}
    for c in cands:
        for e in existing:
            d = _haversine_km(c.lat, c.lng, e.lat, e.lng) * 1000
            if d > max_m:
                continue
            # ร้านเดิมมี place_id คนละตัว = Google ถือว่าคนละสถานที่ (2 สาขาในตึกเดียว)
            if e.gpid and e.gpid != c.pid:
                continue
            prev = out.get(c.pid)
            if prev is None or d < prev["dist"]:
                out[c.pid] = {"id": e.id, "name": e.name, "sc": e.sc,
                              "gpid": e.gpid, "dist": d}
    return out


async def name_collisions(session, min_reviews: int) -> list[dict]:
    """
    ร้านที่จะเลื่อน ซึ่งชื่อตรงกับแถวใน places อยู่แล้ว

    3 กรณี:
      fill  = ร้านเดิมยังไม่มี google_place_id → เป็นร้านเดียวกัน UPDATE เติมให้
              (เกิดจากร้านที่ backfill_place_id หาไม่เจอด้วยชื่อ แต่ Nearby Search
               หาเจอเพราะค้นด้วยพิกัด+type)
      same  = place_id ตรงกัน → ร้านเดียวกันแน่ ไม่มีอะไรต้องทำ
      clash = place_id ต่างกัน → คนละร้านชื่อเหมือน ต้องดูด้วยมือ ข้ามไว้ก่อน
    """
    rows = (await session.execute(
        text(f"""
            SELECT c.google_place_id AS cpid, c.name, c.google_reviews_total AS g,
                   p.id AS pid, p.google_place_id AS ppid,
                   (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS scraped
            FROM place_candidates c
            JOIN places p ON p.name = c.name
            WHERE {keep_sql('c', min_reviews)}
            ORDER BY c.google_reviews_total DESC
        """))).fetchall()
    out = []
    for r in rows:
        kind = ("same" if r.ppid == r.cpid
                else ("fill" if r.ppid is None else "clash"))
        out.append({"kind": kind, "cpid": r.cpid, "name": r.name, "g": r.g,
                    "pid": r.pid, "ppid": r.ppid, "scraped": r.scraped})
    return out


# ---------------------------------------------------------------------------
# โหมด: ตั้งธงคัดออกด้วยมือ
# ---------------------------------------------------------------------------

async def apply_reject_list(session) -> None:
    p("=" * 70)
    p("  ตั้งธง decision='reject' ให้ร้านที่คัดออกด้วยมือ")
    p("=" * 70)
    p("\n  (ความรู้ท้องถิ่นที่ google_types บอกไม่ได้ — Google ติด type restaurant")
    p("   ให้โรงแรมที่มีห้องอาหาร ทำให้ตัวกรองอัตโนมัติแยกไม่ออก)\n")
    done = skipped = 0
    for pid, reason in MANUAL_REJECT.items():
        row = (await session.execute(
            text("""SELECT name, decision FROM place_candidates
                    WHERE google_place_id = :pid"""), {"pid": pid})).fetchone()
        if not row:
            p(f"  ⚠️ ไม่พบ place_id {pid} ในตารางพัก — ข้าม")
            skipped += 1
            continue
        if row.decision == "reject":
            p(f"  – ตั้งไว้แล้ว: {row.name[:44]}")
            skipped += 1
            continue
        await session.execute(
            text("""UPDATE place_candidates SET decision = 'reject'
                    WHERE google_place_id = :pid"""), {"pid": pid})
        p(f"  ✅ {row.name[:44]}")
        p(f"     เหตุผล: {reason}")
        done += 1
    await session.commit()
    p(f"\n  ตั้งธงใหม่ {done} ร้าน | ข้าม {skipped} ร้าน")
    p("\n  ข้อมูลไม่ถูกลบ — แถวยังอยู่ครบในตารางพัก แค่ไม่ถูกเลื่อนเข้า places")
    p("  ยกเลิกได้ด้วย: UPDATE place_candidates SET decision='new' WHERE ...")
    p("=" * 70)


# ---------------------------------------------------------------------------
# โหมด: ยิง Details
# ---------------------------------------------------------------------------

_SAVE_DETAILS = text("""
    UPDATE place_candidates SET
        formatted_address  = :addr,
        opening_hours      = :hours,
        details_fetched_at = NOW()
    WHERE google_place_id = CAST(:pid AS varchar(64))
""")


async def fetch_details(session, min_reviews: int, limit, max_requests) -> None:
    targets = (await session.execute(
        text(f"""
            SELECT c.google_place_id AS pid, c.name
            FROM place_candidates c
            WHERE {keep_sql('c', min_reviews)}
              AND c.details_fetched_at IS NULL
            ORDER BY c.google_reviews_total DESC
            {f'LIMIT {int(limit)}' if limit else ''}
        """))).fetchall()

    if not targets:
        p("✅ ดึง Details ครบแล้วทุกร้านที่ผ่านเกณฑ์ (ใช้ --promote ต่อได้)")
        return

    try:
        places_api.require_api_key()
    except PlacesApiError as e:
        p(f"❌ {e}")
        return

    p(f"ยิง Places Details: {len(targets)} ร้าน"
      + (f" | เพดานคำขอ {max_requests}" if max_requests is not None else ""))
    p(f"เก็บ formatted_address + opening_hours (Nearby Search ไม่ให้ 2 ฟิลด์นี้)\n")

    ok = no_hours = failed = 0
    for i, t in enumerate(targets):
        if max_requests is not None and places_api.request_count >= max_requests:
            p(f"\n⛔ ชนเพดานคำขอ {max_requests} — หยุดที่ร้านที่ {i + 1}/{len(targets)}")
            p("   รันคำสั่งเดิมซ้ำได้เลย จะทำต่อจากจุดนี้ "
              "(ข้ามร้านที่ details_fetched_at ไม่ใช่ NULL)")
            break

        p(f"[{i + 1}/{len(targets)}] {t.name[:50]}")
        try:
            d = place_details(t.pid)
        except PlacesApiError as e:
            p(f"  ❌ {e}")
            failed += 1
            time.sleep(REQUEST_DELAY_SEC)
            continue

        if d["_status"] != "OK":
            p(f"  ⚠️ ดึงไม่ได้ ({d['_status']})")
            failed += 1
            time.sleep(REQUEST_DELAY_SEC)
            continue

        hours = d.get("opening_hours") or NO_HOURS
        await session.execute(_SAVE_DETAILS, {
            "addr": d.get("formatted_address"), "hours": hours, "pid": t.pid,
        })
        await session.commit()
        if d.get("opening_hours"):
            ok += 1
        else:
            no_hours += 1
        p(f"  ✅ {hours[:44]}")
        p(f"     {(d.get('formatted_address') or '-')[:58]}")
        time.sleep(REQUEST_DELAY_SEC)

    p("\n" + "=" * 60)
    p(f"✅ ได้เวลาทำการ       {ok}")
    p(f"➖ Google ไม่มีเวลา   {no_hours}")
    p(f"❌ ดึงไม่ได้          {failed}")
    p(f"📡 คำขอที่ยิงจริง     {places_api.request_count}")
    p(f"💰 ประเมินค่าใช้จ่าย  "
      f"~${places_api.request_count * COST_PER_REQUEST_USD:.2f} "
      f"(ยืนยันยอดจริงที่ Billing > Reports)")
    p(f"\nขั้นต่อไป (ไม่ใช้เครดิต):")
    p(f"  uv run python scripts/promote_candidates.py --promote")
    p("=" * 60)


# ---------------------------------------------------------------------------
# โหมด: เลื่อนเข้า places
# ---------------------------------------------------------------------------

# INSERT ร้านใหม่ — คำนวณ zone/ระยะทางด้วยฟังก์ชันเดิมของโปรเจกต์ใน Python
# แล้วส่งค่าเข้ามา (ไม่คำนวณใน SQL) เพื่อให้ผลตรงกับที่ scraper คำนวณเป๊ะ
#
# scraped_at = NULL โดยเจตนา → auto_refresh หยิบไปเก็บรีวิวต่อ (NULLS FIRST)
# overall_rating = NULL โดยเจตนา → ปล่อยให้ save_to_db เติมตอน scrape จริง
#   ไม่เอา google_rating มาใส่ เพราะคอลัมน์นั้นหมายถึง "เรตติ้งที่ scrape มา"
#   ถ้าปนสองแหล่งในคอลัมน์เดียวจะเทียบกันไม่ได้ (เหตุผลเดียวกับ migration 012)
_INSERT_PLACE = text("""
    INSERT INTO places (
        name, search_query, opening_hours, business_status,
        location, zone, distance_nu_km, distance_psru_km, scraped_at,
        google_place_id, google_types, formatted_address,
        google_rating, google_reviews_total, api_fetched_at, discovered_by
    ) VALUES (
        :name, :name, :hours, :status,
        ST_MakePoint(:lng, :lat), :zone, :dnu, :dpsru, NULL,
        CAST(:pid AS varchar(64)), :types, :addr,
        :rating, :total, NOW(), 'api'
    )
    RETURNING id
""")

# ร้านที่มีอยู่แล้วแต่ยังไม่มี place_id → เติมเฉพาะคอลัมน์ฝั่ง API
# ไม่แตะ name / location / opening_hours / business_status / zone / scraped_at /
# deep_* / overall_rating — หลักการเดียวกับ backfill_place_id.py
_FILL_PLACE = text("""
    UPDATE places SET
        google_place_id      = CAST(:pid AS varchar(64)),
        google_types         = :types,
        formatted_address    = :addr,
        google_rating        = :rating,
        google_reviews_total = :total,
        api_fetched_at       = NOW(),
        discovered_by        = COALESCE(discovered_by, 'scrape')
    WHERE id = :id
""")

_MARK_PROMOTED = text("""
    UPDATE place_candidates
    SET matched_place_id = :pid_int, decision = 'existing'
    WHERE google_place_id = CAST(:pid AS varchar(64))
""")


async def promote(session, min_reviews: int, limit) -> None:
    collisions = {c["cpid"]: c for c in await name_collisions(session, min_reviews)}
    # ตรวจพิกัดด้วย ไม่ใช่แค่ชื่อ — ดูเหตุผลใน coord_collisions()
    near = await coord_collisions(session, min_reviews)

    rows = (await session.execute(
        text(f"""
            SELECT c.google_place_id AS pid, c.name, c.lat, c.lng,
                   c.google_types, c.google_rating, c.google_reviews_total AS total,
                   c.business_status, c.formatted_address, c.opening_hours
            FROM place_candidates c
            WHERE {keep_sql('c', min_reviews)}
            ORDER BY c.google_reviews_total DESC
            {f'LIMIT {int(limit)}' if limit else ''}
        """))).fetchall()

    if not rows:
        p("✅ ไม่มีร้านที่ต้องเลื่อน (หรือเลื่อนไปแล้วทั้งหมด)")
        return

    p(f"เลื่อนเข้า places: {len(rows)} ร้าน\n")
    inserted = filled = skipped = no_details = outside = 0

    for i, r in enumerate(rows):
        # bbox เดียวกับ save_to_db — กันร้านนอกจังหวัดหลุดเข้า places
        if not is_in_phitsanulok(r.lat, r.lng):
            p(f"[{i + 1}/{len(rows)}] ⚠️ นอกพิษณุโลก ข้าม: {r.name[:44]}")
            outside += 1
            continue

        # พิกัดตรงกับร้านเดิมที่ยังไม่มี place_id = ร้านเดียวกัน ชื่อต่างกัน
        # -> เติม place_id ให้ร้านเดิม ไม่สร้างแถวใหม่ (กันแถวซ้ำ 26 คู่ที่เคยเกิด)
        hit = near.get(r.pid)
        if hit and hit["gpid"] is None:
            await session.execute(_FILL_PLACE, {
                "pid": r.pid, "types": r.google_types, "addr": r.formatted_address,
                "rating": r.google_rating, "total": r.total, "id": hit["id"],
            })
            await session.execute(_MARK_PROMOTED,
                                  {"pid_int": hit["id"], "pid": r.pid})
            await session.commit()
            filled += 1
            p(f"[{i + 1}/{len(rows)}] 🔗 พิกัดตรงกับร้านเดิม id={hit['id']} "
              f"(ห่าง {hit['dist']:.0f} ม.) — เติม place_id ไม่สร้างแถวใหม่")
            p(f"     API : {r.name[:40]}")
            p(f"     เดิม: {hit['name'][:40]}  (เก็บ {hit['sc']} รีวิว)")
            continue

        col = collisions.get(r.pid)
        if col and col["kind"] == "clash":
            p(f"[{i + 1}/{len(rows)}] ⚠️ ชื่อชนกับร้านอื่นที่มี place_id ต่างกัน — ข้าม")
            p(f"     {r.name[:52]}  (places id={col['pid']})")
            p(f"     ต้องดูด้วยมือว่าเป็นร้านเดียวกันหรือคนละร้านชื่อเหมือน")
            skipped += 1
            continue

        if r.formatted_address is None and r.opening_hours is None:
            no_details += 1

        zone = assign_zone(r.lat, r.lng)
        dnu, dpsru = distance_to_campus_km(r.lat, r.lng)
        params = {
            "name": r.name, "hours": r.opening_hours, "status": r.business_status,
            "lat": r.lat, "lng": r.lng, "zone": zone, "dnu": dnu, "dpsru": dpsru,
            "pid": r.pid, "types": r.google_types, "addr": r.formatted_address,
            "rating": r.google_rating, "total": r.total,
        }

        if col and col["kind"] == "fill":
            await session.execute(_FILL_PLACE, {**params, "id": col["pid"]})
            new_id = col["pid"]
            filled += 1
            p(f"[{i + 1}/{len(rows)}] 🔗 เติม place_id ให้ร้านเดิม id={new_id}: "
              f"{r.name[:38]}")
            p(f"     Google มี {r.total:,} รีวิว | เก็บได้แล้ว {col['scraped']} "
              f"({col['scraped'] / r.total * 100:.0f}%)")
        elif col and col["kind"] == "same":
            p(f"[{i + 1}/{len(rows)}] – มีใน places แล้ว (place_id ตรงกัน) ข้าม: "
              f"{r.name[:38]}")
            skipped += 1
            await session.execute(_MARK_PROMOTED,
                                  {"pid_int": col["pid"], "pid": r.pid})
            await session.commit()
            continue
        else:
            new_id = (await session.execute(_INSERT_PLACE, params)).scalar()
            inserted += 1
            p(f"[{i + 1}/{len(rows)}] ✅ id={new_id} zone={zone} "
              f"{r.total:,} รีวิว  {r.name[:36]}")

        await session.execute(_MARK_PROMOTED, {"pid_int": new_id, "pid": r.pid})
        await session.commit()

    total = (await session.execute(text("SELECT count(*) FROM places"))).scalar()
    queue = (await session.execute(
        text("SELECT count(*) FROM places WHERE scraped_at IS NULL"))).scalar()

    p("\n" + "=" * 62)
    p(f"✅ เพิ่มร้านใหม่           {inserted}")
    p(f"🔗 เติม place_id ร้านเดิม  {filled}")
    p(f"–  ข้าม                    {skipped}")
    if outside:
        p(f"⚠️  นอกพิษณุโลก           {outside}")
    if no_details:
        p(f"\n⚠️  ยังไม่มีที่อยู่/เวลาทำการ {no_details} ร้าน")
        p(f"    รัน --details ก่อนถ้าอยากได้ครบ (ต้องทำก่อนเครดิตหมด 31 ต.ค. 2026)")
    p(f"\n📊 places รวมทั้งหมด       {total} แถว")
    p(f"⏳ คิว refresh (scraped_at IS NULL)  {queue} ร้าน")
    p(f"\nขั้นต่อไป — เก็บรีวิว (ไม่ใช้เครดิต):")
    p(f"  uv run python scripts/auto_refresh.py --limit 40")
    p("=" * 62)


# ---------------------------------------------------------------------------
# DRY-RUN
# ---------------------------------------------------------------------------

async def dry_run(session, min_reviews: int) -> None:
    K = keep_sql("c", min_reviews)
    p("=" * 72)
    p(f"  DRY-RUN — ไม่ยิง API ไม่เขียนอะไร (เกณฑ์ >= {min_reviews} รีวิว)")
    p("=" * 72)

    tot = (await session.execute(text("""
        SELECT count(*) n,
               count(*) FILTER (WHERE decision = 'new') new_,
               count(*) FILTER (WHERE decision = 'existing') ex,
               count(*) FILTER (WHERE decision = 'reject') rej
        FROM place_candidates"""))).fetchone()
    p(f"\n  ตารางพัก place_candidates (บันทึกการสำรวจ — ไม่ลบอะไร)")
    p(f"    ทั้งหมด {tot.n:,} | new {tot.new_:,} | existing {tot.ex} | reject {tot.rej}")

    x = (await session.execute(text(f"""
        SELECT count(*) n,
               count(*) FILTER (WHERE c.google_reviews_total <= 200) ref,
               count(*) FILTER (WHERE c.google_reviews_total > 200) deep,
               count(*) FILTER (WHERE c.details_fetched_at IS NULL) need_det,
               coalesce(sum(LEAST(c.google_reviews_total, 850)), 0) cap
        FROM place_candidates c WHERE {K}"""))).fetchone()
    hrs = (x.ref * 14 / 60 + x.deep * 3) / 60
    p(f"\n  ผ่านเกณฑ์ที่จะเลื่อน {x.n} ร้าน")
    p(f"    refresh (<=200 รีวิว)  {x.ref:>4} x 14 วิ  = {x.ref * 14 / 60:>5.0f} นาที")
    p(f"    deep (>200 รีวิว)      {x.deep:>4} x 3 นาที = {x.deep * 3 / 60:>5.1f} ชม.")
    p(f"    เวลา scrape รวม       ~{hrs:.1f} ชม.  (ไม่รวมเวลาที่โดนบล็อกแล้วพัก)")
    p(f"    รีวิวที่เก็บได้ (เพดาน 850/ร้าน) ~{x.cap:,}")

    p(f"\n  ต้องยิง Details อีก {x.need_det} ร้าน "
      f"≈ ${x.need_det * COST_PER_REQUEST_USD:.2f}  [ใช้เครดิต · ก่อน 31 ต.ค. 2026]")

    pending = [pid for pid in MANUAL_REJECT if (await session.execute(
        text("""SELECT 1 FROM place_candidates
                WHERE google_place_id = :p AND decision = 'new'"""),
        {"p": pid})).fetchone()]
    if pending:
        p(f"\n  ⚠️ ยังไม่ได้ตั้งธงคัดออกด้วยมือ {len(pending)} ร้าน — รัน --reject-list ก่อน")
        for pid in pending:
            p(f"     {MANUAL_REJECT[pid]}")

    cols = await name_collisions(session, min_reviews)
    p(f"\n  ตรวจการชนชื่อกับ places เดิม (name เป็น UNIQUE): {len(cols)} ร้าน")
    for c in cols:
        label = {"fill": "🔗 เป็นร้านเดียวกัน → UPDATE เติม place_id ให้ร้านเดิม",
                 "same": "– place_id ตรงกัน → ข้าม",
                 "clash": "⚠️ place_id ต่างกัน → คนละร้านชื่อเหมือน ต้องดูมือ"}[c["kind"]]
        p(f"    {c['name'][:46]}")
        p(f"      Google {c['g']:,} รีวิว | places id={c['pid']} เก็บได้ {c['scraped']}")
        p(f"      {label}")

    z = (await session.execute(text(f"""
        SELECT c.zone, count(*) n, coalesce(sum(c.google_reviews_total), 0) rv
        FROM place_candidates c WHERE {K} GROUP BY 1 ORDER BY n DESC"""))).fetchall()
    p(f"\n  โซนที่ร้านใหม่จะไปอยู่ (คำนวณด้วย assign_zone เดิม ไม่แก้นิยามโซน)")
    for r in z:
        p(f"    {(r.zone or '-'):<14}{r.n:>4} ร้าน {r.rv:>8,} รีวิว")

    top = (await session.execute(text(f"""
        SELECT c.name, c.google_reviews_total g, c.google_rating rt, c.zone,
               c.google_types
        FROM place_candidates c WHERE {K}
        ORDER BY c.google_reviews_total DESC LIMIT 15"""))).fetchall()
    p(f"\n  15 อันดับแรกที่จะเลื่อน")
    for r in top:
        kind = next((t for t in _WANT_TYPES if t in (r.google_types or "")), "-")
        p(f"    {r.g:>6,} ⭐{float(r.rt) if r.rt else 0:.1f} {(r.zone or '-'):<12}"
          f"{kind:<18} {r.name[:30]}")

    p(f"\n  ลำดับที่แนะนำ:")
    p(f"    1. --reject-list        ฟรี   ตั้งธงคัดออกด้วยมือ")
    p(f"    2. --details --limit 5  ~฿4   ทดสอบเส้นทาง Details")
    p(f"    3. --details            ~${x.need_det * COST_PER_REQUEST_USD:.2f}  "
      f"ยิงครบ [ก่อน 31 ต.ค.]")
    p(f"    4. --promote            ฟรี   เขียนเข้า places")
    p("\n" + "=" * 72)


async def run(args):
    async with AsyncSessionLocal() as session:
        if args.reject_list:
            await apply_reject_list(session)
        elif args.details:
            await fetch_details(session, args.min_reviews, args.limit,
                                args.max_requests)
        elif args.do_promote:
            await promote(session, args.min_reviews, args.limit)
        else:
            await dry_run(session, args.min_reviews)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="เลื่อนร้านจาก place_candidates เข้า places")
    ap.add_argument("--reject-list", action="store_true",
                    help="ตั้งธง decision='reject' ให้ร้านที่คัดออกด้วยมือ (ไม่ยิง API)")
    ap.add_argument("--details", action="store_true",
                    help="ยิง Places Details เก็บที่อยู่เต็ม + เวลาทำการ [ใช้เครดิต]")
    ap.add_argument("--promote", action="store_true", dest="do_promote",
                    help="เขียนร้านที่ผ่านเกณฑ์เข้าตาราง places (ไม่ยิง API)")
    ap.add_argument("--min-reviews", type=int, default=MIN_REVIEWS_DEFAULT,
                    help=f"เกณฑ์จำนวนรีวิวบน Google (ค่าเริ่มต้น {MIN_REVIEWS_DEFAULT})")
    ap.add_argument("--limit", type=int, default=None,
                    help="จำกัดจำนวนร้าน (ใช้ทดสอบ)")
    ap.add_argument("--max-requests", type=int, default=None,
                    help="เพดานแข็ง: หยุดเมื่อยิงครบ N คำขอ")
    asyncio.run(run(ap.parse_args()))
