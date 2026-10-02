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

# ── DEEP SCAN (เก็บรีวิวย้อนหลังให้ครบ — สั่งเองเท่านั้น) ──────
# ต่างจาก refresh: ไม่หยุดเมื่อเจอรีวิวเดิม — scroll จนสุดจริง (ร้านละไม่เกิน 10 นาที)
# ใช้กับร้านที่เคยติดเพดาน scroll เดิม (60 รอบ) จนเก็บรีวิวได้ไม่ครบ
# uv run python scripts\deep_scan.py --dry-run              # ดูรายชื่อร้านก่อน (ไม่แตะเน็ต)
# uv run python scripts\deep_scan.py                        # capped (รีวิว >=190) ทีละ 5 ร้าน พัก 20 นาที
# uv run python scripts\deep_scan.py --targets all --limit 3 --wait 30
# uv run python scripts\test_deep_block.py                  # ทดสอบการจัดการบล็อก (offline, rollback ทุกอย่าง)
# ⚠️ ไม่ต่อ analyze/classify ให้อัตโนมัติ — เก็บครบแล้วสั่ง analyze.py เอง

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

# ── ล้างรีวิวซ้ำในไฟล์ master JSON ──────────────
# data/phitsanulok_accumulated.json เคยสะสมรีวิวซ้ำ เพราะกันซ้ำด้วย text[:80] ดิบ
# ที่มีวันที่สัมพัทธ์ติดมา (แก้ต้นเหตุที่ _merge_reviews แล้ว — ใช้ hash เหมือน DB)
# ไฟล์นี้เป็นแค่ backup ฝั่ง scraper — ไม่มีโค้ดไหนอ่านไปใช้วิเคราะห์
# uv run python scripts\dedup_accumulated_json.py           # ดูก่อน ไม่แตะไฟล์
# uv run python scripts\dedup_accumulated_json.py --apply   # ล้างจริง (สำรองไฟล์เดิมให้)

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

# ── เติม google_place_id + ฟิลด์ API ให้ร้านเดิม (ขั้นแรกของงาน discover) ─
# ต้องใส่ GOOGLE_PLACES_API_KEY ใน .env + เปิด Places API/billing ใน Google Cloud
# เขียนแค่ 7 คอลัมน์ใหม่ (google_place_id, google_types, formatted_address,
#   google_rating, google_reviews_total, api_fetched_at, discovered_by)
#   ไม่แตะ name/location/overall_rating/opening_hours/business_status/zone/deep_*
# ⚠️ รัน --limit 5 ก่อนเสมอ แล้วเช็ค Billing > Reports ว่าเครดิตครอบ Places API ไหม
# uv run python scripts\backfill_place_id.py                # DRY-RUN: นับ + ประเมินราคา (ไม่ยิง API)
# uv run python scripts\backfill_place_id.py --report       # อ่านอย่างเดียว: ตารางจุดตรวจ 4 ข้อ
# uv run python scripts\backfill_place_id.py --limit 5      # ทดสอบ 5 ร้าน (ยิงจริง ~฿5)
# uv run python scripts\backfill_place_id.py --all          # ยิงทุกร้านที่ยังไม่มี place_id
# uv run python scripts\backfill_place_id.py --all --force  # ยิงซ้ำรวมร้านที่มีแล้ว
# uv run python scripts\backfill_place_id.py --all --max-requests 100   # เพดานแข็ง
# uv run python scripts\backfill_place_id.py --limit 5 --max-requests 0 # ทดสอบว่าเพดานทำงาน (ไม่ยิงเลย)

