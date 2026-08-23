"""
generate_report.py — สร้างรายงานประจำเดือน (PDF / Word / HTML)

PDF ใช้ Playwright (Chromium) เรนเดอร์ HTML → รองรับภาษาไทยสมบูรณ์
Word ใช้ python-docx → แก้ไขต่อเองได้

รัน:
  uv run python scripts/generate_report.py                       # เดือนล่าสุดที่มีข้อมูล, ทั้ง PDF+Word
  uv run python scripts/generate_report.py --month 2026-06       # ระบุเดือน
  uv run python scripts/generate_report.py --format pdf          # เอาแค่ PDF
  uv run python scripts/generate_report.py --format docx         # เอาแค่ Word
  uv run python scripts/generate_report.py --out D:\\myreports    # เลือกโฟลเดอร์ปลายทาง
"""
import argparse
import asyncio
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal
from reports.report_data import collect, thai_month_label
from reports.render_html import render as render_html

DEFAULT_OUT = Path("data/reports")


def safe_print(t: str) -> None:
    try:
        print(t)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"))


async def latest_month_with_data(session) -> tuple[int, int]:
    """หาเดือนล่าสุดที่มีรีวิว (ข้ามเดือนปัจจุบันที่ยังไม่จบ)"""
    r = await session.execute(
        text("""
            SELECT EXTRACT(YEAR FROM review_date_approx)::int  AS y,
                   EXTRACT(MONTH FROM review_date_approx)::int AS m
            FROM reviews
            WHERE review_date_approx IS NOT NULL
              AND review_date_approx < DATE_TRUNC('month', NOW())
            ORDER BY review_date_approx DESC LIMIT 1
        """)
    )
    row = r.fetchone()
    if not row:
        today = date.today()
        return today.year, today.month
    return row.y, row.m


async def html_to_pdf(html: str, out_path: Path) -> None:
    """แปลง HTML → PDF ด้วย Chromium (ภาษาไทยเรนเดอร์ถูกต้อง 100%)"""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html, wait_until="load")
        await page.pdf(
            path=str(out_path),
            format="A4",
            print_background=True,
            margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"},
        )
        await browser.close()


def parse_month(s: str | None) -> tuple[int, int] | None:
    if not s:
        return None
    y, m = s.split("-")
    return int(y), int(m)


async def main(month_arg: str | None, fmt: str, out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as session:
        ym = parse_month(month_arg) or await latest_month_with_data(session)
        year, month = ym
        safe_print(f"กำลังสร้างรายงานเดือน {thai_month_label(year, month)} ...")

        data = await collect(session, year, month)

    if not data.has_data:
        safe_print(f"⚠️  ไม่มีข้อมูลรีวิวในเดือน {data.period_label} — จะสร้างรายงานเปล่าให้")
    else:
        safe_print(f"   รีวิว {data.reviews_in_month:,} | คำบ่น {data.complaints_in_month:,} "
                   f"| คำชม {data.praise_in_month:,}")

    stem = f"report_{year}-{month:02d}"
    made: list[Path] = []

    if fmt in ("pdf", "both", "html"):
        html = render_html(data)
        html_path = out / f"{stem}.html"
        html_path.write_text(html, encoding="utf-8")
        if fmt == "html":
            made.append(html_path)
        else:
            pdf_path = out / f"{stem}.pdf"
            await html_to_pdf(html, pdf_path)
            made.append(pdf_path)
            made.append(html_path)

    if fmt in ("docx", "both"):
        from reports.render_docx import build
        docx_path = out / f"{stem}.docx"
        build(data, str(docx_path))
        made.append(docx_path)

    safe_print("\n✅ สร้างรายงานเสร็จ:")
    for f in made:
        size = f.stat().st_size / 1024
        safe_print(f"   {f}  ({size:,.0f} KB)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=None, help="เดือนที่ต้องการ เช่น 2026-06 (ไม่ระบุ = เดือนล่าสุดที่มีข้อมูล)")
    ap.add_argument("--format", default="both", choices=["both", "pdf", "docx", "html"],
                    help="รูปแบบไฟล์ (default: both = PDF + Word)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="โฟลเดอร์ปลายทาง")
    a = ap.parse_args()
    asyncio.run(main(a.month, a.format, a.out))
