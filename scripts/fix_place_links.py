"""
fix_place_links.py — ซ่อมความเชื่อมโยงของแถวร้านที่ผิด ทีละรายการที่ระบุชัด

ต่างจาก merge_duplicate_places.py ที่หาคู่เองด้วยเกณฑ์อัตโนมัติ — ตัวนี้ทำ
**เฉพาะรายการที่ระบุด้วย id** เพราะเคสที่เหลือต้องใช้คนตัดสิน

3 โหมด:
  --merge KEEP DROP   รวมสองแถวที่เป็นร้านเดียวกัน
  --move-api FROM TO  ย้ายข้อมูล Places API ไปแถวที่เป็นเจ้าของจริง
  --delete ID         ลบแถวที่เป็นข้อมูลขยะ

⚠️ ลำดับใน --merge สำคัญมาก (บทเรียนจาก merge_duplicate_places)
  1. ย้าย reviews ด้วย ON CONFLICT (place_id, text_hash) DO NOTHING
     ถ้าไม่มี ON CONFLICT จะชน unique เมื่อสองแถวมีรีวิวเดียวกัน
     (วัดจริง: วงเวียนสถานีรถไฟ ~ สถานีรถไฟพิษณุโลก ซ้ำกัน 73 จาก 79 อัน)
  2. ย้าย snapshot_places.place_id — **ไม่ปล่อยให้ CASCADE ลบ**
     ตารางนี้ไม่มี unique constraint นอกจาก PK จึงย้ายได้ปลอดภัย
     ถ้าปล่อยให้ CASCADE จะเสียประวัติ snapshot ของร้านนั้น (เคสนี้ 60 แถว)
  3. ย้าย place_candidates.matched_place_id (FK เป็น SET NULL)
     ต้องทำก่อน DELETE ไม่งั้นค่าจะกลายเป็น NULL แล้ว promote ใส่แถวซ้ำกลับมา
  4. ย้ายข้อมูล API ให้แถวที่เก็บไว้ **เฉพาะช่องที่ยังว่าง** (COALESCE)
  5. DELETE แถวที่ทิ้ง
  6. ตั้ง google_place_id ของแถวที่เก็บไว้ **หลัง** DELETE
     เพราะ uq_places_google_place_id เป็น UNIQUE — ถ้าตั้งก่อนลบจะชนกันเอง

⚠️ ตรวจซ้ำก่อนลบทุกครั้ง — นับรีวิวของแถวที่จะลบต้องเป็น 0 แล้ว
  ถ้าไม่ใช่ หยุดทันทีและไม่ลบ ดีกว่าลบแล้วรีวิวหาย

รัน (DRY-RUN เป็นค่าเริ่มต้นทุกโหมด):
  uv run python scripts/fix_place_links.py --merge 387 75
  uv run python scripts/fix_place_links.py --merge 387 75 --apply
  uv run python scripts/fix_place_links.py --move-api 346 455 --apply
  uv run python scripts/fix_place_links.py --delete 259 --apply
"""
import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from scraper.scraper import DEEP_MIN_RATIO, SERVE_CEILING_DEEP

API_FIELDS = ["google_place_id", "google_types", "formatted_address",
              "google_rating", "google_reviews_total", "api_fetched_at"]


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


async def row(session, pid: int):
    return (await session.execute(text("""
        SELECT p.id, p.name, p.google_place_id AS gp, p.google_types AS gt,
               p.formatted_address AS addr, p.google_rating AS gr,
               p.google_reviews_total AS g, p.api_fetched_at AS af,
               p.zone, p.scrape_excluded AS ex,
               ST_Y(p.location) AS lat, ST_X(p.location) AS lng,
               (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS sc,
               (SELECT count(*) FROM snapshot_places s WHERE s.place_id = p.id) AS snap,
               (SELECT count(*) FROM place_candidates c
                  WHERE c.matched_place_id = p.id) AS cand
        FROM places p WHERE p.id = :i
    """), {"i": pid})).fetchone()


def show(r, label: str) -> None:
    p(f"    {label} id={r.id}  {r.name[:46]}")
    p(f"        รีวิว {r.sc} · snapshot {r.snap} แถว · candidates {r.cand} แถว")
    p(f"        pid={r.gp or '-'} · G={r.g or '-'} · ดาว={r.gr or '-'} · โซน={r.zone}")
    p(f"        พิกัด ({float(r.lat):.7f}, {float(r.lng):.7f})"
      if r.lat is not None else "        ไม่มีพิกัด")


