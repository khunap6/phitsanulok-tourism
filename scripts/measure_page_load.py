"""measure_page_load.py — วัดเวลาโหลดหน้าเว็บสำหรับตารางที่ 4.12

⚠️ วิธีวัดตามที่ระบุในเล่ม
  เปิดหน้าเว็บแต่ละหน้า 5 ครั้ง ล้างแคชก่อนทุกครั้ง
  แล้วอ่านเวลาโหลดจากเครื่องมือนักพัฒนาของเว็บเบราว์เซอร์

  สคริปต์นี้ทำแบบเดียวกันแต่ให้ทำซ้ำได้
  **สร้าง browser context ใหม่ทุกครั้ง** ซึ่งได้แคชว่างจริง
  ไม่ใช่แค่กด reload ซึ่งยังใช้ไฟล์จากแคชเดิม

⚠️ รายงานสองตัวเลข เพราะ "เวลาโหลด" ของเว็บแบบ SPA กำกวม
  1. โหลดเอกสาร (load event)
     คือเลขที่ช่อง Load ของแท็บ Network แสดง
     แต่ ณ จุดนี้หน้าจอ **ยังไม่มีข้อมูล** เพราะ React เพิ่งเริ่มเรียก API
  2. ข้อมูลขึ้นครบ (เห็นตัวเลขจริงบนหน้าจอ)
     คือเวลาที่ผู้ใช้ใช้งานได้จริง ซึ่งเป็นตัวที่ควรรายงานในเล่ม

  ถ้ารายงานแต่ตัวแรกจะดูเร็วเกินจริงมาก (ต่างกันหลายเท่า)
  และไม่ตรงกับสิ่งที่ผู้ใช้รู้สึก

⚠️ ตัวเลขนี้วัดบนเครื่องที่รันทั้ง frontend, API และฐานข้อมูลพร้อมกัน
  จึงเป็น "เวลาบนเครื่องพัฒนา" ไม่ใช่เวลาบนเครื่องผู้ใช้จริงผ่านอินเทอร์เน็ต
  ต้องระบุข้อนี้ในเล่ม

ก่อนรันต้องเปิดสองอย่างไว้
  uv run uvicorn api.main:app --port 8000
  cd frontend && npm run build && npx vite preview --port 4173

รัน:
  uv run python scripts/measure_page_load.py
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "reports" / "page_load.md"
OUT_JSON = ROOT / "reports" / "page_load.json"

# เกณฑ์ที่ระบุในเล่ม
THRESHOLD_SEC = 5.0

# หน้า, path, และตัวบอกว่า "ข้อมูลขึ้นครบแล้ว"
#
# ⚠️ ตัวบอกต้องเป็นสิ่งที่ปรากฏ **หลังข้อมูลมาถึง** เท่านั้น
#   ถ้าเลือกสิ่งที่มีอยู่ตั้งแต่แรก (เช่น หัวข้อหน้า) จะวัดได้เร็วเกินจริง
#   ที่นี่ใช้การหายไปของตัว placeholder '…' ซึ่ง KPICard แสดงระหว่างโหลด
PAGES = [
    ("แดชบอร์ดหลัก", "/"),
    ("วิเคราะห์ตามโซน", "/zones"),
    ("แผนที่", "/map"),
]

# เวลาที่ถือว่า "คำขอ API นิ่งแล้ว" (ไม่มีคำขอใหม่เข้ามาอีก)
API_IDLE_MS = 800


def p(m: str = "") -> None:
    try:
        print(m, flush=True)
    except UnicodeEncodeError:
        print(m.encode("ascii", "replace").decode("ascii"), flush=True)


# ⚠️ นิยาม "ข้อมูลขึ้นครบ" = คำขอไปยัง /api/ หยุดนิ่งแล้ว
#
#   รุ่นแรกของสคริปต์นี้ใช้การดูข้อความบนหน้าจอ (เช่น การ์ด KPI เลิกแสดง '…')
#   ซึ่งใช้ได้กับหน้าที่เป็นตัวเลข แต่ **ใช้ไม่ได้กับหน้าแผนที่**
#   เพราะหน้านั้นเป็นแผนที่ ไม่ใช่ตัวอักษร
#   ผลคือการวัดครั้งแรกของหน้าแผนที่รอจนหมดเวลา 30 วินาทีแล้วได้ค่าว่าง
#   ทั้งที่หน้าเว็บทำงานปกติ — เป็นความผิดของตัววัด ไม่ใช่ของระบบ
#
#   การรอให้คำขอ API นิ่งใช้ได้กับทุกหน้าเหมือนกันหมด และตรงกับสิ่งที่
#   แท็บ Network แสดงว่า "โหลดเสร็จแล้ว"
#
# ⚠️ นับเฉพาะคำขอที่ไปยัง /api/ ของระบบนี้
#   ไม่นับคำขอของ Google Maps ซึ่งโหลดภาพแผนที่ต่อเนื่องไม่มีวันนิ่ง
#   ถ้านับด้วยจะรอไม่จบ


def run(base: str, runs: int, headed: bool) -> dict:
    import time as _time

    from playwright.sync_api import sync_playwright

    results: dict[str, list[dict]] = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        for name, path in PAGES:
            rows: list[dict] = []
            for i in range(1, runs + 1):
                # ⚠️ context ใหม่ = แคช คุกกี้ storage ว่างทั้งหมด
                #   เทียบเท่าการล้างแคชก่อนเปิดทุกครั้ง
                ctx = browser.new_context()
                page = ctx.new_page()

                # ⚠️ ต้องนับทั้ง "คำขอที่ยังไม่จบ" และ "เวลาตอบล่าสุด"
                #   รุ่นก่อนดูแค่เวลาตอบล่าสุด แล้วพลาดกรณีที่หน้าโซน
                #   ยิงสองคำขอพร้อมกัน: alerts จบที่ 204 ms แต่ zones จบที่ 1,763 ms
                #   ตัววัดเห็นว่า "ไม่มีคำขอใหม่ 800 ms" ตั้งแต่ 1,004 ms
                #   แล้วรายงานว่าโหลดเสร็จที่ 0.3 วินาที ทั้งที่ยังรออีกคำขอ
                #   ถ้าไม่เช็คคำขอค้าง จะได้ตัวเลขเร็วเกินจริงและเล่มจะผิด
                st = {"last": None, "pending": 0}

                def _on_request(req, _s=st):
                    if "/api/" in req.url:
                        _s["pending"] += 1

                def _on_done(req, _s=st):
                    if "/api/" in req.url:
                        _s["pending"] = max(0, _s["pending"] - 1)
                        _s["last"] = _time.monotonic()

                page.on("request", _on_request)
                page.on("requestfinished", _on_done)
                page.on("requestfailed", _on_done)

                t0 = _time.monotonic()
                page.goto(base + path, wait_until="load", timeout=60_000)
                doc_ms = page.evaluate(
                    "() => Math.round(performance.getEntriesByType('navigation')[0]"
                    ".loadEventEnd)")

                # รอจนไม่มีคำขอ /api/ ใหม่เป็นเวลา API_IDLE_MS
                ready_ms = None
                deadline = t0 + 60.0
                while _time.monotonic() < deadline:
                    lt = st["last"]
                    if (st["pending"] == 0 and lt is not None
                            and (_time.monotonic() - lt) * 1000 >= API_IDLE_MS):
                        ready_ms = round((lt - t0) * 1000)
                        break
                    page.wait_for_timeout(100)
                fcp = page.evaluate(
                    "() => { const e = performance.getEntriesByType('paint')"
                    ".find(x => x.name === 'first-contentful-paint');"
                    " return e ? Math.round(e.startTime) : null; }")
                api_n = page.evaluate(
                    "() => performance.getEntriesByType('resource')"
                    ".filter(r => r.name.includes('/api/')).length")
                rows.append({"ครั้งที่": i, "โหลดเอกสาร_ms": doc_ms,
                             "fcp_ms": fcp, "ข้อมูลขึ้นครบ_ms": ready_ms,
                             "จำนวนคำขอ_api": api_n})
                ctx.close()
                p(f"  {name} ครั้งที่ {i}: เอกสาร {doc_ms} ms · "
                  f"FCP {fcp} ms · ข้อมูลครบ {ready_ms} ms · API {api_n} คำขอ")
            results[name] = rows
        browser.close()
    return results


def summarize(rows: list[dict], key: str) -> dict:
    vals = [r[key] for r in rows if r[key] is not None]
    if not vals:
        return {"ค่าเฉลี่ย": None, "ต่ำสุด": None, "สูงสุด": None, "ผ่านเกณฑ์": None}
    mean = statistics.mean(vals)
    return {"ค่าเฉลี่ย": round(mean / 1000, 3),
            "ต่ำสุด": round(min(vals) / 1000, 3),
            "สูงสุด": round(max(vals) / 1000, 3),
            "ผ่านเกณฑ์": max(vals) / 1000 < THRESHOLD_SEC}


def write_report(res: dict, base: str, runs: int) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [f"# ผลการวัดเวลาตอบสนองของหน้าเว็บ (สร้างอัตโนมัติ {now})", "",
         "สร้างด้วย `scripts/measure_page_load.py`", "",
         f"เปิดหน้าเว็บแต่ละหน้า **{runs} ครั้ง** โดยสร้าง browser context ใหม่ทุกครั้ง",
         "ซึ่งได้แคชว่างจริง ไม่ใช่แค่กด reload",
         f"วัดจาก Chromium headless · เสิร์ฟด้วย production build ที่ `{base}`", "",
         "⚠️ **รายงานสองตัวเลข เพราะ \"เวลาโหลด\" ของเว็บแบบ SPA กำกวม**", "",
         "| ตัวเลข | ความหมาย |",
         "|---|---|",
         "| โหลดเอกสาร | เลขที่ช่อง Load ของแท็บ Network แสดง — "
         "ณ จุดนี้หน้าจอ**ยังไม่มีข้อมูล** |",
         "| ข้อมูลขึ้นครบ | เวลาที่ตัวเลขจริงปรากฏบนหน้าจอ = ใช้งานได้จริง |", "",
         "**ตัวที่ควรใส่ในเล่มคือ \"ข้อมูลขึ้นครบ\"** เพราะตรงกับสิ่งที่ผู้ใช้รู้สึก",
         "ถ้ารายงานแต่ \"โหลดเอกสาร\" จะดูเร็วเกินจริง", "",
         "---", ""]

    for metric, title in (("ข้อมูลขึ้นครบ_ms", "ตารางที่ 4.12 เวลาโหลดหน้าเว็บ (วินาที)"),
                          ("โหลดเอกสาร_ms", "ตารางเสริม — เวลาโหลดเอกสารอย่างเดียว (วินาที)")):
        L += [f"## {title}", ""]
        hdr = "| หน้า | " + " | ".join(f"ครั้งที่ {i}" for i in range(1, runs + 1))
        hdr += f" | เฉลี่ย | ผลตามเกณฑ์ (< {THRESHOLD_SEC:.0f} วินาที) |"
        L += [hdr, "|---" * (runs + 3) + "|"]
        for name, rows in res.items():
            s = summarize(rows, metric)
            cells = []
            for r in rows:
                v = r[metric]
                cells.append(f"{v / 1000:.3f}" if v is not None else "—")
            verdict = ("ผ่าน" if s["ผ่านเกณฑ์"] else "ไม่ผ่าน") if s["ผ่านเกณฑ์"] is not None else "—"
            avg = f"{s['ค่าเฉลี่ย']:.3f}" if s["ค่าเฉลี่ย"] is not None else "—"
            L.append(f"| {name} | " + " | ".join(cells) + f" | {avg} | {verdict} |")
        L.append("")

    L += ["---", "", "## ข้อสังเกต", ""]
    for name, rows in res.items():
        a = summarize(rows, "โหลดเอกสาร_ms")
        b = summarize(rows, "ข้อมูลขึ้นครบ_ms")
        napi = rows[0]["จำนวนคำขอ_api"]
        if a["ค่าเฉลี่ย"] and b["ค่าเฉลี่ย"]:
            L.append(f"- **{name}** โหลดเอกสาร {a['ค่าเฉลี่ย']:.3f} วินาที "
                     f"แต่ข้อมูลขึ้นครบที่ {b['ค่าเฉลี่ย']:.3f} วินาที "
                     f"(เรียก API {napi} คำขอหลังเอกสารโหลดเสร็จ)")
    L += ["",
          "## ข้อจำกัดของการวัดนี้", "",
          "1. **วัดบนเครื่องเดียวที่รันทั้ง frontend, API และฐานข้อมูลพร้อมกัน**",
          "   จึงไม่มีเวลาเดินทางของเครือข่ายจริง ตัวเลขจะเร็วกว่าการใช้งานจริง",
          "2. **วัดด้วย Chromium headless** ซึ่งไม่ต้องวาดภาพจริงบนจอ",
          "   เบราว์เซอร์ที่มีหน้าต่างจริงจะช้ากว่านี้เล็กน้อย",
          "3. **ฐานข้อมูลอุ่นแล้ว** การรันครั้งแรกสุดหลังเพิ่งเปิดเครื่องจะช้ากว่านี้",
          f"4. **วัดเพียง {runs} ครั้งต่อหน้า** ค่าเฉลี่ยจึงยังไวต่อค่าผิดปกติ",
          "5. **ไม่ได้จำลองความเร็วเน็ตที่ช้า** ถ้าต้องการตัวเลขที่ใกล้ผู้ใช้จริง",
          "   ต้องใช้ network throttling ในเครื่องมือนักพัฒนา", ""]
    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(
        {"generated_at": now, "base": base, "runs": runs,
         "threshold_sec": THRESHOLD_SEC, "results": res},
        ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:4173")
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--headed", action="store_true")
    a = ap.parse_args()

    p(f"วัดเวลาโหลด {a.runs} ครั้งต่อหน้า จาก {a.base}")
    p("")
    res = run(a.base, a.runs, a.headed)
    write_report(res, a.base, a.runs)

    p("")
    p("=" * 72)
    p(f"  ตารางที่ 4.12 เวลาโหลดหน้าเว็บ (วินาที) — เกณฑ์ < {THRESHOLD_SEC:.0f} วินาที")
    p("=" * 72)
    for name, rows in res.items():
        s = summarize(rows, "ข้อมูลขึ้นครบ_ms")
        d = summarize(rows, "โหลดเอกสาร_ms")
        p(f"  {name}")
        p(f"      ข้อมูลขึ้นครบ  เฉลี่ย {s['ค่าเฉลี่ย']} วินาที "
          f"(ต่ำสุด {s['ต่ำสุด']} สูงสุด {s['สูงสุด']}) -> "
          f"{'ผ่าน' if s['ผ่านเกณฑ์'] else 'ไม่ผ่าน'}")
        p(f"      โหลดเอกสาร     เฉลี่ย {d['ค่าเฉลี่ย']} วินาที")
    p("")
    p(f"เขียนที่ {OUT_MD.relative_to(ROOT)} และ {OUT_JSON.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
