# Phitsanulok Tourism Pain Point Analyzer

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-4169E1?style=flat&logo=postgresql&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?style=flat&logo=react&logoColor=black)
![License](https://img.shields.io/badge/License-Academic-lightgrey?style=flat)

> ระบบวิเคราะห์ Pain Point การท่องเที่ยวจังหวัดพิษณุโลก โดยดึงรีวิวจาก Google Maps วิเคราะห์ด้วย NLP และแสดงผลบน Interactive Dashboard + Map  
> **วิทยานิพนธ์ระดับปริญญาตรี — มหาวิทยาลัยนเรศวร**

---

## สารบัญ

- [ภาพรวม](#ภาพรวม)
- [Tech Stack](#tech-stack)
- [โครงสร้างโปรเจกต์](#โครงสร้างโปรเจกต์)
- [การติดตั้ง](#การติดตั้ง)
- [วิธีการใช้งาน](#วิธีการใช้งาน)
- [API Endpoints](#api-endpoints)
- [หลักการที่ใช้](#หลักการที่ใช้)
- [ข้อจำกัด](#ข้อจำกัด)
- [คำสั่งที่ใช้บ่อย](#คำสั่งที่ใช้บ่อย)

---

## ภาพรวม

```
Google Maps Reviews
       ↓  Playwright / Selenium (Phase 2)
PostgreSQL 16 + PostGIS 3.6
       ↓  WangchanBERTa + Rule-based NLP (Phase 3)
analyzed_reviews table
       ↓  FastAPI REST API (Phase 4)
React 18 Dashboard + Map (Phase 6)
```

ระบบทำงาน 3 ขั้นตอนอัตโนมัติทุกสัปดาห์ (APScheduler):

| เวลา (วันจันทร์) | Job | หน้าที่ |
|---|---|---|
| 02:00 | `weekly_discover` | ค้นหาสถานที่ท่องเที่ยวใหม่ |
| 03:00 | `weekly_refresh` | อัปเดตรีวิวจากสถานที่เดิม |
| 05:00 | `weekly_analyze` | วิเคราะห์รีวิวทั้งหมดด้วย NLP |

---

## Tech Stack

| Layer | เทคโนโลยี |
|---|---|
| Database | PostgreSQL 16 + PostGIS 3.6 |
| ORM | SQLAlchemy 2.x async + GeoAlchemy2 |
| Scraper | Playwright (primary) → Selenium undetected-chromedriver (fallback) |
| NLP | PyThaiNLP 5 + WangchanBERTa + Rule-based (9 categories) |
| API | FastAPI 0.115 + Uvicorn |
| Scheduler | APScheduler 3.10 |
| Frontend | React 18 + Vite + TailwindCSS + Recharts + Google Maps API |
| Package Manager | uv (Python), npm (Node.js) |

---

## โครงสร้างโปรเจกต์

```
phitsanulok-tourism/
├── .env                          # environment variables (ไม่ commit)
├── pyproject.toml                # Python dependencies
├── alembic.ini                   # database migration config
├── GUIDE.md                      # เอกสารนี้
│
├── db/
│   ├── models.py                 # SQLAlchemy ORM (Place, Review, AnalyzedReview, ScrapeJob)
│   ├── database.py               # async engine + session factory
│   └── migrations/versions/
│       └── 001_initial_schema.py # สร้าง 4 ตาราง + PostGIS extension
│
├── scraper/
│   ├── scraper_core.py           # Playwright scraping logic (anti-detection, scrolling)
│   └── scraper.py                # DB integration, run_discover(), run_refresh()
│
├── nlp/
│   ├── preprocessor.py           # PyThaiNLP tokenize + clean
│   ├── sentiment.py              # WangchanBERTa + Claude API fallback
│   ├── topic_model.py            # rule-based 9 pain point categories
│   └── pipeline.py               # run_analysis() orchestrator
│
├── api/
│   ├── main.py                   # FastAPI app + CORS + APScheduler lifespan
│   ├── dependencies.py           # get_db() dependency
│   ├── routers/
│   │   ├── places.py             # /api/places/*
│   │   ├── reviews.py            # /api/reviews
│   │   ├── analysis.py           # /api/insights/*
│   │   ├── stats.py              # /api/health, /api/jobs, /api/map/geojson
│   │   └── admin.py              # /api/admin/trigger/*, /api/admin/jobs/status
│   └── schemas/                  # Pydantic v2 response models
│
├── scheduler/
│   └── scheduler.py              # 3 weekly cron jobs (Mon 02/03/05:00 Bangkok)
│
└── frontend/                     # React 18 + Vite
    ├── src/
    │   ├── pages/
    │   │   ├── Dashboard.tsx     # KPIs + Charts + Review list
    │   │   └── MapView.tsx       # Google Maps + Markers + InfoWindow
    │   ├── components/           # KPICard, PainPointChart, SeverityPie, ...
    │   ├── hooks/                # usePlaces, useInsights, useReviews
    │   └── api/client.ts         # axios instance
    └── package.json
```

---

## การติดตั้ง

### ความต้องการ

| รายการ | เวอร์ชัน | หมายเหตุ |
|---|---|---|
| Python | 3.12+ | จัดการด้วย `uv` (ติดตั้งด้านล่าง) |
| PostgreSQL | 16.x | ต้องมี **PostGIS extension** ด้วย |
| Node.js | 18+ | สำหรับ React frontend |
| Google Chrome | ล่าสุด | สำหรับ Playwright (browser จะติดตั้งอัตโนมัติในขั้นที่ 6) |
| Git | ล่าสุด | สำหรับ clone repo |
| RAM | 4 GB+ | WangchanBERTa ต้องการ ~2 GB (ถ้าใช้ Claude API แทนก็ไม่ต้อง) |

### API Keys ที่ต้องเตรียม

โปรเจกต์นี้ใช้ API 3 ตัว — ใส่ในไฟล์ `.env` ก่อนรัน:

| Key | ใช้ทำอะไร | ขอที่ไหน |
|---|---|---|
| `ANTHROPIC_API_KEY` | วิเคราะห์รีวิว NLP (Claude Haiku) | [console.anthropic.com](https://console.anthropic.com) |
| `VITE_GOOGLE_MAPS_KEY` | แสดงแผนที่หน้าเว็บ — ต้องเปิด **Maps JavaScript API** ใน Google Cloud | [console.cloud.google.com](https://console.cloud.google.com) |
| `GOOGLE_PLACES_API_KEY` | สคริปต์ `fetch_hours_api.py` ดึงเวลาทำการ 7 วัน — ต้องเปิด **Places API** | เดียวกับข้างบน (ใช้คนละคีย์แนะนำ) |

> 💡 Google ให้เครดิตฟรี **$200/เดือน** และเทรียล **~฿10,000** พอเหลือ ๆ สำหรับงานนี้

---

### ขั้นตอนติดตั้ง

**1. ติดตั้ง `uv` (Python package manager)**

```powershell
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**2. Clone repo**

```bash
git clone https://github.com/<username>/phitsanulok-tourism.git
cd phitsanulok-tourism
```

> ถ้าเป็น **private repo**: `git clone https://<username>@github.com/...` แล้วใส่ **Personal Access Token** เป็นรหัสผ่าน (GitHub → Settings → Developer settings → Personal access tokens)

**3. ตั้งค่า `.env`**

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

เปิดไฟล์ `.env` แล้วใส่ค่า:
- `DATABASE_URL` และ `SYNC_DATABASE_URL` — เปลี่ยน `password` เป็นรหัส PostgreSQL ของเครื่อง
- API keys 3 ตัว (ดูตาราง "API Keys" ด้านบน) — key ไหนไม่มีปล่อยว่างได้ ฟีเจอร์ที่ต้องใช้จะปิดตัวเองแบบ graceful

**4. สร้าง Database + เปิด PostGIS**

```powershell
# Windows (PowerShell) — ปรับ path ให้ตรงเวอร์ชัน PostgreSQL ที่ติดตั้ง
$env:PGPASSWORD="postgres"
& "D:\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE phitsanulok_tourism;"
& "D:\PostgreSQL\16\bin\psql.exe" -U postgres -d phitsanulok_tourism -c "CREATE EXTENSION postgis;"
```

```bash
# macOS / Linux
createdb -U postgres phitsanulok_tourism
psql -U postgres -d phitsanulok_tourism -c "CREATE EXTENSION postgis;"
```

> ⚠️ Windows: ถ้าคำสั่ง `psql` ขึ้น "not recognized" แปลว่า PostgreSQL ยังไม่อยู่ใน PATH — ใช้ full path ตามตัวอย่าง (`D:\PostgreSQL\16\bin\...`) หรือเพิ่ม `C:\Program Files\PostgreSQL\16\bin` เข้า PATH

**5. เตรียมข้อมูลใน Database — เลือก 1 ใน 2 แบบ**

**แบบ A — Restore ข้อมูลพร้อมใช้ (แนะนำ)** ⭐ — ได้ทั้ง schema + ข้อมูลจริง ~300 ร้าน 24k รีวิว วิเคราะห์เสร็จแล้ว พร้อมเปิดใช้งานเลย

```powershell
# Windows (PowerShell)
$env:PGPASSWORD="postgres"
& "D:\PostgreSQL\16\bin\psql.exe" -U postgres -d phitsanulok_tourism -f backup\seed.sql
```

```bash
# macOS / Linux
psql -U postgres -d phitsanulok_tourism -f backup/seed.sql
```

> ไฟล์ `backup/seed.sql` มี schema + ข้อมูลครบ (dump จาก `pg_dump`) — **ไม่ต้องรัน migration หรือ scrape ใหม่**

**แบบ B — เริ่มจาก database ว่าง** (ถ้าอยาก scrape ข้อมูลเองใหม่)

```bash
uv run alembic upgrade head    # สร้างตารางเปล่าตาม schema
# แล้วค่อย scrape (ดูขั้น "เก็บข้อมูลครั้งแรก" ด้านล่าง)
```

**6. ติดตั้ง Python dependencies + Playwright browser**

```bash
uv sync                              # ติดตั้ง Python packages ทั้งหมด
uv run playwright install chromium   # ติดตั้ง Chromium สำหรับ scraper
```

**7. ติดตั้ง Frontend dependencies**

```bash
cd frontend
npm install
cd ..
```

---

### ทดสอบว่าติดตั้งสำเร็จ

เปิด 2 terminal:

**Terminal 1 — Backend API:**
```bash
uv run uvicorn api.main:app --reload --port 8000
```
→ เปิด http://localhost:8000/docs ควรเห็นหน้า Swagger

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```
→ เปิด http://localhost:5173 ควรเห็นหน้า Dashboard พร้อมข้อมูล ✅

---

### Checklist ตอนติดตั้ง

- [ ] Python 3.12+, uv, Node 18+, PostgreSQL 16+PostGIS, Git ครบ
- [ ] `.env` ใส่ API keys ครบ (อย่างน้อย `ANTHROPIC_API_KEY` + `VITE_GOOGLE_MAPS_KEY`)
- [ ] Database `phitsanulok_tourism` มี + เปิด PostGIS extension แล้ว
- [ ] Load `backup/seed.sql` เข้า DB แล้ว (แบบ A)
- [ ] `uv sync` + `uv run playwright install chromium` เสร็จ
- [ ] `npm install` ใน `frontend/` เสร็จ
- [ ] Backend (8000) + Frontend (5173) รันได้พร้อมกัน

---

### สำหรับผู้พัฒนา — อัปเดต `seed.sql` ก่อน push

ถ้ามีข้อมูลใหม่ที่อยาก share ผ่าน git ให้เครื่องอื่น clone:

```powershell
# Windows
$env:PGPASSWORD="postgres"
& "D:\PostgreSQL\16\bin\pg_dump.exe" -U postgres -d phitsanulok_tourism -f "backup\seed.sql"
git add backup/seed.sql
git commit -m "update seed data"
git push
```

> ✅ `.gitignore` ตั้งไว้ให้ commit เฉพาะ `backup/seed.sql` ไฟล์เดียว — backup อื่น ๆ (`db_backup_*.sql`) จะไม่ขึ้น git โดยอัตโนมัติ

---

### 🖥️ ติดตั้งข้ามเครื่อง (clone ไป laptop/เครื่องอื่น)

ทำตามขั้นที่ 1–7 ด้านบนก่อน แล้ว **เพิ่ม 3 เรื่องนี้** เพราะบางอย่างไม่ได้อยู่ใน git:

**1. โมเดล WangchanBERTa ไม่อยู่ใน git (ใหญ่ ~800 MB) → ต้องฝึกใหม่บนเครื่องนั้น**
```bash
# ชุดข้อมูลฝึกอยู่ใน git แล้ว (data/training/) — ฝึกใหม่ได้เลย
uv run python nlp/train/train.py --task category --epochs 10
uv run python nlp/train/train.py --task sentiment --epochs 10
```
> มี GPU (NVIDIA) → ~6 นาที/โมเดล | ไม่มี GPU (CPU) → ~50 นาที/โมเดล
> ⚠️ ถ้ายังไม่ฝึก ระบบจะใช้ rule-based/Claude แทนอัตโนมัติ (ผลด้อยกว่า)

**2. ถ้า laptop ไม่มีการ์ดจอ NVIDIA → เอา PyTorch CUDA ออก (ไม่งั้นโหลด 2.6 GB โดยเปล่าประโยชน์)**
ใน `pyproject.toml` ลบ 2 บล็อกนี้ แล้ว `uv sync` ใหม่:
```toml
[[tool.uv.index]]  ... pytorch-cu128 ...
[tool.uv.sources]  torch = { index = "pytorch-cu128" }
```
> ถ้ามี GPU NVIDIA ไม่ต้องแก้ (ใช้ได้เลย)

**3. `.env` ไม่อยู่ใน git → ก็อปจาก `.env.example` แล้วแก้:**
- รหัสผ่าน PostgreSQL (`DATABASE_URL` / `SYNC_DATABASE_URL`)
- API keys 3 ตัว
- **ลบ/คอมเมนต์บรรทัด `PLAYWRIGHT_BROWSERS_PATH` / `HF_HOME`** ถ้าเครื่องไม่มีไดรฟ์ `D:` (ค่าเริ่มต้นจะลง C: เอง)

> 💡 ตอน `uv run playwright install chromium` ครั้งแรกบนเครื่องใหม่ ต้องต่อเน็ตเพื่อโหลด Chromium (~150 MB)

---

## วิธีการใช้งาน

### รัน Backend API

```bash
# จากโฟลเดอร์ phitsanulok-tourism/
uv run uvicorn api.main:app --reload --port 8000
```

Swagger UI: **http://localhost:8000/docs**

### รัน Frontend

```bash
cd frontend
npm run dev
# เปิด http://localhost:5173
```

### เก็บข้อมูลครั้งแรก

หลังรัน backend แล้ว เปิด Swagger UI แล้วเรียกตามลำดับ:

```
1. POST /api/admin/trigger/discover  →  ค้นหาสถานที่ใหม่ (15–30 นาที)
2. POST /api/admin/trigger/refresh   →  ดึงรีวิวเพิ่มเติม (20–60 นาที)
3. POST /api/admin/trigger/analyze   →  วิเคราะห์ NLP (5–15 นาที)
```

ดูสถานะ job: `GET /api/admin/jobs/status`

---

## API Endpoints

### Places
| Method | Path | หน้าที่ |
|---|---|---|
| GET | `/api/places` | รายชื่อสถานที่ทั้งหมด |
| GET | `/api/places/{id}` | ข้อมูลสถานที่เดียว |
| GET | `/api/places/nearby?lat=&lng=&radius=` | สถานที่ในรัศมี (PostGIS) |
| GET | `/api/places/{id}/pain-points` | สรุป pain point ของสถานที่ |
| GET | `/api/places/{id}/reviews` | รีวิวของสถานที่ |

### Insights
| Method | Path | หน้าที่ |
|---|---|---|
| GET | `/api/insights/summary` | ภาพรวม KPIs + top categories |
| GET | `/api/insights/top-places` | สถานที่ที่มีปัญหามากสุด |
| GET | `/api/insights/categories` | นับรีวิวแต่ละหมวด |
| GET | `/api/insights/heatmap` | GeoJSON สำหรับ heatmap |
| GET | `/api/map/geojson` | GeoJSON FeatureCollection ทุกสถานที่ |

### Admin
| Method | Path | หน้าที่ |
|---|---|---|
| POST | `/api/admin/trigger/discover` | สั่ง scrape ทันที |
| POST | `/api/admin/trigger/refresh` | สั่ง refresh ทันที |
| POST | `/api/admin/trigger/analyze` | สั่ง analyze ทันที |
| GET | `/api/admin/jobs/status` | ดูสถานะ scheduler + ประวัติ jobs |

---

## หลักการที่ใช้

### Web Scraping
- **Playwright** ควบคุม Chromium แบบ headless ดึง DOM จาก Google Maps
- Anti-detection: สุ่ม delay (2–5 วินาที), user-agent rotation, ปิด automation flag
- **MD5 deduplication**: hash เนื้อหารีวิว → `ON CONFLICT DO NOTHING` ไม่บันทึกซ้ำ
- Fallback chain: Playwright (3 retry) → Selenium undetected-chromedriver

### Spatial Database
- **PostGIS** เก็บพิกัด GPS เป็น `GEOMETRY(POINT, 4326)` พร้อม GIST index อัตโนมัติ
- `ST_DWithin()` ค้นหาสถานที่ในรัศมี, `ST_MakePoint(lng, lat)` บันทึกพิกัด
- กรองพื้นที่พิษณุโลก: bbox lat 16.35–17.35, lng 100.05–101.2

### NLP Pipeline
ทำงาน 3 ขั้นตอนต่อเนื่อง:

```
ข้อความรีวิว
    → [A] PyThaiNLP newmm tokenize + ลบ stopword/emoji/URL
    → [B] WangchanBERTa → positive / negative / neutral
    → [C] Rule-based keyword → 1 ใน 9 หมวด pain point
    → บันทึก analyzed_reviews
```

**9 หมวด Pain Point:**

| หมวด | ตัวอย่าง keyword |
|---|---|
| การเดินทางและที่จอดรถ | จอดรถ, จราจร, ถนน |
| ความสะอาดและสิ่งแวดล้อม | สกปรก, ขยะ, กลิ่น |
| ราคาและความคุ้มค่า | แพง, ค่าเข้า, คุ้มค่า |
| การบริการและเจ้าหน้าที่ | บริการ, พนักงาน, ไม่สุภาพ |
| ความปลอดภัย | อันตราย, ลื่น, ราวจับ |
| สิ่งอำนวยความสะดวก | ที่นั่ง, ร้านอาหาร, น้ำดื่ม |
| ข้อมูลและป้ายบอกทาง | ป้าย, หลงทาง, ไม่ชัดเจน |
| ความแออัดและการจัดการ | คนเยอะ, คิวยาว, แออัด |
| พ่อค้าแม่ค้าและการรบกวน | รุม, หลอก, รบกวน |

**Fallback strategy (อัตโนมัติ):**
```
WangchanBERTa (GPU/CPU)  →  ถ้าไม่ได้
Claude Haiku API          →  ถ้าไม่มี API key
Rule-based ล้วน           →  ทำงานได้เสมอ
```

---

## ข้อจำกัด

### การเก็บข้อมูล (Scraping)
- **Google Maps ToS**: การ scrape ขัดต่อข้อกำหนดการใช้งานของ Google เหมาะสำหรับงานวิจัย/วิชาการเท่านั้น — **หน่วยงานรัฐ/เชิงพาณิชย์ควรใช้ Google Places API อย่างเป็นทางการแทน**
- **DOM เปลี่ยนได้**: Google Maps อัปเดต UI บ่อย CSS selector ที่ใช้อาจพังได้ ต้องตรวจสอบเป็นระยะ
- **Rate Limiting / บล็อก**: อาจถูก CAPTCHA หรือ block ชั่วคราวถ้า scrape เร็วเกินไป ระบบมีมาตรการ (delay 8–16 วิ/ร้าน + ตรวจจับสัญญาณบล็อกจริง + auto-pause 2→4→6 ชม.) แต่**ไม่รับประกัน 100%** — ถ้าโดนบล็อกซ้ำต้องเปลี่ยน IP (mobile hotspot/VPN)
- **วันที่รีวิวเป็นค่าโดยประมาณ**: Google ให้วันที่แบบสัมพัทธ์ ("7 เดือนที่แล้ว") ระบบคำนวณย้อนเป็นวันที่โดยประมาณ → ความละเอียดระดับ**เดือน** ไม่ใช่วัน ทำให้แยกราย**สัปดาห์**ไม่ได้ (ตาราง trend รายสัปดาห์จึงมีข้อมูลน้อย — ใช้รายเดือนแทน)
- **ภาษาไทยเป็นหลัก**: รีวิวภาษาอื่นอาจวิเคราะห์ได้ไม่แม่นยำ

### NLP / โมเดล
- **ใช้ WangchanBERTa ที่ fine-tune เอง** (Knowledge Distillation จากป้ายของ Claude) — อารมณ์ macro-F1 ≈ 0.71, หมวดหมู่ ≈ 0.60 บนชุดทดสอบสมดุล; ยังไม่สมบูรณ์แบบ โดยเฉพาะหมวดที่มีตัวอย่างฝึกน้อย (ความปลอดภัย / พ่อค้าแม่ค้า) อาจจัดผิดได้
- **Severity จาก rating**: ระดับความรุนแรง (สูง/กลาง/ต่ำ) ประเมินจากคะแนนดาวของรีวิวเชิงลบ ไม่ใช่การวิเคราะห์ความรุนแรงจากเนื้อหาโดยตรง
- **โมเดลไม่รวมใน git** (ใหญ่ ~800 MB) — ฝึกใหม่ได้ด้วย `nlp/train/train.py` (ต้องมีชุดข้อมูลฝึกใน `data/training/`)
- **รีวิวให้ดาวอย่างเดียว** (ไม่มีข้อความ) จัดหมวดไม่ได้ — คงไว้เป็น rule-based ตามเดิม

### อคติของข้อมูล (สำคัญถ้านำไปใช้ตัดสินใจ)
- ข้อมูลสะท้อนเฉพาะ**คนที่เขียนรีวิว Google** ซึ่งมักเป็นคนที่ประทับใจมากหรือไม่พอใจมาก — **ไม่ใช่ตัวแทนนักท่องเที่ยวทั้งหมด**
- การเผยแพร่ข้อมูล**รายชื่อร้าน**ที่ถูกร้องเรียน มีความเสี่ยงด้านหมิ่นประมาท (ป.อาญา ม.326/328) และ PDPA — ควรเผยแพร่แบบ**รวมกลุ่ม/ไม่ระบุชื่อร้าน** ต่อสาธารณะ, ข้อมูลรายร้านส่งให้เจ้าของร้านเท่านั้น

### ระบบ
- **ต้องรัน server ค้างไว้**: APScheduler ทำงานเฉพาะเมื่อ `uvicorn` รันอยู่ — ⚠️ มันจะ scrape + เรียก Claude อัตโนมัติทุกวันจันทร์ (02:00/03:00/05:00) ถ้าไม่ต้องการให้แก้/ปิดใน `scheduler/scheduler.py`
- **ไม่มี Authentication**: Admin endpoints ไม่มีการยืนยันตัวตน ไม่ควร expose ออก internet โดยตรง
- **พื้นที่พิษณุโลกเท่านั้น**: bounding box กำหนดตายตัว ต้องแก้โค้ดถ้าขยายพื้นที่
- **ต้องมี API keys 3 ตัว**: `VITE_GOOGLE_MAPS_KEY` (แผนที่, ต้องเปิด Maps JavaScript API), `GOOGLE_PLACES_API_KEY` (เวลาทำการ, ต้องเปิด Places API), `ANTHROPIC_API_KEY` (เฉพาะตอนสร้างชุดข้อมูลฝึกโมเดล — วิเคราะห์ปกติไม่ต้องใช้แล้ว)
- **GPU (ถ้ามี)**: ระบบใช้ GPU อัตโนมัติถ้าเจอ CUDA (ฝึก/วิเคราะห์เร็วขึ้น ~10–30 เท่า) — ตั้ง PyTorch CUDA ไว้ใน `pyproject.toml` แล้ว; เครื่องไม่มีการ์ด NVIDIA ให้ลบบล็อก `[tool.uv.sources]`/`[[tool.uv.index]]` แล้ว `uv sync` ใหม่ (จะกลับเป็น CPU)
- **Cache ลงไดรฟ์ D:**: ตั้ง env `UV_CACHE_DIR`/`HF_HOME`/`PLAYWRIGHT_BROWSERS_PATH` ฯลฯ ชี้ไป `D:\AppCache` แล้ว (กันไดรฟ์ C: เต็ม) — เครื่องใหม่ที่ไม่มีไดรฟ์ D: ต้องตั้งใหม่

---

## คำสั่งที่ใช้บ่อย

```bash
# รัน backend
uv run uvicorn api.main:app --reload --port 8000

# รัน frontend
cd frontend && npm run dev

# migration
uv run alembic upgrade head
uv run alembic history

# ทดสอบ scrape 5 สถานที่ (ไม่ผ่าน server)
uv run python -c "
import asyncio
from db.database import AsyncSessionLocal
from scraper.scraper import run_discover

async def main():
    async with AsyncSessionLocal() as s:
        print(await run_discover(s, headless=False, max_places=5))
asyncio.run(main())
"

# เพิ่ม package ใหม่
uv add <package-name>
npm install <package-name> --prefix frontend
```

---

## License

โปรเจกต์นี้จัดทำเพื่อวัตถุประสงค์ทางวิชาการ (วิทยานิพนธ์ระดับปริญญาตรี มหาวิทยาลัยนเรศวร) เท่านั้น  
ห้ามนำระบบ scraping ไปใช้เชิงพาณิชย์หรือในลักษณะที่ขัดต่อข้อกำหนดการใช้งานของ Google Maps
