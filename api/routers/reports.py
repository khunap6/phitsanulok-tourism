"""
reports.py — API สร้าง/ดาวน์โหลดรายงานประจำเดือน (PDF / Word / HTML)

PDF สร้างด้วย Playwright (Chromium) → ภาษาไทยถูกต้อง 100%
Word สร้างด้วย python-docx → ผู้ใช้แก้ไขต่อเองได้
"""
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from reports.render_html import render as render_html
from reports.report_data import collect, thai_month_label

router = APIRouter(prefix="/reports", tags=["reports"])

MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("/months")
async def available_months(db: Annotated[AsyncSession, Depends(get_db)]):
    """เดือนที่มีข้อมูลให้ออกรายงานได้ (ตัดเดือนปัจจุบันที่ยังไม่จบออก)"""
    result = await db.execute(
        text("""
            SELECT EXTRACT(YEAR FROM review_date_approx)::int  AS year,
                   EXTRACT(MONTH FROM review_date_approx)::int AS month,
                   COUNT(*) AS reviews
            FROM reviews
            WHERE review_date_approx IS NOT NULL
              AND review_date_approx < DATE_TRUNC('month', NOW())
            GROUP BY 1, 2
            HAVING COUNT(*) >= 10
            ORDER BY 1 DESC, 2 DESC
            LIMIT 24
        """)
    )
    return [
        {"year": r.year, "month": r.month,
         "label": thai_month_label(r.year, r.month), "reviews": r.reviews}
        for r in result.fetchall()
    ]


@router.get("/download")
async def download_report(
    db: Annotated[AsyncSession, Depends(get_db)],
    year: int,
    month: int,
    format: str = "pdf",
):
    """สร้างรายงานแล้วส่งไฟล์กลับทันที (format: pdf | docx | html)"""
    if format not in ("pdf", "docx", "html"):
        raise HTTPException(400, "format ต้องเป็น pdf, docx หรือ html")
    if not (1 <= month <= 12):
        raise HTTPException(400, "month ต้องอยู่ระหว่าง 1-12")

    data = await collect(db, year, month)
    stem = f"report_{year}-{month:02d}"

    if format == "html":
        return HTMLResponse(render_html(data))

    if format == "pdf":
        from playwright.async_api import async_playwright
        html = render_html(data)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / f"{stem}.pdf"
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_content(html, wait_until="load")
                await page.pdf(
                    path=str(out), format="A4", print_background=True,
                    margin={"top": "14mm", "bottom": "14mm", "left": "12mm", "right": "12mm"},
                )
                await browser.close()
            content = out.read_bytes()
    else:  # docx
        from reports.render_docx import build
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / f"{stem}.docx"
            build(data, str(out))
            content = out.read_bytes()

    return Response(
        content=content,
        media_type=MEDIA[format],
        headers={"Content-Disposition": f'attachment; filename="{stem}.{format}"'},
    )
