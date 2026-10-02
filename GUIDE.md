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
| `GOOGLE_PLACES_API_KEY` | สคริปต์ที่เรียก **Places API** — `fetch_hours_api.py` (เวลาทำการ 7 วัน) และ `backfill_place_id.py` (เติม `google_place_id`) | เดียวกับข้างบน (ใช้คนละคีย์แนะนำ) |

> ⚠️ **เรื่องเครดิตฟรี — อย่าเชื่อตัวเลขในเอกสาร ให้ดูของบัญชีตัวเอง**
>
> เครดิตที่ Google ให้เป็น **"Free Trial" แบบก้อนเดียว (One-time) และมีวันหมดอายุ**
> ไม่ใช่วงเงินที่เติมใหม่ทุกเดือน (เอกสารฉบับก่อนเขียนว่า "$200/เดือน" ซึ่ง**ผิด**)
>
> ดูของจริงที่ **Billing → Credits** จะเห็น `Original value` / `Remaining value` /
> `Start date` / `End date` / `Type: One-time` — **วันหมดอายุสำคัญกว่าจำนวนเงิน**
> เพราะงานส่วน API ทั้งหมดต้องยิงให้เสร็จก่อนวันนั้น (ส่วนการ scrape ไม่ใช้เครดิต
> จึงทำหลังหมดอายุได้)
>
> ช่อง **Usage scope** มักเขียนว่า *"Certain usage; see the terms"* = **เครดิตไม่ครอบทุกบริการ**
> วิธีรู้แน่ว่าครอบ Places API ไหม: ยิงทดสอบน้อย ๆ (`--limit 5` ≈ ฿5) แล้วรอ ~24 ชม.
> ไปดู **Billing → Reports** กรอง service = Places API ว่ายอดถูกหักจากเครดิตหรือขึ้นเป็น cost จริง
>
> ก่อนยิงจำนวนมาก ตั้ง **Budgets & alerts** และจำกัดคีย์ที่ **Credentials → API restrictions**
> (คีย์ฝั่ง server จำกัดด้วย IP · คีย์ `VITE_GOOGLE_MAPS_KEY` ที่รันในเบราว์เซอร์จำกัดด้วย HTTP referrer)
>
> 💡 ตัวที่กินเครดิต**ต่อเนื่อง**คือ Maps JavaScript API บนหน้าเว็บ (คิดเงินทุกครั้งที่โหลดแผนที่)
> ไม่ใช่สคริปต์ Places API ซึ่งเป็นค่าใช้จ่ายครั้งเดียวจบ — ถ้าเห็นยอดขึ้นโดยไม่ได้รันสคริปต์ ให้สงสัยคีย์ฝั่ง frontend ก่อน

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
| GET | `/api/places/{id}/reviews` | ⚠️ **DEPRECATED** — ใช้ `/api/reviews?place_id=` แทน (ดูตาราง Reviews) |

### Reviews
| Method | Path | หน้าที่ |
|---|---|---|
| GET | `/api/reviews` | รายการรีวิวแบบแบ่งหน้า — **ทางเดียวที่ควรใช้** |

พารามิเตอร์ของ `/api/reviews` (ไม่ส่ง = ไม่กรอง):

| พารามิเตอร์ | ค่า | หน้าที่ |
|---|---|---|
| `place_id` | int | เฉพาะร้านเดียว (แทน `/places/{id}/reviews` เดิม) |
| `date_from` / `date_to` | `YYYY-MM-DD` | ช่วงวันที่เขียนรีวิว |
| `view_mode` | `complaints` \| `praise` \| `all` | คำบ่น / คำชม / ทั้งหมด |
| `status` | `operational` \| `closed` \| `all` | สถานะร้าน |
| `category` / `severity` | str | หมวด pain point / ระดับความรุนแรง |
| `page` / `page_size` | int | แบ่งหน้า (page_size ≤ 100) |

คืน `{total, hidden_no_text, page, page_size, items}` — `hidden_no_text` คือรีวิวที่เข้า
เงื่อนไขครบแต่ไม่มีข้อความ (ให้ดาวอย่างเดียว) ถูกซ่อนจากรายการ ใช้บอกผู้ใช้ว่าซ่อนไปกี่รายการ

> ⚠️ **อย่าใช้ `/api/places/{id}/reviews`** แม้จะดูเป็นทางการกว่า — ตัวนั้นไม่รู้จัก
> `date_from`/`date_to`/`view_mode`/`status` จึงคืนรีวิวทุกช่วงเวลาทุกอารมณ์เสมอ
> ถ้าหน้าจอกรองอยู่แล้วไปเรียกตัวนั้น ตัวเลขกับรายการจะไม่ตรงกันโดยไม่มีอะไรฟ้อง

### Insights
| Method | Path | หน้าที่ |
|---|---|---|
| GET | `/api/insights/summary` | ภาพรวม KPIs + top categories |
| GET | `/api/insights/top-places` | สถานที่ที่มีปัญหามากสุด |
| GET | `/api/insights/positive-highlights` | หมวดที่ถูกชมบ่อยสุด |
| GET | `/api/insights/zones` | สรุปแยกโซน |
| GET | `/api/insights/zones/{zone}/pain-points` · `/breakdown` | รายละเอียดต่อโซน |
| GET | `/api/insights/category-places` · `/category-reviews` | drill-down จากหมวด → ร้าน → รีวิว |
| GET | `/api/insights/trending` | ตารางแนวโน้มปัญหาแยก bucket เวลา |
| GET | `/api/insights/alerts` | แจ้งเตือนปัญหาที่เพิ่มขึ้น |
| GET | `/api/insights/categories` | นับรีวิวแต่ละหมวด (frontend ไม่ได้เรียก) |
| GET | `/api/insights/heatmap` | GeoJSON สำหรับ heatmap (frontend ไม่ได้เรียก) |
| GET | `/api/map/geojson` | GeoJSON FeatureCollection ทุกสถานที่ |
| GET | `/api/reports/months` · `/reports/download` | รายงานประจำเดือน (PDF/Word/HTML) |

**ตัวกรองช่วงเวลา** — `summary`, `top-places`, `positive-highlights`, `zones`,
`zones/{z}/*`, `category-*`, `trending`, `map/geojson`, `reviews` รับ
`date_from`/`date_to` (`YYYY-MM-DD`) ทุกตัว ไม่ส่ง = ไม่กรอง
ส่วน `map/geojson` และ `reviews` รับ `status` ด้วย (default `all` = ไม่กรอง)

> ตัวกรองทั้งหมดมาจาก `api/filters.py` แหล่งเดียว (`date_filter` / `status_filter` /
> `sentiment_filter` / `NON_PROBLEM_CATEGORIES`) — router และ `reports/report_data.py`
> import จากที่นั่น **ห้ามเขียนซ้ำ** ไม่งั้นแก้ที่เดียวแล้วอีกที่ไม่เปลี่ยน
> ตัวเลขบนแดชบอร์ดกับในรายงานจะไม่ตรงกัน

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

### การจัดหมวดสถานที่ (Place Types)

สถานที่ในระบบมีข้อมูลหมวดหมู่ **2 ชุด ที่มาจากแหล่งต่างกัน** และมีคุณภาพต่างกันมาก

| | `google_category` | `google_types` |
|---|---|---|
| ที่มา | scrape จากป้ายหมวดใต้ชื่อร้านบนหน้า Google Maps | Google Places API (`types[]`) |
| รูปแบบ | ข้อความไทยอิสระ ตามภาษาของ listing | enum อังกฤษ มีเอกสารกำกับ |
| จำนวนค่าที่พบจริง | **65 ค่า** จาก 323 ร้าน | 8 ค่าที่เราเลือกใช้ |
| ปัญหา | Google เปลี่ยนคำได้ทุกเมื่อ · มีภาษาญี่ปุ่นปน · บางแถวเป็นข้อความปุ่ม UI | คงที่ เทียบข้ามร้านได้ |

`google_category` ใช้เป็น **fallback** เมื่อร้านยังไม่มี `google_types` (ร้านที่ scrape มาก่อนจะเริ่มใช้ Places API)

#### ทำไมต้องกำหนด `type` แทนการค้นด้วยคำค้นภาษาไทย

การ discover ด้วยคำค้นอิสระ (`"คาเฟ่ ทะเลแก้ว พิษณุโลก"`) มีปัญหา 3 ข้อ:

1. **ไม่รู้ว่าครบหรือไม่ครบ** — คำค้นให้ผลตามอัลกอริทึมจัดอันดับของ Google ไม่ใช่ตามพื้นที่ จึงบอกไม่ได้ว่า "ค้นแล้วหมดแล้ว" หรือ "ยังเหลือ"
2. **ทำซ้ำไม่ได้** — ผลของคำค้นเดียวกันเปลี่ยนตามเวลา/ตำแหน่ง/ประวัติการใช้งาน เขียนในบทวิธีวิจัยว่า "ค้นด้วยคำนี้" แล้วคนอื่นทำซ้ำไม่ได้ผลเท่ากัน
3. **หมวดปนกัน** — คำว่า "คาเฟ่" จับได้ทั้งร้านกาแฟ ร้านขนม และร้านอาหารที่ตั้งชื่อว่าคาเฟ่

การค้นด้วย `type` + จุดศูนย์กลาง + รัศมี ให้ผลที่ **ทำซ้ำได้** และ **บอกขอบเขตได้ชัด** — อ้างในบทวิธีวิจัยได้ว่าเก็บ type อะไร ในพื้นที่ใด รัศมีเท่าไร

#### 7 `type` ที่ใช้ และเหตุผล

ตัวเลขคือ **ข้อมูลที่เก็บได้แล้ว** (323 ร้าน / 38,029 รีวิว) จัดกลุ่มตาม type ที่จะใช้

| `type` | ร้าน | รีวิว | ทำไมต้องมี |
|---|---:|---:|---|
| `cafe` | 120 | 9,123 | กลุ่มใหญ่สุดของข้อมูล เป็นพื้นที่หลักที่นักศึกษา/นักท่องเที่ยวใช้จริง |
| `restaurant` | 93 | 14,896 | **รีวิวมากที่สุด** และเป็นกลุ่มที่ pain point เรื่องบริการ/ราคา/ความสะอาดชัดที่สุด |
| `tourist_attraction` | 38 | 3,606 | แกนกลางของคำถามวิจัยเรื่องการท่องเที่ยว |
| `park` | 11 | 3,449 | รวมอุทยานแห่งชาติ + สวนสาธารณะ — pain point เรื่องสิ่งอำนวยความสะดวก/ความปลอดภัยเด่น |
| `museum` | 5 | 1,794 | รีวิวต่อร้านสูง (เฉลี่ย 359) แม้จำนวนร้านน้อย |
| `university` | 18 | 1,270 | 2 ใน 3 โซนศึกษาคือย่านมหาวิทยาลัย ตัวมหาวิทยาลัยเองเป็นสถานที่ที่ถูกรีวิว |
| `bakery` | 2 | 320 | แยกจาก `cafe` เพราะ Google แยก — ถ้าไม่ระบุจะค้นไม่เจอร้านขนมล้วน |
| **รวม (7 type)** | **287** | **34,458** | |

#### แต่ละ `type` ครอบ `google_category` อะไร

ตรวจสอบจากข้อมูลจริงทั้ง 65 ค่า:

**`cafe`** — ร้านกาแฟ (116) · ชาไข่มุก (2) · คาเฟ่แมว (1) · `コーヒーショップ・喫茶店` (1)

**`restaurant`** — ร้านอาหาร (59) · **ภัตตาคารอาหาร**ไทย (12) / จีน (2) / บุฟเฟต์ (2) / เช้า (1) / ติ่มซำ (1) / เช้าและกลางวัน (1) / ญี่ปุ่น (1) / เกาหลี (1) / ประเภทไก่ (1) · ร้านก๋วยเตี๋ยว (2) · ร้านอาหารครอบครัว (2) · อาหารฟาสต์ฟูด (2) · ร้านบาร์บีคิว (1) · ร้านสเต็ก (1) · โรงอาหาร (1) · ร้านอาหารเมนูเนื้อ (1) · ครัวซุป (1) · `レストラン` (1)

**`tourist_attraction`** — สถานที่ท่องเที่ยว (27) · สถานที่สำคัญทางประวัติศาสตร์ (3) · ตลาดกลางคืน (2) · ตลาดนัด (1) · ตลาด (1) · สวนน้ำ (1) · กรมส่งเสริมการท่องเที่ยวในท้องถิ่น (1) · บริษัทท่องเที่ยว (1) · ตัวแทนท่องเที่ยวเข้าชมสถานที่ (1)

**`park`** — อุทยานแห่งชาติ (3) · สวนสาธารณะ (3) · อุทยาน (3) · สวนสาธารณะของเมือง (1) · สวน (1)

**`museum`** — พิพิธภัณฑ์ (4) · พิพิธภัณฑ์ประวัติศาสตร์ท้องถิ่น (1)

**`university`** — มหาวิทยาลัย (7) · มหาวิทยาลัยรัฐ (4) · ฝ่ายวิชาการ (2) · ห้องสมุดมหาวิทยาลัย (1) · คณะนิติศาสตร์ (1) · คณะวิทยาศาสตร์ (1) · สถาบันการศึกษา (1) · ศูนย์การเรียนรู้ (1)

**`bakery`** — ร้านเบเกอรี่ (1) · ร้านขนมหวาน (1)

#### สิ่งที่ 7 type นี้ "ไม่" ครอบ — และทำไมถึงถูกต้อง

**15 ร้าน / 1,094 รีวิว** อยู่นอกทุก type:

ร้านกล้องถ่ายรูป (3) · สตูดิโอถ่ายภาพ (2) · นักพัฒนาอสังหาริมทรัพย์ (2) · ร้านเฟอร์นิเจอร์ (1, **696 รีวิว**) · ศูนย์กีฬา (1) · ศูนย์ประชุม (1) · สนามกีฬา (1) · ร้านกรอบรูป (1) · รัฐบาล (1) · ที่พัก (1) · โรงเรียนมัธยมศึกษา (1)

พวกนี้**ไม่ใช่สถานที่ท่องเที่ยว** — ร้านเฟอร์นิเจอร์กับสำนักงานอสังหาฯ หลุดเข้ามาเพราะคำค้นภาษาไทยจับพลาด ฉะนั้นรายการ type **ทำหน้าที่เป็นตัวกรองความเกี่ยวข้องไปด้วย** ไม่ใช่แค่ตัวจัดกลุ่ม

⚠️ อีก **4 ร้าน** มี `google_category` เป็นข้อความปุ่มบนหน้าเว็บ ไม่ใช่หมวดจริง:
`เพิ่มเว็บไซต์` (3 ร้าน) · `เพิ่มเวลาทำการ` (1 ร้าน) — ทั้ง 4 ร้านมี 0 รีวิว เป็นบั๊กของ selector ตอน scrape หมวด ปัญหานี้หายไปเองเมื่อใช้ `google_types` เพราะ API ไม่มีค่าเหล่านี้

และ **6 ร้าน** ไม่มี `google_category` เลย (73 รีวิว)

#### ⚠️ ก่อนเพิ่ม `type` ใหม่ ต้องเช็ค Table 1 / Table 2 ก่อนเสมอ

เอกสาร Google แบ่ง type เป็นสองตาราง และ**ความต่างนี้ไม่มีอะไรฟ้องตอนรัน**:

| | ใช้กรองการค้นหา | ตัวอย่าง |
|---|---|---|
| **Table 1** | ✅ ได้ | `cafe` `restaurant` `bakery` `tourist_attraction` `museum` `park` `university` `church` `hindu_temple` `mosque` `synagogue` |
| **Table 2** | ❌ ไม่ได้ (คืนมาได้เท่านั้น) | `place_of_worship` `food` `point_of_interest` `establishment` `health` `finance` |

ถ้าส่ง type จาก Table 2 ไปเป็นพารามิเตอร์ `type` **Google จะเพิกเฉยเงียบ ๆ**
ไม่มี error ไม่มีคำเตือน แล้วคืน**ทุก establishment ในรัศมี**มาให้

