# ============================================================
#  run_commands.ps1 — คำสั่งสำหรับรัน Scraper + NLP
#
#  วิธีใช้: ลบ # ออกหน้าคำสั่งที่ต้องการ แล้วรัน:
#    .\run_commands.ps1
#
#  หรือ copy คำสั่งไปวางใน PowerShell โดยตรง
# ============================================================

Set-Location "D:\Claude_Workspace\New\WebScraping\phitsanulok-tourism"

# ── DISCOVER (หาสถานที่ใหม่) ─────────────────────────────────
# uv run python scripts\discover_5.py      # ทดสอบ 5 สถานที่
# uv run python scripts\discover_20.py     # 20 สถานที่
# uv run python scripts\discover_50.py     # 50 สถานที่ (~1 ชม.)

# ── REFRESH (ดึงรีวิวเพิ่มจากสถานที่เดิม) ───────────────────
# uv run python scripts\refresh_all.py     # ทุกสถานที่

# ── ANALYZE (วิเคราะห์ NLP) ──────────────────────────────────
# uv run python scripts\analyze.py         # วิเคราะห์จนหมด

# ── CHECK DB (ดูสถานะ Database) ──────────────────────────────
# uv run python scripts\check_db.py

# ── RUN ALL (ทำครบทุกขั้นตอน) ────────────────────────────────
# uv run python scripts\run_all.py         # ปรับ MAX_PLACES ใน run_all.py ก่อน
