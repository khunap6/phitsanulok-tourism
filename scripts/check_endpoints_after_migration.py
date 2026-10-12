"""check_endpoints_after_migration.py — ตรวจทุก endpoint หลังย้ายมาป้ายชุด v2

⚠️ ตรวจอะไร
  1. ทุก endpoint ตอบ 200 ไม่ 500 (pydantic ไม่ตกเพราะ None โผล่ในฟิลด์บังคับ)
  2. ชื่อหมวดที่คืนมาเป็นชื่อชุด v2 จริง ไม่ใช่ชื่อ v1 ที่หลงเหลือ
  3. ตัวเลขสอดคล้องกันข้าม endpoint ที่ควรใช้ฐานเดียวกัน (กฎ 1)
  4. ตัวกรองหมวดรับได้ทั้งชื่อ v2 ชื่อเดิม v1 และเลข id แล้วได้ผลเท่ากัน
  5. ชื่อหมวดที่ไม่มีจริงต้องคืนผลว่าง ไม่ใช่คืนทุกหมวด

⚠️ ใช้ httpx.AsyncClient + ASGITransport ใน asyncio.run() เดียว
  ไม่ใช้ TestClient เพราะ TestClient สร้าง event loop ของตัวเอง
  แล้วชนกับ async engine ของ SQLAlchemy (เคยทำให้ล่มทั้งชุดทดสอบ)

⚠️ สคริปต์นี้อ่านอย่างเดียว ไม่เขียนฐานข้อมูล

รัน:
  uv run python scripts/check_endpoints_after_migration.py
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from api.filters import CATEGORY_V2_NAME, NON_PROBLEM_NAMES_ALL  # noqa: E402
from api.main import app  # noqa: E402

V2_NAMES = set(CATEGORY_V2_NAME.values())
# ชื่อ v1 ที่ต้อง "ไม่โผล่" อีกแล้วในผลลัพธ์ (ยกเว้นฟิลด์ที่ลงท้าย _legacy)
V1_ONLY = {"บรรยากาศและการตกแต่งร้าน", "การเดินทางและที่จอดรถ",
           "ข้อมูลและป้ายบอกทาง", "สิ่งอำนวยความสะดวก", "ความปลอดภัย",
           "ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)", "อื่นๆ", "ไม่มี"}

ok = 0
fail: list[str] = []
warn: list[str] = []


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def check(name: str, cond: bool, detail: str = "") -> None:
    global ok
    if cond:
        ok += 1
        p(f"  ผ่าน  {name}")
    else:
        fail.append(f"{name} — {detail}")
        p(f"  ตก    {name}  {detail}")


def collect_cat_names(obj, out: set, path: str = "") -> None:
    """เดินทั้ง response หาค่าที่อยู่ในคีย์ชื่อหมวด ข้ามฟิลด์ *_legacy"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.endswith("_legacy"):
                continue
            if k in ("category", "top_category") and isinstance(v, str):
                out.add(v)
            elif k in ("pain_point_category",) and isinstance(v, str):
                out.add(v)
            elif k in ("categories", "pain_point_categories") and isinstance(v, list):
                out.update(x for x in v if isinstance(x, str))
            elif k == "pain_point_totals" and isinstance(v, dict):
                out.update(v.keys())
            else:
                collect_cat_names(v, out, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            collect_cat_names(v, out, f"{path}[{i}]")


async def main() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://test/api", timeout=120.0) as c:
        all_names: set[str] = set()

        p("=" * 72)
        p("1. ทุก endpoint ต้องตอบ 200")
        p("=" * 72)
        endpoints = [
            "/insights/zones",
            "/insights/zones?status=operational",
            "/insights/zones/city_center/pain-points",
            "/insights/zones/city_center/pain-points?view_mode=praise",
            "/insights/zones/city_center/pain-points?view_mode=all",
            "/insights/zones/city_center/breakdown",
            "/insights/category-places",
            "/insights/category-places?view_mode=praise",
            "/insights/summary",
            "/insights/summary?view_mode=praise",
            "/insights/summary?status=operational",
            "/insights/top-places",
            "/insights/top-places?sort=rate",
            "/insights/positive-highlights",
            "/insights/categories",
            "/insights/categories?status=operational",
            "/insights/trending",
            "/insights/alerts",
            "/insights/heatmap",
            "/insights/snapshots",
            "/aspects/summary",
            "/aspects/overview",
            "/aspects/categories",
            "/reviews?page_size=5",
            "/reviews?page_size=5&view_mode=complaints",
            "/map/geojson",
        ]
        bodies: dict[str, object] = {}
        for url in endpoints:
            try:
                r = await c.get(url.lstrip("/"))
            except Exception as e:  # noqa: BLE001
                check(url, False, f"ยิงไม่ได้: {type(e).__name__}: {e}")
                continue
            body_preview = ""
            if r.status_code != 200:
                body_preview = r.text[:300].replace("\n", " ")
            check(url, r.status_code == 200, f"HTTP {r.status_code} {body_preview}")
            if r.status_code == 200:
                try:
                    bodies[url] = r.json()
                    collect_cat_names(bodies[url], all_names)
                except ValueError:
                    pass

        p("")
        p("=" * 72)
        p("2. ชื่อหมวดที่คืนมาต้องเป็นชุด v2 ไม่มีชื่อ v1 หลงเหลือ")
        p("=" * 72)
        leaked = sorted(all_names & V1_ONLY)
        unknown = sorted(n for n in all_names
                         if n not in V2_NAMES and n not in NON_PROBLEM_NAMES_ALL)
        p(f"  ชื่อหมวดที่พบในผลลัพธ์ {len(all_names)} ชื่อ")
        for n in sorted(all_names):
            mark = "v2" if n in V2_NAMES else ("v1!" if n in V1_ONLY else "??")
            p(f"    [{mark}] {n}")
        check("ไม่มีชื่อหมวด v1 หลงเหลือ", not leaked, f"พบ {leaked}")
        check("ไม่มีชื่อหมวดที่ไม่รู้จัก", not unknown, f"พบ {unknown}")

        p("")
        p("=" * 72)
        p("3. ตัวเลขสอดคล้องกันข้าม endpoint (กฎ 1)")
        p("=" * 72)
        # /insights/categories?status=operational ต้องมีผลรวมเท่ากับ
        # /insights/summary?status=operational total_with_text ลบรีวิวที่ไม่มีหมวด
        s = bodies.get("/insights/summary?status=operational")
        cats = bodies.get("/insights/categories?status=operational")
        if isinstance(s, dict) and isinstance(cats, list):
            cat_sum = sum(x["count"] for x in cats)
            twt = s["total_with_text"]
            check("ผลรวมรายหมวด <= total_with_text",
                  cat_sum <= twt,
                  f"รายหมวดรวม {cat_sum:,} > total_with_text {twt:,} "
                  "— หน่วยนับต้องเป็นรีวิว ไม่ใช่การกล่าวถึง")
            p(f"        รายหมวดรวม {cat_sum:,} / total_with_text {twt:,} "
              f"({cat_sum / twt * 100:.1f}%)")

        # /aspects/summary ต้องมีผลรวมเกินจำนวนรีวิว (หน่วยการกล่าวถึง)
        a = bodies.get("/aspects/summary")
        if isinstance(a, dict) and a.get("items"):
            m_sum = sum(x["n_reviews"] for x in a["items"])
            tot = a["total_reviews"]
            check("ชั้น aspect ผลรวมเกินจำนวนรีวิว (ถูกต้องตามหน่วยนับ)",
                  m_sum > tot, f"รวม {m_sum:,} ไม่เกิน {tot:,}")
            p(f"        การกล่าวถึงรวม {m_sum:,} / รีวิว {tot:,} "
              f"= {m_sum / tot:.2f} หมวด/รีวิว")
            prim = sum(x["n_primary"] for x in a["items"])
            check("ชั้น aspect หน่วยหมวดหลักรวมเท่าจำนวนรีวิว",
                  prim == a["total_primary"],
                  f"รวมหมวดหลัก {prim:,} != total_primary {a['total_primary']:,}")

        # sev_total ต้องมาด้วยและ high+medium+low ต้องเท่ากับมันเป๊ะ
        cp = bodies.get("/insights/category-places")
        if isinstance(cp, list) and cp:
            bad = [r for r in cp
                   if "sev_total" not in r
                   or r["high"] + r["medium"] + r["low"] != r["sev_total"]]
            check("category-places: high+medium+low = sev_total",
                  not bad, f"ไม่ตรง {len(bad)} แถว (ตัวอย่าง {bad[:1]})")
            bad2 = [r for r in cp if r["neg"] + r["pos"] + r["neu"] != r["total"]]
            check("category-places: neg+pos+neu = total",
                  not bad2, f"ไม่ตรง {len(bad2)} แถว (ตัวอย่าง {bad2[:1]})")

        p("")
        p("=" * 72)
        p("4. ตัวกรองหมวดรับได้ทั้งชื่อ v2 ชื่อเดิม v1 และเลข id")
        p("=" * 72)
        # หมวด 3 = บรรยากาศ · ชื่อเดิม v1 = บรรยากาศและการตกแต่งร้าน
        trio = {
            "ชื่อ v2": "บรรยากาศ ทัศนียภาพ และการตกแต่ง",
            "ชื่อเดิม v1": "บรรยากาศและการตกแต่งร้าน",
            "เลข id": "3",
        }
        counts = {}
        for label, val in trio.items():
            r = await c.get("insights/category-places",
                            params={"category": val, "view_mode": "all"})
            if r.status_code != 200:
                check(f"category={label}", False, f"HTTP {r.status_code}")
                continue
            counts[label] = sum(x["total"] for x in r.json())
        if len(counts) == 3:
            vals = set(counts.values())
            check("สามวิธีอ้างหมวดเดียวกันได้ผลเท่ากัน",
                  len(vals) == 1, f"ได้ {counts}")
            p(f"        {counts}")

        p("")
        p("=" * 72)
        p("5. ชื่อหมวดที่ไม่มีจริงต้องคืนผลว่าง ไม่ใช่คืนทุกหมวด")
        p("=" * 72)
        r = await c.get("insights/category-places",
                        params={"category": "หมวดที่ไม่มีอยู่จริงเลย", "view_mode": "all"})
        check("category ที่ไม่รู้จัก -> ลิสต์ว่าง",
              r.status_code == 200 and r.json() == [],
              f"HTTP {r.status_code} ได้ {len(r.json()) if r.status_code == 200 else '?'} แถว")
        r = await c.get("reviews", params={"category": "หมวดที่ไม่มีอยู่จริงเลย",
                                            "page_size": 5})
        if r.status_code == 200:
            check("/reviews category ที่ไม่รู้จัก -> total 0",
                  r.json()["total"] == 0, f"total = {r.json()['total']}")

        p("")
        p("=" * 72)
        p("6. ฟิลด์ชั้นเดิมยังอยู่ ไม่ได้ลบทิ้ง (กฎ 3)")
        p("=" * 72)
        rv = bodies.get("/reviews?page_size=5")
        if isinstance(rv, dict) and rv.get("items"):
            it = rv["items"][0]
            for fld in ("sentiment", "pain_point_category", "severity"):
                check(f"/reviews มีฟิลด์ {fld}", fld in it, f"คีย์ที่มี {list(it)}")

    p("")
    p("=" * 72)
    p(f"สรุป: ผ่าน {ok} · ตก {len(fail)} · เตือน {len(warn)}")
    p("=" * 72)
    for x in fail:
        p(f"  ตก: {x}")
    for x in warn:
        p(f"  เตือน: {x}")
    if fail:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
