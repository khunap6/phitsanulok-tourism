"""project_paths.py — แหล่งความจริงเดียวของ path ทั้งโปรเจกต์

⚠️ ทำไมต้องมีไฟล์นี้
  โปรเจกต์นี้ถูกย้ายโฟลเดอร์มาแล้วจริง
  จาก D:\\Claude_Workspace\\New\\WebScraping\\phitsanulok-tourism
  มา   D:\\Workspace\\New\\WebScraping\\phitsanulok-tourism
  ตอนย้ายแล้วพบว่า run_commands.ps1 ยัง Set-Location ไป path เก่าที่ไม่มีอยู่แล้ว
  คือพังเงียบ ๆ ไม่มีอะไรฟ้อง จนกว่าจะรันแล้วหาไฟล์ไม่เจอ

  ไฟล์นี้ทำให้ย้ายเครื่องหรือย้ายโฟลเดอร์แล้ว **ไม่ต้องแก้โค้ดสักบรรทัด**
  และมีที่เดียวให้ตรวจว่าอะไรยังหาไม่เจอ

⚠️ หลักการ: path ในโปรเจกต์ห้ามเขียนแบบเต็ม
  PROJECT_ROOT คำนวณจากตำแหน่งของไฟล์นี้เอง ไม่ใช่ค่าคงที่
  path ย่อยทุกตัวต่อจาก PROJECT_ROOT
  ตรวจแล้วว่าสคริปต์ 40 ไฟล์ในโปรเจกต์คำนวณ root จากตำแหน่งตัวเองถูกหมด
  จึงไม่ต้องแก้ไฟล์เหล่านั้น ไฟล์นี้มีไว้สำหรับ
    1. path ภายนอกที่ขึ้นกับเครื่อง (PostgreSQL, cache) ซึ่งเลี่ยงไม่ได้
    2. สคริปต์ PowerShell ที่ไม่มีกลไกคำนวณ root แบบ Python
    3. ตัวตรวจว่าทุกอย่างอยู่ครบ (--check) ก่อนเริ่มงานบนเครื่องใหม่

⚠️ ลำดับการหาค่า path ภายนอก (จากสำคัญที่สุดไปน้อยที่สุด)
    1. ตัวแปรสภาพแวดล้อมของเชลล์ (ชนะทุกอย่าง — ใช้ override ชั่วคราวได้)
    2. ไฟล์ .env ในโปรเจกต์
    3. เดาจากตำแหน่งที่พบได้บ่อย (auto-detect)
    4. None = หาไม่เจอ ให้ผู้ใช้ตั้งเอง
  ⚠️ ห้ามใส่ค่าเริ่มต้นแบบเต็ม path ลงในโค้ด
    ถ้าใส่ เครื่องที่ไม่มี path นั้นจะได้ค่าที่ชี้ไปที่ไม่มีอยู่
    แล้วข้อความ error จะชี้ไปผิดทาง หายาก

รัน:
  uv run python project_paths.py            # รายงานสภาพ path ทั้งหมด
  uv run python project_paths.py --json     # ออกเป็น JSON ให้สคริปต์อื่นอ่าน
  uv run python project_paths.py --ps1      # ออกเป็นตัวแปร PowerShell
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

# ── รากของโปรเจกต์ ──────────────────────────────────────────────
#
# ⚠️ ไฟล์นี้ต้องอยู่ที่รากของโปรเจกต์เท่านั้น ถ้าย้ายไปโฟลเดอร์ย่อย
#   ต้องแก้บรรทัดนี้ด้วย ไม่งั้นทุก path จะเลื่อนไปหนึ่งชั้นทั้งระบบ
PROJECT_ROOT = Path(__file__).resolve().parent

# ── path ภายในโปรเจกต์ (ย้ายเครื่องแล้วไม่พัง) ──────────────────
API = PROJECT_ROOT / "api"
DB = PROJECT_ROOT / "db"
MIGRATIONS = DB / "migrations" / "versions"
NLP = PROJECT_ROOT / "nlp"
NLP_TRAIN = NLP / "train"
SCRAPER = PROJECT_ROOT / "scraper"
SCRIPTS = PROJECT_ROOT / "scripts"
SCHEDULER = PROJECT_ROOT / "scheduler"
SHARED = PROJECT_ROOT / "shared"
DOCS = PROJECT_ROOT / "docs"
FRONTEND = PROJECT_ROOT / "frontend"
FRONTEND_SRC = FRONTEND / "src"

DATA = PROJECT_ROOT / "data"
LABELING = DATA / "labeling"
MODELS = PROJECT_ROOT / "models"
REPORTS = PROJECT_ROOT / "reports"
EVALUATION = REPORTS / "evaluation"
BACKUP = PROJECT_ROOT / "backup"
LOGS = PROJECT_ROOT / "logs"

ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
# ⚠️ frontend มี .env ของตัวเองแยกจากราก
#   Vite อ่านได้แค่ไฟล์ใน frontend/ และแค่ตัวแปรที่ขึ้นต้นด้วย VITE_
#   คีย์แผนที่จึงอยู่ที่นี่ ไม่ใช่ที่ .env ราก ถ้าหาผิดที่จะคิดว่าคีย์หาย
FRONTEND_ENV = FRONTEND / ".env"
FRONTEND_ENV_EXAMPLE = FRONTEND / ".env.example"

# ── โมเดลที่ระบบใช้ตอนทำงานจริง ────────────────────────────────
#
# ⚠️ ชื่อโฟลเดอร์คือสัญญา สคริปต์เทรนเขียนทับโฟลเดอร์เดิมทุกครั้ง
#   ถ้าเปลี่ยนชื่อ ต้องแก้ OUT_DIR/START_FROM ใน nlp/train/* ด้วย
MODEL_CATEGORY_MULTILABEL = MODELS / "wangchanberta-category-multilabel"
MODEL_ASPECT_SENTIMENT = MODELS / "wangchanberta-aspect-sentiment"
MODEL_OVERALL_SENTIMENT = MODELS / "wangchanberta-overall-sentiment"
# สองตัวล่างเป็นจุดตั้งต้นของการเทรน (START_FROM) ไม่ได้ใช้ตอบคำถามผู้ใช้
MODEL_SENTIMENT_BASE = MODELS / "wangchanberta-sentiment"
MODEL_CATEGORY_BASE = MODELS / "wangchanberta-category"

# ── ไฟล์ตั้งค่าที่เป็นแหล่งความจริง ─────────────────────────────
#
# ⚠️ มีชุดหมวดสามรุ่นอยู่พร้อมกันโดยเจตนา อย่าลบตัวเก่า
#   v1 category_labels.json (12 หมวด) — ของเดิม ยังใช้ map ค่าเก่าในฐานข้อมูล
#   v2 categories.json      (11 หมวด) — รุ่นที่ api/frontend/nlp/db ใช้ตอนนี้
#   v3 categories_v3.json   (14 หมวด) — รุ่นที่กำลังทำ ยังอยู่แค่ใน scripts/
#   ดูว่าใครอ่านไฟล์ไหนได้จาก --check
CAT_V1 = SHARED / "category_labels.json"
CAT_V2 = SHARED / "categories.json"
CAT_V3 = SHARED / "categories_v3.json"
SENTIMENT_LABELS = SHARED / "sentiment_labels.json"
SCOPE = SHARED / "scope.json"


def _read_env_file() -> dict[str, str]:
    """อ่าน .env แบบง่าย ไม่พึ่ง python-dotenv เพื่อให้ --check รันได้เสมอ

    ⚠️ ไม่ expand ตัวแปรและไม่ลบ quote ซ้อน อ่านแบบตรงไปตรงมา
      ถ้า .env มีรูปแบบซับซ้อนกว่านี้ ให้ใช้ค่าจาก os.environ แทน
    """
    out: dict[str, str] = {}
    if not ENV_FILE.exists():
        return out
    for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


_ENV = _read_env_file()


def env(name: str, default: str | None = None) -> str | None:
    """ค่าจากเชลล์ก่อน แล้วค่อย .env แล้วค่อย default"""
    return os.environ.get(name) or _ENV.get(name) or default


# ── path ภายนอกที่ขึ้นกับเครื่อง ────────────────────────────────

def _first_existing(cands: list[Path]) -> Path | None:
    for c in cands:
        if c.exists():
            return c
    return None


def pg_bin() -> Path | None:
    """โฟลเดอร์ bin ของ PostgreSQL (ที่มี psql.exe / pg_dump.exe)

    ⚠️ บนเครื่องที่ใช้พัฒนาอยู่ psql **ไม่อยู่ใน PATH**
      พิมพ์ pg_dump เปล่า ๆ จะได้ "not recognized as the name of a cmdlet"
      จึงต้องเรียกด้วย full path เสมอ — ดูตัวอย่างใน run_commands.ps1

    ⚠️ ห้าม hardcode เวอร์ชัน เครื่องใหม่อาจลง PostgreSQL คนละเวอร์ชัน
      ฟังก์ชันนี้จึงไล่หาและเลือกเวอร์ชันสูงสุดที่เจอ
    """
    explicit = env("PG_BIN")
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None

    # ถ้าอยู่ใน PATH อยู่แล้วก็ใช้ที่นั่น
    which = shutil.which("psql")
    if which:
        return Path(which).parent

    found: list[tuple[int, Path]] = []
    for base in (Path("D:/PostgreSQL"), Path("C:/PostgreSQL"),
                 Path("C:/Program Files/PostgreSQL"),
                 Path("C:/Program Files (x86)/PostgreSQL")):
        if not base.is_dir():
            continue
        for child in base.iterdir():
            b = child / "bin"
            if (b / "psql.exe").exists() or (b / "psql").exists():
                try:
                    ver = int("".join(ch for ch in child.name if ch.isdigit()) or 0)
                except ValueError:
                    ver = 0
                found.append((ver, b))
    if not found:
        return None
    return max(found, key=lambda x: x[0])[1]


def psql() -> Path | None:
    b = pg_bin()
    if not b:
        return None
    return _first_existing([b / "psql.exe", b / "psql"])


def pg_dump() -> Path | None:
    b = pg_bin()
    if not b:
        return None
    return _first_existing([b / "pg_dump.exe", b / "pg_dump"])


def cache_dirs() -> dict[str, Path | None]:
    """โฟลเดอร์ cache ที่ตั้งให้ไปอยู่ไดรฟ์อื่นเพื่อไม่ให้ไดรฟ์ระบบเต็ม

    ⚠️ ถ้าไม่ได้ตั้ง ค่าเป็น None = ใช้ค่าเริ่มต้นของเครื่องมือนั้นเอง
      ซึ่งทำงานได้ปกติ แค่กินพื้นที่ไดรฟ์ผู้ใช้ ไม่ใช่ปัญหาต้องแก้
    """
    out: dict[str, Path | None] = {}
    for name in ("PLAYWRIGHT_BROWSERS_PATH", "HF_HOME", "UV_CACHE_DIR"):
        v = env(name)
        out[name] = Path(v) if v else None
    return out


def database_url(sync: bool = False) -> str | None:
    """⚠️ คืน URL ดิบซึ่งมีรหัสผ่านอยู่ข้างใน ห้าม print ลง log"""
    return env("SYNC_DATABASE_URL" if sync else "DATABASE_URL")


def redacted_database_url(sync: bool = False) -> str:
    """URL แบบซ่อนรหัสผ่าน สำหรับแสดงในรายงาน"""
    url = database_url(sync)
    if not url:
        return "(ไม่ได้ตั้ง)"
    if "@" not in url or "//" not in url:
        return url
    head, tail = url.split("//", 1)
    creds, host = tail.split("@", 1)
    user = creds.split(":", 1)[0]
    return f"{head}//{user}:***@{host}"


# ── ตัวตรวจ ────────────────────────────────────────────────────

# ไฟล์/โฟลเดอร์ที่ต้องมี ไม่มีแล้วระบบทำงานไม่ได้
REQUIRED = [
    ("โฟลเดอร์", API), ("โฟลเดอร์", DB), ("โฟลเดอร์", NLP),
    ("โฟลเดอร์", SCRIPTS), ("โฟลเดอร์", SHARED), ("โฟลเดอร์", FRONTEND_SRC),
    ("โฟลเดอร์", LABELING),
    ("ไฟล์", CAT_V1), ("ไฟล์", CAT_V2), ("ไฟล์", SENTIMENT_LABELS),
    ("ไฟล์", PROJECT_ROOT / "pyproject.toml"),
    ("ไฟล์", PROJECT_ROOT / "alembic.ini"),
]

# มีก็ดี ไม่มีก็ยังทำงานได้บางส่วน
OPTIONAL = [
    ("ไฟล์", ENV_FILE, "ไม่มีแล้วต่อฐานข้อมูลไม่ได้ — คัดลอกจาก .env.example"),
    ("ไฟล์", CAT_V3, "ชุดหมวด v3 ที่กำลังทำ ยังไม่ได้ใช้ตอนรันจริง"),
    ("ไฟล์", SCOPE, "นิยามขอบเขตงานวิจัย ใช้โดย api/filters.py และ migration 019"),
    ("โฟลเดอร์", MODELS, "ไม่มีแล้ววิเคราะห์รีวิวใหม่ไม่ได้ (เทรนใหม่ได้)"),
    ("โฟลเดอร์", PROJECT_ROOT / ".venv", "สร้างใหม่ด้วย uv sync"),
    ("โฟลเดอร์", FRONTEND / "node_modules", "สร้างใหม่ด้วย npm install ใน frontend/"),
    ("โฟลเดอร์", LOGS, "สร้างอัตโนมัติตอนรัน"),
    ("โฟลเดอร์", BACKUP, "สร้างอัตโนมัติตอนสำรองข้อมูล"),
    ("ไฟล์", FRONTEND_ENV,
     "ไม่มีแล้วแผนที่หน้าเว็บขึ้นข้อความแทนแผนที่ "
     "(ต้องมี VITE_GOOGLE_MAPS_KEY — Vite อ่านจาก frontend/.env เท่านั้น)"),
]

RUNTIME_MODELS = [
    ("หมวด (multi-label)", MODEL_CATEGORY_MULTILABEL),
    ("อารมณ์รายหมวด", MODEL_ASPECT_SENTIMENT),
    ("อารมณ์รวม", MODEL_OVERALL_SENTIMENT),
]


def p(msg: str = "") -> None:
    """พิมพ์แบบไม่ล้มถ้า console เป็น cp874 (ไทยบางตัวพิมพ์ไม่ได้)"""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


def check() -> int:
    """ตรวจทุก path แล้วคืนจำนวนปัญหาที่ต้องแก้"""
    problems = 0

    p("=" * 70)
    p("  รากของโปรเจกต์")
    p("=" * 70)
    p(f"  {PROJECT_ROOT}")
    p(f"  ที่อยู่ปัจจุบันของเชลล์: {Path.cwd()}")
    if Path.cwd().resolve() != PROJECT_ROOT:
        p("  หมายเหตุ: เชลล์ไม่ได้อยู่ที่รากโปรเจกต์ — สคริปต์ยังทำงานได้")
        p("            เพราะทุกตัวคำนวณ path จากตำแหน่งไฟล์ตัวเอง")

    p("")
    p("=" * 70)
    p("  ที่ต้องมี")
    p("=" * 70)
    for kind, path in REQUIRED:
        ok = path.exists()
        if not ok:
            problems += 1
        p(f"  {'มี   ' if ok else 'ขาด  '} {kind} {path.relative_to(PROJECT_ROOT)}")

    p("")
    p("=" * 70)
    p("  มีก็ดี")
    p("=" * 70)
    for kind, path, why in OPTIONAL:
        ok = path.exists()
        rel = path.relative_to(PROJECT_ROOT)
        p(f"  {'มี   ' if ok else 'ไม่มี '} {kind} {rel}")
        if not ok:
            p(f"         -> {why}")

    p("")
    p("=" * 70)
    p("  โมเดลที่ใช้ตอนทำงานจริง")
    p("=" * 70)
    for name, path in RUNTIME_MODELS:
        if not path.exists():
            p(f"  ไม่มี  {name}: {path.relative_to(PROJECT_ROOT)}")
            continue
        # ⚠️ โมเดลหมวดเก็บ config ไว้ใน thresholds.json ไม่ใช่ about.json
        meta = None
        for fn in ("about.json", "thresholds.json"):
            f = path / fn
            if f.exists():
                try:
                    meta = json.loads(f.read_text(encoding="utf-8"))
                    break
                except ValueError:
                    pass
        if meta is None:
            p(f"  มี    {name}: ไม่มี about.json/thresholds.json -> ย้อนทำซ้ำไม่ได้")
            continue
        seed, ep = meta.get("run_seed"), meta.get("epochs")
        if seed is None or ep is None:
            p(f"  มี    {name}: ไม่ได้บันทึก seed/epochs -> ย้อนทำซ้ำไม่ได้")
        else:
            p(f"  มี    {name}: seed={seed} epochs={ep}")

    p("")
    p("=" * 70)
    p("  path ภายนอกที่ขึ้นกับเครื่อง")
    p("=" * 70)
    b = pg_bin()
    if b:
        p(f"  พบ    PostgreSQL bin: {b}")
        for nm, f in (("psql", psql()), ("pg_dump", pg_dump())):
            p(f"        {'มี   ' if f else 'ขาด  '} {nm}: {f or '-'}")
    else:
        problems += 1
        p("  ขาด   PostgreSQL bin — หาไม่เจอทั้งใน PATH และที่ที่พบได้บ่อย")
        p("        แก้โดยตั้ง PG_BIN ใน .env เช่น PG_BIN=D:\\PostgreSQL\\16\\bin")
        p("        (ไฟล์สำรองฐานข้อมูลและ seed.sql ต้องใช้ pg_dump/psql)")

    for name, path in cache_dirs().items():
        if path is None:
            p(f"  ไม่ตั้ง {name} — ใช้ค่าเริ่มต้นของเครื่องมือ (ทำงานได้)")
        elif path.exists():
            p(f"  มี    {name}: {path}")
        else:
            problems += 1
            p(f"  ชี้ผิด {name}: {path} (ตั้งไว้แต่ไม่มีโฟลเดอร์นี้)")
            p("        แก้โดยสร้างโฟลเดอร์ หรือลบบรรทัดนั้นออกจาก .env")

    p("")
    p("=" * 70)
    p("  ฐานข้อมูล")
    p("=" * 70)
    for sync in (False, True):
        nm = "SYNC_DATABASE_URL" if sync else "DATABASE_URL"
        url = database_url(sync)
        if not url:
            problems += 1
            p(f"  ขาด   {nm} — ตั้งใน .env")
        else:
            p(f"  มี    {nm}: {redacted_database_url(sync)}")

    p("")
    p("=" * 70)
    p("  ชุดหมวดที่มีอยู่")
    p("=" * 70)
    for nm, f in (("v1 (ของเดิม)", CAT_V1), ("v2 (ใช้ตอนรันจริง)", CAT_V2),
                  ("v3 (กำลังทำ)", CAT_V3)):
        if not f.exists():
            p(f"  ไม่มี  {nm}: {f.name}")
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            problems += 1
            p(f"  เสีย  {nm}: {f.name} อ่านเป็น JSON ไม่ได้")
            continue
        n = len(d.get("categories") or d.get("keys") or [])
        p(f"  มี    {nm}: {f.name} version={d.get('version', '-')} {n} หมวด")

    problems += check_doc_paths()

    p("")
    p("=" * 70)
    if problems:
        p(f"  สรุป: มี {problems} เรื่องที่ต้องแก้ (ดูบรรทัดที่ขึ้น 'ขาด' หรือ 'ชี้ผิด')")
    else:
        p("  สรุป: path ครบทุกอย่าง")
    p("=" * 70)
    return problems


def check_doc_paths() -> int:
    """หา path ในเอกสารที่ชี้ไปไฟล์ที่ไม่มีอยู่

    ⚠️ ทำไมต้องตรวจ เคยเกิดจริงแล้ว
      คู่มือให้คนตรวจป้ายเขียนว่า "อ่านนิยามได้ที่
      reports/evaluation/sentiment_guideline.md" แต่ไฟล์นั้นไม่มีอยู่
      คนที่ทำตามคู่มือจึงไม่มีนิยามให้อ่านเลย และไม่มีอะไรฟ้อง
      เอกสารที่ชี้ไปไฟล์ผิดอันตรายกว่าเอกสารที่ไม่เขียนอะไร

    ⚠️ จับเฉพาะ path ที่อยู่ใน backtick และดูเหมือน path ของโปรเจกต์
      (มี / หรือ นามสกุลไฟล์) ถ้าจับกว้างกว่านี้จะได้ false positive เยอะ
      จนไม่มีใครอ่านผลลัพธ์

    ⚠️ ต้องลองหลาย base ก่อนตัดสินว่าขาด
      เอกสารบางฉบับเขียน path เทียบจากโฟลเดอร์ของตัวเอง เช่น
      docs/frontend_status.md เขียน `src/utils/categoryLabel.ts`
      ซึ่งหมายถึง frontend/src/utils/categoryLabel.ts
      ถ้าเทียบจากรากอย่างเดียวจะรายงานขาด 6 ไฟล์ที่มีอยู่จริง
      แล้วตัวตรวจนี้จะกลายเป็นตัวเตือนหลอกที่ไม่มีใครอ่าน
    """
    import re
    pat = re.compile(
        r"`([A-Za-z0-9_./-]+\.(?:py|json|csv|md|ts|tsx|sql|ps1|toml|ini|txt))`")
    # base ที่ยอมให้เทียบได้ นอกจากรากโปรเจกต์
    bases = [PROJECT_ROOT, FRONTEND, FRONTEND_SRC, SCRIPTS, NLP, API, REPORTS, DOCS]
    skip_dirs = ("node_modules", ".venv", ".git", "backup")
    missing: list[tuple[str, int, str]] = []
    checked = 0
    docs = [PROJECT_ROOT / "GUIDE.md", PROJECT_ROOT / "PROJECT_SUMMARY.md"]
    docs += sorted(DOCS.glob("*.md"))
    docs += sorted(REPORTS.rglob("*.md"))
    for doc in docs:
        if not doc.exists() or any(d in str(doc) for d in skip_dirs):
            continue
        for i, line in enumerate(
                doc.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            for m in pat.finditer(line):
                ref = m.group(1)
                # ข้ามชื่อไฟล์เปล่า ๆ ที่ไม่ได้ระบุที่อยู่ (อ้างลอย ๆ ไม่ใช่ path)
                if "/" not in ref:
                    continue
                checked += 1
                if not any((b / ref).exists() for b in bases):
                    missing.append((str(doc.relative_to(PROJECT_ROOT)), i, ref))
    p("")
    p("=" * 70)
    p("  path ในเอกสารที่ชี้ไปไฟล์ที่ไม่มีอยู่")
    p("=" * 70)
    p(f"  ตรวจ {checked} การอ้างอิง ใน {len(docs)} เอกสาร")
    if not missing:
        p("  ทุกการอ้างอิงชี้ไปไฟล์ที่มีอยู่จริง")
        return 0
    seen: set[str] = set()
    for doc, line, ref in missing:
        key = f"{doc}:{ref}"
        if key in seen:
            continue
        seen.add(key)
        p(f"  ขาด   {ref}")
        p(f"        อ้างใน {doc}:{line}")
    p(f"  รวม {len(seen)} การอ้างอิงที่ชี้ไปไฟล์ที่ไม่มี")
    return len(seen)


def as_dict() -> dict:
    """path ทั้งหมดในรูป dict สำหรับสคริปต์อื่นหรือภาษาอื่น"""
    proj = {k: str(v) for k, v in sorted(globals().items())
            if k.isupper() and isinstance(v, Path)}
    return {
        "project_root": str(PROJECT_ROOT),
        "paths": proj,
        "external": {
            "pg_bin": str(pg_bin() or ""),
            "psql": str(psql() or ""),
            "pg_dump": str(pg_dump() or ""),
            **{k: str(v or "") for k, v in cache_dirs().items()},
        },
        "database_url_redacted": redacted_database_url(),
        "sync_database_url_redacted": redacted_database_url(sync=True),
    }


def as_ps1() -> str:
    """ออกเป็นตัวแปร PowerShell

    ⚠️ มีไว้ให้ run_commands.ps1 เรียกใช้ เพื่อไม่ต้องเขียน path เต็มในสคริปต์
      วิธีใช้ใน PowerShell:
        uv run python project_paths.py --ps1 | Out-String | Invoke-Expression
    """
    d = as_dict()
    lines = [
        "# สร้างอัตโนมัติจาก project_paths.py — ห้ามแก้ตรงนี้",
        f'$PROJECT_ROOT = "{d["project_root"]}"',
    ]
    for k, v in d["paths"].items():
        lines.append(f'${k} = "{v}"')
    ext = d["external"]
    # ⚠️ ชื่อ $PG คงไว้ตามที่ run_commands.ps1 เดิมใช้ เพื่อไม่ต้องแก้ทุกบรรทัด
    lines.append(f'$PG = "{ext["pg_bin"]}"')
    lines.append(f'$PSQL = "{ext["psql"]}"')
    lines.append(f'$PGDUMP = "{ext["pg_dump"]}"')
    return "\n".join(lines)


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--json" in args:
        print(json.dumps(as_dict(), ensure_ascii=False, indent=2))
    elif "--ps1" in args:
        print(as_ps1())
    else:
        raise SystemExit(1 if check() else 0)