**เคยเกิดขึ้นจริง (ค่าเสียหาย ~$4.65):**

เราใส่ `place_of_worship` เพราะวัดคือแหล่งท่องเที่ยวหลักของพิษณุโลก ยิงไป 82 เซลล์
ได้ผล 2,878 รายการ แต่เป็นศาสนสถานจริง **43 รายการ (1%)** ที่เหลือคือ:

```
1,286  point_of_interest,establishment  (ไม่มีหมวดเฉพาะ)
  215  lodging          โรงแรม/ที่พัก
  178  store            ร้านค้า
  108  car_repair       อู่ซ่อมรถ
   58  atm,finance      ตู้เอทีเอ็ม
   38  gas_station      ปั๊มน้ำมัน
```

และเพราะมันนับทุกธุรกิจ จึง**ชนเพดาน 60 ถึง 52 จาก 82 เซลล์ (63%)** สูงสุดของทุก type
เทียบกับ 7 type จาก Table 1 ที่ตรง **100% ทุกตัว**

**วิธีป้องกันที่ใส่ไว้ในโค้ดแล้ว 3 ชั้น:**
1. `UNSEARCHABLE_TYPES` ใน `scripts/discover_api.py` — ปฏิเสธก่อนยิงคำขอแรก
2. ตัวเฝ้าระวังตอนรัน — นับว่าผลที่ได้มี type ที่ขอจริงกี่ % เมื่อเก็บตัวอย่างครบ 20 รายการ
   แล้วอัตราต่ำกว่า 50% จะ**หยุด type นั้นทันที** และข้ามเซลล์ที่เหลือ
3. `--verify-types` — ตรวจย้อนหลังจากคอลัมน์ `discover_cells.type_matched`

**เรื่องวัดไทย**: Table 1 มีแค่ `church` / `hindu_temple` / `mosque` / `synagogue`
— **ไม่มี `buddhist_temple`** ฉะนั้น Nearby Search หาวัดด้วย `type` ไม่ได้ในทางโครงสร้าง
ถ้าต้องการวัดเพิ่มต้องใช้ **Text Search** (`textsearch?query=วัด`) ซึ่งเป็น endpoint คนละตัว
(ปัจจุบันมีวัดใน `places` 9 แห่ง + ได้ศาสนสถานมาโดยบังเอิญอีก 45 แห่ง ผ่านเกณฑ์ 22 แห่ง)

#### ซอยเซลล์ที่ชนเพดาน — `--subdivide-capped`

เซลล์ที่ได้ครบ 60 ผล = ข้อมูล**ขาด** ต้องค้นซ้ำด้วยวงเล็กลง แต่**ไม่ต้อง discover ใหม่ทั้งหมด**

```bash
uv run python scripts/discover_api.py --subdivide-capped        # DRY-RUN: นับงาน + ราคา
uv run python scripts/discover_api.py --subdivide-capped --run  # ยิงจริง
```

โหมดนี้อ่านเซลล์ที่ `hit_cap = true` จาก `discover_cells` แล้วซอยเฉพาะคู่
**(เซลล์, type)** ที่ข้อมูลขาดจริง เป็นวงรัศมีครึ่งหนึ่งของเซลล์แม่

**ทำไมต้องเจาะจง ไม่ใช่ `--cell-radius 0.5` ทั้งกระดาน:**

| วิธี | งาน | ค่าใช้จ่าย |
|---|---|---|
| `--cell-radius 0.5` (ซอยทั้ง 83 เซลล์ × 7 type) | 2,208 | **~$72** |
| `--subdivide-capped` (เฉพาะคู่ที่ขาด) | 223 | **~$6–17** |

เซลล์ที่ได้ 3 ผลไม่มีเหตุให้ซอย และเซลล์ที่ชนเพดานเฉพาะ `restaurant`
ก็ไม่ต้องซอยให้ `museum` ด้วย

โหมดนี้**ข้าม type ที่ Google เพิกเฉย**อัตโนมัติ (ทั้งจาก `UNSEARCHABLE_TYPES`
และจาก `type_matched` ที่วัดได้) เพราะซอยแล้วจะยิ่งได้ของนอกเรื่องเพิ่ม ไม่ได้ของที่ต้องการ
— เฉพาะการข้าม `place_of_worship` 52 เซลล์ ประหยัดไป **~$18**

รองรับ**หลายชั้น**: เซลล์ 0.5 กม. ที่ยังชนเพดานอีก รันซ้ำจะได้ลูก 0.25 กม.
(แต่ละแถวจำ `cell_radius_m` ของตัวเอง จึงหารสองจากค่าจริง ไม่ใช่ค่าคงที่)

⚠️ เซลล์ย่อยต้องปู**แลตทิซเดียวต่อ (type, ขนาดแม่)** ไม่ใช่ปูแยกทีละเซลล์แม่ —
เซลล์ที่ชนเพดานมักอยู่ติดกันเป็นผืน ถ้าปูแยกจะเยื้องกันจนทับซ้อนแต่ตัดซ้ำไม่ได้
(วัดแล้ว: 375 เซลล์ → 223 เซลล์ ประหยัด 40%)

#### ข้อควรระวังเมื่อใช้ `type` ค้นหา

- **Places API คืนได้สูงสุด 60 ผล/คำขอ** (20 × 3 หน้า) ถ้าเซลล์ไหนได้ครบ 60 พอดี = **น่าจะถูกตัด** ต้องซอยเซลล์ย่อยลงอีก สคริปต์ต้อง log จำนวนผลทุกเซลล์เพื่อจับกรณีนี้
- **ค่าใช้จ่ายคือ จำนวนเซลล์ × จำนวน type** — เพิ่ม type 1 ตัวคือเพิ่มคำขอเท่ากับจำนวนเซลล์ทั้งหมด
- ร้านหนึ่งมี `types[]` ได้หลายค่า (เช่น `["cafe","bakery","food","point_of_interest"]`) จึงอาจถูกคืนซ้ำจากหลาย type — กันซ้ำด้วย `google_place_id` เสมอ
- `type` ทั่วไปอย่าง `food`, `point_of_interest`, `establishment` **ห้ามใช้ค้นหา** เพราะกว้างจนชนเพดาน 60 ผลทุกเซลล์

### ข้อมูลจาก Google Places API

ตาราง `places` มีคอลัมน์ 2 ชุดที่มาจากคนละแหล่ง และ**ไม่ทับกันโดยเจตนา**

| มาจาก scrape (Playwright) | มาจาก Places API (migration 012) |
|---|---|
| `overall_rating` | `google_rating` |
| `google_category` | `google_types` |
| `opening_hours` · `business_status` · `price_level` | — (API เขียนเฉพาะตอน discover ร้านใหม่) |
| `location` · `name` | — (เก็บเป็นข้อมูลรายงาน ไม่ทับของเดิม) |

เก็บทั้งสองชุดเพราะ (ก) เทียบได้ว่าค่าที่ scrape มาเพี้ยนไหม (ข) ไม่ทำลายข้อมูลที่ใช้ในรายงานที่ออกไปแล้ว

#### 7 คอลัมน์ที่เพิ่มใน migration 012

| คอลัมน์ | ชนิด | ความหมาย |
|---|---|---|
| `google_place_id` | `varchar(64)` UNIQUE | กุญแจถาวรของสถานที่บน Google — ฟิลด์เดียวในชุดนี้ที่เงื่อนไข Google ให้เก็บได้ไม่จำกัดเวลา |
| `google_types` | `text` | `types[]` เก็บเป็น CSV เช่น `cafe,bakery,food` |
| `formatted_address` | `text` | ที่อยู่เต็มจาก API |
| `google_rating` | `numeric(2,1)` | เรตติ้งจาก API (แยกจาก `overall_rating`) |
| `google_reviews_total` | `integer` | **จำนวนรีวิวที่ Google มี** — ⚠️ อ่านคำเตือนด้านล่างก่อนใช้ |
| `api_fetched_at` | `timestamptz` | ดึงมาเมื่อไร — ใช้ทั้งในบทวิธีวิจัยและตรวจว่าข้อมูลเก่าแค่ไหน |
| `discovered_by` | `varchar(20)` | `'scrape'` = มาจาก Playwright · `'api'` = ค้นเจอด้วย Places API |

`google_place_id` เป็น UNIQUE เพราะตาราง `places` ใช้ `name` เป็นกุญแจ (UNIQUE) ซึ่ง
**จับกรณีร้านเดียวกันถูกบันทึกสองแถวด้วยชื่อต่างกันไม่ได้** — UNIQUE บน `place_id`
ทำให้กรณีนั้นโผล่มาให้เห็นแทนที่จะเงียบ

#### ⚠️ `google_reviews_total` — ห้ามใช้เป็นตัวส่วนของอัตราส่วน

มันคือจำนวนรีวิวที่ Google **มี** ไม่ใช่จำนวนที่เรา **เก็บได้**

ตัวเศษของทุกอัตราในระบบนี้มาจากตาราง `reviews` ที่ผ่านตัวกรองชุดหนึ่ง
(ช่วงวันที่ + สถานะร้าน + `text_clean <> ''` + มีแถวใน `analyzed_reviews`)
การเอาตัวส่วนที่**ไม่**ผ่านตัวกรองชุดเดียวกันมาใช้ผิดกฎข้อ 1 ของโปรเจกต์
และจะทำให้ทุกเปอร์เซ็นต์บนหน้าเว็บและในรายงานต่ำกว่าความจริงโดยไม่มีอะไรฟ้อง

**ใช้ได้ทางเดียว** — เป็นตัวส่วนของเมตริกคนละตัวคือ *ความครบถ้วนของการเก็บข้อมูล*:

```
เก็บได้ / google_reviews_total  =  เก็บรีวิวได้กี่ % ของที่มีอยู่จริง
```

ซึ่งเป็นตัวเลขที่บทวิธีวิจัยควรมี (ตอบว่า "ข้อมูลที่ใช้วิเคราะห์ครอบคลุมแค่ไหน")
และต้องเขียนกำกับให้ชัดว่าเป็นอัตราอะไร ไม่ใช่เอาไปปนกับอัตราปัญหา

#### เติมข้อมูลให้ร้านที่มีอยู่แล้ว — `backfill_place_id.py`

```bash
uv run python scripts/backfill_place_id.py                # DRY-RUN: นับ + ประเมินราคา (ไม่ยิง API)
uv run python scripts/backfill_place_id.py --report       # อ่านอย่างเดียว: ตารางจุดตรวจ 4 ข้อ
uv run python scripts/backfill_place_id.py --limit 5      # ยิงจริง 5 ร้าน (ทดสอบก่อนเสมอ)
uv run python scripts/backfill_place_id.py --all          # ยิงทุกร้านที่ยังไม่มี place_id
uv run python scripts/backfill_place_id.py --all --force  # ยิงซ้ำรวมร้านที่มีแล้ว
uv run python scripts/backfill_place_id.py --all --max-requests 100   # เพดานแข็ง
```

**สคริปต์นี้ `UPDATE` ได้แค่ 7 คอลัมน์ข้างบน** — `name` / `location` /
`overall_rating` / `opening_hours` / `business_status` / `zone` / `scraped_at` /
`deep_*` ไม่อยู่ในคำสั่ง `UPDATE` เลย จึงทำข้อมูลเดิมเสียหายไม่ได้ในทางโครงสร้าง

`--limit 5` ตอบ 2 คำถามในคราวเดียวด้วยเงินไม่ถึง 10 บาท:
1. Find Place รับ `fields` ชุดเต็มได้ไหม (1 คำขอ/ร้าน) หรือต้องถอยไปใช้ Details (2 คำขอ/ร้าน) — สคริปต์รายงานเส้นทางที่ใช้จริง
2. เครดิตทดลองใช้ครอบ Places API ไหม (ดู Billing → Reports หลังรัน ~24 ชม.)

**ตารางจุดตรวจ 4 ข้อ** จาก `--report`:

| # | วัดอะไร | อ่านผลยังไง |
|---|---|---|
| 1 | จับคู่ได้ / ไม่พบ | "ไม่พบ" เยอะ = ชื่อใน DB เพี้ยนจากของจริงบน Google |
| 2 | `place_id` ซ้ำ | > 0 = มีร้านซ้ำใน DB อยู่แล้ว รีวิวถูกแยกคนละแถว |
| 3 | พิกัด API ห่างจากของเรา > 200 ม. | เยอะ = `locationbias` หลวมเกิน จับผิดร้าน |
| 4 | `google_reviews_total` เทียบจำนวนที่เก็บได้ | ได้อัตรา yield จริง → ใช้ตั้งเกณฑ์คัดร้านใหม่แทนการเดา |

### ค้นหาร้านใหม่ด้วย Places API (discover)

มีสองวิธี **ทั้งคู่ยังใช้ได้ ไม่ได้แทนกัน**

| | `discover_by_zone.py` (เดิม) | `discover_api.py` (ใหม่) |
|---|---|---|
| วิธีค้น | คำค้นภาษาไทยบน Google Maps ผ่าน Playwright | `type` + จุดศูนย์กลาง + รัศมี ผ่าน Places API |
| ทำซ้ำได้ | ❌ ผลเปลี่ยนตามเวลา/ตำแหน่ง/ประวัติการใช้งาน | ✅ พารามิเตอร์เดียวกัน = ผลเดียวกัน |
| รู้ว่าครบหรือยัง | ❌ บอกไม่ได้ | ✅ ถ้าไม่มีเซลล์ไหนชนเพดาน 60 = ครบในพื้นที่นั้น |
| ค่าใช้จ่าย | ฟรี (แต่เสี่ยงถูกบล็อก) | เสียเงินต่อคำขอ |
| เก็บรีวิวด้วย | ได้ (`DISCOVER_MAX_REVIEWS`) | ไม่ได้ — คนละงาน ต้อง refresh/deep ต่อ |

#### "รัศมีค้นหา" ไม่ใช่ "รัศมีโซน" — สองค่าที่ไม่เกี่ยวกัน

```
รัศมีโซน    2.0 กม.  →  assign_zone()  →  ทุกหน้าที่แยกตามโซน   [ตรึงไว้ ห้ามแตะ]
รัศมีค้นหา  4.0 กม.  →  discover_api.py เท่านั้น ไม่มีใครอื่นอ่าน  [ของใหม่]
```

ค้นกว้างกว่าโซนเพราะถ้าค้นแค่ 2 กม. **จะไม่มีวันรู้ว่าขยายโซนแล้วจะได้ร้านเพิ่มไหม**
ร้านที่เจอในระยะ 2–4 กม. จะได้ `zone='other'` ตามกฎเดิมอย่างถูกต้อง แต่เก็บ
`nearest_zone` + `dist_km` ไว้ด้วย → ได้ "ตารางวงแหวน" ที่ตอบคำถามเรื่องรัศมี
**โดยยังไม่ต้องเปลี่ยนนิยามโซน** (ตัวเลขในรายงานเก่าจึงไม่ขยับ)

#### ตารางพัก — ผลไม่ไหลเข้า `places` ตรง ๆ

| ตาราง | หน้าที่ |
|---|---|
| `place_candidates` | ร้านที่ค้นเจอ (PK = `google_place_id` กันซ้ำอัตโนมัติ) พร้อม `decision` = `new` / `existing` |
| `discover_cells` | log ทุก (เซลล์ × type) ที่ยิง: `pages`, `results`, `hit_cap`, `status` |

**เหตุผล 3 ข้อ:**
1. **resume ได้** — `discover_cells` จำว่าเซลล์ไหนทำแล้ว รันซ้ำจะข้ามให้เอง ถ้าพังกลางทางหรือชนเพดานงบ **ไม่ต้องจ่ายค่าเซลล์เดิมอีก**
2. **มีด่านให้คนดูก่อน** — ข้อมูลดิบจาก Google ไม่ไหลเข้าฐานวิทยานิพนธ์ทันที
3. **วัดปัญหาชื่อซ้ำได้ก่อนเสี่ยง** — `places.name` เป็น UNIQUE ถ้าเขียนเข้า `places` ตรง ๆ แล้ว Google คืนร้านชื่อซ้ำ จะยุบเป็นแถวเดียว รีวิวปนกันเงียบ ๆ

