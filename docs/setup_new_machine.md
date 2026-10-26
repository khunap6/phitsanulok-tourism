# ย้ายเครื่อง / ย้ายโฟลเดอร์

ปรับปรุง 2026-10-19

> **คำสั่งเดียวที่ต้องจำ**
> ```bash
> uv run python project_paths.py
> ```
> บอกว่าอะไรครบ อะไรขาด และต้องแก้อะไร ถ้าขึ้น "path ครบทุกอย่าง" คือพร้อมใช้

---

## 1. ทำไมโปรเจกต์นี้ย้ายได้โดยไม่ต้องแก้โค้ด

**path ภายในโปรเจกต์ไม่มีการเขียนแบบเต็มเลย** สคริปต์ทุกตัวคำนวณรากโปรเจกต์
จากตำแหน่งไฟล์ตัวเอง (`Path(__file__).resolve().parent.parent`)
ตรวจแล้วว่า **40 ไฟล์ที่ทำแบบนี้ชี้มาที่รากถูกหมด**

สิ่งที่เหลือและขึ้นกับเครื่องมีแค่ 3 กลุ่ม ซึ่งอยู่ที่ `project_paths.py` ที่เดียว

| กลุ่ม | ตัวอย่าง | ถ้าไม่มี |
|---|---|---|
| โฟลเดอร์ bin ของ PostgreSQL | `D:\PostgreSQL\16\bin` | สำรองฐานข้อมูลไม่ได้ (ระบบอื่นยังทำงาน) |
| โฟลเดอร์ cache | `D:\AppCache\*` | ใช้ค่าเริ่มต้นของเครื่องมือ (ทำงานได้ แค่กินพื้นที่ไดรฟ์ระบบ) |
| ไฟล์ `.env` | รหัสฐานข้อมูล, API key | ต่อฐานข้อมูลไม่ได้ |

---

## 2. บทเรียนที่ทำให้ต้องมีไฟล์นี้

โปรเจกต์นี้ **ถูกย้ายโฟลเดอร์มาแล้วจริง**

```
จาก  D:\Claude_Workspace\New\WebScraping\phitsanulok-tourism
มา    D:\Workspace\New\WebScraping\phitsanulok-tourism
```

ตอนย้ายแล้วพบว่า `run_commands.ps1` ยัง `Set-Location` ไป path เก่าที่ไม่มีอยู่แล้ว
**พังเงียบ ๆ ไม่มีอะไรฟ้อง** จนกว่าจะรันแล้วหาไฟล์ไม่เจอ

และพบบั๊กซ่อนในไฟล์เดียวกัน บรรทัดกำหนด `$PG = "D:\PostgreSQL\16\bin"`
ถูกเขียน **ต่อท้ายคอมเมนต์ในบรรทัดเดียวกัน** จึงถูกคอมเมนต์ไปทั้งบรรทัด
ใครเปิดใช้คำสั่ง `pg_dump` ด้านล่างจะได้ `$PG` เป็นค่าว่าง
แล้วเรียก `"\pg_dump.exe"` ซึ่งไม่มีอยู่

ทั้งสองอย่างแก้แล้ว และตอนนี้ `run_commands.ps1` ดึง path จาก `project_paths.py`

---

## 3. ขั้นตอนบนเครื่องใหม่

### 3.1 ของที่ต้องลงก่อน

| เครื่องมือ | ตรวจด้วย | หมายเหตุ |
|---|---|---|
| Git | `git --version` | |
| uv | `uv --version` | ตัวจัดการ Python ของโปรเจกต์นี้ |
| Node.js 18+ | `node --version` | สำหรับหน้าเว็บ |
| PostgreSQL 16 + PostGIS | ดูข้อ 3.4 | ต้องมี PostGIS ด้วย ไม่ใช่ PostgreSQL เปล่า |

⚠️ **ไม่ต้องลง Python แยก** `uv sync` จะดึง Python 3.14 มาเองตาม `pyproject.toml`

### 3.2 โคลนและติดตั้ง

```bash
git clone https://github.com/khunap6/phitsanulok-tourism.git
cd phitsanulok-tourism
uv sync
cd frontend && npm install && cd ..
```

