"""seed_categories.py — เติมตาราง categories จาก shared/categories.json

⚠️ แหล่งความจริงคือไฟล์ json ไม่ใช่ตารางในฐาน
  ตารางมีไว้ให้คิวรี join เอาชื่อได้โดยไม่ต้องฝังชื่อไทยลง SQL
  ถ้าแก้ json ต้องรันสคริปต์นี้ใหม่ให้ตรงกัน

⚠️ ใช้ upsert ไม่ใช่ลบแล้วใส่ใหม่
  review_aspects.category_id อ้างถึงตารางนี้ด้วย FK แบบ RESTRICT
  ถ้า DELETE แล้ว INSERT ใหม่จะลบแถวที่มีคนอ้างอยู่ไม่ได้ และถ้าลบได้
  ก็จะพา aspect หายไปด้วย — upsert ปลอดภัยกว่าและรันซ้ำได้

รัน:
  uv run python scripts/seed_categories.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import text

from db.database import AsyncSessionLocal, engine


def p(msg: str = "") -> None:
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("ascii", "replace").decode("ascii"), flush=True)


async def main() -> None:
    doc = json.loads((ROOT / "shared" / "categories.json").read_text(encoding="utf-8"))
    cats = doc["categories"]
    version = doc.get("version", "v2")

    async with AsyncSessionLocal() as s:
        for c in cats:
            await s.execute(text("""
                INSERT INTO categories (id, name, is_non_problem, version)
                VALUES (:id, :name, :np, :ver)
                ON CONFLICT (id) DO UPDATE
                   SET name = EXCLUDED.name,
                       is_non_problem = EXCLUDED.is_non_problem,
                       version = EXCLUDED.version
            """), {"id": c["id"], "name": c["name"],
                   "np": c["is_non_problem"], "ver": version})
        await s.commit()

        rows = (await s.execute(text(
            "SELECT id, name, is_non_problem FROM categories ORDER BY id"))).fetchall()

    p(f"เติมตาราง categories แล้ว {len(rows)} หมวด (เวอร์ชัน {version})")
    p("")
    p(f"{'id':>3}  {'หมวด':<42} เป็นปัญหาได้?")
    for r in rows:
        p(f"{r.id:>3}  {r.name:<42} {'ไม่ใช่' if r.is_non_problem else 'ใช่'}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