#### เพดาน 60 ผล — เรื่องที่ต้องเข้าใจก่อนเชื่อผล

Nearby Search คืนได้สูงสุด **60 รายการต่อคำขอ** (20 × 3 หน้า) และ **API ไม่บอกว่าจริง ๆ มีเท่าไร**

ฉะนั้นเซลล์ที่ได้ครบ 60 พอดี = **ข้อมูลขาด ไม่ใช่ครบ** สคริปต์บันทึก `hit_cap = true`
ไว้ และ `--report` จะเตือนพร้อมรายชื่อเซลล์ แก้ด้วยการซอยเซลล์ย่อย:

```bash
uv run python scripts/discover_api.py --run --cell-radius 0.5
```

เซลล์ 0.5 กม. เป็นชุดคนละขนาด (`cell_radius_m` ต่างกัน) จึงไม่ถูกข้ามด้วย resume

#### การปูเซลล์ — ทำไมต้องคำนวณ ไม่ใช่กะ

`scraper/grid.py` ปูวงกลมเล็กบนแลตทิซหกเหลี่ยม ระยะเพื่อนบ้าน `s = r√3`
(หลวมที่สุดที่ยังคลุมครบ) รัศมีค้น 4 กม. + เซลล์ 1 กม. → **83 เซลล์** สำหรับ 3 โซน

⚠️ **สองบั๊กที่เคยเขียนผิด — บันทึกไว้เพื่อไม่ให้ทำซ้ำ:**

1. **ขอบพื้นที่ต้องเผื่อเต็มรัศมีเซลล์ ไม่ใช่ครึ่ง** — จุดที่ขอบ (ระยะ R) อาจต้อง
   ใช้เซลล์ที่ศูนย์กลางห่างออกไปถึง `r` คือที่ระยะ `R+r` ถ้ากรองทิ้งที่ `R+r/2`
   ขอบจะมีรูโหว่ แล้วเราจะเชื่อผิดว่า "ค้นครบแล้ว" — **แย่กว่ารู้ว่าขาด**
2. **หลายโซนต้องใช้แลตทิซอันเดียว** ไม่ใช่สร้างแยกโซนแล้วมาตัดที่ซ้ำ เพราะแลตทิซ
   จากคนละจุดศูนย์กลางไม่เรียงตรงกัน เซลล์ในเขตทับซ้อนเยื้องกันจนตัดซ้ำไม่ได้
   (วัดแล้วตัดได้ **0 เซลล์** = จ่ายเงินซ้ำฟรี) ปูแลตทิซเดียวได้ 83 เซลล์
   แทน 93 เซลล์ (ประหยัด 11%) และผลเป็น deterministic

`grid.covers()` มีไว้พิสูจน์ว่าไม่มีรูโหว่ — ทดสอบด้วยการสุ่ม 3,000 จุดต่อโซน
บวกจุดบนเส้นรอบวงทุก 1 องศา

#### คำสั่ง

```bash
uv run python scripts/discover_api.py                    # DRY-RUN: นับเซลล์ + ประเมินราคา (ไม่ยิง API)
uv run python scripts/discover_api.py --report           # อ่านอย่างเดียว: สรุปผล + ตารางวงแหวน
uv run python scripts/discover_api.py --run --types cafe # type เดียว 83 คำขอ — วัดอัตราหน้า/เซลล์จริงก่อน
uv run python scripts/discover_api.py --run --max-requests 40   # ยิงจริงแบบจำกัดวงเงิน
uv run python scripts/discover_api.py --run --zones rajabhat    # เฉพาะโซนเดียว
uv run python scripts/discover_api.py --run                     # ทุกเซลล์ที่ยังไม่เคยทำ
uv run python scripts/discover_api.py --verify-types            # ตรวจว่า Google เคารพ type ไหม (ไม่ยิง API)
uv run python scripts/discover_api.py --subdivide-capped        # DRY-RUN: ซอยเฉพาะเซลล์ที่ชนเพดาน
uv run python scripts/discover_api.py --subdivide-capped --run  # ยิงจริง (ถูกกว่า --cell-radius 0.5 ~7 เท่า)
```

**ค่าใช้จ่ายประเมิน**: 664 งาน (83 เซลล์ × 8 type) → **664–1,992 คำขอ ≈ $17–50**
ช่วงกว้างเพราะเซลล์ที่มีร้านเกิน 20 ต้องยิงหน้าถัดไป (1–3 คำขอต่อเซลล์)

**แนะนำ**: รัน `--types cafe` ก่อน (83 คำขอ ~$2) เพื่อวัดอัตราหน้าต่อเซลล์จริง
แล้วคูณกลับจะประเมินค่าใช้จ่ายทั้งงานได้แม่น ดีกว่าเดาจากช่วง $17–50

### เลื่อนร้านจากตารางพักเข้าระบบ — `promote_candidates.py`

ร้านในตาราง `place_candidates` **ไม่มีใครในระบบอ่านเลย** — หน้าเว็บ, API, scraper,
รายงาน ทั้งหมดอ่านจาก `places` ตารางพักเป็นบันทึกการสำรวจ ยังไม่ใช่ข้อมูลของระบบ

```
place_candidates ──[promote_candidates.py]──> places ──> auto_refresh ──> reviews ──> NLP ──> เว็บ
   บันทึกสำรวจ           เฉพาะที่ผ่านเกณฑ์        กลุ่มตัวอย่างที่ศึกษา
```

#### ⚠️ ห้ามเลื่อนร้านที่ไม่ผ่านเกณฑ์เข้า `places`

`scraper/scraper.py` เลือกคิว refresh ด้วย
```sql
WHERE scraped_at IS NULL OR ... ORDER BY scraped_at ASC NULLS FIRST
```

แถวใหม่ที่ `scraped_at` เป็น NULL จึง**ขึ้นหัวคิวทันที** ถ้าเลื่อนผู้สมัครทั้งหมดเข้าไป
`auto_refresh` จะไล่ scrape ทุกแถว — ส่วนใหญ่เป็นร้านที่ Google เองมี 0 รีวิว
เสียเวลาหลายสิบชั่วโมงและดันร้านที่ควรเก็บไปท้ายคิว