### 3.3 ตั้งค่า .env (มีสองไฟล์ อย่าลืมตัวที่สอง)

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env
```

⚠️ **`frontend/.env` เป็นไฟล์แยก** Vite อ่านได้แค่ไฟล์ใน `frontend/`
และแค่ตัวแปรที่ขึ้นต้นด้วย `VITE_` คีย์แผนที่จึงอยู่ที่นั่น ไม่ใช่ที่ `.env` ราก
ถ้าหาผิดที่จะคิดว่าคีย์หาย

ค่าที่ต้องกรอก

| ไฟล์ | คีย์ | ได้มาจาก |
|---|---|---|
| `.env` | `DATABASE_URL`, `SYNC_DATABASE_URL` | รหัส postgres ของเครื่อง |
| `.env` | `ANTHROPIC_API_KEY` | ใช้แค่ตอนติดป้ายชุดตัวอย่าง ไม่ใช้ตอนรันระบบ |
| `.env` | `GOOGLE_PLACES_API_KEY` | ใช้ดึงเวลาทำการ |
| `frontend/.env` | `VITE_GOOGLE_MAPS_KEY` | ต้องเปิด Maps JavaScript API |

### 3.4 ฐานข้อมูล

```bash
uv run python project_paths.py     # ดูว่าหา psql เจอไหม
```

ถ้าขึ้น `ขาด PostgreSQL bin` ให้ตั้งใน `.env`

```
PG_BIN=D:\PostgreSQL\16\bin
```

⚠️ **ไม่ต้องตั้งถ้าหาเจออยู่แล้ว** `project_paths.py` ไล่หาให้เอง
(ดูใน `PATH` ก่อน แล้วค่อยหาใน `D:\PostgreSQL\*`, `C:\PostgreSQL\*`,
`C:\Program Files\PostgreSQL\*` แล้วเลือกเวอร์ชันสูงสุดที่เจอ)
และ **ห้าม hardcode เวอร์ชัน** เครื่องใหม่อาจลงคนละเวอร์ชัน

สร้างฐานข้อมูล (ใช้ path ที่ `project_paths.py` หาได้)

```powershell
uv run python project_paths.py --ps1 | Out-String | Invoke-Expression
& "$PSQL" -U postgres -c "CREATE DATABASE phitsanulok_tourism;"
& "$PSQL" -U postgres -d phitsanulok_tourism -c "CREATE EXTENSION postgis;"
& "$PG\pg_restore.exe" -U postgres -d phitsanulok_tourism --no-owner --no-privileges "backup\seed.dump"
uv run alembic upgrade head
```

⚠️ **ต้อง `CREATE EXTENSION postgis;` ก่อน restore เสมอ**
ตาราง `places.location` เป็นชนิด geometry ถ้ายังไม่มี extension จะ restore ไม่ผ่าน

⚠️ `pg_restore` จะเตือนเรื่อง `spatial_ref_sys` ว่าข้อมูลซ้ำ
**ไม่ใช่ข้อผิดพลาด** เพราะ extension สร้างตารางนั้นไว้แล้ว ข้ามไปได้

| ไฟล์ | รูปแบบ | ขนาด | คำสั่ง restore |
|---|---|---|---|
| `backup/seed.dump` | custom บีบอัด | ~16 MB | `pg_restore` |
| `backup/seed.sql` | ข้อความล้วน (เก่า 30 ก.ย.) | 89.5 MB | `psql -f` |

ใช้ `seed.dump` เป็นหลัก ตัว `.sql` เก็บไว้เพื่อความเข้ากันได้ย้อนหลังเท่านั้น
และ **ข้อมูลในนั้นเก่ากว่า** คือยังไม่มีคอลัมน์ `in_scope` และยังไม่ได้วิเคราะห์ใหม่ทั้งฐาน

สร้าง dump รอบใหม่เมื่อข้อมูลเปลี่ยน

```powershell
uv run python project_paths.py --ps1 | Out-String | Invoke-Expression
$env:PGPASSWORD = "<รหัสใน .env>"
& "$PGDUMP" -U postgres -d phitsanulok_tourism -Fc -Z 9 --no-owner --no-privileges -f "backup\seed.dump"
```

### 3.5 โมเดล

โฟลเดอร์ `models/` **ไม่อยู่ใน git** (ใหญ่เกิน) มีสองทาง

1. คัดลอกโฟลเดอร์ `models/` มาจากเครื่องเดิมทั้งก้อน
2. เทรนใหม่ตาม `docs/model_config_decision.md` ซึ่งระบุ seed และ epoch ไว้ครบ
   จึงได้ผลเหมือนเดิมทุกค่า

⚠️ **ถ้าไม่มี `models/` ระบบยังเปิดได้** แค่วิเคราะห์รีวิวใหม่ไม่ได้
ข้อมูลที่วิเคราะห์ไว้แล้วอยู่ในฐานข้อมูล ไม่ได้อยู่ในโมเดล

### 3.6 ตรวจก่อนเริ่มงาน

```bash
uv run python project_paths.py                          # path ครบไหม
uv run python scripts/measure_everything.py             # ข้อมูลครบไหม
uv run python scripts/check_endpoints_after_migration.py # API ตอบถูกไหม
cd frontend && npx tsc --noEmit && npm run build         # หน้าเว็บ build ผ่านไหม
```

---

## 4. `project_paths.py` ใช้ยังไง

### ใน Python

```python
from project_paths import LABELING, MODELS, REPORTS, pg_dump