# ── DISCOVER ร้านใหม่ด้วย Places Nearby Search (ขั้น 2) ────────────
# ผลลงตารางพัก place_candidates ไม่เข้า places ตรง ๆ + resume ได้ผ่าน discover_cells
# รัศมีค้นหา 4 กม. (คนละค่ากับรัศมีโซน 2 กม. ซึ่งไม่ถูกแตะ) · 83 เซลล์ x 8 type = 664 งาน
# ⚠️ ค่าใช้จ่าย 664-1,992 คำขอ ~$17-50 — เริ่มด้วย --types cafe เพื่อวัดอัตราจริงก่อน
# uv run python scripts\discover_api.py                     # DRY-RUN: นับเซลล์ + ประเมินราคา (ไม่ยิง)
# uv run python scripts\discover_api.py --report            # อ่านอย่างเดียว: สรุปผล + ตารางวงแหวน
# uv run python scripts\discover_api.py --run --types cafe  # type เดียว 83 คำขอ ~$2 (แนะนำก่อน)
# uv run python scripts\discover_api.py --run --max-requests 40   # ยิงจริงแบบจำกัดวงเงิน
# uv run python scripts\discover_api.py --run --zones rajabhat    # เฉพาะโซนเดียว
# uv run python scripts\discover_api.py --run                     # ทุกเซลล์ที่ยังไม่เคยทำ
# uv run python scripts\discover_api.py --verify-types            # ตรวจว่า Google เคารพ type ไหม (ไม่ยิง API)
# uv run python scripts\discover_api.py --subdivide-capped        # DRY-RUN: ซอยเฉพาะเซลล์ที่ชนเพดาน 60
# uv run python scripts\discover_api.py --subdivide-capped --run  # ยิงจริง (ถูกกว่า --cell-radius 0.5 ~7 เท่า)
# uv run python scripts\discover_api.py --run --max-requests 0    # ทดสอบว่าเพดานทำงาน (ไม่ยิงเลย)
#
# ⚠️ ห้ามใส่ type จาก Table 2 ของ Google (place_of_worship, food, point_of_interest,
#    establishment, ...) เพราะ Google จะเพิกเฉยเงียบ ๆ แล้วคืนทุกอย่างในรัศมีมาให้
#    สคริปต์กันไว้แล้วผ่าน UNSEARCHABLE_TYPES แต่ถ้าเจอ type ใหม่ต้องเช็คเอกสารก่อน
#    https://developers.google.com/maps/documentation/places/web-service/legacy/supported_types

# ── เลื่อนร้านจากตารางพักเข้า places (ขั้นสุดท้ายของงาน discover) ────
# ตารางพักเก็บผู้สมัครทั้งหมด (ไม่ลบ) แต่เลื่อนเข้า places เฉพาะที่ผ่านเกณฑ์
# เกณฑ์: >=50 รีวิวบน Google + เป็นประเภทที่สนใจ + ไม่ใช่เชน/ห้าง/โรงแรม
# ⚠️ ห้ามเลื่อนร้านที่ไม่ผ่านเกณฑ์ — scraped_at=NULL จะขึ้นหัวคิว refresh ทันที
#    (scraper.py: ORDER BY scraped_at ASC NULLS FIRST) แล้ว auto_refresh จะไล่ scrape ทั้งหมด
# uv run python scripts\promote_candidates.py                      # DRY-RUN: รายชื่อ + ราคา + ตรวจชนชื่อ
# uv run python scripts\promote_candidates.py --reject-list        # ตั้งธงคัดออกด้วยมือ (ฟรี)
# uv run python scripts\promote_candidates.py --details --limit 5  # ทดสอบ Details 5 ร้าน (~฿4)
# uv run python scripts\promote_candidates.py --details            # ยิง Details ครบ [ใช้เครดิต ก่อน 31 ต.ค.]
# uv run python scripts\promote_candidates.py --promote            # เขียนเข้า places (ฟรี)
# uv run python scripts\promote_candidates.py --min-reviews 30     # ปรับเกณฑ์ (ไม่ต้องยิง API ใหม่)
#
# แล้วเก็บรีวิวต่อด้วย auto_refresh (ไม่ใช้เครดิต ทำหลังเครดิตหมดได้)
# uv run python scripts\auto_refresh.py --limit 40

