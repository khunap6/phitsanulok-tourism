"""
test_incremental.py — พิสูจน์ logic ของ incremental scan แบบ offline (ไม่ต่อเน็ต)

จำลองหน้าเว็บที่มีรีวิวอยู่ แล้วนับว่า scraper "scroll กี่รอบ" ในแต่ละสถานการณ์:
  A) รีวิวทั้งหมดเป็นของเดิม  → ควรหยุดทันที (scroll ~0 รอบ)
  B) มีรีวิวใหม่แทรกอยู่ด้านบน → ควร scroll ต่อจนโหลดครบ
  C) ร้านใหม่ (ไม่รู้ของเดิม)  → ควร scroll เต็มเหมือนเดิม

รัน: uv run python scripts/test_incremental.py
"""
import asyncio

from dotenv import load_dotenv
load_dotenv()

from scraper import scraper_core as sc


def safe_print(t: str) -> None:
    try:
        print(t)
    except UnicodeEncodeError:
        print(t.encode("ascii", errors="replace").decode("ascii"))


# ── หน้าเว็บปลอม: ไม่มีปุ่มแท็บ/จัดเรียง (count()=0) → ข้ามไปเลย ──
class _FakeLocator:
    async def count(self):
        return 0
    @property
    def first(self):
        return self
    async def click(self, **kw):
        raise RuntimeError("no button")
    def filter(self, **kw):
        return self


class FakePage:
    def locator(self, *a, **kw):
        return _FakeLocator()
    def get_by_role(self, *a, **kw):
        return _FakeLocator()


async def scenario(name: str, total_reviews: int, known_count: int, batch: int = 10):
    """
    total_reviews = จำนวนรีวิวทั้งหมดบนหน้า
    known_count   = จำนวนรีวิว "ท้ายรายการ" ที่เรามีอยู่แล้ว (ของเดิม)
                    → รีวิวใหม่ = total - known อยู่ด้านบน (เรียงใหม่ล่าสุด)
    """
    all_texts = [f"review-{i:03d}-" + "x" * 50 for i in range(total_reviews)]
    # ของเดิม = ท้ายรายการ (เก่ากว่า)
    known_hashes = {sc.review_text_hash(t) for t in all_texts[total_reviews - known_count:]} if known_count else set()

    state = {"loaded": batch, "scrolls": 0}

    async def fake_extract(page, cap):
        return [{"rating": 5, "text": t, "date": ""} for t in all_texts[: state["loaded"]]][:cap]

    async def fake_scroll(page, times=1):
        state["scrolls"] += times
        state["loaded"] = min(total_reviews, state["loaded"] + batch)

    orig_extract, orig_scroll = sc._extract_visible_reviews, sc.scroll_reviews
    sc._extract_visible_reviews, sc.scroll_reviews = fake_extract, fake_scroll
    try:
        reviews = await sc.extract_reviews(FakePage(), max_reviews=200, known_hashes=known_hashes)
    finally:
        sc._extract_visible_reviews, sc.scroll_reviews = orig_extract, orig_scroll

    safe_print(f"\n[{name}]")
    safe_print(f"  รีวิวบนหน้า {total_reviews} | ของเดิมที่รู้จัก {known_count}")
    safe_print(f"  → scroll {state['scrolls']} รอบ | ได้รีวิว {len(reviews)} อัน")
    return state["scrolls"]


async def main():
    safe_print("=" * 62)
    safe_print("ทดสอบ logic incremental scan (offline — ไม่ต่อเน็ต)")
    safe_print(f"เกณฑ์หยุด: เรียงสำเร็จ={sc.KNOWN_STOP_SORTED} / เรียงไม่สำเร็จ={sc.KNOWN_STOP_UNSORTED} อันติดกัน")
    safe_print("=" * 62)

    a = await scenario("A) ไม่มีรีวิวใหม่เลย (ของเดิมล้วน)", total_reviews=200, known_count=200)
    b = await scenario("B) มีรีวิวใหม่ 3 อันด้านบน", total_reviews=200, known_count=197)
    c = await scenario("C) ร้านใหม่ (ไม่รู้ของเดิม)", total_reviews=200, known_count=0)

    safe_print("\n" + "=" * 62)
    safe_print("สรุป")
    safe_print(f"  A ไม่มีของใหม่ : scroll {a:2d} รอบ")
    safe_print(f"  B มีของใหม่    : scroll {b:2d} รอบ")
    safe_print(f"  C ร้านใหม่     : scroll {c:2d} รอบ  (scan เต็ม)")
    ok = a < c and a <= 3
    safe_print(f"\n  {'✅ ผ่าน' if ok else '❌ ไม่ผ่าน'} — A ต้อง scroll น้อยกว่า C อย่างชัดเจน")
    if c > 0:
        safe_print(f"  ประหยัด scroll ได้ {(1 - a / c) * 100:.0f}% เมื่อไม่มีรีวิวใหม่")
    safe_print("=" * 62)


asyncio.run(main())
