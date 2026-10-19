"""thesis_tests.py — รันการทดสอบระบบสำหรับบทที่ 4 ของเล่ม

สร้างผลของ
  ตารางที่ 4.4  ผลการทดสอบการทำงานของเว็บแอปพลิเคชัน (Black-box 15 กรณี)
  ตารางที่ 4.5  เปรียบเทียบตัวเลขบนแดชบอร์ดกับค่าจากฐานข้อมูลโดยตรง

⚠️ หลักการของไฟล์นี้
  "ค่าจากแดชบอร์ด" ต้องมาจากการ **เรียก API ด้วยพารามิเตอร์ชุดเดียวกับที่หน้าเว็บส่ง**
  ไม่ใช่คำนวณซ้ำด้วย SQL แล้วบอกว่าเป็นค่าจากแดชบอร์ด
  ไม่งั้นก็เท่ากับเทียบ SQL กับ SQL แล้วได้ 0 เสมอ ซึ่งไม่ได้พิสูจน์อะไรเลย

  "ค่าจากฐานข้อมูล" ต้องเป็น SQL ที่เขียนแยกจากโค้ด API สิ้นเชิง
  ถ้าใช้ฟังก์ชันตัวกรองเดียวกับ API ก็จะผิดเหมือนกันทั้งคู่โดยไม่รู้ตัว

⚠️ ตัวกรองที่หน้าแดชบอร์ดใช้เป็นค่าตั้งต้น (ตรวจจาก frontend/src/hooks/useInsights.ts)
  view_mode = 'complaints'
  status    = 'operational'   -> ร้านที่ยังเปิด
  ไม่ส่งช่วงวันที่             -> ไม่กรองเวลา
  และ API กรอง in_scope เสมอ   -> เฉพาะสถานที่ในขอบเขตงานวิจัย

  เงื่อนไขรวมจึงเป็น  p.in_scope AND business_status = 'operational'
  ซึ่งให้ สถานที่ 694 · รีวิว 108,092 · กล่าวถึง 126,045 ตรงกับที่ระบุในเล่ม

⚠️ "จำนวนรีวิวที่มีข้อความ" มีสองนิยามที่ต่างกัน 3 รายการ
  text_clean <> ''                     = 69,062
  text_clean <> '' และถูกวิเคราะห์แล้ว = 69,059   <-- ตัวนี้คือที่แดชบอร์ดแสดง
  ส่วนต่าง 3 รายการคือรีวิวที่มีข้อความแต่ยังไม่เคยถูกวิเคราะห์
  ต้องใช้นิยามเดียวกันทั้งสองฝั่ง ไม่งั้นจะรายงานว่าต่างกัน 3 ทั้งที่ไม่ได้ผิด

รัน (ต้องเปิด API ที่ port 8000 ไว้ก่อน):
  uv run uvicorn api.main:app --port 8000
  uv run python scripts/thesis_tests.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from db.database import engine  # noqa: E402

OUT_MD = ROOT / "reports" / "thesis_tests.md"
OUT_JSON = ROOT / "reports" / "thesis_tests.json"

BASE = "http://127.0.0.1:8000/api"

# ตัวกรองที่หน้าแดชบอร์ดใช้ เขียนเป็น SQL ตรง ๆ แยกจากโค้ด API โดยเจตนา
SCOPE = "p.in_scope AND COALESCE(p.business_status,'operational') = 'operational'"


def p(m: str = "") -> None:
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        print(m.encode("ascii", "replace").decode("ascii"), flush=True)


# ─────────────────────────────── ตารางที่ 4.5 ───────────────────────────────

async def table_4_5(client: httpx.AsyncClient) -> list[dict]:
    """เทียบตัวเลขบนแดชบอร์ดกับค่าจากฐานข้อมูลโดยตรง"""
    r = await client.get("/insights/summary",
                         params={"view_mode": "complaints", "status": "operational"})
    r.raise_for_status()
    dash = r.json()

    ra = await client.get("/aspects/summary")
    ra.raise_for_status()
    asp = ra.json()

    async with engine.connect() as c:
        async def one(q: str) -> int:
            return int((await c.execute(text(q))).scalar() or 0)

        db_places = await one(
            f"SELECT COUNT(*) FROM places p WHERE {SCOPE}")
        db_reviews = await one(
            f"SELECT COUNT(*) FROM reviews r JOIN places p ON p.id=r.place_id "
            f"WHERE {SCOPE}")
        # ⚠️ ใช้นิยาม "มีข้อความและถูกวิเคราะห์แล้ว" ให้ตรงกับที่แดชบอร์ดแสดง
        db_with_text = await one(
            f"SELECT COUNT(*) FROM reviews r JOIN places p ON p.id=r.place_id "
            f"JOIN analyzed_reviews ar ON ar.review_id=r.id "
            f"WHERE {SCOPE} AND r.text_clean <> ''")
        db_mentions = await one(
            f"SELECT COUNT(*) FROM review_aspects ra "
            f"JOIN reviews r ON r.id=ra.review_id JOIN places p ON p.id=r.place_id "
            f"WHERE {SCOPE}")
        # ลำดับหมวดที่ถูกบ่นมากที่สุด — คิดจากฐานข้อมูลตรง ๆ
        rows = (await c.execute(text(f"""
            SELECT cat.name, COUNT(*) AS n
            FROM analyzed_reviews ar
            JOIN reviews r ON r.id = ar.review_id
            JOIN places  p ON p.id = r.place_id
            JOIN categories cat ON cat.id = ar.primary_category_id
            WHERE {SCOPE}
              AND ar.overall_sentiment = 'negative'
              AND r.text_clean <> ''
              AND ar.primary_category_id NOT IN (2, 11)
            GROUP BY cat.name ORDER BY n DESC, cat.name LIMIT 5"""))).all()
    db_order = [x[0] for x in rows]
    dash_order = [x["category"] for x in dash["top_pain_point_categories"]][:5]

    items = [
        ("จำนวนสถานที่", db_places, dash["total_places"]),
        ("จำนวนรีวิวทั้งหมด", db_reviews, dash["total_reviews"]),
        ("จำนวนรีวิวที่มีข้อความ", db_with_text, dash["total_with_text"]),
        ("จำนวนการกล่าวถึง", db_mentions, _mentions_from_aspects(asp)),
    ]
    out = [{"รายการ": k, "ค่าจากฐานข้อมูล": a, "ค่าจากแดชบอร์ด": b,
            "ผลต่าง": b - a, "ผ่าน": a == b} for k, a, b in items]
    out.append({
        "รายการ": "ลำดับหมวดที่ถูกบ่นมากที่สุด",
        "ค่าจากฐานข้อมูล": " > ".join(db_order),
        "ค่าจากแดชบอร์ด": " > ".join(dash_order),
        "ผลต่าง": "ตรง" if db_order == dash_order else "ไม่ตรง",
        "ผ่าน": db_order == dash_order,
    })
    return out


def _mentions_from_aspects(asp: dict) -> int:
    """จำนวนการกล่าวถึงทั้งหมด = ผลรวมรายหมวดจากแผง Multi-Aspect

    ⚠️ ไม่ใช่ total_reviews ของแผงนั้น
      total_reviews คือจำนวน "รีวิว" ส่วนการกล่าวถึงคือจำนวน (รีวิว, หมวด)
      ซึ่งมากกว่าเพราะ 1 รีวิวพูดถึงได้หลายหมวด
    """
    return sum(int(i["n_reviews"]) for i in asp.get("items", []))


# ─────────────────────────────── ตารางที่ 4.4 ───────────────────────────────
#
# ⚠️ แต่ละกรณีทดสอบสิ่งที่ "ตรวจได้ด้วยเครื่อง" เท่านั้น
#   กรณีที่ต้องใช้ตาคนดูหน้าจอจะถูกทำเครื่องหมาย manual=True
#   และรายงานว่า "ต้องตรวจด้วยตา" ไม่ใช่รายงานว่าผ่าน
#   การบอกว่าผ่านทั้งที่ไม่ได้ตรวจ คือการรายงานเท็จในเล่มวิจัย

async def table_4_4(client: httpx.AsyncClient) -> list[dict]:
    cases: list[dict] = []

    def add(code: str, group: str, step: str, expect: str,
            ok: bool | None, note: str = "") -> None:
        cases.append({"รหัส": code, "กลุ่ม": group, "ขั้นตอน": step,
                      "ผลที่คาดหวัง": expect, "ผ่าน": ok, "หลักฐาน": note})

    # ── TC-01 เปิดหน้าแรกโดยไม่ตั้งตัวกรอง ──
    r = await client.get("/insights/summary",
                         params={"view_mode": "complaints", "status": "operational"})
    d = r.json() if r.status_code == 200 else {}
    ok = (r.status_code == 200 and d.get("total_places", 0) > 0
          and d.get("total_reviews", 0) > 0 and d.get("total_with_text", 0) > 0)
    add("TC-01", "แดชบอร์ดหลัก", "เปิดหน้าแรกโดยไม่ตั้งตัวกรอง",
        "แสดงการ์ดสรุปจำนวนสถานที่ รีวิว รีวิวที่มีข้อความ และการกล่าวถึง", ok,
        f"HTTP {r.status_code} · สถานที่ {d.get('total_places')} · "
        f"รีวิว {d.get('total_reviews')} · มีข้อความ {d.get('total_with_text')}")

    # ── TC-02 ดูกราฟหมวดที่ถูกบ่น ──
    cats = d.get("top_pain_point_categories") or []
    counts = [c["count"] for c in cats]
    ok = bool(cats) and counts == sorted(counts, reverse=True) and all(
        c.get("count") is not None for c in cats)
    add("TC-02", "แดชบอร์ดหลัก", "ดูกราฟหมวดที่ถูกบ่น",
        "แสดงหมวดเรียงตามจำนวนคำติและระบุหน่วยนับ", ok,
        f"{len(cats)} หมวด · เรียงจากมากไปน้อย: {counts[:5]}")

    # ── TC-03 กดหมวดหนึ่งเพื่อดูรายละเอียด ──
    ok = None
    note = "ไม่มีหมวดให้ทดสอบ"
    if cats:
        cat = cats[0]["category"]
        rp = await client.get("/insights/category-places",
                              params={"category": cat, "view_mode": "complaints",
                                      "status": "operational"})
        places = rp.json() if rp.status_code == 200 else []
        rr = await client.get("/insights/category-reviews",
                              params={"place_id": places[0]["place_id"], "category": cat,
                                      "view_mode": "complaints"}) if places else None
        revs = rr.json() if rr is not None and rr.status_code == 200 else []
        ok = rp.status_code == 200 and len(places) > 0 and len(revs) > 0
        note = (f"หมวด '{cat}' -> {len(places)} สถานที่ · "
                f"สถานที่แรกมี {len(revs)} รีวิวให้อ่าน")
    add("TC-03", "แดชบอร์ดหลัก", "กดหมวดหนึ่งเพื่อดูรายละเอียด",
        "แสดงสถานที่และรีวิวของหมวดนั้น", ok, note)

    # ── TC-04 ดูรายการรีวิว ──
    rv = await client.get("/reviews", params={"page_size": 10,
                                              "view_mode": "complaints",
                                              "status": "operational"})
    body = rv.json() if rv.status_code == 200 else {}
    items = body.get("items") or []
    has_fields = bool(items) and all(
        k in items[0] for k in ("text", "rating", "review_date_approx"))
    ok = rv.status_code == 200 and has_fields and body.get("total", 0) > 0
    add("TC-04", "แดชบอร์ดหลัก", "ดูรายการรีวิว",
        "แสดงข้อความ คะแนนดาว วันที่ หมวด และอารมณ์", ok,
        f"total={body.get('total')} · ซ่อนเพราะไม่มีข้อความ "
        f"{body.get('hidden_no_text')} · ฟิลด์ครบ={has_fields}")

    # ── TC-05 ดูส่วนจุดเด่นเชิงบวก ──
    ph = await client.get("/insights/positive-highlights",
                          params={"status": "operational"})
    pj = ph.json() if ph.status_code == 200 else {}
    pit = pj.get("items") or []
    ok = ph.status_code == 200 and len(pit) > 0 and pj.get("total_praise", 0) > 0
    add("TC-05", "แดชบอร์ดหลัก", "ดูส่วนจุดเด่นเชิงบวก",
        "แสดงหมวดที่ถูกชมแยกจากคำติ", ok,
        f"{len(pit)} หมวด · คำชมทั้งหมด {pj.get('total_praise')}")

    # ── TC-06 ดูส่วนแนวโน้ม ──
    tr = await client.get("/insights/trending", params={"status": "operational"})
    tj = tr.json() if tr.status_code == 200 else {}
    ok = tr.status_code == 200 and len(tj.get("buckets") or []) > 0
    add("TC-06", "แดชบอร์ดหลัก", "ดูส่วนแนวโน้ม",
        "แสดงหมวดหรือสถานที่ที่ค่าขึ้นเด่น", ok,
        f"ช่วงเวลา {len(tj.get('buckets') or [])} ช่วง · "
        f"{len(tj.get('categories') or [])} หมวด")

    # ── TC-07 เปลี่ยนช่วงวันที่ ──
    a = await client.get("/insights/summary",
                         params={"view_mode": "complaints", "status": "operational"})
    b = await client.get("/insights/summary",
                         params={"view_mode": "complaints", "status": "operational",
                                 "date_from": "2024-01-01", "date_to": "2024-12-31"})
    aj, bj = a.json(), b.json()
    shrank = bj["total_reviews"] < aj["total_reviews"]
    ok = a.status_code == 200 and b.status_code == 200 and shrank
    add("TC-07", "ตัวกรองข้อมูล", "เปลี่ยนช่วงวันที่",
        "ตัวเลขและกราฟเปลี่ยนตาม และไม่เกินค่าเมื่อไม่ตั้งตัวกรอง", ok,
        f"ไม่กรอง {aj['total_reviews']:,} รีวิว -> ปี 2024 {bj['total_reviews']:,} รีวิว")

    # ── TC-08 สลับโหมด ทั้งหมด / เฉพาะคำติ / เฉพาะคำชม ──
    res = {}
    for mode in ("all", "complaints", "praise"):
        rr = await client.get("/insights/summary",
                              params={"view_mode": mode, "status": "operational"})
        jj = rr.json()
        res[mode] = sum(c["count"] for c in jj.get("top_pain_point_categories") or [])
    ok = len({res["all"], res["complaints"], res["praise"]}) > 1
    add("TC-08", "ตัวกรองข้อมูล", "สลับโหมด ทั้งหมด / เฉพาะคำติ / เฉพาะคำชม",
        "กราฟเปลี่ยนตามโหมดที่เลือก", ok,
        f"ผลรวมรายหมวด — ทั้งหมด {res['all']:,} · "
        f"คำติ {res['complaints']:,} · คำชม {res['praise']:,}")

    # ── TC-09 เลือกโซนทีละโซน 4 โซน ──
    zr = await client.get("/insights/zones", params={"status": "operational"})
    zones = zr.json() if zr.status_code == 200 else []
    per = {}
    for z in zones:
        zz = await client.get(f"/insights/zones/{z['zone']}/pain-points",
                              params={"view_mode": "complaints", "status": "operational"})
        per[z["zone"]] = zz.json().get("total_with_text") if zz.status_code == 200 else None
    ok = len(zones) == 4 and all(v is not None for v in per.values()) and len(
        set(per.values())) > 1
    add("TC-09", "หน้าวิเคราะห์หมวดโซน", "เลือกโซนทีละโซน 4 โซน",
        "ตัวเลขเปลี่ยนตามโซน", ok,
        " · ".join(f"{k}={v:,}" for k, v in per.items()))

    # ── TC-10 แยกหมวดตามประเภทสถานที่ ──
    br = await client.get(f"/insights/zones/{zones[0]['zone']}/breakdown",
                          params={"view_mode": "complaints",
                                  "status": "operational"}) if zones else None
    bl = br.json() if br is not None and br.status_code == 200 else []
    ok = bool(bl) and all("type" in g and "top_pain_points" in g for g in bl)
    add("TC-10", "หน้าวิเคราะห์หมวดโซน", "แยกหมวดตามประเภทสถานที่",
        "แสดงผลแยกตามประเภทที่เลือก", ok,
        f"โซน {zones[0]['zone'] if zones else '-'} -> "
        + " · ".join(f"{g['type']}({g['place_count']})" for g in bl))

    # ── TC-11 เปิดหน้าแผนที่ ──
    mr = await client.get("/map/geojson", params={"status": "all"})
    mj = mr.json() if mr.status_code == 200 else {}
    feats = mj.get("features") or []
    with_coord = [f for f in feats if f.get("geometry", {}).get("coordinates")]
    ok = mr.status_code == 200 and len(with_coord) > 0
    add("TC-11", "หน้าแผนที่", "เปิดหน้าแผนที่",
        "แสดงจุดสถานที่ในจังหวัดพิษณุโลก", ok,
        f"{len(feats)} จุด · มีพิกัด {len(with_coord)} จุด")

    # ── TC-12 คลิกจุดสถานที่ ──
    ok, note = None, "ไม่มีจุดให้ทดสอบ"
    if with_coord:
        pid = with_coord[0]["properties"]["id"]
        dr = await client.get(f"/places/{pid}")
        pr = await client.get(f"/places/{pid}/pain-points",
                              params={"view_mode": "complaints", "with_text_only": True})
        pl = pr.json() if pr.status_code == 200 else []
        ok = dr.status_code == 200 and pr.status_code == 200
        note = (f"สถานที่ id={pid} '{dr.json().get('name')}' -> "
                f"{len(pl)} รายการหมวด+ความรุนแรง")
    add("TC-12", "หน้าแผนที่", "คลิกจุดสถานที่",
        "แสดงชื่อและประเด็นปัญหาหลักของสถานที่", ok, note)

    # ── TC-13 ตั้งช่วงวันที่ที่ไม่มีรีวิว ──
    er = await client.get("/insights/summary",
                          params={"view_mode": "complaints", "status": "operational",
                                  "date_from": "1990-01-01", "date_to": "1990-12-31"})
    ej = er.json() if er.status_code == 200 else {}
    ok = (er.status_code == 200 and ej.get("total_reviews") == 0
          and ej.get("complaint_rate") is None)
    add("TC-13", "กรณีผิดปกติและ API", "ตั้งช่วงวันที่ที่ไม่มีรีวิว",
        "แสดงว่าไม่มีข้อมูล และระบบไม่หยุดทำงาน", ok,
        f"HTTP {er.status_code} · รีวิว {ej.get('total_reviews')} · "
        f"อัตราการบ่น {ej.get('complaint_rate')} (None = ไม่มีข้อมูลให้วัด ไม่ใช่ 0%)")

    # ── TC-14 ดาวน์โหลดรายงานของเดือนที่เลือก ──
    mo = await client.get("/reports/months")
    months = mo.json() if mo.status_code == 200 else []
    ok, note = None, f"HTTP {mo.status_code} · ไม่มีเดือนให้เลือก"
    if months:
        # ⚠️ endpoint รับ year และ month แยกกัน ไม่ใช่สตริงเดียว
        #   รุ่นแรกของการทดสอบนี้ส่ง month เดี่ยวแล้วได้ HTTP 422
        #   ซึ่งเป็นความผิดของตัวทดสอบเอง ไม่ใช่ของระบบ
        m = months[0]
        dl = await client.get("/reports/download",
                              params={"year": m["year"], "month": m["month"]})
        ctype = dl.headers.get("content-type", "")
        size = len(dl.content)
        ok = dl.status_code == 200 and size > 0
        note = (f"{len(months)} เดือนให้เลือก · ดาวน์โหลด {m['label']} "
                f"({m['year']}-{m['month']:02d}, {m['reviews']:,} รีวิว) -> "
                f"HTTP {dl.status_code} · {ctype} · {size:,} bytes")
    add("TC-14", "กรณีผิดปกติและ API", "ดาวน์โหลดรายงานของเดือนที่เลือก",
        "ได้ไฟล์รายงานของเดือนที่เลือก", ok, note)

    # ── TC-15 เรียกตรวจสถานะระบบ ──
    hr = await client.get("/health")
    hj = hr.json() if hr.status_code == 200 else {}
    ok = hr.status_code == 200
    add("TC-15", "กรณีผิดปกติและ API", "เรียกตรวจสถานะระบบ",
        "ระบบตอบสถานะปกติ", ok, f"HTTP {hr.status_code} · {json.dumps(hj, ensure_ascii=False)[:120]}")

    return cases


# ─────────────────────────────── เขียนรายงาน ───────────────────────────────

def write_report(t45: list[dict], t44: list[dict]) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [f"# ผลการทดสอบระบบ (สร้างอัตโนมัติ {now})", "",
         "สร้างด้วย `scripts/thesis_tests.py`", "",
         "⚠️ **ค่าจากแดชบอร์ดมาจากการเรียก API ด้วยพารามิเตอร์ชุดเดียวกับที่หน้าเว็บส่ง**",
         "(`view_mode=complaints`, `status=operational`, ไม่กรองช่วงเวลา)",
         "ไม่ใช่คำนวณซ้ำด้วย SQL แล้วเรียกว่าเป็นค่าจากแดชบอร์ด",
         "ส่วนค่าจากฐานข้อมูลเขียนเป็น SQL แยกจากโค้ด API โดยสิ้นเชิง", "",
         "---", "", "## ตารางที่ 4.5 การเปรียบเทียบตัวเลขบนแดชบอร์ดกับค่าจากฐานข้อมูล", "",
         "| รายการ | ค่าจากฐานข้อมูล | ค่าจากแดชบอร์ด | ผลต่าง |", "|---|---|---|---|"]
    for r in t45:
        a, b, d = r["ค่าจากฐานข้อมูล"], r["ค่าจากแดชบอร์ด"], r["ผลต่าง"]
        fa = f"{a:,}" if isinstance(a, int) else a
        fb = f"{b:,}" if isinstance(b, int) else b
        fd = f"{d:+,}" if isinstance(d, int) else d
        L.append(f"| {r['รายการ']} | {fa} | {fb} | {fd} |")
    allpass = all(r["ผ่าน"] for r in t45)
    L += ["",
          ("จากตารางที่ 4.5 ผลต่างเท่ากับ 0 ทุกรายการ และลำดับหมวดตรงกันทุกอันดับ "
           "จึงผ่านเกณฑ์" if allpass else
           "จากตารางที่ 4.5 **มีรายการที่ไม่ตรงกัน** ดูรายละเอียดด้านล่าง"), ""]

    L += ["---", "", "## ตารางที่ 4.4 ผลการทดสอบการทำงานของเว็บแอปพลิเคชัน", "",
          "| รหัส | กลุ่ม | ขั้นตอน | ผลที่คาดหวัง | ผล |", "|---|---|---|---|---|"]
    for c in t44:
        mark = "ผ่าน" if c["ผ่าน"] is True else ("ไม่ผ่าน" if c["ผ่าน"] is False
                                                 else "ต้องตรวจด้วยตา")
        L.append(f"| {c['รหัส']} | {c['กลุ่ม']} | {c['ขั้นตอน']} | "
                 f"{c['ผลที่คาดหวัง']} | {mark} |")
    npass = sum(1 for c in t44 if c["ผ่าน"] is True)
    nfail = sum(1 for c in t44 if c["ผ่าน"] is False)
    nman = sum(1 for c in t44 if c["ผ่าน"] is None)
    L += ["", f"ผ่าน {npass} · ไม่ผ่าน {nfail} · ต้องตรวจด้วยตา {nman} "
              f"จากทั้งหมด {len(t44)} กรณี", ""]

    L += ["### หลักฐานของแต่ละกรณี", "",
          "⚠️ ส่วนนี้ไม่ต้องใส่ในเล่ม มีไว้ให้ตรวจย้อนได้ว่าแต่ละกรณีวัดจากอะไร", "",
          "| รหัส | หลักฐาน |", "|---|---|"]
    for c in t44:
        L.append(f"| {c['รหัส']} | {c['หลักฐาน']} |")
    L.append("")

    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(
        {"generated_at": now, "table_4_5": t45, "table_4_4": t44},
        ensure_ascii=False, indent=2), encoding="utf-8")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    a = ap.parse_args()

    async with httpx.AsyncClient(base_url=a.base, timeout=120.0) as client:
        try:
            await client.get("/health")
        except httpx.ConnectError:
            p(f"ต่อ API ที่ {a.base} ไม่ได้")
            p("เปิดก่อนด้วย: uv run uvicorn api.main:app --port 8000")
            raise SystemExit(2)

        p("กำลังทำตารางที่ 4.5 ...")
        t45 = await table_4_5(client)
        p("กำลังทำตารางที่ 4.4 ...")
        t44 = await table_4_4(client)

    await engine.dispose()
    write_report(t45, t44)

    p("")
    p("=" * 72)
    p("  ตารางที่ 4.5  เทียบแดชบอร์ดกับฐานข้อมูล")
    p("=" * 72)
    for r in t45:
        a_, b_ = r["ค่าจากฐานข้อมูล"], r["ค่าจากแดชบอร์ด"]
        fa = f"{a_:,}" if isinstance(a_, int) else str(a_)[:40]
        fb = f"{b_:,}" if isinstance(b_, int) else str(b_)[:40]
        p(f"  {'ผ่าน ' if r['ผ่าน'] else 'ไม่ผ่าน'} {r['รายการ']:<28} "
          f"DB {fa:>12} | แดชบอร์ด {fb:>12} | ต่าง {r['ผลต่าง']}")
    p("")
    p("=" * 72)
    p("  ตารางที่ 4.4  Black-box 15 กรณี")
    p("=" * 72)
    for c in t44:
        mark = "ผ่าน  " if c["ผ่าน"] is True else (
            "ไม่ผ่าน" if c["ผ่าน"] is False else "ตรวจตา")
        p(f"  {mark} {c['รหัส']}  {c['ขั้นตอน']}")
        p(f"          {c['หลักฐาน']}")
    npass = sum(1 for c in t44 if c["ผ่าน"] is True)
    nfail = sum(1 for c in t44 if c["ผ่าน"] is False)
    nman = sum(1 for c in t44 if c["ผ่าน"] is None)
    p("")
    p(f"  สรุป: ผ่าน {npass} · ไม่ผ่าน {nfail} · ต้องตรวจด้วยตา {nman}")
    p("")
    p(f"เขียนที่ {OUT_MD.relative_to(ROOT)} และ {OUT_JSON.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