# ── เช็คความครบถ้วน + กู้ร้านที่ scrape พังเงียบ ─────────────────
# ⚠️ Google จำกัดอัตราแบบเงียบได้ — ไม่ขึ้น CAPTCHA แต่เสิร์ฟรีวิวให้น้อยจนเกือบศูนย์
#    ตัวตรวจจับบล็อกเดิมจับไม่ได้ ร้านจะถูกตี scraped_at แล้วเข้า cooldown 7-30 วัน
#    ลายเซ็น: ร้านหลายสิบแห่งเก็บได้เป๊ะ 5 หรือเป๊ะ 10 รีวิว (ไม่ใช่การกระจายธรรมชาติ)
#
# auto_refresh มีตัวตัดวงจรแล้ว: เก็บได้ < 40% ของ LEAST(google,850) -> พัก 2/4/6 ชม.
#   ครบ 3 ครั้งยังต่ำ -> หยุดและคืนสถานะ throttled (ไม่ต่อ analyze/classify)
#
# uv run python scripts\requeue_shortfall.py                  # DRY-RUN: ดูร้านที่เก็บไม่ครบ
# uv run python scripts\requeue_shortfall.py --apply          # ส่งกลับเข้าคิว (ไม่ลบรีวิว)
# uv run python scripts\requeue_shortfall.py --min-coverage 0.3 --apply
# uv run python scripts\requeue_shortfall.py --max-shortfalls 3 --apply  # ลองอีกรอบ
#
# ขั้นตอนเมื่อเจอพังเงียบ: หยุด scrape -> เปลี่ยน IP -> requeue --apply -> รันใหม่ --limit 20

# ── BACKUP / SEED DATABASE (สำหรับ git) ──────────────────────
# ⚠️ pg_dump / psql ไม่ได้อยู่ใน PATH ของเครื่องนี้ ต้องเรียกด้วย full path
#    (พิมพ์ pg_dump เปล่า ๆ จะได้ "not recognized as the name of a cmdlet")
#    ปรับ path ให้ตรงเวอร์ชันที่ติดตั้ง — เครื่องนี้คือ D:\PostgreSQL\16\bin
#    ถ้าไม่ตั้ง PGPASSWORD มันจะถามรหัสให้พิมพ์ (รหัสอยู่ใน .env: SYNC_DATABASE_URL)$PG = "D:\PostgreSQL\16\bin"
#    $env:PGPASSWORD = "<รหัสใน .env>"    # ตั้งไว้ถ้าไม่อยากพิมพ์รหัสทุกครั้ง
#    $env:PGPASSWORD = "<รหัสใน .env>"; & "D:\PostgreSQL\16\bin\pg_dump.exe" -U postgres -d phitsanulok_tourism -f "backup\seed.sql"

# อัพเดต seed.sql ก่อน commit เข้า git (มีทั้ง schema + ข้อมูล)
# & "$PG\pg_dump.exe" -U postgres -d phitsanulok_tourism -f "backup\seed.sql"

# Backup ปกติ (timestamp) — ไม่ขึ้น git เพราะ .gitignore กันไว้
# & "$PG\pg_dump.exe" -U postgres -d phitsanulok_tourism -f "backup\db_backup_$(Get-Date -Format yyyyMMdd_HHmmss).sql"

# ── RESTORE DATABASE (หลัง clone / ย้อนกลับ) ─────────────────
# & "$PG\psql.exe" -U postgres -d phitsanulok_tourism -f "backup\seed.sql"

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

