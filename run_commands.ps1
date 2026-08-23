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

# ── DISCOVER (หาสถานที่ใหม่อย่างเดียว — ไม่ดึงรีวิว, เร็ว+เสี่ยงบล็อกน้อย) ──
# เก็บแค่ ชื่อ/พิกัด/หมวดหมู่/เวลาทำการ/สถานะร้าน — รีวิวมาจาก refresh ทีหลัง
# uv run python scripts\discover_5.py        # ทดสอบ 5 สถานที่
# uv run python scripts\discover_20.py       # 20 สถานที่
# uv run python scripts\discover_50.py       # 50 สถานที่

# ── REFRESH (เก็บข้อมูลที่ขาด + รีวิวเพิ่มจากร้านเดิม) ────────
# ⚡ ตั้งแต่ v2 เป็น INCREMENTAL: หยุด scroll ทันทีที่เจอรีวิวเดิม (เร็วขึ้นมาก)
#    - ร้านใหม่ / ยังไม่เคยเก็บ  → scan เต็ม
#    - ร้านเดิมที่ไม่มีรีวิวใหม่  → หยุดหลัง scroll ไม่กี่รอบ (ประหยัด ~90%)
#    - ร้านที่นิ่งหลายรอบ        → ถูกเว้นรอบนานขึ้นเอง (7 → 14 → 30 วัน)
# uv run python scripts\refresh_all.py --limit 40   # แมนนวล ทีละ 40 ร้าน (รันซ้ำเอง)
# uv run python scripts\refresh_all.py              # ทุกร้านรวดเดียว (เสี่ยงโดนบล็อก)

# ── ทดสอบ logic incremental (offline ไม่ต่อเน็ต ไม่โดนบล็อก) ──
# uv run python scripts\test_incremental.py

# ── SNAPSHOT สถิติ (ฐานของระบบแจ้งเตือน + เทียบย้อนหลัง) ─────
# auto_refresh จะเก็บให้อัตโนมัติหลัง analyze อยู่แล้ว — คำสั่งนี้ไว้เก็บเอง
# uv run python scripts\take_snapshot.py                     # เก็บ ณ ตอนนี้
# uv run python scripts\take_snapshot.py --label 2026-W34    # ตั้งชื่อช่วง
# uv run python scripts\take_snapshot.py --as-of 2026-06-30  # ย้อนอดีต (นับรีวิวถึงวันนั้น)
# uv run python scripts\take_snapshot.py --list              # ดูรายการที่เก็บไว้

# ── AUTO REFRESH (อัตโนมัติ คำสั่งเดียว วนจนครบ + analyze + classify) ─
# uv run python scripts\auto_refresh.py             # เต็มรูปแบบ (แนะนำ — เดินจากเครื่องได้)
# uv run python scripts\auto_refresh.py --limit 40 --wait 15
# uv run python scripts\auto_refresh.py --no-followup   # ไม่ต่อ analyze/classify

# ── ANALYZE (วิเคราะห์ NLP) ──────────────────────────────────
# uv run python scripts\analyze.py           # วิเคราะห์รีวิวใหม่ที่ยังไม่วิเคราะห์ (ใช้ WangchanBERTa fine-tuned)

# ── RE-ANALYZE ทั้งระบบด้วย WangchanBERTa (โมเดล fine-tune เอง, รันบน GPU) ──
# วิเคราะห์ "ทุกรีวิว" ใหม่ (เขียนทับของเดิม) — ใช้เมื่อฝึกโมเดลใหม่/ปรับปรุงโมเดล
# ผลของ Claude (claude_category/claude_sentiment) เก็บไว้เทียบ ไม่ถูกแตะ
# ⚠️ backup ก่อนเสมอ (ดูส่วน BACKUP ด้านล่าง)
# uv run python scripts\reanalyze_all.py            # ดูก่อนว่าจะทำกี่รีวิว (ไม่แตะข้อมูล)
# uv run python scripts\reanalyze_all.py --apply    # วิเคราะห์ใหม่จริง (~2-5 นาทีบน GPU)
#
# หลัง re-analyze เสร็จ อย่าลืมอัปเดต snapshot + สร้างรายงานใหม่:
# uv run python scripts\take_snapshot.py --label ปัจจุบัน
# uv run python scripts\generate_report.py

# ── ฝึกโมเดล WangchanBERTa เอง (Knowledge Distillation จากป้ายของ Claude) ──
# uv run python scripts\label_training_data.py           # ดูว่าต้องติดป้ายเพิ่มกี่รีวิว (ใช้ Claude API)
# uv run python scripts\label_training_data.py --apply   # ติดป้ายเพิ่ม (เสียเงิน ~$0.5)
# uv run python nlp\train\prepare_data.py --task category   # เตรียมชุดข้อมูลฝึก
# uv run python nlp\train\prepare_data.py --task sentiment
# uv run python nlp\train\train.py --task category --epochs 10   # ฝึก (GPU ~6 นาที / CPU ~50 นาที)
# uv run python nlp\train\train.py --task sentiment --epochs 10
# uv run python nlp\train\compare_models.py --task category      # เทียบผลกับระบบเดิม

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

# ── REPORT รายเดือน (PDF / Word / HTML) ──────────────────────
# กดจากหน้าเว็บได้ที่การ์ด "รายงานประจำเดือน" หรือใช้คำสั่ง:
# uv run python scripts\generate_report.py                    # เดือนล่าสุด, ได้ทั้ง PDF+Word
# uv run python scripts\generate_report.py --month 2026-06    # ระบุเดือน
# uv run python scripts\generate_report.py --format pdf       # เอาแค่ PDF
# uv run python scripts\generate_report.py --format docx      # เอาแค่ Word
# ไฟล์ออกที่ data
eports

# -- DEDUP: ล้างรีวิวซ้ำ + กันซ้ำในอนาคต --------------------
# สาเหตุเดิม: hash คำนวณจากข้อความดิบที่มีวันที่ติดมา ("7 เดือนที่แล้ว")
# พอ scrape รอบใหม่วันที่เลื่อน -> hash เปลี่ยน -> บันทึกซ้ำ (เคยซ้ำ 3,453 แถว)
# แก้แล้วโดยเปลี่ยนไป hash จาก text_clean (ตัดวันที่ออกแล้ว)
# uv run python scripts\dedup_reviews.py          # ดูก่อนว่ามีซ้ำเท่าไหร่ (ไม่ลบ)
# uv run python scripts\dedup_reviews.py --apply  # ลบจริง (backup ก่อน!)
# uv run python scripts	est_dedup.py             # เทสต์ว่าระบบกันซ้ำยังทำงาน
