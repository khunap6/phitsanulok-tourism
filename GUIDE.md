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
| Python | 3.12+ | จัดการด้วย `uv` |
| PostgreSQL | 16.x | + PostGIS extension |
| Google Chrome | ล่าสุด | สำหรับ Playwright / Selenium |
| Node.js | 18+ | สำหรับ React frontend |
| RAM | 4 GB+ | WangchanBERTa ต้องการ ~2 GB |

### ขั้นตอน

**1. Clone และติดตั้ง Python dependencies**

```bash
git clone https://github.com/<username>/phitsanulok-tourism.git
cd phitsanulok-tourism
uv sync
```

**2. สร้าง Database**

```sql
-- ใน pgAdmin หรือ psql
CREATE DATABASE phitsanulok_tourism;
```

**3. ตั้งค่า `.env`**

```env
DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@localhost:5432/phitsanulok_tourism
SYNC_DATABASE_URL=postgresql://postgres:PASSWORD@localhost:5432/phitsanulok_tourism
ANTHROPIC_API_KEY=your_key_here        # optional — ใช้ Claude สำหรับ NLP fallback
VITE_GOOGLE_MAPS_KEY=your_key_here     # สำหรับแผนที่ใน frontend
```

**4. Run Database Migration**

```bash
uv run alembic upgrade head
```

**5. ติดตั้ง Playwright Browser**

```bash
uv run playwright install chromium
```

**6. ติดตั้ง Frontend dependencies**

```bash
cd frontend
npm install
```

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

### การเก็บข้อมูล
- **Google Maps ToS**: การ scrape ขัดต่อข้อกำหนดการใช้งานของ Google เหมาะสำหรับงานวิจัย/วิชาการเท่านั้น ห้ามใช้เชิงพาณิชย์
- **DOM เปลี่ยนได้**: Google Maps อัปเดต UI บ่อย CSS selector ที่ใช้อาจพังได้ ต้องตรวจสอบเป็นระยะ
- **Rate Limiting**: อาจถูก CAPTCHA หรือ block ชั่วคราวถ้า scrape เร็วเกินไป ระบบมี delay แต่ไม่รับประกัน 100%
- **ภาษาไทยเป็นหลัก**: รีวิวภาษาอื่นอาจวิเคราะห์ได้ไม่แม่นยำ

### NLP
- **WangchanBERTa ใช้ทรัพยากรสูง**: โหลด model ครั้งแรก 1–3 นาที, ต้องการ RAM ~2 GB, ไม่มี GPU จะช้ามาก
- **Rule-based มีขอบเขต**: รีวิวที่ไม่มี keyword ตรงกันจะตกหมวด "อื่นๆ" เสมอ
- **Severity จาก rating**: ใช้คะแนนดาวเป็น proxy ไม่ใช่การวิเคราะห์ความรุนแรงจากเนื้อหา

### ระบบ
- **ต้องรัน server ค้างไว้**: APScheduler ทำงานได้เฉพาะเมื่อ `uvicorn` รันอยู่ ถ้า server หยุดก็จะไม่มี schedule
- **ไม่มี Authentication**: Admin endpoints ไม่มีการยืนยันตัวตน ไม่ควร expose ออก internet โดยตรง
- **พื้นที่พิษณุโลกเท่านั้น**: bounding box กำหนดไว้ตายตัว ต้องแก้โค้ดถ้าต้องการขยายพื้นที่
- **Google Maps API Key**: frontend ต้องการ key จาก Google Cloud Console (มี free tier จำกัด)

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