# ── แก้ NLP ที่วิเคราะห์จากข้อความดิบ (พบ 2026-09-26) ───────────────
# nlp/pipeline.py เคยดึง r.text (ดิบ มีปุ่ม "ชอบ"/"แชร์"/วันที่/ป้าย "บริการ: 5" ปน)
# แก้เป็น r.text_clean แล้ว — รีวิวที่ scrape ใหม่จะสะอาด
# uv run python scripts\fix_dirty_keywords.py           # DRY-RUN: ดูแถวที่ผิด
# uv run python scripts\fix_dirty_keywords.py --apply   # ล้างหมวดของรีวิวดาวเปล่า
#
# รีวิวที่มีข้อความต้องวิเคราะห์ใหม่ด้วย WangchanBERTa (ห้ามใช้ rule-based แทน)
# & "$PG\pg_dump.exe" -U postgres -d phitsanulok_tourism -f "backup\before_reanalyze.sql"
# uv run python scripts\reanalyze_all.py                # ดูก่อนว่าจะทำกี่แถว
# uv run python scripts\reanalyze_all.py --apply        # วิเคราะห์ใหม่จาก text_clean

# ── กู้ review_date_approx ที่แปลงไม่ได้ (พบ 2026-09-26) ────────────
# 2 บั๊ก: date_parser ไม่รับ "ที่ผ่านมา" + scraper หยิบป้าย "มื้อที่ไป" มาเป็นวันที่
# แก้ต้นตอทั้งคู่แล้ว — รีวิวที่ scrape ใหม่จะได้วันที่ถูก
# ⚠️ รีวิวที่ review_date_approx เป็น NULL จะหายจากทุกหน้าที่กรองช่วงวันที่
# uv run python scripts\backfill_review_dates.py           # DRY-RUN
# uv run python scripts\backfill_review_dates.py --apply   # กู้จริง (ไม่แตะ review_date ดิบ)

# ── แถวร้านซ้ำ + รีวิวซ้ำข้ามร้าน (พบ 2026-09-26) ──────────────────
# promote ใช้ชื่อจาก API แต่ scraper ใช้ชื่อบนหน้าเว็บ -> ON CONFLICT (name) ไม่ตรง
# -> INSERT แถวใหม่ = ร้านเดียวกันมี 2 แถว + คิว refresh วนไม่รู้จบ
# แก้ต้นตอแล้ว: promote_candidates.py ตรวจพิกัดด้วย (coord_collisions)
# uv run python scripts\merge_duplicate_places.py           # DRY-RUN: ดูคู่ที่จะรวม
# uv run python scripts\merge_duplicate_places.py --apply   # รวมจริง (ไม่ลบรีวิว)
#
# รีวิวข้อความเดียวกันอยู่หลายร้าน (Google ย้าย listing / scrape ผิดร้าน)
# ⚠️ ควร backup ก่อน — ลบแถว reviews จะลบ analyzed_reviews ตาม (CASCADE)
# uv run python scripts\dedup_cross_place.py           # DRY-RUN
# uv run python scripts\dedup_cross_place.py --apply   # ลบจริง (เหลือสำเนาละ 1 อัน)

# ── deep scan ด้วยเกณฑ์ gap (ใช้ google_reviews_total เป็นเฉลย) ──────
# เกณฑ์เดิม (capped/zero/shallow) เรียงด้วย cnt DESC ซึ่งกลับหัวกับผลตอบแทน
# และใช้ WHERE deep_scanned_at IS NULL จึงข้ามร้าน 33 แห่งที่ถูกตีว่า deep แล้ว
# แต่เก็บได้แค่ ~200 (~8,449 รีวิวที่เข้าถึงไม่ได้)
# gap เรียงด้วย min(google,850) - เก็บได้ และไม่บังคับ deep_scanned_at IS NULL
# uv run python scripts\deep_scan.py --targets gap --dry-run   # ดูคิวก่อน
# uv run python scripts\deep_scan.py --targets gap --limit 5   # ทดสอบ 5 ร้าน
# uv run python scripts\deep_scan.py --targets gap             # รันเต็ม
#
# ลำดับที่ควรทำ: auto_refresh -> requeue_shortfall (เช็ค) -> deep_scan --targets gap
#   refresh ก่อนเพราะร้านที่ Google มี <=200 รีวิว refresh ได้ 94% ใน 14 วิ
#   ส่วน deep ใช้ 3 นาทีเพื่อผลเท่าเดิม — เก็บ deep ไว้ให้ร้านที่เกินเพดาน 200