# ─────────────────────────────────────────────────────────────────────
async def do_merge(session, keep_id: int, drop_id: int, apply: bool) -> None:
    keep, drop = await row(session, keep_id), await row(session, drop_id)
    p("=" * 78)
    p(f"  {'ทำจริง' if apply else 'DRY-RUN'} — รวมสองแถวที่เป็นร้านเดียวกัน")
    p("=" * 78)
    if not keep or not drop:
        p(f"  ไม่พบแถว id={keep_id if not keep else drop_id}")
        return
    show(keep, "เก็บไว้")
    show(drop, "จะลบ   ")

    dist = (await session.execute(text("""
        SELECT ST_Distance(a.location::geography, b.location::geography)
        FROM places a, places b WHERE a.id = :k AND b.id = :d
    """), {"k": keep_id, "d": drop_id})).scalar()
    dup = (await session.execute(text("""
        SELECT count(*) FROM reviews a JOIN reviews b ON a.text_hash = b.text_hash
        WHERE a.place_id = :d AND b.place_id = :k
    """), {"k": keep_id, "d": drop_id})).scalar()
    p("")
    p(f"  สองแถวห่างกัน {float(dist or 0):.0f} เมตร")
    p(f"  รีวิวของแถวที่จะลบ {drop.sc} อัน · ซ้ำกับแถวที่เก็บไว้ {dup} อัน "
      f"→ ย้ายได้จริง {drop.sc - dup} อัน")
    p(f"  snapshot ที่จะย้าย {drop.snap} แถว (ไม่ปล่อยให้ CASCADE ลบ)")
    p(f"  candidates ที่จะชี้ใหม่ {drop.cand} แถว")

    move_api = {f: getattr(drop, {"google_place_id": "gp", "google_types": "gt",
                                  "formatted_address": "addr",
                                  "google_rating": "gr",
                                  "google_reviews_total": "g",
                                  "api_fetched_at": "af"}[f])
                for f in API_FIELDS}
    will_move = [f for f in API_FIELDS
                 if move_api[f] is not None and getattr(
                     keep, {"google_place_id": "gp", "google_types": "gt",
                            "formatted_address": "addr", "google_rating": "gr",
                            "google_reviews_total": "g",
                            "api_fetched_at": "af"}[f]) is None]
    p(f"  ฟิลด์ API ที่จะย้ายให้แถวที่เก็บไว้: {will_move or '(ไม่มี — มีอยู่แล้ว)'}")

    # ── ตัวนับของแถวที่เก็บไว้อาจต้องรีเซ็ต ──
    #
    # ⚠️ ปัญหาที่เจอจริง (แพตามสั่งนั่งชิว 2026-10-02)
    #   แถวที่เก็บไว้มี deep_scanned_at ตั้งแล้วและ deep_attempts = 6
    #   แต่พอรับ google_reviews_total = 544 มาจากแถวที่ลบ กลายเป็นเก็บได้ 1%
    #   ตัวนับทั้งสองทำให้มันหายจากทุกคิว deep:
    #     deep_scanned_at ตั้งแล้ว -> ตัดออกจาก capped/zero/shallow/all
    #     deep_attempts >= เพดาน  -> ตัดออกจาก gap (ไปอยู่กลุ่มยอมแพ้)
    #   ช่องว่าง 539 รีวิวจะถูกฝังเงียบโดยไม่มีอะไรรายงาน
    #
    #   ตัวนับพวกนั้นสะสมตอนที่ระบบยังไม่รู้เพดานจริงของร้าน จึงไม่สะท้อน
    #   ความเป็นจริงหลังรวมแถว — รีเซ็ตให้ได้โอกาสใหม่เต็มจำนวน
    new_sc = keep.sc + (drop.sc - dup)
    new_g = keep.g if keep.g is not None else drop.g
    new_ceil = min(new_g, SERVE_CEILING_DEEP) if new_g else 0
    need_reset = bool(new_ceil) and new_sc < DEEP_MIN_RATIO * new_ceil
    if need_reset:
        p("")
        p(f"  ⚠️ หลังรวมจะเก็บได้ {new_sc}/{new_ceil} = "
          f"{new_sc / new_ceil * 100:.0f}% (ต่ำกว่าเกณฑ์ "
          f"{DEEP_MIN_RATIO * 100:.0f}%)")
        p(f"     จะรีเซ็ตตัวนับของแถวที่เก็บไว้ให้กลับเข้าคิวได้:")
        p(f"       deep_scanned_at       {'ตั้งแล้ว' if keep else '-'} -> NULL")
        p(f"       deep_attempts         -> 0")
        p(f"       refresh_shortfalls    -> 0")
        p(f"       consecutive_no_change -> 0")
        p(f"       scraped_at            -> NULL (กลับหัวคิว refresh)")

    if not apply:
        p("")
        p("  ยังไม่ได้แก้อะไร — เติม --apply เพื่อทำจริง")
        p("=" * 78)
        return

    # 1. ย้ายรีวิว
    await session.execute(text("""
        INSERT INTO reviews (place_id, rating, text, text_clean, text_hash,
                             review_date, review_date_approx, scraped_at)
        SELECT :k, rating, text, text_clean, text_hash,
               review_date, review_date_approx, scraped_at
        FROM reviews WHERE place_id = :d
        ON CONFLICT (place_id, text_hash) DO NOTHING
    """), {"k": keep_id, "d": drop_id})
    # 2. ย้าย snapshot
    await session.execute(text("""
        UPDATE snapshot_places SET place_id = :k WHERE place_id = :d
    """), {"k": keep_id, "d": drop_id})
    # 3. ย้าย candidates
    await session.execute(text("""
        UPDATE place_candidates SET matched_place_id = :k WHERE matched_place_id = :d
    """), {"k": keep_id, "d": drop_id})
    # 4. ลบรีวิวต้นทางแล้วตรวจว่าว่างจริงก่อนลบแถว
    await session.execute(text("DELETE FROM reviews WHERE place_id = :d"),
                          {"d": drop_id})
    left = (await session.execute(text(
        "SELECT count(*) FROM reviews WHERE place_id = :d"), {"d": drop_id})).scalar()
    if left:
        await session.rollback()
        p(f"  🛑 หยุด — แถวที่จะลบยังมีรีวิว {left} อัน ไม่ลบและยกเลิกทั้งหมด")
        return
    # 5. DELETE แถว
    await session.execute(text("DELETE FROM places WHERE id = :d"), {"d": drop_id})
    # 6. ตั้งฟิลด์ API หลัง DELETE (uq_places_google_place_id เป็น UNIQUE)
    if will_move:
        sets = ", ".join(f"{f} = COALESCE({f}, :{f})" for f in API_FIELDS)
        await session.execute(
            text(f"UPDATE places SET {sets} WHERE id = :k"),
            {**move_api, "k": keep_id})
    # 7. รีเซ็ตตัวนับถ้ายังเก็บได้ต่ำกว่าเกณฑ์ (ดูเหตุผลด้านบน)
    if need_reset:
        await session.execute(text("""
            UPDATE places SET
                deep_scanned_at = NULL,
                deep_attempts = 0,
                refresh_shortfalls = 0,
                consecutive_no_change = 0,
                scraped_at = NULL
            WHERE id = :k
        """), {"k": keep_id})
    await session.commit()

    after = await row(session, keep_id)
    p("")
    p(f"  ✅ รวมแล้ว")
    show(after, "ผลลัพธ์ ")
    p("=" * 78)


