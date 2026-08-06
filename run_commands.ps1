# ============================================================
#  run_commands.ps1 — คำสั่งสำหรับรัน Scraper + NLP + LDA + Backup
#
#  วิธีใช้: ลบ # ออกหน้าคำสั่งที่ต้องการ แล้วรัน:
#    .\run_commands.ps1
#
#  หรือ copy คำสั่งไปวางใน PowerShell โดยตรง
# ============================================================

Set-Location "D:\Claude_Workspace\New\WebScraping\phitsanulok-tourism"

# ── UTF-8 ENCODING (ให้ terminal แสดงภาษาไทยถูกต้อง) ──────────
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
chcp 65001 > $null

# ── DISCOVER (หาสถานที่ใหม่) ─────────────────────────────────
# uv run python scripts\discover_5.py        # ทดสอบ 5 สถานที่
# uv run python scripts\discover_20.py       # 20 สถานที่
# uv run python scripts\discover_50.py       # 50 สถานที่ (~1 ชม.)

# ── REFRESH (เก็บข้อมูลที่ขาด + รีวิวเพิ่มจากร้านเดิม) ────────
# uv run python scripts\refresh_all.py --limit 40   # แมนนวล ทีละ 40 ร้าน (รันซ้ำเอง)
# uv run python scripts\refresh_all.py              # ทุกร้านรวดเดียว (เสี่ยงโดนบล็อก)

# ── AUTO REFRESH (อัตโนมัติ คำสั่งเดียว วนจนครบ + analyze + classify) ─
# uv run python scripts\auto_refresh.py             # เต็มรูปแบบ (แนะนำ — เดินจากเครื่องได้)
# uv run python scripts\auto_refresh.py --limit 40 --wait 15
# uv run python scripts\auto_refresh.py --no-followup   # ไม่ต่อ analyze/classify

# ── ANALYZE (วิเคราะห์ NLP) ──────────────────────────────────
# uv run python scripts\analyze.py           # วิเคราะห์จนหมด

# ── CHECK DB (ดูสถานะ Database) ──────────────────────────────
# uv run python scripts\check_db.py

# ── RUN ALL (ทำครบทุกขั้นตอน) ────────────────────────────────
# uv run python scripts\run_all.py           # ปรับ MAX_PLACES ใน run_all.py ก่อน

# ── ZONE-BASED DISCOVERY (ค้นหาแบบแยกพื้นที่) ────────────────
# uv run python scripts\assign_zones.py                             # ติด zone ให้ข้อมูลเดิม
# uv run python scripts\discover_by_zone.py                         # scrape ทุกโซน
# uv run python scripts\discover_by_zone.py --zone naresuan         # เฉพาะ ม.นเรศวร
# uv run python scripts\discover_by_zone.py --zone rajabhat         # เฉพาะ ม.ราชภัฏ
# uv run python scripts\discover_by_zone.py --zone city_center      # เฉพาะตัวเมือง

# ── CLASSIFY "อื่นๆ" ด้วย AI (Claude Haiku 4.5) ──────────────
# ต้องตั้ง ANTHROPIC_API_KEY ใน .env ก่อน (เอา key จาก console.anthropic.com)
# uv run python scripts\classify_other_llm.py --limit 40   # ทดสอบ 40 อันก่อน
# uv run python scripts\classify_other_llm.py              # จัดหมวดทั้งหมด

# ── TEST TOOLS ───────────────────────────────────────────────
# uv run python scripts\test_discover.py     # ทดสอบ selector ของ Google Maps

# ── GOOGLE CATEGORY (ทดสอบ + backfill ข้อมูลเดิม) ─────────────
# uv run python scripts\test_category_selector.py         # ทดสอบ selector ดึง google_category ก่อน
# uv run python scripts\backfill_category.py --limit 10   # ทดสอบ backfill แค่ 10 แห่งก่อน
# uv run python scripts\backfill_category.py              # backfill ทุกแห่งที่ยังเป็น NULL
# uv run python scripts\backfill_category.py --visible    # เปิด browser ให้เห็น (debug)

# ── RESCRAPE ข้อมูลร้าน (เวลาทำการใหม่ + สถานะร้าน + ราคา, ไม่เก็บรีวิว) ─
# อัปเดตข้อมูลร้านเดิมให้ตรงโค้ดปัจจุบัน (เวลาทำการทั้งสัปดาห์แบบใหม่) — เร็ว ไม่แตะคิวรีวิว
# uv run python scripts\rescrape_places.py --limit 10   # ทดสอบ 10 ร้านก่อน
# uv run python scripts\rescrape_places.py              # เฉพาะร้านที่เวลายังเป็นฟอร์แมตเก่า/ว่าง (resume ได้)
# uv run python scripts\rescrape_places.py --all        # บังคับ rescrape ทุกร้าน
# uv run python scripts\rescrape_places.py --visible    # เปิด browser ให้เห็น (debug)

# ── เวลาทำการครบ 7 วัน ผ่าน Google Places API (ทางการ, เชื่อถือได้) ────
# ต้องใส่ GOOGLE_PLACES_API_KEY ใน .env + เปิด Places API/billing ใน Google Cloud
# uv run python scripts\fetch_hours_api.py             # DRY-RUN: นับร้าน + ประเมินค่าใช้จ่าย (ไม่ยิง API)
# uv run python scripts\fetch_hours_api.py --limit 5   # ทดสอบ 5 ร้านแรก (ยิงจริง)
# uv run python scripts\fetch_hours_api.py --all       # ยิงทุกร้านที่เวลายังไม่ครบ
# uv run python scripts\fetch_hours_api.py --all --force  # ยิงทุกร้าน (รวมที่ครบแล้ว)

# ── BACKUP / SEED DATABASE (สำหรับ git) ──────────────────────
# อัพเดต seed.sql ก่อน commit เข้า git (มีทั้ง schema + ข้อมูล)
# pg_dump -U postgres -d phitsanulok_tourism -f "backup\seed.sql"

# Backup ปกติ (timestamp) — ไม่ขึ้น git เพราะ .gitignore กันไว้
# pg_dump -U postgres -d phitsanulok_tourism -f "backup\db_backup.sql"

# ── RESTORE DATABASE (หลัง clone / ย้อนกลับ) ─────────────────
# psql -U postgres -d phitsanulok_tourism -f "backup\seed.sql"

# ── RUN SERVERS (เปิดเว็บ) ───────────────────────────────────
# [Terminal 1] Backend API:
# uv run uvicorn api.main:app --reload

# [Terminal 2] Frontend:
# cd frontend ; npm run dev
# เปิด http://localhost:5173