# ── ขอบเขตร้าน: กันโรงแรม/เขตปกครองไม่ให้เข้าคิว (migration 017) ─────
# ⚠️ ต้องรัน migration ก่อน ไม่งั้นทุกคำสั่งที่สร้างคิวจะพังเพราะไม่มีคอลัมน์
#    และ ALTER TABLE places ต้องรอให้ auto_refresh/deep_scan หยุดก่อน
#    (มันถือ transaction ค้างบน places ทั้งรอบ -> ALTER จะคาคิวและบล็อกงานอื่น)
# uv run alembic upgrade head
#
# ตั้งธง scrape_excluded — ไม่ลบร้าน ไม่ลบรีวิว ถอนคืนได้
# uv run python scripts\exclude_places.py --pure-lodging           # DRY-RUN
# uv run python scripts\exclude_places.py --pure-lodging --apply   # ที่พักล้วน 7 ร้าน
# uv run python scripts\exclude_places.py --admin-areas --apply    # เขตปกครอง 2 แถว
# uv run python scripts\exclude_places.py --report                 # ดูว่ากันอะไรไว้
# uv run python scripts\exclude_places.py --include 664 1618       # ถอนคืน
#
# ⚠️ ธงนี้กรองแค่คิว scrape ไม่กรองสถิติ pain point
#    รีวิว 67 อันจาก 3 ร้านที่กันไว้ยังถูกนับใน api/ ตามเดิม

# ── ซ่อม google_category ที่เก็บข้อความปุ่ม UI มา (พบ 2026-09-27) ─────
# ร้านที่เจ้าของไม่ได้ยืนยันข้อมูล Google จะเอาปุ่ม 'เพิ่มเว็บไซต์'/'เพิ่มเวลาทำการ'
# มาวางตำแหน่ง DOM เดียวกับหมวด -> scraper เก็บข้อความปุ่มมาเป็นหมวด (4 ร้าน)
# ปิดต้นเหตุแล้วใน scraper_core._is_ui_button_text()
# uv run python scripts\fix_place_category.py            # DRY-RUN
# uv run python scripts\fix_place_category.py --apply    # แก้ 29 + ล้างขยะ 2
#
# ไม่ทับหมวดที่ดีอยู่แล้ว ('ร้านอาหารญี่ปุ่น' ละเอียดกว่า 'restaurant')

# ── ปลดล็อกร้านที่ชนเพดาน refresh_shortfalls ────────────────────────
# ใช้เมื่อเปลี่ยน IP หรือย้ายไปรันช่วง 02:00-05:00 — ไม่ใช่คำสั่งรันทุกรอบ
# uv run python scripts\requeue_shortfall.py --reset-shortfalls          # ดูก่อน
# uv run python scripts\requeue_shortfall.py --reset-shortfalls --apply  # ล้างตัวนับ
# uv run python scripts\requeue_shortfall.py --apply                     # ส่งเข้าคิว

# ── listing แบบโรงแรมไม่มีไอคอนดาว -> เก็บได้ 0 (พบ 2026-09-27) ──────
# ร้านที่ Google จัดเป็น lodging ใช้ข้อความ "4/5" แทนไอคอนดาว
# โค้ดเดิมยึด aria-label "N ดาว" จึงหาการ์ดรีวิวไม่เจอเลย
# วัดจริง: โจ๊กอัมรินทร์นคร มีการ์ดรีวิว 112 ใบ แต่ star label แค่ 5 (ฮิสโตแกรม)
# ความเสียหาย 26 ร้าน = 5,650 รีวิวที่เข้าไม่ถึง
#
# แก้แล้วด้วย _extract_reviews_any() -> ทางสำรอง [data-review-id]
# เป็นทางสำรอง ไม่ใช่แทนที่ เพื่อไม่ให้ text_hash ของรีวิวเดิมเปลี่ยน
#
# 23 ใน 26 ร้านอยู่ในคิวแล้ว -> auto_refresh รอบต่อไปเก็บได้เอง
# อีก 3 ร้าน (sf=3) ต้องปลดล็อกก่อน:
# uv run python scripts\requeue_shortfall.py --reset-shortfalls --apply
# uv run python scripts\requeue_shortfall.py --apply