# ─────────────────────────────────────────────────────────────────────
async def do_move_api(session, src_id: int, dst_id: int, apply: bool) -> None:
    src, dst = await row(session, src_id), await row(session, dst_id)
    p("=" * 78)
    p(f"  {'ทำจริง' if apply else 'DRY-RUN'} — ย้ายข้อมูล Places API ไปแถวเจ้าของจริง")
    p("=" * 78)
    if not src or not dst:
        p("  ไม่พบแถว")
        return
    show(src, "ย้ายจาก")
    show(dst, "ไปที่  ")
    p("")
    p(f"  ฟิลด์ที่ย้าย: {', '.join(API_FIELDS)} + location")
    p(f"  แถวต้นทางจะถูกล้างให้ว่าง และตั้ง scraped_at = NULL "
      f"เพื่อให้ scrape ใหม่ด้วยการค้นชื่อ (จะได้พิกัดของตัวเอง)")
    p(f"  ⚠️ ไม่แตะรีวิวทั้งสองแถว ({src.sc} และ {dst.sc} อัน)")

    if not apply:
        p("")
        p("  ยังไม่ได้แก้อะไร — เติม --apply เพื่อทำจริง")
        p("=" * 78)
        return

    # ล้างต้นทางก่อน แล้วจึงตั้งปลายทาง (uq_places_google_place_id เป็น UNIQUE)
    await session.execute(text("""
        UPDATE places SET
            google_place_id = NULL, google_types = NULL,
            formatted_address = NULL, google_rating = NULL,
            google_reviews_total = NULL, api_fetched_at = NULL,
            scraped_at = NULL, refresh_shortfalls = 0,
            consecutive_no_change = 0
        WHERE id = :s
    """), {"s": src_id})
    await session.execute(text("""
        UPDATE places SET
            google_place_id = :gp, google_types = :gt,
            formatted_address = :addr, google_rating = :gr,
            google_reviews_total = :g, api_fetched_at = :af,
            location = ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)
        WHERE id = :d
    """), {"gp": src.gp, "gt": src.gt, "addr": src.addr, "gr": src.gr,
           "g": src.g, "af": src.af, "lat": src.lat, "lng": src.lng,
           "d": dst_id})
    await session.commit()

    p("")
    p("  ✅ ย้ายแล้ว")
    show(await row(session, src_id), "ต้นทาง ")
    show(await row(session, dst_id), "ปลายทาง")
    p("")
    p("  ⚠️ แถวปลายทางต้องคำนวณ zone/distance ใหม่:")
    p("     uv run python scripts/verify_coords.py --use-api --apply")
    p("=" * 78)