และ `places` ถูกใช้นับสถิติบนหน้าเว็บ/รายงาน เพิ่มจำนวนแถวหลายเท่าโดยส่วนใหญ่
ไม่มีรีวิว จะทำให้ทุกตัวส่วนเปลี่ยนความหมาย (ผิดหลักเดียวกับกฎ "ตัวเศษกับตัวส่วน
ต้องผ่านตัวกรองชุดเดียวกัน")

#### เกณฑ์คัดเลือก 3 ข้อ

1. `decision = 'new'` — ยังไม่ถูกเลื่อนและไม่ถูกคัดออก
2. `google_reviews_total >= 50`
3. เป็นประเภทที่สนใจ และไม่ใช่เชน/ห้าง/โรงแรม

**ที่มาของเลข 50** — วัดจากข้อมูลจริง: รีวิวเชิงลบมี **2,405 จาก 38,029 = 6%**

| Google มี | คาดว่าได้คำบ่นที่วิเคราะห์ได้ |
|---|---|
| 13 รีวิว | ~1 อัน |
| **50 รีวิว** | **~3 อัน** |
| 100 รีวิว | ~6 อัน |
| 200 รีวิว | ~12 อัน |

เกณฑ์ 50 พอสำหรับวิเคราะห์**ภาพรวม** (รวมเป็นหมวด/โซน) แต่**ไม่พอสำหรับสรุปรายร้าน**
— ห้ามเขียนว่า "ร้าน X มีปัญหาเรื่อง Y" จากคำบ่น 3 อัน

#### ⚠️ 2 บทเรียนในการเขียนตัวกรอง

**① ใช้ `google_types` (ตัวตนจริง) ไม่ใช่ `source_type` (วิธีที่ค้นเจอ)**

เพราะการค้นด้วย `place_of_worship` ถูก Google เพิกเฉยแล้วคืนทุกอย่างในรัศมีมาให้
ถ้ากรองด้วย `source_type` จะทิ้ง**วัดจริง 4 แห่ง** (วัดคูหาสวรรค์ 252 รีวิว,
วัดเด่นโบสถ์โพธิ์งาม, วัดสะกัดน้ำมัน, วัดสระสี่เหลี่ยม) ที่เผอิญถูกคืนจากคำค้นนั้น
รวมถึงหอประชุมศรีวชิรโชติ (261) และ มทร.ล้านนา พิษณุโลก (54) ซึ่งเป็น `university`

**② ตัดโรงแรม/ห้างเฉพาะที่เป็น "ล้วน"**

Google ติด type `restaurant` ให้โรงแรมที่มีห้องอาหาร ถ้าตัดทุกอย่างที่มี `lodging`
จะตัดร้านอาหารที่ตั้งอยู่ในโรงแรม/ข้างซูเปอร์ทิ้งไปด้วย เกณฑ์จึงเป็น
"มี `lodging`/`shopping_mall`/`supermarket` **และไม่มี** `restaurant`/`cafe`"
ส่วนโรงแรมที่มีห้องอาหารดักด้วยคำในชื่อ (`โรงแรม`, `hotel`, `resort`, ...)

**③ ความรู้ท้องถิ่นที่ `google_types` บอกไม่ได้ → `MANUAL_REJECT`**

บางที่เป็นโรงแรมแต่ Google ให้ `lodging,restaurant,food` เหมือนร้านอาหารในโรงแรมเป๊ะ
แยกด้วยกฎอัตโนมัติไม่ได้ ใส่ `google_place_id` ใน `MANUAL_REJECT` พร้อมเหตุผล
แล้วรัน `--reject-list` เพื่อตั้งธง `decision='reject'`

ใช้ `google_place_id` ไม่ใช่ชื่อ เพราะชื่อบน Google เปลี่ยนได้ และ `ON CONFLICT`
ของ `discover_api.py` **ไม่ทับคอลัมน์ `decision`** → ธงที่ตั้งด้วยมืออยู่ถาวร
แม้รัน discover ซ้ำ

**④ ตัวกรองต้องระบุ alias ทุกคอลัมน์**

`place_candidates` กับ `places` มีคอลัมน์ชื่อซ้ำกันหลายตัว (`name`, `google_types`,
`google_reviews_total`, `formatted_address`) พอ JOIN สองตารางแล้วใช้ชื่อเปล่า
Postgres จะตอบ `AmbiguousColumnError` ทันที — จึงเขียนเป็นฟังก์ชัน
`keep_sql(alias)` ไม่ใช่สตริงคงที่

#### การชนชื่อ — `places.name` เป็น UNIQUE

ความเสี่ยงที่เฝ้าระวังมาตั้งแต่ migration 012 **วัดแล้วชนแค่ 1 ร้าน** และเป็น
ร้านเดียวกันจริง ไม่ต้องรื้อโครงสร้างอะไร สคริปต์จัดการ 3 กรณี:

| กรณี | การกระทำ |
|---|---|
| ชื่อตรง + ร้านเดิมไม่มี `google_place_id` | **UPDATE** เติม place_id ให้ร้านเดิม (เป็นร้านเดียวกัน) |
| ชื่อตรง + `google_place_id` ตรงกัน | ข้าม (มีอยู่แล้ว) |
| ชื่อตรง + `google_place_id` **ต่างกัน** | ข้าม + รายงาน (คนละร้านชื่อเหมือน ต้องดูด้วยมือ) |

กรณีแรกเกิดกับ `ร้านแกงบ้านเรา` — เป็น 1 ใน 11 ร้านที่ `backfill_place_id` หาไม่เจอ
ด้วยชื่อ แต่ Nearby Search หาเจอเพราะค้นด้วยพิกัด+type ผลคือได้ place_id มาเติม
และรู้ว่าเก็บรีวิวได้ 10 จาก 466 (2%) → เข้าคิว deep scan ได้

#### ค่าที่เขียนลง `places`

```
zone              <- assign_zone(lat, lng)            [ฟังก์ชันเดิม ไม่แก้นิยามโซน]
distance_nu_km    <- distance_to_campus_km(...)       [ฟังก์ชันเดิม]
distance_psru_km  <- distance_to_campus_km(...)
location          <- ST_MakePoint(lng, lat)
opening_hours     <- จาก Places Details (รูปแบบเดียวกับที่ scraper เก็บ)
scraped_at        <- NULL    << ให้ auto_refresh หยิบไปเก็บรีวิว
discovered_by     <- 'api'   << แยกได้ว่าร้านไหนมาจาก scrape ร้านไหนมาจาก API
overall_rating    <- NULL    << ปล่อยว่าง ไม่เอา google_rating มาใส่
```

⚠️ **`overall_rating` ปล่อย NULL โดยเจตนา** — คอลัมน์นั้นหมายถึง "เรตติ้งที่ scrape มา"
ถ้าเอา `google_rating` มาใส่จะปนสองแหล่งในคอลัมน์เดียวแล้วเทียบกันไม่ได้
(เหตุผลเดียวกับที่ migration 012 แยกคอลัมน์ไว้) `save_to_db` จะเติมเองตอน scrape จริง

#### คำสั่ง

```bash
uv run python scripts/promote_candidates.py                      # DRY-RUN: รายชื่อ + ราคา + ตรวจชนชื่อ
uv run python scripts/promote_candidates.py --reject-list        # ตั้งธงคัดออกด้วยมือ (ฟรี)
uv run python scripts/promote_candidates.py --details --limit 5  # ทดสอบ Details 5 ร้าน
uv run python scripts/promote_candidates.py --details            # ยิง Details ครบ [ใช้เครดิต]
uv run python scripts/promote_candidates.py --promote            # เขียนเข้า places (ฟรี)
uv run python scripts/promote_candidates.py --min-reviews 30     # ปรับเกณฑ์
```

**แยก `--details` กับ `--promote` โดยเจตนา** — ขั้นแรกเสียเงินและมีกำหนด
(วันหมดอายุเครดิต) ขั้นสองฟรีและย้อนกลับได้ ถ้ารวมเป็นคำสั่งเดียวแล้วพังกลางทาง
จะไม่รู้ว่าจ่ายค่า API ไปแล้วกี่ร้านแต่ยังไม่เข้า `places` → ต้องยิงซ้ำทั้งชุด = จ่ายสองรอบ

`--details` resume ได้ผ่าน `details_fetched_at` · `--promote` resume ได้ผ่าน `decision`

#### เกณฑ์เปลี่ยนใจได้ฟรี

เพราะตารางพัก**เก็บผู้สมัครไว้ทั้งหมด ไม่ลบอะไร** การเปลี่ยนเกณฑ์ภายหลังไม่ต้อง
ยิง API ใหม่และไม่ติดวันหมดอายุเครดิต — แค่ `--min-reviews 30 --details --promote`
ก็ดึงร้านกลุ่มถัดไปเข้ามาได้

### เช็คว่าเก็บรีวิวครบแล้วหรือยัง + กันการ scrape พังเงียบ

ก่อนมี `google_reviews_total` เราไม่มีทางรู้ว่าร้านหนึ่ง "เก็บครบแล้ว" หรือ "เก็บพลาด"
เพราะไม่มีตัวเทียบ — scrape ได้ 5 รีวิวกับได้ 500 รีวิว ระบบมองเหมือนกันว่าสำเร็จ

#### "ครบ" มี 3 ความหมาย ต้องเลือกก่อนวัด

| เกณฑ์ | ใช้เมื่อไร |
|---|---|
| `เก็บได้ / google_reviews_total` | ดูภาพรวมว่าขาดเท่าไรจากที่มีอยู่จริง |
| **`เก็บได้ / LEAST(google_reviews_total, 850)`** | ✅ **ตัวที่ควรใช้ตัดสินความสำเร็จ** |
| `เก็บได้ >= google_reviews_total` | นับว่าร้านไหนครบแล้ว |

**ทำไมต้องมีเพดาน 850** — Google เสิร์ฟรีวิวผ่านการ scroll ได้จำกัด วัดจากร้านที่
deep สำเร็จ 26 ร้าน: ต่ำสุด 433 · มัธยฐาน 785 · สูงสุด 890 วัดพระศรีฯ deep แล้ว
ได้ 832 จาก 10,058 = 8% ซึ่ง**ไม่ใช่ความล้มเหลว** ถ้าเทียบกับยอดเต็มจะเข้าใจผิดว่า
ร้านใหญ่ล้มเหลวทั้งหมด

⚠️ ร้านที่ไม่มี `google_reviews_total` (Places API หาไม่เจอ) **วัดไม่ได้** ต้องแยกออก
จากการคำนวณ ไม่ใช่นับเป็น 0

#### คิวรีเช็คความครบถ้วนรายร้าน

```sql
SELECT p.name,
       (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) AS scraped,
       p.google_reviews_total                                   AS google_has,
       LEAST(p.google_reviews_total, 850)                       AS ceiling,
       round(100.0 * (SELECT count(*) FROM reviews r WHERE r.place_id = p.id)
             / NULLIF(LEAST(p.google_reviews_total, 850), 0), 0) AS pct
FROM places p
WHERE p.google_reviews_total IS NOT NULL
ORDER BY ceiling - (SELECT count(*) FROM reviews r WHERE r.place_id = p.id) DESC
LIMIT 30;
```

#### 🔴 ปัญหาที่เคยเกิด — Google จำกัดอัตราแบบเงียบ

**25-26 ก.ย. 2026**: Google เสิร์ฟรีวิวให้น้อยลงเรื่อย ๆ จนเกือบศูนย์ โดย
**ไม่ขึ้น CAPTCHA และไม่ขึ้นหน้า sorry** ตัวตรวจจับบล็อกเดิมดูแค่สองอย่างนั้น
จึงไม่ทำงาน งาน `refresh` จบด้วย `status='done'` ทุกรอบ ระบบรันต่ออีก ~10 ชั่วโมง

วัดรายชั่วโมงแล้วเห็นชัดว่าสลับดี-พัง:
```
25 ก.ย. 17:00   33 ร้าน  4,868/5,632   86%  ✅
25 ก.ย. 19:00   61 ร้าน  4,317/13,815  31%  ⚠️
25 ก.ย. 20:00   54 ร้าน  2,071/15,044  14%  🔴
25 ก.ย. 21:00   70 ร้าน  5,805/6,661   87%  ✅
26 ก.ย. 01:00   17 ร้าน    149/1,137   13%  🔴
```

**ความเสียหาย**: 131 ร้านถูกตี `scraped_at = NOW()` ทั้งที่เก็บได้ไม่ถึง 20%
ของที่ควรได้ (รวม ~31,761 รีวิวที่ควรได้) และ `update_scan_stats` เพิ่ม
`consecutive_no_change` ทำให้ติด cooldown 7-30 วัน — ร้านพวกนี้จะไม่ถูกหยิบมาทำอีก

**ลายเซ็นที่บ่งบอก**: 93 ร้านเก็บได้**เป๊ะ 5** และ 40 ร้าน**เป๊ะ 10**
การกระจายแบบนี้ไม่เกิดเองตามธรรมชาติ เป็น scraper หยุดที่จุดเดียวกันซ้ำ ๆ
(ร้านเดิม 300 ร้านที่ scrape ก่อนหน้านี้ มีแบบนี้เพียง 13 ร้าน)

#### กลไกป้องกัน 2 ชั้นที่เพิ่มเข้ามา

**ชั้นที่ 1 — ตัวตัดวงจรใน `auto_refresh.py`**

หลังจบแต่ละรอบ คำนวณ `เก็บได้ / LEAST(google, 850)` ของร้านที่ scrape ในรอบนั้น
ถ้าต่ำกว่า **40%** → ปฏิบัติเหมือนโดนบล็อก: พัก 2→4→6 ชม. แล้วลองใหม่
ครบ 3 ครั้งยังต่ำ → หยุดและคืนสถานะ `throttled`

เกณฑ์ 40% มาจากข้อมูลจริง (ชั่วโมงปกติ 86-91% · ชั่วโมงพัง 13-31%) ทดสอบแล้วว่า
แยกได้ 3 จาก 28 ชั่วโมง — แย่สุด 3% ดีสุด 98%

ต้องมีปริมาณที่คาดหวัง ≥ 200 รีวิวก่อนตัดสิน (`YIELD_MIN_EXPECTED`) ไม่งั้นรอบที่
เจอร้านเล็ก 3 ร้านจะสะดุดผิด

⚠️ **ไม่ใช้ `reviews_new` เป็นสัญญาณ** เพราะร้านที่เก็บครบแล้วจะได้ 0 อย่างถูกต้อง
แยกจากความล้มเหลวไม่ได้ ต้องเทียบกับ "ที่ควรได้" เท่านั้น

**ชั้นที่ 2 — `scripts/requeue_shortfall.py`**

ส่งร้านที่เก็บได้น้อยผิดปกติกลับเข้าคิว:
```
scraped_at            -> NULL   กลับไปหัวคิว refresh (NULLS FIRST)
consecutive_no_change -> 0      ล้าง cooldown ที่ตั้งผิด
refresh_shortfalls    -> +1     นับกันวน scrape ร้านเดิมไม่รู้จบ
```

**ไม่ลบรีวิวที่เก็บได้แล้ว** — รีวิว 5 อันนั้นยังอยู่ครบ รอบใหม่จะเพิ่มทับด้วย
`ON CONFLICT (place_id, text_hash)` ไม่เกิดรายการซ้ำ

**ทำไมต้องมี `refresh_shortfalls`** (migration 016) — ร้านบางแห่ง Google บอกว่ามี
500 รีวิวแต่เสิร์ฟให้จริงแค่ 50 (รีวิวถูกซ่อน/ลบไป) ถ้ารีเซ็ตทุกครั้งที่เก็บได้
ต่ำกว่าคาด ร้านกลุ่มนี้จะถูกวน scrape ไม่รู้จบ ตัวนับนี้ทำให้ยอมแพ้ได้หลังลอง
ซ้ำ 2 ครั้ง — หลักการเดียวกับ `deep_attempts` ใน migration 011

```bash
uv run python scripts/requeue_shortfall.py                   # DRY-RUN: ดูว่าจะแตะร้านไหน
uv run python scripts/requeue_shortfall.py --apply           # ทำจริง
uv run python scripts/requeue_shortfall.py --min-coverage 0.3 --apply
uv run python scripts/requeue_shortfall.py --max-shortfalls 3 --apply   # ลองอีกรอบ
```

#### ขั้นตอนเมื่อเจอ scrape พังเงียบ

```
1. หยุด scrape ทันที (ยิ่งรันยิ่งเผาคิว เพราะร้านถูกตี scraped_at แล้วเข้า cooldown)
2. เปลี่ยน IP — mobile hotspot / VPN
3. uv run python scripts/requeue_shortfall.py          # ดูความเสียหาย
4. uv run python scripts/requeue_shortfall.py --apply  # ส่งกลับเข้าคิว
5. uv run python scripts/auto_refresh.py --limit 20    # รันใหม่ช้าลง
```

### ⚠️ NLP ต้องอ่าน `text_clean` ไม่ใช่ `text`

`reviews` มีคอลัมน์ข้อความ 2 ตัว และ**ใช้ผิดตัวไม่มีอะไรฟ้อง**

| | เนื้อหา |
|---|---|
| `r.text` | ข้อความดิบจากหน้าเว็บ — มีชื่อคนรีวิว, `Local Guide · 536 รีวิว · 2,957 รูปภาพ`, วันที่สัมพัทธ์ (`3 ปีที่แล้ว`), ปุ่ม `ชอบ`/`แชร์`, `คำตอบจากเจ้าของ`, ป้ายคะแนนย่อย (`อาหาร: 5  บริการ: 5  บรรยากาศ: 5`) |
| `r.text_clean` | ข้อความที่ผู้รีวิวเขียนจริง ผ่าน `clean_review_text()` แล้ว |

#### บั๊กที่เกิดขึ้นจริง (พบ 2026-09-26)

`nlp/pipeline.py` ดึง `r.text` มาวิเคราะห์ — เส้นทาง incremental ที่
`scripts/analyze.py` และ `auto_refresh` เรียกใช้ (ส่วน `scripts/reanalyze_all.py`
ใช้ `text_clean` ถูกต้องอยู่แล้ว)

**ผลที่วัดได้:**
```
keywords 32% มีคำ "ชอบ" · 29% มีคำ "แชร์" · 49% มีคำ "ปี"
ทั้งที่ไม่มีคำเหล่านั้นใน text_clean เลย
```

แยกตามวันที่วิเคราะห์เห็นชัดว่าบั๊กเข้ามาเมื่อไร:
```
2026-07-28   4,164 แถว    สกปรก     0%   <- reanalyze_all (text_clean ถูก)
2026-08-24   1,056 แถว    สกปรก    33%   <- เริ่มพัง
2026-09-10   8,484 แถว    สกปรก    61%
2026-09-26  21,527 แถว    สกปรก    48%
```

**ความเสียหาย 2 แบบ:**

1. **รีวิวที่ให้ดาวอย่างเดียว 3,494 แถว ถูกติดป้าย pain point** จากคำในป้าย UI
   ```
   review_id=126307  ดาว 1  ป้าย "การบริการและเจ้าหน้าที่"  sentiment=positive
     ข้อความดิบ: '...2 สัปดาห์ที่แล้ว\nใหม่\nบริการ: 1\nชอบ\nแชร์'
     text_clean: '' (ผู้รีวิวไม่ได้เขียนอะไร)
   ```
   ป้าย `บริการ: 1` ถูกนับเป็นคำบ่นเรื่องบริการ

2. **หมวดของรีวิวที่มีข้อความเพี้ยน** — วัดด้วยการเทียบผลจาก raw vs clean
   บน 4,000 รีวิว: หมวดเปลี่ยน 5.9% โดย `ราคาและความคุ้มค่า` พองเกินจริง 18%,
   `การบริการและเจ้าหน้าที่` 11%, `การเดินทางและที่จอดรถ` 6%

#### 🔴 กับดักตอนแก้ — ห้ามใช้ `rule_based_categorize` คำนวณหมวดใหม่

หมวดที่มีอยู่มาจาก **WangchanBERTa** (โมเดลที่ fine-tune เอง) การคำนวณใหม่ด้วย
`rule_based_categorize` (ตัวจับคำ) **ไม่ใช่การแก้ แต่เป็นการแทนที่ผลของโมเดล
ที่ฝึกแล้วด้วยตัวที่อ่อนกว่า** — ทดลองแล้วได้ผลแย่ลงชัดเจน:

```
'ตึกสีส้มเด่นตรงถนนคนเดิน มีทั้งเครื่องดื่มและขนม'
  WangchanBERTa -> ความคิดเห็นทั่วไป (ถูก — บรรยายที่ตั้ง)
  rule-based    -> การเดินทางและที่จอดรถ (ผิด — จับแค่คำว่า "ถนน")
```

และสองโมเดลใช้ชุดชื่อหมวดไม่เหมือนกัน (`ความคิดเห็นทั่วไป` vs `อื่นๆ`)
การเทียบข้ามโมเดลจึงให้เลข "เปลี่ยน 94.5%" ที่ไม่มีความหมาย

**ถ้าเลข "หมวดเปลี่ยน" สูงผิดปกติ ให้สงสัยว่ากำลังเทียบคนละโมเดล ไม่ใช่เจอบั๊กใหญ่**

#### วิธีแก้ที่ถูก — แยก 2 งาน

**① `nlp/pipeline.py`** — เปลี่ยนคิวรีเป็น `COALESCE(r.text_clean,'') AS text`
และเพิ่ม `_empty_row()` สำหรับรีวิวที่ไม่มีข้อความ

⚠️ ต้อง**บันทึกแถว** ให้รีวิวดาวเปล่า ไม่ใช่ข้ามไป เพราะ `_load_unanalyzed`
หยิบ "รีวิวที่ยังไม่มีแถวใน `analyzed_reviews`" ถ้าข้ามจะถูกหยิบมาซ้ำไม่จบ
แถวนั้นตั้ง `pain_point_category = NULL` และ `model_used = 'rating-only'`
ส่วน `sentiment` ยังประเมินจากดาวได้ เพราะดาวเป็นข้อมูลจริง

**② `scripts/fix_dirty_keywords.py`** — ล้างหมวดของรีวิวดาวเปล่าที่ติดป้ายผิด

```bash
uv run python scripts/fix_dirty_keywords.py           # DRY-RUN
uv run python scripts/fix_dirty_keywords.py --apply   # แก้จริง
```

แก้เฉพาะแถวที่ `text_clean` ว่าง **และ**ติดป้ายหมวดเฉพาะ →
ตั้ง `pain_point_category` / `pain_point_thai` = NULL, `keywords` = `{}`

**ไม่แตะ** แถวที่ติดป้าย `ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)` (15,128 แถว) เพราะ
ป้ายนั้นถูกต้องสำหรับรีวิวที่ไม่ได้ระบุปัญหา · **ไม่แตะ** `sentiment` / `severity`
(มาจากดาว) · **ไม่แตะ** `claude_*` (เก็บเทียบในวิทยานิพนธ์)

**③ รีวิวที่มีข้อความ** — ใช้ `scripts/reanalyze_all.py --apply` ซึ่งใช้
`text_clean` + WangchanBERTa ตัวเดียวกันอยู่แล้ว จึงแก้ `keywords` + `category`
+ `pain_point_thai` + `sentiment` ได้พร้อมกันโดยไม่เปลี่ยนโมเดล
(53,475 แถว · ควร backup ก่อน)

#### คิวรีตรวจว่ายังมีปัญหาไหม

```sql
-- ต้องเป็น 0: ไม่มีข้อความ แต่ติดป้ายหมวดเฉพาะ
SELECT count(*) FROM analyzed_reviews a JOIN reviews r ON r.id = a.review_id
WHERE COALESCE(r.text_clean,'') = '' AND a.pain_point_category IS NOT NULL
  AND a.pain_point_category <> 'ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)';

-- ควรเป็น 0: keywords มีคำจากป้าย UI ที่ไม่มีใน text_clean
SELECT count(*) FROM analyzed_reviews a JOIN reviews r ON r.id = a.review_id
WHERE COALESCE(r.text_clean,'') <> '' AND EXISTS (
  SELECT 1 FROM unnest(a.keywords) k
  WHERE k IN ('ชอบ','แชร์','Local','Guide','รูปภาพ','คำตอบ')
    AND r.text_clean NOT LIKE '%' || k || '%');
```

### ⚠️ วันที่รีวิว — 2 บั๊กที่ทำให้รีวิวหายจากหน้าที่กรองเวลา

`reviews` เก็บวันที่ 2 คอลัมน์

| | เนื้อหา |
|---|---|
| `review_date` | ข้อความดิบจาก Google — สัมพัทธ์ ณ เวลาที่ scrape (`"3 เดือนที่แล้ว"`) |
| `review_date_approx` | วันที่จริงที่คำนวณไว้**ตอน scrape** — ใช้กรอง/เรียง/รายงาน |

`review_date` เพี้ยนขึ้นเรื่อย ๆ ตามเวลา (`"3 ปีที่แล้ว"` ที่เก็บมาเมื่อ 2 ปีก่อน
วันนี้คือ 5 ปี) ส่วน `review_date_approx` นิ่งเพราะตรึงไว้ตอนเก็บ

⚠️ **ถ้า `review_date_approx` เป็น NULL รีวิวนั้นหายไปจากทุกคิวรีที่กรองช่วงวันที่**
ซึ่งหน้า Dashboard กรองเป็นค่าเริ่มต้น — รีวิวมีข้อความครบแต่มองไม่เห็น

#### บั๊กที่พบ 2026-09-26 (1,658 รีวิว = 2.3%)

**บั๊ก A — `scraper/date_parser.py` รับแค่ `"ที่แล้ว"` / `"ago"`** (368 รีวิว)

Google ใช้ `"ที่ผ่านมา"` ด้วย โดยพบว่าใช้กับรีวิวใหม่ ๆ (`"2 วันที่ผ่านมา"`)
ขณะที่รีวิวเก่าใช้ `"ที่แล้ว"` → แก้เป็น `_PAST_MARKERS = ("ที่แล้ว", "ที่ผ่านมา", "ago")`

**บั๊ก B — scraper หยิบป้าย "มื้อที่ไป" มาเป็นวันที่** (908 รีวิว)

โค้ด JS ใน `scraper_core.py` ผิด 2 จุดพร้อมกัน:

```js
// ผิด
container.querySelectorAll('span').forEach(s => {
    if (/(เดือน|สัปดาห์|วัน|ปี|ago|...)/i.test(t) && t.length < 35)
        dateText = t;        // ไม่ break -> span สุดท้ายชนะ
});
```

1. เงื่อนไขจับคำว่า **`วัน` เปล่า ๆ** ทำให้ป้าย "มื้อที่ไป" ของ Google เข้าเงื่อนไขด้วย:
   `วันธรรมดา` · `วันเสาร์-อาทิตย์` · `วันหยุดนักขัตฤกษ์` · และ **`อาหารกลางวัน`**
   (มีคำว่า "วัน" อยู่ข้างใน)
2. ใช้ `forEach` + `dateText = t` โดย**ไม่ `break`** → span สุดท้ายชนะ
   Google วางวันที่ไว้ก่อนแล้ววางป้าย "มื้อที่ไป" ทีหลัง ป้ายจึงเขียนทับวันที่ทุกครั้ง

แก้เป็น: ต้องมีคำบอกอดีต (`ที่แล้ว`/`ที่ผ่านมา`/`ago`) **และ** เอา span แรกที่เจอแล้ว `break`
— เกณฑ์เดียวกับ `_PAST_MARKERS` ใน `date_parser.py` (แก้ที่หนึ่งต้องแก้ที่นั่นด้วย)

#### กู้ข้อมูลเก่า — `backfill_review_dates.py`

```bash
uv run python scripts/backfill_review_dates.py           # DRY-RUN
uv run python scripts/backfill_review_dates.py --apply   # แก้จริง
```

หาวลีวันที่จาก 2 แหล่งตามลำดับ: `review_date` ก่อน แล้วค่อยหาใน `r.text` (ดิบ)
— **วันที่จริงยังอยู่ในข้อความดิบ** แม้ `review_date` จะถูกป้ายทับไปแล้ว

**ผลที่ได้**: กู้คืน 1,277 อัน (910 จากข้อความดิบ + 367 จาก `review_date`)
เหลือกู้ไม่ได้ 381 อัน (0.5%) — ป้ายทับและข้อความดิบไม่มีวันที่เลย

```
รีวิวที่มีวันที่  70,582 -> 71,859  (97.7% -> 99.5%)
```

#### ⚠️ ต้องอ้างอิง `scraped_at` ไม่ใช่วันนี้

```
'2 วันที่ผ่านมา'  scrape เมื่อ 2026-08-23
  อ้างอิงวันนี้      -> 2026-09-24   ผิดไป 34 วัน
  อ้างอิง scraped_at -> 2026-08-21   ถูก
```

`parse_relative_date(phrase, reference)` รับ reference ได้ — ต้องส่ง `r.scraped_at`
เสมอเมื่อ backfill ย้อนหลัง ไม่งั้นรีวิวเก่าจะเลื่อนมาใกล้ปัจจุบันทั้งหมด

#### คิวรีตรวจ

```sql
-- ควรน้อยที่สุด: รีวิวที่หายจากหน้าที่กรองวันที่
SELECT count(*) FROM reviews WHERE review_date_approx IS NULL;

-- ต้องเป็น 0 ทั้งสาม: วันที่เป็นไปไม่ได้
SELECT count(*) FILTER (WHERE review_date_approx > CURRENT_DATE)          AS อนาคต,
       count(*) FILTER (WHERE review_date_approx < DATE '2008-01-01')     AS ก่อน_google_maps,
       count(*) FILTER (WHERE review_date_approx > scraped_at::date)      AS เกิดหลัง_scrape
FROM reviews WHERE review_date_approx IS NOT NULL;
```

ข้อสุดท้ายสำคัญ — รีวิวต้องเกิด**ก่อน**วันที่เรา scrape เสมอ ถ้าเกินคือคำนวณผิด
(มักเกิดจากลืมส่ง reference แล้วไปอ้างอิงวันนี้)

### ⚠️ แถวร้านซ้ำ + รีวิวซ้ำข้ามร้าน

#### ปัญหา 1 — promote สร้างแถวร้านซ้ำ (พบ 2026-09-26 · 26 คู่)

```
promote_candidates.py  สร้างแถวด้วยชื่อจาก Google API -> "Pang Ki Khao Man Kai"
auto_refresh           ค้นชื่อนั้น Google Maps แสดงชื่อไทย -> "พังกี่ข้าวมันไก่"
save_to_db             ON CONFLICT (name) ไม่ตรง        -> INSERT แถวใหม่
```

ผลคือร้านเดียวกันมี 2 แถว:
```
id=3084  Google 791 รีวิว | Pang Ki Khao Man Kai   (จาก API · 0 รีวิว)
id=3705  เก็บ  200 รีวิว | พังกี่ข้าวมันไก่        (จาก scrape · ไม่มีเฉลย)
```

**ความเสียหาย 3 อย่าง**
1. นับร้านเกินจริง (792 ควรเป็น 766)
2. ตัวเลขความครบถ้วนเพี้ยน — แถว API มีเฉลยแต่ 0 รีวิว (0%) ส่วนแถวที่มีรีวิว
   ไม่มีเฉลย (วัดไม่ได้) ทั้งที่ของจริงคือ 200/791 = 25%
3. **คิว refresh วนไม่รู้จบ** — แถว API ค้าง `scraped_at = NULL` ตลอดไป
   เพราะ refresh สร้างแถวใหม่ทุกครั้งไม่มาเติมแถวเดิม (57 จาก 151 ร้านในคิว)

#### 🔴 บทเรียน — ตรวจ "พิกัดซ้ำ" ไม่ใช่ "ชื่อซ้ำ"

ตอนออกแบบ promote ตรวจแค่ชื่อตรงกันเป๊ะ (`JOIN places p ON p.name = c.name`)
เจอ 1 คู่แล้วสรุปว่าปลอดภัย — **ผิดทิศ**

ปัญหาไม่ใช่ชื่อชนกัน แต่เป็น **ชื่อไม่ชนทั้งที่เป็นร้านเดียวกัน**
ชื่ออังกฤษจาก API กับชื่อไทยบนหน้าเว็บเทียบกันด้วยข้อความไม่ได้เลย
**พิกัดเท่านั้นที่เชื่อได้** — คู่ที่พบจริงทั้ง 26 คู่ห่างกัน **0 เมตร**

`promote_candidates.py` เพิ่ม `coord_collisions()` แล้ว: ผู้สมัครที่พิกัดตรงกับ
ร้านเดิม (< 40 ม.) ที่ยังไม่มี `google_place_id` → **เติม place_id ให้ร้านเดิม
ไม่สร้างแถวใหม่**

ข้ามกรณีที่ร้านเดิมมี `google_place_id` คนละตัว — Google ถือว่าคนละสถานที่
(2 สาขาในตึกเดียวกันมีจริง)

#### กู้ข้อมูลเก่า — `merge_duplicate_places.py`

```bash
uv run python scripts/merge_duplicate_places.py           # DRY-RUN
uv run python scripts/merge_duplicate_places.py --apply   # รวมจริง
```

**เก็บแถวที่มีรีวิวไว้ ไม่ใช่แถวจาก API** เพราะชื่อของมันคือชื่อที่ Google Maps
แสดงจริง → refresh รอบหน้าจะ match แถวเดิมและไม่สร้างใหม่อีก
ถ้าเก็บแถว API ไว้ ปัญหาจะเกิดซ้ำทุกรอบ scrape

⚠️ **ลำดับการทำงานสำคัญ — ทำผิดลำดับพังทั้งสองทาง**
```
1. ชี้ place_candidates.matched_place_id ไปแถวที่เก็บ  (FK เป็น SET NULL)
2. DELETE แถวที่ซ้ำ
3. ตั้ง google_place_id ให้แถวที่เก็บ
```
ข้อ 3 ต้องอยู่**หลัง**ข้อ 2 เพราะ `uq_places_google_place_id` เป็น UNIQUE —
ตั้งค่าซ้ำกับแถวที่ยังมีอยู่จะได้ `UniqueViolationError` (เทสต์จับได้)
ทั้งสามอยู่ใน transaction เดียว ถ้าพังจะ rollback ไม่เกิดสภาพครึ่ง ๆ

⚠️ `reviews.place_id` และ `snapshot_places.place_id` เป็น **ON DELETE CASCADE**
สคริปต์จึงยืนยันว่าแถวที่จะลบมี **0 รีวิว ทันทีก่อนลบทุกครั้ง** ไม่เชื่อค่าที่อ่านมาตอนแรก

**ผลที่ได้**: places 792 → 766 · คิว refresh 151 → 125 · รีวิวไม่หายแม้แต่อันเดียว

#### ปัญหา 2 — รีวิวซ้ำข้ามร้าน (102 ข้อความ · 205 แถว · 0.28%)

`uq_place_text_hash` กันรีวิวซ้ำ**ในร้านเดียวกัน** แต่กันข้ามร้านไม่ได้

สาเหตุ 2 แบบ:
1. **Google ย้าย/รวม listing** — Kyoto Shi Cafe (สาขาหลัก) เก็บได้ 193 รีวิว
   แต่ Google บอกว่ามี 4 · 84 อันเป็นสำเนาของ "สาขาท่าทอง" (225/211)
2. **scraper จับหน้าผิดร้าน** — ค้นชื่อร้าน A แล้ว Google Maps แสดงร้าน B

#### หลักฐานที่ใช้ตัดสินว่าลบสำเนาไหน

```
over = เก็บได้ - LEAST(google_reviews_total, 850)
```

ร้านที่ `over` เป็นบวกมาก = เก็บรีวิวได้เกินกว่าที่ Google บอกว่ามี
→ ส่วนเกินน่าจะเป็นของร้านอื่นที่หลุดมา จึงลบสำเนาที่อยู่ร้านนั้น

**ถ้าไม่มีร้านไหน `over` เป็นบวก = ไม่มีหลักฐาน → ปล่อยไว้ ไม่เดา**
เช่น `วงเวียนสถานีรถไฟพิษณุโลก` กับ `สถานีรถไฟพิษณุโลก` ห่างกัน 480 ม.
เป็นสถานที่ใกล้กันจริง คนรีวิวอาจหมายถึงที่เดียวกัน — ตัดสินแทนไม่ได้

```bash
uv run python scripts/dedup_cross_place.py           # DRY-RUN
uv run python scripts/dedup_cross_place.py --apply   # ลบจริง (backup ก่อน)
```

**ผลที่ได้**: ลบ 88 แถว (72,240 → 72,152) · ปล่อยไว้ 14 กลุ่มที่ตัดสินไม่ได้
**ทุกข้อความยังเหลือสำเนาอย่างน้อย 1 อัน** — ไม่มีข้อความไหนหายจากระบบ

⚠️ ลบแถวใน `reviews` จะลบแถวใน `analyzed_reviews` ตามไปด้วย (CASCADE)

#### คิวรีตรวจ

```sql
-- ควรเป็น 0: แถวร้านซ้ำ (พิกัดเดียวกัน ฝั่งหนึ่งมีเฉลยแต่ 0 รีวิว)
SELECT count(*) FROM places a JOIN places b
  ON a.id < b.id AND ST_DWithin(a.location::geography, b.location::geography, 40)
WHERE a.google_place_id IS NOT NULL AND b.google_place_id IS NULL
  AND (SELECT count(*) FROM reviews r WHERE r.place_id = a.id) = 0
  AND (SELECT count(*) FROM reviews r WHERE r.place_id = b.id) > 0;

-- ดูรีวิวที่ยังซ้ำข้ามร้าน (ที่เหลือคือกลุ่มที่ตัดสินไม่ได้)
SELECT count(*) FROM (
  SELECT r.text_clean FROM reviews r
  WHERE length(COALESCE(r.text_clean,'')) > 40
  GROUP BY r.text_clean HAVING count(DISTINCT r.place_id) > 1) q;
```

### deep scan — เลือกร้านด้วย `--targets gap`

เกณฑ์เลือกร้านของ `deep_scan.py` มี 5 ตัว

| `--targets` | เลือกร้านที่ | เรียงด้วย |
|---|---|---|
| `capped` | มีรีวิว >= 190 (น่าจะโดนเพดาน 200 ตัด) | จำนวนที่มีอยู่ |
| `zero` | ยังไม่มีรีวิวเลย | จำนวนที่มีอยู่ |
| `shallow` | มี >= 50 แต่ช่วงวันที่แคบกว่า 730 วัน | จำนวนที่มีอยู่ |
| `all` | รวม 3 ตัวบน | จำนวนที่มีอยู่ |
| **`gap`** | **ยังขาดรีวิวจริงเทียบ `google_reviews_total`** | **จำนวนที่เก็บคืนได้** |

#### ทำไมต้องมี `gap` — 2 ปัญหาที่เกณฑ์อื่นแก้ไม่ได้

**① เรียงกลับหัวกับผลตอบแทน**

เกณฑ์อื่นใช้ `ORDER BY cnt DESC` (จำนวนรีวิวที่มีอยู่แล้ว) ซึ่งสวนทางกับความคุ้ม:

```
พระพุทธชินราช      มี  12 รีวิว | Google 7,028 -> เก็บคืนได้ 838  ← ควรทำก่อน
ร้านที่ deep สำเร็จ  มี 800 รีวิว | Google 890   -> เก็บคืนได้  50
```

ร้านแรกจะอยู่**ท้ายคิว** ทั้งที่คุ้มกว่า 17 เท่า

**② ร้านที่ถูกตี `deep_scanned_at` ไว้แล้วแต่เก็บได้แค่ ~200**

เกณฑ์อื่นใช้ `WHERE deep_scanned_at IS NULL` จึง**ข้ามร้านกลุ่มนี้ถาวร**

พบ 33 ร้าน รวม **~8,449 รีวิวที่เข้าถึงไม่ได้เลย**:
```
ฟ้าไทยฟาร์ม                    199 / Google 1,950
National Museum Buddha         200 / Google 2,912
ร้านขนมจีนต้นก้ามปู            204 / Google 2,209
```

สาเหตุ: เกณฑ์ผ่านของ deep scan เดิมดูแค่ `collected > 0` ไม่ได้ดูว่าครบไหม
รอบที่เก็บได้แค่ 200 (เพดาน refresh) ก็ผ่านและถูกตี `deep_scanned_at`

`gap` จึง **ไม่บังคับ `deep_scanned_at IS NULL`** เพื่อครอบร้านกลุ่มนี้

#### เกณฑ์ของ `gap` — 3 เงื่อนไข

```sql
google_reviews_total IS NOT NULL                          -- ต้องมีเฉลยก่อน
AND LEAST(google_reviews_total, 850) > 200                -- refresh ทำเองไม่ได้
AND LEAST(google_reviews_total, 850) - COUNT(reviews) >= 50  -- ยังขาดพอสมควร
```

⚠️ **เงื่อนไขที่ 2 สำคัญ** — ตัดร้านที่ `refresh` ทำเองได้ออก

วัดจากข้อมูลจริง: ร้านที่ Google มี 50-199 รีวิว `refresh` เก็บได้ **94%** ใน 14 วินาที
ส่วน `deep` ได้ 95% แต่ใช้ 3 นาที — **เสียเวลา 13 เท่าเพื่อผลเท่าเดิม**
`deep` คุ้มเฉพาะร้านที่ `refresh` ตัดทิ้ง คือร้านที่มีเกิน `MAX_REVIEWS_PER_PLACE` (200)

ไม่กรองข้อนี้จะได้คิว 212 ร้าน (กรองแล้วเหลือ 130) โดย 82 ร้านที่เกินมาไม่คุ้มทำเลย

⚠️ **เพดาน 850 ไม่ใช่ `google_reviews_total` ตรง ๆ** — Google เสิร์ฟผ่าน scroll
ได้จำกัด (วัดจากร้านที่ deep สำเร็จ 26 ร้าน: ต่ำสุด 433 · มัธยฐาน 785 · สูงสุด 890)
วัดพระศรีฯ deep แล้วได้ 832/10,058 = 8% ซึ่ง**คือเต็มที่แล้ว ไม่ใช่ล้มเหลว**
ถ้าเทียบกับยอดเต็มร้านใหญ่จะติดคิวตลอดไปและวน deep ไม่รู้จบ

⚠️ **`--targets all` ไม่รวม `gap`** เพราะ `gap` ใช้ `WHERE` คนละแบบ
(ไม่บังคับ `deep_scanned_at IS NULL`) ต้องเรียก `--targets gap` แยก

#### คำสั่ง

```bash
uv run python scripts/deep_scan.py --targets gap --dry-run       # ดูคิวก่อน
uv run python scripts/deep_scan.py --targets gap --limit 5       # ทดสอบ 5 ร้าน
uv run python scripts/deep_scan.py --targets gap                 # รันเต็ม
```

#### ลำดับที่ควรทำ

```
1. auto_refresh       ร้านที่ Google มี <= 200 รีวิว (เร็ว 14 วิ/ร้าน ได้ 94%)
2. requeue_shortfall  เช็คว่ารอบ refresh ไม่ถูกจำกัดอัตราแบบเงียบ
3. deep_scan --targets gap   ร้านที่เกินเพดาน refresh (3 นาที/ร้าน)
4. analyze + take_snapshot
```

⚠️ **refresh ก่อน deep** — ร้านใหม่ที่มี 0 รีวิวจะได้ ~200 อันจาก refresh ใน 14 วินาที
ถ้า deep เลยก็ได้เหมือนกันแต่ใช้ 3 นาที เอาเวลาไปทำร้านอื่นดีกว่า

### ขอบเขตร้าน — กันร้านนอกขอบเขตด้วย `scrape_excluded`

ขอบเขตงานเก็บรีวิวเฉพาะ **ร้านอาหาร / คาเฟ่ / แหล่งท่องเที่ยว / สวน / พิพิธภัณฑ์**
ไม่รวมโรงแรม-ที่พัก เชนใหญ่ ห้างสรรพสินค้า เพราะปัญหาของที่พักเป็นคนละชุดกับ
ปัญหาการท่องเที่ยวเชิงกิน-เที่ยว (เช็คอิน ห้องพัก ราคาต่อคืน) เอามารวมจะทำให้
หมวดปัญหาปนกัน

**ทำไมตั้งธง ไม่ลบร้านทิ้ง**

| ถ้าลบร้าน | ถ้าตั้งธง |
|---|---|
| `reviews.place_id` เป็น ON DELETE CASCADE → รีวิวที่เก็บมาแล้วหายตามไป กู้ไม่ได้ | รีวิวอยู่ครบ |
| เสียตัวส่วนวัดความครอบคลุมพื้นที่ (โซนนี้มีกี่ร้าน เราเก็บไปกี่ร้าน) | ข้อมูล API ยังอยู่ใช้เป็นตัวส่วนได้ |
| ถอนคืนไม่ได้ | `--include <id>` ถอนคืนได้ |

**คอลัมน์ (migration 017)**

| คอลัมน์ | ความหมาย |
|---|---|
| `scrape_excluded boolean NOT NULL DEFAULT false` | true = ไม่เข้าคิว scrape |
| `scrape_excluded_reason text` | เหตุผล เก็บไว้ให้ย้อนดูได้ว่าตัดเพราะอะไร |

**⚠️ ทุกจุดที่สร้างคิวต้องกรองพร้อมกัน 5 จุด** — ถ้าเติมไม่ครบจะเกิดอาการแปลก

| ไฟล์ | ฟังก์ชัน |
|---|---|
| `scraper/scraper.py` | `load_existing_places`, `load_places_to_refresh` |
| `scripts/auto_refresh.py` | `eligible_count` |
| `scripts/deep_scan.py` | `load_targets` (ทุก target รวม `gap`) |
| `scripts/requeue_shortfall.py` | ทั้งคิวและรายงานความครบถ้วน |

`load_places_to_refresh` กับ `eligible_count` **ต้องใช้เกณฑ์ตรงกันเป๊ะ** ไม่งั้น
`auto_refresh` จะนับว่ามีงานเหลือแต่ `run_refresh` ไม่หยิบร้านไหนมาทำ → loop วนไม่จบ
(กับดักเดียวกับที่คอมเมนต์ใน `eligible_count` เตือนไว้ตั้งแต่เดิม)

**⚠️ ธงนี้ไม่ใช่ตัวกรองของสถิติ pain point**
รีวิวที่เก็บมาก่อนถูกตั้งธงยังอยู่ในฐานและยังถูกนับใน `api/` ตามเดิม
(ตอนตั้งธงรอบแรกมี 67 อันจาก 3 ร้าน) ถ้าจะตัดออกจากการวิเคราะห์ด้วย ต้องเติม
ตัวกรองใน `api/` แยกอีกชุด และต้องเติม**ทั้งตัวตั้งและตัวส่วนพร้อมกัน** (กฎข้อ 1)
ไม่ใช่เติมข้างเดียว

**เกณฑ์ที่ใช้**

`--pure-lodging` → `google_types` มี `lodging` แต่**ไม่มี** `restaurant` และ `cafe`
ที่ต้องยกเว้นร้านที่มีทั้งคู่ เพราะคาเฟ่ที่มีห้องพักด้วยยังเป็นคาเฟ่จริง —
168 HEAVEN CAFE Resort เก็บได้ 127 รีวิว, บ้านติดดินสโลว์บาร์ 49, Baan Lhang Wangh
ถ้ากวาดทุกร้านที่มี `lodging` จะตัดคาเฟ่จริงออก 3 ร้าน

`--admin-areas` → แถวที่เป็นเขตปกครอง ไม่ใช่ร้าน (`locality,political`,
`administrative_area_level_4,political`) หลุดเข้ามาตอน discover 2 แถว:
`ตำบล ท่าโพธิ์` และ `เขาสมอแคลง` ทั้งคู่ไม่มี `google_reviews_total` เพราะ Google
ไม่นับรีวิวให้เขตปกครอง ปล่อยไว้จะเสียเวลา scrape เปล่าและถูกตี
`refresh_shortfalls` เพิ่มทุกรอบ

**ใช้ `google_types` ไม่ใช่ `google_category`** เพราะ `google_types` มาจาก API ตรง ๆ
ส่วน `google_category` มาจากการอ่าน DOM ซึ่งพลาดได้ (ดูหัวข้อถัดไป)

```powershell
uv run python scripts\exclude_places.py --pure-lodging          # DRY-RUN
uv run python scripts\exclude_places.py --pure-lodging --apply
uv run python scripts\exclude_places.py --admin-areas --apply
uv run python scripts\exclude_places.py --report                # ดูว่ากันอะไรไว้
uv run python scripts\exclude_places.py --include 664 1618      # ถอนคืน
```

---

### ⚠️ `google_category` เก็บข้อความปุ่ม UI มาเป็นหมวด

ร้านที่เจ้าของยังไม่ได้ยืนยันข้อมูลกับ Google จะ**ไม่มีหมวดหมู่**แสดงในหน้าร้าน
แต่ Google เอา**ปุ่มชวนแก้ไขข้อมูล**มาวางที่ตำแหน่ง DOM เดียวกัน ตัวอ่านหมวดใน
`scraper_core` จึงเก็บข้อความปุ่มมาเป็นหมวด เจอจริง 4 ร้าน:

| id | ร้าน | หมวดที่ได้ | ที่จริง |
|---|---|---|---|
| 664 | Nature Park Resort | `'เพิ่มเว็บไซต์'` | ที่พัก |
| 827 | ทศวรรณ เกสต์เฮ้าส์ | `'เพิ่มเว็บไซต์'` | ที่พัก |
| 651 | พีพี การ์เด้น | `'เพิ่มเวลาทำการ'` | ไม่ทราบ |
| 3596 | โจ๊กอัมรินทร์นคร (เจ้าเก่า) | `'เพิ่มเว็บไซต์'` | ไม่ทราบ |

ค่าผิดแบบนี้แย่กว่าค่าว่าง เพราะ `zone_breakdown()` จะนับ `'เพิ่มเว็บไซต์'`
เป็นหมวดหนึ่งในกราฟ

**ปิดต้นเหตุแล้ว** — `scraper_core._is_ui_button_text()` ทิ้งข้อความกลุ่มนี้แล้ว
ปล่อยเป็น `None` รายการคำนำหน้าอยู่ใน `UI_BUTTON_PREFIXES` ที่ไฟล์เดียวกัน
`fix_place_category.py` import ชุดเดียวกันไปใช้ — ถ้าเขียนรายการซ้ำสองที่
จะเพี้ยนกันเมื่อ Google เพิ่มปุ่มใหม่

**ซ่อมข้อมูลที่ค้าง** — `fix_place_category.py` อ่าน `google_types` จาก API
มาเติมหมวดภาษาไทย ตามหลัก 3 ข้อ:

1. **ไม่ทับหมวดที่ดีอยู่แล้ว** แตะเฉพาะแถวที่เป็นข้อความปุ่มหรือ `NULL`
   เพราะหมวดที่ scrape มาถูกต้องละเอียดกว่า types เยอะ (`'ร้านอาหารญี่ปุ่น'`
   ละเอียดกว่า `restaurant` · `'รีสอร์ท'` ละเอียดกว่า `lodging`)
   ทับทิ้งคือทำให้ข้อมูลหยาบลง ไม่ใช่การซ่อม
2. **type ที่เฉพาะเจาะจงที่สุดชนะ ไม่ใช่ตัวแรกในสตริง** Google เรียง `types`
   ไม่คงที่ บางร้านขึ้นต้นด้วย `establishment` ที่ไร้ความหมาย จึงไล่ตามลำดับ
   ของเราใน `TYPE_TO_THAI` (`bakery` → `cafe` → `restaurant` → … → `food`)
3. **ล้างข้อความปุ่มเป็น `NULL` แม้เดาหมวดใหม่ไม่ได้** แต่แถวที่ `NULL`
   อยู่แล้วและเดาไม่ได้ ไม่ต้องแตะ

ที่**ไม่แมปโดยเจตนา**: `school`, `secondary_school`, `local_government_office`,
`general_contractor` — Google ติด type พวกนี้ผิดบ่อย (ศาลสมเด็จพระนเรศวรฯ ได้
`secondary_school` · จุดเล่นน้ำท้ายเขื่อนได้ `local_government_office`) แมปแล้ว
จะผิดกว่าเดิม และ `establishment`, `point_of_interest` ที่กว้างเกินจะบอกอะไร
ผลคือครอบคลุม 70 จาก 76 ชุด types ที่มีในฐาน

```powershell
uv run python scripts\fix_place_category.py            # DRY-RUN
uv run python scripts\fix_place_category.py --apply
```

---

### ปลดล็อกร้านที่ชน `refresh_shortfalls` — `--reset-shortfalls`

ตัวนับ `refresh_shortfalls` ออกแบบให้ "ยอมแพ้" หลังลองครบตามเพดาน ซึ่งถูกต้อง
เมื่อสาเหตุคือ Google เสิร์ฟรีวิวให้ได้เท่านั้นจริง (รีวิวถูกซ่อน/ลบ)

แต่มีสาเหตุอีกแบบ: Google เสิร์ฟหน้าร้านแบบ**ไม่มีส่วนรีวิวมาให้เลย** ซึ่งเกิด
แบบไม่คงที่ — ร้านเดิมรอบหน้าอาจได้ครบ (ยืนยันด้วยการรันสดแล้ว: `โกปี๊ฮับ`
สำเร็จรอบหนึ่งและล้มเหลวอีกรอบ) ร้านกลุ่มนี้จะถูกกันออกถาวรทั้งที่ยังเก็บได้

`--reset-shortfalls` ล้างตัวนับให้กลับเป็น 0 **ไม่แตะ `scraped_at`** — ให้
`requeue_shortfall` รอบต่อไปตัดสินใจเองว่าร้านไหนควรกลับเข้าคิวตามเกณฑ์
ความครบถ้วน ถ้าล้างตัวนับพร้อมรีเซ็ต `scraped_at` ในคำสั่งเดียวจะข้ามเกณฑ์ไปเลย

**ไม่ใช่คำสั่งที่ควรรันทุกรอบ** — ถ้ารันทุกรอบตัวนับจะไร้ความหมาย ใช้เมื่อ
เปลี่ยน IP แล้ว หรือย้ายไปรันช่วง 02:00-05:00 ที่โหลดน้อย

```powershell
uv run python scripts\requeue_shortfall.py --reset-shortfalls          # ดูก่อน
uv run python scripts\requeue_shortfall.py --reset-shortfalls --apply
uv run python scripts\requeue_shortfall.py --apply                     # แล้วส่งเข้าคิว
```

---

### ⚠️ listing แบบโรงแรมไม่ render ไอคอนดาว — ทำให้เก็บได้ 0 รีวิว

พบ 2026-09-27 จากข้อสังเกตของผู้ใช้ว่า "ร้านที่ดึงไม่ได้มักเป็นคาเฟ่+ที่พัก
หรือร้านอาหาร+ที่พัก และถ้ากดรีวิวเข้าไปจะไม่มีดาว แต่เป็นคะแนนเต็ม"

**อาการ** `Collected 0 reviews` ทั้งที่ร้านมีคะแนนรวมและ Google บอกว่ามีรีวิวหลายร้อย
ไม่มีสัญญาณบล็อก ไม่มี CAPTCHA

**สาเหตุ** ร้านที่ Google จัดเป็น `lodging` จะได้ listing แบบโรงแรม (มีปุ่ม
"ตรวจสอบห้องว่าง" และช่องเช็คอิน/เช็คเอาท์) หน้าแบบนี้ **ไม่ render ไอคอนดาว**
ใช้ข้อความ `4/5` แทน และต่อท้ายด้วยคะแนนย่อย `ห้องพัก:` `บริการ:` `สถานที่ตั้ง:`

โค้ดเดิมทั้งสามตัวยึด `aria-label` ที่ match `^[1-5]\s*(ดาว|star)` เหมือนกันหมด
จึงพังพร้อมกัน:

| ฟังก์ชัน | ผลบนหน้าแบบโรงแรม |
|---|---|
| `_extract_visible_reviews` | เริ่มค้นจาก element ดาว → หาจุดเริ่มไม่ได้ → คืน 0 |
| `_count_review_nodes` | นับได้ 5 (ฮิสโตแกรม 1-5 ดาว ไม่ใช่การ์ดรีวิว) |
| `reviews_feed_ready` | อ่านค่าจากตัวข้างบน → `open_reviews_tab()` คืน False |

วัดจากหน้าจริง:

| ร้าน | การ์ด `[data-review-id]` | `aria-label "N ดาว"` | ข้อความ `"N/5"` |
|---|---|---|---|
| โจ๊กอัมรินทร์นคร (เจ้าเก่า) | **112** | 5 | 10 |
| Baan Lhang Wangh | **101** | 5 | 10 |
| ร้านอาหารลุงแย้ม (ปกติ) | 106 | **15** | 0 |

ร้านปกติได้ 15 = ฮิสโตแกรม 5 + การ์ดรีวิว 10 ส่วนร้านที่พังได้แค่ฮิสโตแกรม

**ความเสียหาย** 26 ร้านที่ Google มี ≥50 รีวิวแต่เก็บได้ 0 = **5,650 รีวิวที่เข้าไม่ถึง**

**วิธีแก้: ทางสำรอง ไม่ใช่แทนที่**

`_extract_reviews_any()` เรียกทางเดิมก่อน ถ้าได้ 0 จึงเรียก
`_extract_cards_fallback()` ที่ยึด `[data-review-id]` แทน

**⚠️ ทำไมต้องเป็นทางสำรอง** ทางเดิมไต่ `parentElement` ขึ้นไปหา container ที่
ข้อความยาว 40-1200 ตัว ส่วนทางใหม่ยึดที่ตัวการ์ดตรง ๆ ข้อความที่ได้จึงไม่เหมือนกัน
→ `text_hash` ไม่เหมือนกัน → **ถ้าเปลี่ยนตัวหลัก รีวิวที่เก็บมาแล้วทั้งหมดจะถูก
INSERT ซ้ำเป็นแถวใหม่** (บั๊กเดิมที่เคยทำให้มีรีวิวซ้ำ 3,453 แถว)

ทางสำรองถูกเรียกเฉพาะตอนทางเดิมได้ 0 = แตะแค่หน้าที่ปัจจุบันเก็บไม่ได้อยู่แล้ว
และ 26 ร้านนั้นมี 0 แถวในฐาน **ความเสี่ยงซ้ำจึงเป็นศูนย์** และไม่ต้องแก้
`review_text_hash()` เลย ยืนยันด้วยเทสบนหน้าจริง: ร้านปกติได้ `text_hash`
เหมือนเดิมทุกอัน (ต่าง 0 อัน)

**⚠️ ตัดบรรทัดโครงสร้างใน JS ไม่ใช่ใน `text_cleaner.py`**
`clean_review_text()` ไม่รู้จัก `4/5`, `"3 เดือนที่แล้ว ใน"`, `Google`,
`ห้องพัก:` แต่**แก้ที่นั่นไม่ได้** เพราะ `review_text_hash()` เรียกฟังก์ชันนั้น
→ เปลี่ยนตัวล้าง = hash ของรีวิวเดิมทุกอันเปลี่ยน → ซ้ำทั้งฐาน
จึงตัดใน `DROP_LINE` ของทางสำรองเท่านั้น

**⚠️ `data-review-id` อยู่บนหลาย element ต่อรีวิวหนึ่งใบ**
ตัวนอกคือการ์ดเต็ม ตัวในคือบล็อกชื่อผู้รีวิว ถ้าไม่ dedupe ด้วยค่า id
จะได้รีวิวซ้ำ 2 เท่า (เทสจับได้: 20 ผลจากรีวิวจริง 10 ใบ)
`querySelectorAll` คืนตามลำดับเอกสาร = ตัวนอกมาก่อน จึงเก็บตัวแรกของแต่ละ id

**⚠️ ตรรกะหาวันที่ต้องตรงกัน 3 ที่**
`_extract_visible_reviews`, `_extract_cards_fallback` และ `_PAST_MARKERS` ใน
`scraper/date_parser.py` — แก้ที่ไหนต้องแก้ให้ครบ บนหน้าแบบโรงแรม span วันที่
เป็น `"3 เดือนที่แล้ว ใน"` แล้วมีบรรทัด `Google` หรือ `Tripadvisor` ต่อ
จึงต้องดึงเฉพาะวลีวันที่ออกมา ไม่เอาหางติดมา

**หมายเหตุ** listing แบบโรงแรมมีรีวิวจาก Tripadvisor ปนมาด้วย (เจอจริงที่
Baan Lhang Wangh) เป็นรีวิวของร้านนั้นจริง แต่ไม่ได้นับใน `google_reviews_total`
ทำให้ความครบถ้วนของร้านกลุ่มนี้อาจเกิน 100% ได้

**ที่ยังไม่แก้และเหตุผล**

กด "ดูเพิ่มเติม" เพื่อขยายรีวิวที่ถูกตัด และเพดาน `text.substring(0, 600)`
ของเราเอง — ทั้งสองอย่างทำให้ `text` ของรีวิวที่เก็บมาแล้วเปลี่ยน →
`text_hash` เปลี่ยน → รีวิวเดิมถูก INSERT ซ้ำ ต้องทำพร้อมแผน dedup แบบเทียบ
prefix ภายในร้านเดียวกัน จึงแยกเป็นงานอีกรอบ
(หลักฐานว่ามีเพดานจริง: รีวิว 57,671 อันในฐาน ยาวสุดแค่ 370 ตัวอักษร)

---

### ⚠️ ร้านติดวนลูปหัวคิว — บัญชีไม่ตรงระหว่างร้านที่ขอกับแถวที่เขียน

พบ 2026-09-27 ตอนตรวจว่าทำไม 12 รอบติดกันได้รีวิวใหม่ 0 อัน
(`scrape_jobs` id 231-242)

**อาการ** 18 ร้านมี `scraped_at IS NULL` แต่ `consecutive_no_change` = 13-43
ซึ่งขัดกันเอง — ถ้าไม่เคยบันทึกสำเร็จ cnc ก็ไม่ควรเพิ่ม

**สาเหตุ 2 ชั้น**

**ชั้นที่ 1 — upsert เขียนผิดแถว** `save_to_db` ใช้ `ON CONFLICT (name)` โดยส่ง
`result["place_name"]` ซึ่งเป็น**ชื่อจริงบนหน้าเว็บ** ไม่ใช่ชื่อที่คิวขอไป
สองค่านี้ไม่ตรงกันบ่อย เพราะการค้นด้วยชื่อบน Google Maps พาไปร้านอื่นได้

วัดจริงด้วยการไล่ `search_query` ของแถวที่ถูกเขียน:

| คิวขอไป | ผลลัพธ์ไป landed ที่ | ห่าง |
|---|---|---|
| `ร้านอาหารปักษ์ใต้` | แอ่นแอ๊นขนมจีนปักใต้คาเฟ่ | **8.8 กม.** |
| `ร้านอาหารปักษ์ใต้` | เขยนครแกงใต้ | 5.3 กม. |
| `Pizza Hut` | พิซซ่าฮัท สาขา พิษณุโลก | 1.9 กม. |
| `Jong Rak` | จงรัก | 961 ม. |
| `RongHuk` | โรงฮัก | 480 ม. |
| `Amarin Nakorn: Rice Porridge` | โจ๊กอัมรินทร์นคร (เจ้าเก่า) | 0 ม. |

แถวที่ขอไปจึงไม่ถูกแตะ `scraped_at` คง NULL แล้วค้างหัวคิวถาวร
(`ORDER BY scraped_at ASC NULLS FIRST`)

**ชั้นที่ 2 — ไม่มีอะไรหยุดการวน**

| กลไก | ทำไมไม่ทำงาน |
|---|---|
| cooldown 7-30 วัน | ใช้กับสาขา `scraped_at < NOW() - interval` เท่านั้น · `scraped_at IS NULL` ข้ามไปเลย |
| `refresh_shortfalls` | ธง `_reviews_failed` ตั้งเฉพาะเมื่อได้ผลลัพธ์ที่มี 0 รีวิว ไม่ตั้งเมื่อ `scrape_place` คืน `None` → 17 จาก 18 ร้านมี sf = 0 |
| `consecutive_no_change` | `update_scan_stats` รับ `place_names` ทั้งชุดที่ขอไป จึงบวกให้ร้านที่ไม่เคยถูกบันทึก → พุ่งถึง 43 อย่างไร้ความหมาย |

**ผลกระทบ** `places[:max_places]` ตัดจากหัวคิว → ทุกรอบที่ `--limit` ≤ 18
ถูกกลุ่มนี้กินสล็อตทั้งหมด ปิดกั้นรีวิว 3,917 อัน

**แก้แล้ว 3 จุดใน `scraper/scraper.py`**

1. `update_scan_stats` รับเฉพาะร้านที่บันทึกสำเร็จจริง — ทั้ง
   `result["place_name"]` และ `result["search_query"]` ไม่ใช่ `place_names` ทั้งชุด
2. แถวที่ขอไปแต่ผลลัพธ์ไป landed แถวอื่น (`search_query != place_name`) →
   ตี `scraped_at = NOW()` ให้ เพื่อออกจากหัวคิว รีวิวอยู่ใต้แถวชื่อจริงแล้ว
   ส่วนแถวซ้ำให้ `merge_duplicate_places.py` รวมทีหลังตามพิกัด
3. ร้านที่ไม่คืนผลลัพธ์เลย (`scrape_place` คืน `None`) → นับ
   `refresh_shortfalls` +1 ชุดเดียวกับเคส "เก็บได้ 0 รีวิว" ให้เพดาน
   `REFRESH_MAX_SHORTFALLS` ทำงาน = เลิกตามเองหลัง 3 ครั้ง

**ล้างค่าที่ค้าง** — `scripts/fix_stuck_queue.py`

ล้าง `consecutive_no_change` เป็น 0 แต่**ไม่แตะ `scraped_at`** (คง NULL ให้ถูก
หยิบมาทำต่อ ซึ่งปลอดภัยแล้วเพราะตัวนับใหม่จะจับได้) และ**ไม่แตะ
`refresh_shortfalls`** (ประวัติความล้มเหลวจริงต้องเก็บไว้)

ทำไมต้องล้าง cnc: `cnc >= 3` = cooldown 30 วัน ถ้าปล่อย 43 ไว้ ร้านพวกนี้
พอ scrape สำเร็จครั้งแรกจะถูกเว้น 30 วันทันที ทั้งที่เพิ่งเริ่มเก็บ

```powershell
uv run python scripts\fix_stuck_queue.py            # DRY-RUN
uv run python scripts\fix_stuck_queue.py --apply
```

**ยังไม่ได้ทำ: ค้นด้วย `google_place_id` แทนชื่อ**
ทดสอบแล้วว่า `https://www.google.com/maps/place/?q=place_id:<id>` เปิดร้านถูก
ทุกครั้ง และร้านทั้ง 18 มี `google_place_id` ครบ วิธีนี้ตัดปัญหาชั้นที่ 1
ที่ต้นเหตุ แต่แตะทางเดินหลักของ scraper จึงควรแยกทำและทดสอบต่างหาก

---

### ⚠️ deep scan ตีว่า "สำเร็จ" ทั้งที่ดึงมาได้ 2%

พบ 2026-10-01 ตอนวิเคราะห์ว่าร้านไหนเก็บไม่ครบเพราะอะไร

**เกณฑ์เดิม** ใน `run_deep_scan`:

```python
scraped_ok = bool(saved_ids) and not sig and not reviews_failed and collected > 0
```

`collected > 0` อ่อนเกินไป — ดึงมาได้ 10 อันจากร้านที่ Google มี 7,028
ก็ถูกตี `deep_scanned_at` ว่าเสร็จถาวร

**ความเสียหายที่วัดได้** 11 จาก 164 ร้านที่ถูกตีว่า deep แล้ว (6.7%)
ดึงมาได้ไม่ถึง 50% ของเพดาน ปิดกั้นรีวิวไว้ 5,517 อัน:

| ร้าน | Google | ดึงมาได้ | % |
|---|---|---|---|
| พระพุทธชินราช | 7,028 | **14** | 2% |
| พระราชวังจันทน์ | 1,424 | 21 | 2% |
| อุทยานแห่งชาติภูหินร่องกล้า | 3,289 | 108 | 13% |
| ครัวท่าโพธิ์ | 845 | 202 | 24% |
| พังกี่ข้าวมันไก่ | 791 | 200 | 25% |
| ร้านแกงบ้านเรา | 466 | 10 | 2% |

ทุกร้านมี `deep_attempts = 0` คือไม่เคยถูกนับว่าล้มเหลวเลย และตรวจพิกัดแล้ว
**ไม่มีแถวแฝดที่เก็บรีวิวไว้** — รีวิวยังไม่ถูกเก็บจริง

`พระพุทธชินราช` คือแหล่งท่องเที่ยวที่มีรีวิวมากสุดในฐาน

**กลไก** deep scroll ได้หน้าแรกราว 10 การ์ด แล้ว Google ไม่ส่งมาเพิ่ม →
ตัวนับ node ไม่โต → ชน `DEEP_NO_GROWTH_LIMIT` → หยุด → `collected = 10 > 0`

**แก้แล้ว — เกณฑ์เทียบสัดส่วน `DEEP_MIN_RATIO = 0.5`**

```python
ceil = LEAST(google_reviews_total, 850)   # อ่านจาก saved_ids ไม่ใช่ชื่อที่ขอ
enough = collected > 0 and (ceil == 0 or collected >= DEEP_MIN_RATIO * ceil)
scraped_ok = bool(saved_ids) and not sig and not reviews_failed and enough
```

**ทำไม 0.5** ร้านที่ deep สำเร็จจริงได้เฉลี่ย **86%** ของเพดาน (มัธยฐาน 94%)
วัดจาก 117 ร้าน ดังนั้น 50% เป็นพื้นหย่อนพอจะไม่ตีร้านที่ Google เสิร์ฟไม่เต็ม
ว่าล้มเหลว แต่ยังจับเคส 2-25% ได้หมด — ทดสอบแล้วจับ 11 ร้านและไม่แตะ 147 ร้าน
ที่สำเร็จจริง

**`ceil == 0` ยกเว้นให้** ร้านที่ Places API ไม่มี `google_reviews_total` ให้
ตัดสินสัดส่วนไม่ได้ จึงใช้เกณฑ์เดิม `collected > 0`

**นับ `deep_attempts` ให้เคสนี้ด้วย** — เดิมนับเฉพาะ "เข้าไม่ถึงหน้ารีวิว"
ถ้าไม่นับ ร้านที่ดึงได้ไม่ถึงเกณฑ์จะถูกลองใหม่ไม่รู้จบ ตอนนี้ครบ
`DEEP_MAX_ATTEMPTS` (3) แล้วย้ายไปกลุ่ม "ยอมแพ้" ซึ่ง `--given-up` ยังเห็นได้
ต่างจากเดิมที่ถูกตี `deep_scanned_at` แล้วหายจากทุกเกณฑ์ยกเว้น `gap`

**ล้างค่าที่ค้าง** — `scripts/fix_false_deep.py`

ตั้ง `deep_scanned_at = NULL` ให้ร้านที่ไม่ผ่านเกณฑ์ใหม่ **ไม่แตะ
`deep_attempts`** (ให้โอกาสใหม่ครบจำนวน) และไม่แตะรีวิว

ทำไมต้องล้างทั้งที่ `--targets gap` กู้ได้อยู่แล้ว: `gap` ไม่บังคับ
`deep_scanned_at IS NULL` จึงเห็นร้านกลุ่มนี้ แต่เกณฑ์อีก 4 ตัว
(`capped`/`zero`/`shallow`/`all`) บังคับ จึงข้ามถาวร และรายงาน
"deep แล้ว N ร้าน" สูงกว่าความจริงทำให้ประเมินงานที่เหลือผิด

```powershell
uv run python scripts\fix_false_deep.py            # DRY-RUN
uv run python scripts\fix_false_deep.py --apply
uv run python scripts\why_incomplete.py            # ดูว่าเหลืออะไรเพราะอะไร
```

---

### ⚠️ พิกัดร้านผิด — อ่าน `@lat,lng` ซึ่งเป็นจุดกลางหน้าจอ ไม่ใช่พิกัดร้าน

พบ 2026-10-01 ตอน deep scan `พระบรมราชานุสาวรีย์สมเด็จพระนเรศวรมหาราช`
เก็บรีวิวได้ 321 อันแล้วถูกปฏิเสธว่า "อยู่นอกพิษณุโลก" ทั้งที่อยู่ใน ม.นเรศวร

**URL ของ Google Maps มีพิกัด 2 ชุดที่คนละความหมาย**

```
/maps/place/<ชื่อ>/@16.7494649,97.8843155,8z/data=...!3d16.7494649!4d100.1914444
                   └── จุดกลางหน้าจอ ──┘ └ซูม┘       └─ พิกัดร้านจริง ─┘
```

`extract_place_coords()` เดิมอ่านแต่ `@lat,lng` พอ Google เปิดหน้าร้านแบบ
ซูมออก จุดกลางหน้าจออยู่ห่างจากร้านมาก วัดจากหน้าจริง:

| ร้าน | ซูม | `@viewport` lng | `!3d!4d` lng | ห่าง |
|---|---|---|---|---|
| พระบรมราชานุสาวรีย์ฯ | **8z** | 97.884 | 100.191 | **247 กม.** |
| OASIS CAFE | **7z** | 95.673 | 100.288 | **~500 กม.** |
| พระพุทธชินราช | 16z | 100.2531 | 100.2621 | 964 ม. |

**ละติจูดมักตรงเป๊ะ** เพราะแผงข้อมูลด้านซ้ายเบียดแผนที่ในแนวนอนเท่านั้น
พิกัดจึงดูถูกต้อง ตรวจด้วยตาเปล่าจับไม่ได้

**ผลกระทบ 2 ทาง**
1. ถ้าลองจิจูดที่เพี้ยนตกนอกกรอบจังหวัด → `is_in_phitsanulok()` ปฏิเสธ →
   **ทิ้งรีวิวที่เก็บมาแล้วทั้งชุด** (เคสนี้ 321 อัน ใช้เวลาเก็บ 56 วินาที)
2. ถ้าตกในกรอบ → ถูกบันทึกเป็นพิกัดจริง → `zone` และ `distance_nu_km` /
   `distance_psru_km` ผิดตามทั้งหมด

**แก้แล้ว** — `extract_place_coords()` เอา `!3d!4d` ก่อนเสมอ ถ้าไม่มีจึงใช้
`@lat,lng` และเฉพาะเมื่อซูม ≥ `_MIN_TRUSTED_ZOOM` (15z) ไม่งั้นคืน `None`
ปล่อยให้ผู้เรียกข้ามร้านนั้น — ดีกว่าบันทึกพิกัดผิดแล้วเชื่อว่าถูก

**ความเสียหายที่วัดได้** — เทียบพิกัดในฐานกับ Places API 745 จาก 771 ร้าน (97%)

| ระยะคลาด | ร้าน | % |
|---|---|---|
| 0-50 ม. (ปกติ) | 611 | 91.3% |
| 100-500 ม. | 11 | 1.6% |
| 500 ม.-2 กม. | 12 | 1.8% |
| 2-10 กม. | 32 | 4.3% |
| เกิน 10 กม. | 4 | 0.5% |

**64 ร้านเพี้ยนเกิน 100 ม.** มากสุด 15,438 ม. และ **22 ร้านอยู่ผิดโซน**
(`CozycafeNU` ถูกจัดเป็น `other` ทั้งที่อยู่รอบ ม.นเรศวร)

ลายเซ็นยืนยัน: ลองจิจูดในฐาน**น้อยกว่า**ของ API ทุกราย (เบนไปทางตะวันตก)
และหลายร้านคลาดเท่ากันเป๊ะ (7,677 ม. ที่ 3 ร้าน · 3,837 ม. ที่ 8 ร้าน)
= ถูก scrape ในรอบเดียวกันโดยหน้าจอแผนที่อยู่ตำแหน่งเดิม

**ซ่อมด้วย `scripts/verify_coords.py`**

แหล่งความจริง 2 ทาง เรียงตามต้นทุน:
1. `place_candidates.lat/lng` — พิกัดจาก Nearby Search ที่เก็บไว้ตอน discover **ฟรี** (669 ร้าน)
2. `place_details(place_id)` — ยิง API 1 คำขอ/ร้าน (76 ร้าน = $1.90)

ซ่อม `location` แล้วคำนวณ `zone` + `distance_*` ใหม่ **เฉพาะร้านที่ซ่อม**
ไม่แตะนิยาม `ZONES` และไม่แตะร้านอื่น — ต่างจากการรัน `assign_zones.py` ทั้งระบบ

```powershell
uv run python scripts\verify_coords.py --use-api            # ตรวจและรายงาน
uv run python scripts\verify_coords.py --use-api --apply    # ซ่อม
```

---

### ⚠️ `backfill_place_id` ค้นด้วย `search_query` ที่ไม่ใช่ชื่อร้านนั้น

เดิมใช้ `search_query` ก่อน `name` เสมอ ด้วยเหตุผลว่า `search_query` คือข้อความ
ที่ค้นเจอร้านนี้จริง — **แต่เหตุผลนั้นใช้ไม่ได้เมื่อสองค่าไม่ตรงกัน**

`save_to_db` upsert ด้วย `ON CONFLICT (name)` โดยใช้ชื่อจริงบนหน้าเว็บ ถ้าการค้น
ด้วย `search_query` พาไปโผล่ที่ร้านอื่น แถวใหม่จะถูกสร้างด้วยชื่อของร้านที่โผล่
ส่วน `search_query` ยังค้างเป็นคำค้นเดิมที่ไม่ใช่ชื่อร้านนี้:

| id | `name` | `search_query` |
|---|---|---|
| 3639 | โรงฮัก | `RongHuk` |
| 4438 | พิซซ่าฮัท สาขา พิษณุโลก | `Pizza Hut` |
| 3512 | จงรัก | `Jong Rak` |

ค้นด้วย `search_query` จึงหาไม่เจอทุกครั้ง — **23 จาก 26 ร้านที่ไม่มี
`google_place_id` มี `name` ไม่ตรงกับ `search_query`**

**แก้แล้ว** — `name <> search_query` → ใช้ `name` เพราะเป็นชื่อที่ Google
แสดงจริงสำหรับแถวนั้น ทดสอบด้วย API แล้วเจอครบ **8/8 ร้าน** ชื่อที่ API คืน
ตรงกับ `name` เป๊ะทุกราย และเผยว่าร้านกลุ่มนี้มีรีวิวที่ยังไม่เก็บอีกเยอะ
(โรงฮัก 366 · พิซซ่าฮัท 338 · สถานีรถไฟพิษณุโลก 284 · ลดาบุฟเฟต์ 216)

**⚠️ ร้านที่ไม่มี `place_id` ไม่ใช่ "ร้านที่หลุดเข้ามาและควรลบ"**
ทดสอบแล้วเป็นร้านจริงในขอบเขตเกือบทั้งหมด ลบทิ้งจะเสียรีวิว 871 อัน
และแถวใน `snapshot_places` 13 ร้าน (ฐานอ้างอิงเทียบก่อน-หลัง)
ร้านที่นอกขอบเขตจริงให้ใช้ `scrape_excluded` ไม่ใช่ DELETE

```powershell
uv run python scripts\backfill_place_id.py --limit 30
uv run python scripts\exclude_places.py --exclude 1185 953 --apply
```

---

### ⚠️ ค้นด้วยชื่อพาไปผิดร้าน — ต้องนำทางด้วย `google_place_id`

พบ 2026-10-02 จากข้อสังเกตของผู้ใช้ว่าร้านบางกลุ่ม deep scan ไม่ขึ้นสักที
และค้นชื่อบน Google Maps แล้วได้ "รายการทั้งประเทศ" ไม่ใช่ร้านเฉพาะเจาะจง

**ปัญหา** `scrape_place()` เดิมค้นด้วย `/maps/search/<ชื่อร้าน>` แล้วคลิกลิงก์
`/maps/place/` อันแรกที่เจอ ชื่อที่กำกวมจึงพาไปร้านอื่นได้ทั้งประเทศ

**วัดจากหน้าจริง — รัน `scrape_place()` ตัวจริงเทียบสองทาง**

| ร้านที่ขอ | ค้นด้วยชื่อ → ได้ | ด้วย `place_id` → ได้ |
|---|---|---|
| `OASIS CAFE` | `โอเอซิส คอฟฟี่ (รางน้ำ)` **(13.761, 100.537) กรุงเทพ** | `OASIS CAFE` (16.841, 100.251) พิษณุโลก |
| `นัทเบเกอรี่` | `นัทเบเกอรี่` **(13.763, 100.546) กรุงเทพ** ⭐4.3 | `นัทเบเกอรี่` (16.821, 100.269) พิษณุโลก ⭐4.7 |

เคส `นัทเบเกอรี่` อันตรายที่สุด — **ชื่อเหมือนกันเป๊ะ** แต่เป็นคนละร้านคนละ
จังหวัด ถ้าดูแค่ชื่อบนหน้าเว็บจะแยกไม่ออกเลย

**ความเสี่ยงที่ตัวกรองจับไม่ได้** ตอนนี้รอดเพราะ `is_in_phitsanulok()` ปฏิเสธ
พิกัดกรุงเทพ (lat 13.76 นอกกรอบ 16.35-17.35) ทำให้ได้ 0 รีวิวแทนที่จะได้
ข้อมูลผิด — **แต่ถ้าร้านชื่อซ้ำอยู่ในพิษณุโลกเอง จะถูกบันทึกเงียบ ๆ**

**ผลข้างเคียงที่โยงกับบั๊กพิกัด** ผลการค้นแบบรายการทำให้แผนที่ซูมออกเป็น 7-8z
→ `@lat,lng` ใน URL กลายเป็นจุดกลางประเทศไทย (ดูหัวข้อพิกัดร้านผิด)
URL ของ `place_id` เป็น **17z เสมอ** จึงปิดบั๊กนั้นที่ต้นเหตุไปด้วย

**แก้แล้ว**

```
scrape_place(page, name, ..., place_id=None)
  place_id มี  -> https://www.google.com/maps/place/?q=place_id:<id>  และข้ามการคลิกผลแรก
  place_id ไม่มี -> /maps/search/<ชื่อ> แล้วคลิกผลแรก (เหมือนเดิมทุกประการ)
```

- `run_scraper(place_ids={ชื่อ: place_id})` ส่งต่อ รูปแบบเดียวกับ `known_hashes_by_place`
- `scraper.load_place_ids(session, names)` โหลดแมปจากฐาน
- `run_refresh` และ `run_deep_scan` โหลดแมปแล้วส่งให้อัตโนมัติ
- **Selenium fallback ยังค้นด้วยชื่อ** — เป็นทางสำรองที่ใช้เมื่อ Playwright
  ล้ม 3 ครั้ง ไม่คุ้มจะแก้ตามทั้งคู่

ร้าน 745 จาก 771 มี `google_place_id` แล้ว ที่เหลือค้นด้วยชื่อเหมือนเดิม

**⚠️ ข้อแลกเปลี่ยน** ถ้า `place_id` ของแถวไหนชี้ผิดร้านอยู่แล้ว การนำทางด้วย
มันจะไปร้านผิด "อย่างมั่นใจ" แทนที่จะพลาดแบบสุ่ม — จึงต้องตรวจพิกัดให้สะอาด
ก่อน ตอนนี้ `verify_coords.py` ยืนยันแล้วว่า 99.7% คลาดไม่เกิน 50 ม.

```powershell
uv run python scripts\verify_coords.py --use-api     # ตรวจก่อนเชื่อ place_id
uv run python scripts\deep_scan.py --targets gap --limit 5
```

ดูบรรทัด `[place_id] เปิดตรงด้วย place_id N/M ร้าน` ตอน refresh และป้าย
`Searching: <ชื่อ>  [place_id]` ตอน deep เพื่อยืนยันว่าทำงาน

---

### แท็บรีวิวหายแบบสุ่ม — รับมือด้วยการโหลดหน้าใหม่แล้วลองซ้ำ

คำถามจากผู้ใช้ 2026-10-02: "ผม search ด้วยชื่อก็เจอ มีแถบรีวิวให้กด ทำไมของคุณไม่มี"

**คำตอบ: scraper เห็นแท็บเหมือนกัน แต่เห็นบ้างไม่เห็นบ้าง**

วัดด้วยการโหลดหน้าเดิมซ้ำ 3 รอบด้วยชุดเดียวกับ scraper:

| ร้าน | เจอแท็บรีวิว |
|---|---|
| แพตามสั่งนั่งชิว | 3/3 |
| OASIS CAFE | 3/3 |
| ก.ข้าวต้มกุ๊ย | **2/3** |

**ความต่างจากเบราว์เซอร์ผู้ใช้:** ผู้ใช้ล็อกอิน Google อยู่ มีคุกกี้และประวัติ
Google จึงเชื่อถือและเสิร์ฟหน้าเต็มเสมอ ส่วน scraper เปิดแบบไม่ล็อกอิน
คุกกี้ว่าง จึงได้หน้าเต็มบ้างไม่เต็มบ้าง — ควบคุมไม่ได้ ต้องรับมือด้วยการลองซ้ำ

**⚠️ สิ่งที่ไม่ใช่สาเหตุ** ครั้งแรกผมทดสอบรอบเดียวแล้วสรุปว่าการกด Escape
(`dismiss_login_modal`) ทำให้แท็บหาย พอทดสอบซ้ำ 3 รอบ/แบบ ได้ผลเท่ากันทั้ง
กดและไม่กด — **Escape ไม่เกี่ยว** บันทึกไว้กันคนอื่นหลงทางซ้ำ

**จุดอ่อนจริงคือจำนวน request ไม่ใช่ตรรกะ**

`open_reviews_tab()` มี 4 ชั้น แต่ทั้ง 4 ชั้นทำงานบนหน้าเดียวกัน และ reload
แค่ 1 ครั้ง = ได้ request ใหม่แค่ 2 ครั้ง ร้านที่ถูกนับว่า "เข้าไม่ถึงหน้ารีวิว"
คือร้านที่พลาดติดกัน 2 ครั้งพอดี

ถ้าโอกาสเจอแท็บต่อการโหลด 1 ครั้งราว 70%:

| โหลดใหม่กี่ครั้ง | โอกาสสำเร็จ |
|---|---|
| 2 (เดิม) | 91% |
| 3 | 97% |
| **4 (ตอนนี้)** | **99%** |

**แก้แล้ว** — `OPEN_TAB_RETRIES = 2` ใน `scraper_core.py`

เมื่อ `open_reviews_tab()` คืน `False` จะ **`page.goto()` ใหม่ทั้งหน้า** แล้วลองอีก
สูงสุด 2 ครั้ง หน่วง 5-8 วินาทีระหว่างครั้ง

ใช้ `goto` ไม่ใช่ `reload` เพราะต้องการ **request ใหม่หมด** ซึ่งเป็นตัวแปรที่
ตัดสินผล ไม่ใช่การ render ซ้ำจาก cache · และใช้ URL ที่ resolve แล้ว
(`/maps/place/...`) ไม่ใช่ URL ตั้งต้น จะได้ไม่ต้อง redirect ซ้ำ

**ต้นทุน** ร้านที่สำเร็จตั้งแต่ครั้งแรก (ส่วนใหญ่) ไม่เสียเวลาเพิ่มเลย

**⚠️ แก้แล้วแต่ยังมีคอขวดอีกชั้น** ทดสอบหลังแก้ 9 รอบ (3 ร้าน × 3) เปิดแท็บ
สำเร็จ 9/9 แต่**ดึงได้ร้านละ 5 รีวิวเท่านั้น** เพราะ Google เสิร์ฟการ์ดมาแค่ 5
และ scroll ไม่โต — เป็นการถูกจำกัดอัตราคนละชั้นกับแท็บรีวิว
การลองซ้ำช่วยเรื่อง "เข้าถึงแท็บ" ไม่ได้ช่วยเรื่อง "Google ยอมเสิร์ฟกี่อัน"

---

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

# เติม google_place_id จาก Places API (DRY-RUN ก่อน แล้วทดสอบ 5 ร้าน แล้วค่อยเต็ม)
uv run python scripts/backfill_place_id.py
uv run python scripts/backfill_place_id.py --limit 5
uv run python scripts/backfill_place_id.py --report

# ค้นหาร้านใหม่ด้วย Places Nearby Search (ลงตารางพัก place_candidates)
uv run python scripts/discover_api.py
uv run python scripts/discover_api.py --run --types cafe
uv run python scripts/discover_api.py --report

# เลื่อนร้านที่ผ่านเกณฑ์จากตารางพักเข้า places
uv run python scripts/promote_candidates.py
uv run python scripts/promote_candidates.py --reject-list
uv run python scripts/promote_candidates.py --details
uv run python scripts/promote_candidates.py --promote

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
