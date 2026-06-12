# ============================================================
#  run_commands.ps1 — คำสั่งสำหรับรัน Scraper + NLP + LDA + Backup
#
#  วิธีใช้: ลบ # ออกหน้าคำสั่งที่ต้องการ แล้วรัน:
#    .\run_commands.ps1
#
#  หรือ copy คำสั่งไปวางใน PowerShell โดยตรง
# ============================================================

Set-Location "D:\Claude_Workspace\New\WebScraping\phitsanulok-tourism"

# ── DISCOVER (หาสถานที่ใหม่) ─────────────────────────────────
# uv run python scripts\discover_5.py        # ทดสอบ 5 สถานที่
# uv run python scripts\discover_20.py       # 20 สถานที่
# uv run python scripts\discover_50.py       # 50 สถานที่ (~1 ชม.)

# ── REFRESH (ดึงรีวิวเพิ่มจากสถานที่เดิม) ───────────────────
# uv run python scripts\refresh_all.py       # ทุกสถานที่

# ── ANALYZE (วิเคราะห์ NLP) ──────────────────────────────────
# uv run python scripts\analyze.py           # วิเคราะห์จนหมด

# ── CHECK DB (ดูสถานะ Database) ──────────────────────────────
# uv run python scripts\check_db.py

# ── RUN ALL (ทำครบทุกขั้นตอน) ────────────────────────────────
# uv run python scripts\run_all.py           # ปรับ MAX_PLACES ใน run_all.py ก่อน

# ── TOPIC MODELING (LDA) ─────────────────────────────────────
# uv run python scripts\topic_model_lda.py   # ค้นหาหมวดหมู่อัตโนมัติ
# uv run python scripts\test_discover.py     # ทดสอบ selector ของ Google Maps

# ── BACKUP DATABASE ──────────────────────────────────────────
# สร้างโฟลเดอร์ backup (ทำครั้งเดียวพอ)
# New-Item -ItemType Directory -Force -Path "backup"

# Backup ฐานข้อมูล PostgreSQL → ไฟล์ .sql
# pg_dump -U postgres -d phitsanulok_tourism -f "backup\db_backup.sql"

# Backup ไฟล์ JSON และผล LDA ทั้งหมด
# xcopy "data" "backup\data" /E /I /Y

# ตรวจสอบว่า backup สำเร็จ (ดูขนาดไฟล์)
# dir backup

# ── RESTORE DATABASE (ใช้เมื่อต้องการย้อนกลับ) ───────────────
# psql -U postgres -d phitsanulok_tourism -f "backup\db_backup.sql"

# ── RUN SERVERS (เปิดเว็บ) ───────────────────────────────────
# [Terminal 1] Backend API:
# uv run uvicorn api.main:app --reload

# [Terminal 2] Frontend:
# cd frontend ; npm run dev
# เปิด http://localhost:5173