# ── ร้านติดวนลูปหัวคิว (พบ 2026-09-27) ───────────────────────────────
# 18 ร้านมี scraped_at NULL แต่ cnc 13-43 -> กินสล็อตทุกรอบไม่เคยสำเร็จ
# เหตุ: save_to_db upsert ด้วยชื่อจริงบนหน้าเว็บ ไม่ใช่ชื่อที่คิวขอ
#       (ขอ 'ร้านอาหารปักษ์ใต้' ไปลงร้านห่าง 8.8 กม.)
#       แถวที่ขอจึงไม่ถูกแตะ + ไม่มีตัวนับใดหยุดการวน
# ทำให้ 12 รอบติดกันได้รีวิวใหม่ 0 อัน ปิดกั้น 3,917 รีวิว
#
# แก้ต้นเหตุแล้ว 3 จุดใน scraper/scraper.py (ดู GUIDE)
# ล้างค่าที่ค้าง:
# uv run python scripts\fix_stuck_queue.py            # DRY-RUN
# uv run python scripts\fix_stuck_queue.py --apply    # ล้าง cnc เป็น 0
#
# แล้วรันต่อด้วย limit ต่ำ — ร้านที่ยังพังจะถูกนับแล้วเลิกตามเองหลัง 3 ครั้ง
# uv run python scripts\auto_refresh.py --limit 15 --wait 25
# ── deep scan ตีว่าสำเร็จทั้งที่ดึงมาได้ 2% (พบ 2026-10-01) ───────────
# เกณฑ์เดิม collected > 0 -> ดึง 10 อันจากร้านที่มี 7,028 ก็ถูกตีว่าเสร็จ
# วัดจริง: 11 จาก 164 ร้านที่ deep แล้ว ได้ไม่ถึง 50% · ปิดกั้น 5,517 รีวิว
#   พระพุทธชินราช 7,028 -> 14 (2%) · พระราชวังจันทน์ 1,424 -> 21 (2%)
# แก้แล้ว: DEEP_MIN_RATIO = 0.5 + นับ deep_attempts ให้เคสนี้ด้วย
#
# ล้างค่าที่ค้าง แล้วรัน deep ใหม่:
# uv run python scripts\fix_false_deep.py            # DRY-RUN
# uv run python scripts\fix_false_deep.py --apply    # deep_scanned_at -> NULL
# uv run python scripts\deep_scan.py --targets gap --dry-run
# uv run python scripts\deep_scan.py --targets gap

# ── วิเคราะห์ว่าร้านไหนเก็บไม่ครบเพราะอะไร ──────────────────────────
# uv run python scripts\why_incomplete.py                    # สรุปตามสาเหตุ
# uv run python scripts\why_incomplete.py --cause deep_done --list 117
# uv run python scripts\coverage_report.py --list-incomplete 30

# ── พิกัดร้านผิด: อ่าน @lat,lng = จุดกลางหน้าจอ (พบ 2026-10-01) ───────
# URL มีพิกัด 2 ชุด: @lat,lng = จุดกลางหน้าจอ · !3d!4d = พิกัดร้านจริง
# ซูมออก 7-8z -> จุดกลางหน้าจอห่างร้าน 247-500 กม. · ละติจูดตรงจึงดูเหมือนถูก
# ผล: deep scan ได้ 321 รีวิวแล้วถูกปฏิเสธว่าอยู่นอกจังหวัด + 64 ร้านพิกัดเพี้ยน
#     22 ร้านอยู่ผิดโซน (สถิติรายโซนผิดตาม)
# แก้แล้ว: extract_place_coords เอา !3d!4d ก่อน · ซูม < 15z คืน None
#
# uv run python scripts\verify_coords.py --use-api           # ตรวจ 745/771 ร้าน
# uv run python scripts\verify_coords.py --use-api --apply   # ซ่อม 64 ร้าน

