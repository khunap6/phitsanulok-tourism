"""verify_export_for_chat.py — ตรวจว่าชุด export_for_chat/ ยังตรงกับโปรเจคจริง

ทำไมต้องมีสคริปต์นี้
  ชุด export_for_chat/ เป็นสำเนาที่เอาไปคุยกับ AI ตอนเขียนเล่ม ถ้าตัวเลขในนั้น
  ไม่ตรงกับฐานข้อมูลจริง เล่มจะอ้างเลขผิดโดยไม่มีอะไรฟ้อง เคยเกิดแล้วหนึ่งครั้ง
  (แทนที่ตัวเลขแบบเหมาทั้งไฟล์ ทำให้สองค่าที่คนละความหมายกลายเป็นค่าเดียวกัน)

ตรวจ 3 ชั้น
  1. สำเนาตรงต้นฉบับไหม      — เทียบไฟล์กับต้นทางในโปรเจค
  2. ตัวเลขลอยไหม             — ทุกตัวเลขใน README ต้องสาวกลับไปถึง measurements.json
  3. ข้อเท็จจริงเชิงโครงสร้าง — จำนวน migration / ตาราง / router ฯลฯ ยังตรงไหม

⚠️ อ่านอย่างเดียวทั้งหมด ไม่แตะฐานข้อมูลและไม่แก้ไฟล์ใด ๆ

รัน:
  uv run python scripts/verify_export_for_chat.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT = ROOT.parent / "export_for_chat"

# ── ชั้นที่ 1: ไฟล์ที่ต้องตรงกับต้นฉบับเป๊ะ ──
# ยกเว้นบรรทัดเวลาที่สร้าง เพราะสำเนาถูกคัดลอกคนละวินาทีกับต้นฉบับ
MIRRORED = {
    "measurements.json": "reports/measurements.json",
    "measurements.md": "reports/measurements.md",
    "limitations.md": "docs/limitations.md",
    "model_config_decision.md": "docs/model_config_decision.md",
    "categories.json": "shared/categories.json",
    "categories_v3.json": "shared/categories_v3.json",
    "place_location_verify.csv": "reports/place_location_verify.csv",
    "gold_v3_guide.md": "reports/evaluation/gold_v3_guide.md",
    "seed_sweep_final.md": "reports/evaluation/seed_sweep_final.md",
}

# ไฟล์ที่เขียนเองในชุด export ไม่มีต้นฉบับให้เทียบ
AUTHORED = ["README.md", "architecture.md", "code_map.md", "decision_log.md",
            "glossary.md", "number_sources.md"]

TIMESTAMP_RE = re.compile(r"(generated_at|สร้างอัตโนมัติ)")

# ── ชั้นที่ 2: ตัวเลขที่ไม่ต้องสาวกลับไปถึง measurements.json ──
#
# ตัวเลขที่ "คำนวณต่อ" หรือ "ยกมาเพื่อบอกว่าห้ามใช้" ไม่ได้อยู่ใน measurements.json
# ตรง ๆ จึงต้องประกาศไว้ใน export_for_chat/number_sources.md พร้อมที่มา
# สคริปต์นี้อ่านรายการจากไฟล์นั้น ไม่ได้ฝังไว้ในโค้ด เพื่อให้ "ที่มาของเลข"
# อยู่กับชุดเอกสารที่เอาไปใช้จริง ไม่ใช่ซ่อนอยู่ในสคริปต์
SOURCES_DOC = "number_sources.md"
DECLARED_RE = re.compile(r"`([\d,]+(?:\.\d+)?)`")

# รูปแบบที่ไม่ใช่ผลการวัดเลย ตัดทิ้งก่อนสแกน (เหตุผลอยู่ใน number_sources.md ข้อ 5)
STRIP_PATTERNS = [
    re.compile(r"`[^`]*`"),                          # โค้ด/ชื่อไฟล์/ชื่อคอลัมน์
    re.compile(r"\d{4}-\d{2}-\d{2}"),                # วันที่ ISO
    re.compile(r"(?:ข้อ|หัวข้อ|บทที่|migration|ข้อที่)\s*\d+(?:\.\d+)*"),
    re.compile(r"(?:Python|PostgreSQL|React|Vite|TypeScript|SQLAlchemy|PostGIS"
               r"|Playwright|RTX|GTX|FastAPI)\s*[\d.]+"),
    re.compile(r"\bv\d+(?:\.\d+)*\b"),               # v2 / v3 / v3.2
    re.compile(r"\bหมวด\s*\d+(?:[–-]\d+)?"),          # หมวด 14 / หมวด 1–12
    re.compile(r"\bseed\s*\d+", re.I),
    re.compile(r"^#{1,6}\s*\d+(?:\.\d+)*"),          # เลขหัวข้อที่หัว markdown
    # เลข migration แบบ 017 018 019
    # ⚠️ ห้ามใช้ \b เฉย ๆ เพราะจะไปกินท่อนหลังของเลขหลักพัน เช่น 114,091 -> 091
    re.compile(r"(?<![\d,])0\d{2}(?![\d,])"),
]

# บรรทัดที่อ้างถึงหัวข้อ เลขแบบ X.Y ในบรรทัดนั้นคือเลขหัวข้อ ไม่ใช่ผลการวัด
SECTION_CONTEXT_RE = re.compile(r"ข้อ|หัวข้อ|บทที่")
SECTION_NUM_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\b")

NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def collect_numbers(obj, out):
    """ดึงค่าตัวเลขทุกตัวใน measurements.json ออกมาเป็นเซ็ต"""
    if isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_numbers(v, out)
    elif isinstance(obj, bool):
        pass
    elif isinstance(obj, (int, float)):
        out.add(float(obj))


def traceable(token: str, values: set[float]) -> bool:
    """ตัวเลขนี้สาวกลับไปถึง measurements.json ได้ไหม

    เทียบทั้งค่าดิบและค่าที่คูณ 100 เพราะเอกสารเขียนสัดส่วนเป็นร้อยละ
    (เก็บ 0.3121 แต่เขียน 31.21%) และเทียบที่จำนวนทศนิยมเท่าที่เอกสารเขียน
    """
    raw = token.replace(",", "")
    try:
        val = float(raw)
    except ValueError:
        return True
    dec = len(raw.split(".")[1]) if "." in raw else 0
    for v in values:
        for cand in (v, v * 100):
            if round(cand, dec) == round(val, dec):
                return True
    return False


def check_mirrors() -> list[str]:
    problems = []
    for name, rel in MIRRORED.items():
        copy = EXPORT / name
        src = ROOT / rel
        if not copy.exists():
            problems.append(f"ไม่มีไฟล์ในชุด export: {name}")
            continue
        if not src.exists():
            problems.append(f"ไม่พบต้นฉบับของ {name} ที่ {rel}")
            continue
        a = copy.read_bytes()
        b = src.read_bytes()
        if a == b:
            continue
        # ต่างแค่บรรทัดเวลาที่สร้าง = ยอมรับได้
        try:
            la = [l for l in a.decode("utf-8").splitlines() if not TIMESTAMP_RE.search(l)]
            lb = [l for l in b.decode("utf-8").splitlines() if not TIMESTAMP_RE.search(l)]
            if la == lb:
                continue
        except UnicodeDecodeError:
            pass
        problems.append(f"เนื้อหาต่างจากต้นฉบับ: {name} (ต้นฉบับ {rel}) — ต้องคัดลอกใหม่")
    return problems


def check_orphan_numbers() -> list[str]:
    meas = json.loads((EXPORT / "measurements.json").read_text(encoding="utf-8"))
    values: set[float] = set()
    collect_numbers(meas, values)

    sources = EXPORT / SOURCES_DOC
    if not sources.exists():
        return [f"ไม่มี {SOURCES_DOC} — ตรวจที่มาของตัวเลขไม่ได้"]
    declared = {m.replace(",", "")
                for m in DECLARED_RE.findall(sources.read_text(encoding="utf-8"))}

    problems = []
    for name in AUTHORED:
        path = EXPORT / name
        if not path.exists():
            problems.append(f"ไม่มีไฟล์ที่เขียนเอง: {name}")
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            scan = line
            for pat in STRIP_PATTERNS:
                scan = pat.sub(" ", scan)
            # ⚠️ ดูบริบทจาก line ตัวเต็ม ไม่ใช่ scan เพราะคำว่า "ข้อ" อาจถูก
            #   STRIP_PATTERNS ตัดไปแล้วพร้อมเลขหัวข้อตัวแรก
            if SECTION_CONTEXT_RE.search(line):
                scan = SECTION_NUM_RE.sub(" ", scan)
            for token in NUM_RE.findall(scan):
                raw = token.replace(",", "")
                if raw in declared:
                    continue
                if traceable(token, values):
                    continue
                problems.append(
                    f"{name}:{lineno} ตัวเลข {token} สาวกลับไม่ถึง — ไม่มีใน measurements.json "
                    f"และไม่ได้ประกาศที่มาไว้ใน {SOURCES_DOC}"
                )
    return problems


def check_structure() -> list[str]:
    """ข้อเท็จจริงเชิงโครงสร้างที่เอกสารอ้างไว้ ต้องยังตรงกับโค้ด"""
    problems = []
    facts = {
        "migration": (len(list((ROOT / "db/migrations/versions").glob("[0-9]*.py"))), 19),
        "ตาราง": ((ROOT / "db/models.py").read_text(encoding="utf-8").count("__tablename__"), 9),
        "router": (len([p for p in (ROOT / "api/routers").glob("*.py")
                        if p.name != "__init__.py"]), 7),
        "โมเดลที่ใช้ทำนาย": (sum(
            (ROOT / "models" / m).exists() for m in
            ("wangchanberta-overall-sentiment", "wangchanberta-category-multilabel",
             "wangchanberta-aspect-sentiment")), 3),
    }
    for label, (actual, expected) in facts.items():
        if actual != expected:
            problems.append(
                f"จำนวน{label} เปลี่ยนเป็น {actual} แต่เอกสารเขียนว่า {expected} "
                f"— ต้องแก้ architecture.md / code_map.md ให้ตรง"
            )

    n_scripts = len(list((ROOT / "scripts").glob("*.py")))
    if n_scripts != 84:  # 83 + ตัวสคริปต์ตรวจนี้เอง
        problems.append(
            f"จำนวนสคริปต์เปลี่ยนเป็น {n_scripts} แต่ code_map.md เขียนว่า 83 "
            f"(ไม่นับ verify_export_for_chat.py) — ต้องแก้ให้ตรง"
        )
    return problems


def main() -> int:
    print("ตรวจชุด export_for_chat/")
    print(f"  ต้นทางโปรเจค : {ROOT}")
    print(f"  ชุดที่ตรวจ    : {EXPORT}")
    print()

    if not EXPORT.exists():
        print(f"ไม่พบโฟลเดอร์ {EXPORT}")
        return 1

    sections = [
        ("1. สำเนาตรงต้นฉบับ", check_mirrors),
        ("2. ตัวเลขสาวกลับได้", check_orphan_numbers),
        ("3. โครงสร้างยังตรง", check_structure),
    ]

    total = 0
    for title, fn in sections:
        problems = fn()
        total += len(problems)
        mark = "ผ่าน" if not problems else f"พบ {len(problems)} จุด"
        print(f"[{mark}] {title}")
        for p in problems:
            print(f"        - {p}")
    print()
    if total == 0:
        print("ผ่านทั้งหมด — ชุด export_for_chat ตรงกับโปรเจคจริง")
        return 0
    print(f"พบปัญหารวม {total} จุด — แก้ก่อนเอาไฟล์ไปใช้เขียนเล่ม")
    return 1


if __name__ == "__main__":
    sys.exit(main())