# ─────────────────────────────────────────────────────────────────────
async def do_delete(session, pid: int, apply: bool, force: bool) -> None:
    r = await row(session, pid)
    p("=" * 78)
    p(f"  {'ทำจริง' if apply else 'DRY-RUN'} — ลบแถวร้าน")
    p("=" * 78)
    if not r:
        p(f"  ไม่พบแถว id={pid}")
        return
    show(r, "จะลบ   ")
    p("")
    p(f"  ผลข้างเคียง (ON DELETE CASCADE):")
    p(f"    reviews ที่จะหาย        {r.sc} อัน")
    p(f"    snapshot_places ที่จะหาย {r.snap} แถว")
    p(f"    place_candidates         {r.cand} แถว -> matched_place_id เป็น NULL")
    if r.cand:
        p(f"    ⚠️ candidates ชี้อยู่ {r.cand} แถว — promote รอบหน้าอาจใส่กลับมา")
        p(f"       ควรตั้ง decision = 'reject' ใน place_candidates ด้วย")

    if r.sc and not force:
        p("")
        p(f"  🛑 ไม่ลบ — แถวนี้มีรีวิว {r.sc} อัน")
        p(f"     ถ้ายืนยันว่าต้องการลบจริง เติม --force")
        p("=" * 78)
        return

    if not apply:
        p("")
        p("  ยังไม่ได้แก้อะไร — เติม --apply เพื่อทำจริง")
        p("=" * 78)
        return

    if r.cand:
        await session.execute(text("""
            UPDATE place_candidates
               SET matched_place_id = NULL, decision = 'reject'
             WHERE matched_place_id = :i
        """), {"i": pid})
    await session.execute(text("DELETE FROM places WHERE id = :i"), {"i": pid})
    await session.commit()

    tot = (await session.execute(text("SELECT count(*) FROM places"))).scalar()
    rev = (await session.execute(text("SELECT count(*) FROM reviews"))).scalar()
    p("")
    p(f"  ✅ ลบแล้ว · ร้านเหลือ {tot} · รีวิว {rev:,}")
    p("=" * 78)


async def run(args) -> int:
    async with AsyncSessionLocal() as s:
        if args.merge:
            await do_merge(s, args.merge[0], args.merge[1], args.apply)
        elif args.move_api:
            await do_move_api(s, args.move_api[0], args.move_api[1], args.apply)
        elif args.delete:
            await do_delete(s, args.delete, args.apply, args.force)
        else:
            p("ต้องระบุโหมด: --merge / --move-api / --delete (ดู --help)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="ซ่อมความเชื่อมโยงของแถวร้าน ทีละรายการที่ระบุด้วย id")
    ap.add_argument("--merge", type=int, nargs=2, metavar=("KEEP", "DROP"),
                    help="รวมสองแถวที่เป็นร้านเดียวกัน (ย้ายรีวิว/snapshot/candidates)")
    ap.add_argument("--move-api", type=int, nargs=2, metavar=("FROM", "TO"),
                    help="ย้ายข้อมูล Places API + พิกัด ไปแถวที่เป็นเจ้าของจริง")
    ap.add_argument("--delete", type=int, metavar="ID",
                    help="ลบแถวร้าน (ต้องมี 0 รีวิว ถ้าไม่ใช่ต้องใส่ --force)")
    ap.add_argument("--apply", action="store_true",
                    help="ทำจริง (ไม่ใส่ = DRY-RUN ดูเฉย ๆ)")
    ap.add_argument("--force", action="store_true",
                    help="ยอมลบแถวที่ยังมีรีวิว (ใช้กับ --delete)")
    sys.exit(asyncio.run(run(ap.parse_args())))