# ── backfill ค้นด้วย search_query ที่ไม่ใช่ชื่อร้านนั้น ──────────────
# name 'โรงฮัก' แต่ search_query 'RongHuk' -> ค้นไม่เจอทุกครั้ง
# 23 จาก 26 ร้านที่ไม่มี place_id เข้าเคสนี้
# แก้แล้ว: name <> search_query -> ใช้ name · ทดสอบเจอ 8/8
# uv run python scripts\backfill_place_id.py --limit 30
#
# ⚠️ ร้านที่ไม่มี place_id ไม่ใช่ร้านที่ควรลบ — เป็นร้านจริงในขอบเขต
#    ลบจะเสียรีวิว 871 อัน + snapshot 13 ร้าน ใช้ scrape_excluded แทน
# uv run python scripts\exclude_places.py --exclude 1185 953 --apply

# ── ค้นด้วยชื่อพาไปผิดร้าน -> นำทางด้วย place_id (พบ 2026-10-02) ──────
# scrape_place เดิมค้น /maps/search/<ชื่อ> แล้วคลิกลิงก์ place อันแรก
# ชื่อกำกวม -> ได้รายการทั้งประเทศ -> คลิกผลแรกไปร้านอื่น
#
# วัดจริงด้วย scrape_place ตัวจริง:
#   ขอ 'OASIS CAFE'  -> ได้ 'โอเอซิส คอฟฟี่ (รางน้ำ)' กรุงเทพ (13.761, 100.537)
#   ขอ 'นัทเบเกอรี่' -> ได้ 'นัทเบเกอรี่' กรุงเทพ (13.763, 100.546) ชื่อซ้ำเป๊ะ!
#   ด้วย place_id    -> ได้ร้านพิษณุโลกถูกตัวทั้งคู่ · พิกัดห่างจากที่เก็บไว้ 0 ม.
#
# รอดมาได้เพราะ is_in_phitsanulok ปฏิเสธพิกัดกรุงเทพ
# แต่ถ้าร้านชื่อซ้ำอยู่ในพิษณุโลกเอง จะถูกบันทึกเงียบ ๆ
#
# แก้แล้ว: run_refresh / run_deep_scan โหลด place_id แล้วเปิดหน้าร้านตรง ๆ
# ดูบรรทัด "[place_id] เปิดตรงด้วย place_id N/M ร้าน" และป้าย [place_id]
#
# uv run python scripts\deep_scan.py --targets gap --limit 5

# ── แท็บรีวิวหายแบบสุ่ม -> ลองโหลดหน้าใหม่ซ้ำ (พบ 2026-10-02) ─────────
# วัดจริง: โหลดหน้าเดิม 3 รอบ -> แพตามสั่งนั่งชิว 3/3 · OASIS CAFE 3/3
#          ก.ข้าวต้มกุ๊ย 2/3  <- พลาดแบบสุ่ม
# เบราว์เซอร์ผู้ใช้ที่ล็อกอิน Google เจอเสมอ · scraper ไม่ล็อกอิน เจอบ้างไม่เจอบ้าง
# ⚠️ Escape (dismiss_login_modal) ไม่ใช่สาเหตุ — ทดสอบซ้ำแล้วผลเท่ากันทั้งสองแบบ
#
# แก้แล้ว: OPEN_TAB_RETRIES = 2 · page.goto() ใหม่ทั้งหน้า ไม่ใช่ reload
#          ได้ request ใหม่รวม 4 ครั้ง -> โอกาสสำเร็จ 91% เป็น 99%
#
# ⚠️ ยังมีคอขวดอีกชั้น: เปิดแท็บได้ 9/9 แต่ Google เสิร์ฟการ์ดมาแค่ 5 อัน
#    และ scroll ไม่โต = ถูกจำกัดอัตรา ต้องพักหรือเปลี่ยน IP