rows = (LABELING / "silver_aspects.csv").read_text(encoding="utf-8-sig")
```

⚠️ สคริปต์เดิม 40 ไฟล์ยังคำนวณ root เองอยู่ และ**ไม่ต้องแก้**
วิธีนั้นถูกต้องและย้ายเครื่องได้เหมือนกัน ไฟล์นี้มีไว้สำหรับ
path ภายนอก, สคริปต์ PowerShell, และตัวตรวจ

### ใน PowerShell

```powershell
uv run python project_paths.py --ps1 | Out-String | Invoke-Expression
# ได้ $PROJECT_ROOT $PG $PSQL $PGDUMP $DATA $MODELS $REPORTS $LABELING ฯลฯ
```

`run_commands.ps1` ทำบรรทัดนี้ให้แล้วที่หัวไฟล์

### ออกเป็น JSON

```bash
uv run python project_paths.py --json
```

---

## 5. ตัวตรวจทำอะไรให้

1. **รากโปรเจกต์** — บอกว่าคำนวณได้เป็นอะไร และเตือนถ้าเชลล์ไม่ได้อยู่ที่ราก
   (ไม่ใช่ปัญหา เพราะสคริปต์คำนวณจากตำแหน่งไฟล์ตัวเอง)
2. **ไฟล์/โฟลเดอร์ที่ต้องมี** — ขาดแล้วระบบทำงานไม่ได้
3. **ไฟล์ที่มีก็ดี** — ขาดแล้วบอกว่าเสียความสามารถอะไรและสร้างคืนยังไง
4. **โมเดล** — มีไหม และ **บันทึก seed/epochs ไว้ไหม**
   ถ้าไม่บันทึกคือย้อนทำซ้ำไม่ได้ ตัวเลขจากมันใช้อ้างในเล่มไม่ได้
5. **path ภายนอก** — หา PostgreSQL ให้ และบอกถ้า cache ตั้งไว้แต่ชี้ไปที่ไม่มีอยู่
6. **ฐานข้อมูล** — มี URL ไหม (แสดงแบบซ่อนรหัสผ่าน)
7. **ชุดหมวด** — มีกี่รุ่น แต่ละรุ่นกี่หมวด
8. **console script ใน `.venv` ยังเรียกได้ไหม** (ดูข้อ 6)
9. **path ในเอกสารที่ชี้ไปไฟล์ที่ไม่มีอยู่**

ข้อ 9 มีเพราะเคยเกิดจริง คู่มือให้คนตรวจป้ายเขียนว่าอ่านนิยามได้ที่
`reports/evaluation/sentiment_guideline.md` แต่ไฟล์นั้นไม่มีอยู่
คนที่ทำตามคู่มือจึงไม่มีนิยามให้อ่านเลย และไม่มีอะไรฟ้อง
**เอกสารที่ชี้ไปไฟล์ผิดอันตรายกว่าเอกสารที่ไม่เขียนอะไร**

⚠️ ตัวตรวจข้อ 9 ลองเทียบหลาย base (ราก, `frontend/`, `frontend/src/`,
`scripts/`, `nlp/`, `api/`, `reports/`, `docs/`) ก่อนตัดสินว่าขาด
เพราะเอกสารบางฉบับเขียน path เทียบจากโฟลเดอร์ของตัวเอง
ถ้าเทียบจากรากอย่างเดียวจะรายงานขาด 6 ไฟล์ที่มีอยู่จริง
แล้วตัวตรวจจะกลายเป็นตัวเตือนหลอกที่ไม่มีใครอ่าน

---

## 6. ปัญหาที่เจอจริงตอนย้ายโฟลเดอร์ — console script ใน .venv พังหมด

**อาการ**

```
uv run uvicorn api.main:app --reload --port 8000
error: uv trampoline failed to canonicalize script path
```

**สาเหตุ** ไฟล์ `.exe` ใน `.venv\Scripts` ที่ uv สร้างเป็น *trampoline*
ซึ่ง **ฝัง path เต็มของ `python.exe` ไว้ข้างในตัวไฟล์**
พอย้ายโฟลเดอร์ path ที่ฝังไว้ก็ชี้ไปที่ไม่มีอยู่

**จุดที่หลอกตาที่สุด** `uv run python` **ยังใช้ได้ปกติ**
เพราะ uv แก้ `python.exe` ให้เองตอนเรียก
แต่ `uv run uvicorn` / `uv run alembic` / `uv run playwright` พังหมด

ตอนตรวจเครื่องนี้หลังย้าย ทดสอบทั้ง 29 ตัวใน `.venv\Scripts`
**พังหมดทุกตัว** มีแต่ `python.exe` ที่ปกติ
ถ้าตรวจด้วย `uv run python` อย่างเดียวจะสรุปผิดว่า venv ใช้งานได้

**ทางแก้**

```bash
uv sync --reinstall
```

สร้าง trampoline ใหม่ทั้งหมด ใช้เวลาราว 1 นาที และ**ไม่ต้องโหลดแพ็กเกจใหม่**
ถ้ามี cache อยู่แล้ว (`UV_CACHE_DIR`)

ถ้าอยากแก้เฉพาะบางตัวเพื่อความเร็ว

```bash
uv sync --reinstall-package uvicorn --reinstall-package alembic
```

**ทางเลี่ยงชั่วคราว** `uv run python -m uvicorn api.main:app --reload --port 8000`
ใช้ได้เสมอเพราะไม่ผ่าน trampoline แต่ไม่ได้แก้ที่ต้นเหตุ

⚠️ `uv run python project_paths.py` ตรวจข้อนี้ให้แล้ว

---

## 7. ข้อจำกัดของตัวตรวจนี้เอง

1. **ไม่ได้ลองต่อฐานข้อมูลจริง** ตรวจแค่ว่ามี URL ตั้งไว้
   จะรู้ว่าต่อได้จริงต้องรัน `scripts/measure_everything.py`
2. **ไม่ได้ตรวจว่า API key ใช้ได้จริง** ตรวจแค่ว่ามีค่าอยู่
3. **ไม่ได้ตรวจเวอร์ชันของเครื่องมือ** เช่น PostgreSQL 15 กับ 16
   ตัวตรวจถือว่าผ่านเหมือนกัน แต่ `backup/seed.sql` อาจคืนค่าไม่ได้ข้ามเวอร์ชัน
4. **ตัวจับ path ในเอกสารจับเฉพาะที่อยู่ใน backtick** และมีนามสกุลไฟล์
   path ที่เขียนลอย ๆ ไม่มี backtick จับไม่ได้
5. **ไม่ตรวจ `models/` ว่าไฟล์น้ำหนักครบ** ตรวจแค่ว่ามีโฟลเดอร์และ metadata
