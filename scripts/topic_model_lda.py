"""
topic_model_lda.py — ค้นหาหมวดหมู่ Pain Point อัตโนมัติด้วย LDA
ใช้ scikit-learn (ไม่ต้อง compile C++)
"""

import asyncio
import os
import json
from pathlib import Path
from collections import Counter
from dotenv import load_dotenv

load_dotenv()

from pythainlp import word_tokenize
from pythainlp.corpus.common import thai_stopwords
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.decomposition import LatentDirichletAllocation
import asyncpg

# ── Config ───────────────────────────────────────────────────────────────────
NUM_TOPICS   = 12
TOP_WORDS    = 10
OUTPUT_DIR   = Path(__file__).parent.parent / "data" / "lda_output"

EXTRA_STOPS = {
    "ที่", "นี้", "ก็", "แต่", "และ", "หรือ", "ใน", "มา", "ไป", "ได้",
    "มี", "ไม่", "ว่า", "จาก", "เป็น", "นะ", "ครับ", "ค่ะ", "คะ", "นะครับ",
    "นะคะ", "มาก", "ดี", "สวย", "พิษณุโลก", "สถานที่", "ท่องเที่ยว",
    "ไว้", "อยู่", "ให้", "กัน", "แล้ว", "ด้วย", "ตรง", "แถว", "ใกล้",
    "ไกล", "เลย", "เดิน", "อีก", "ครั้ง", "ก่อน", "หลัง", "พอ",
    "เพราะ", "เวลา", "วัน", "ปี", "เดือน", "สัปดาห์", "ตอน",
    "ทำ", "รู้สึก", "คิด", "อยาก", "ต้อง", "ควร", "ร้าน", "แห่ง",
    "cafe", "coffee", "คาเฟ่", "มา", "ไป", "ได้", "ว่า",
}
STOP_WORDS = frozenset(thai_stopwords()) | EXTRA_STOPS


# ── Helpers ──────────────────────────────────────────────────────────────────

def tokenize(text: str) -> str:
    """ตัดคำและคืนค่าเป็น string (สำหรับ CountVectorizer)"""
    tokens = word_tokenize(text, engine="newmm", keep_whitespace=False)
    filtered = [
        t for t in tokens
        if len(t) >= 2
        and t not in STOP_WORDS
        and not t.isdigit()
        and not t.isspace()
    ]
    return " ".join(filtered)


def label_topic(keywords: list[str]) -> str:
    """ตั้งชื่อหมวดจาก keyword อัตโนมัติ"""
    kw = set(keywords)
    rules = [
        ({"จอดรถ","ที่จอด","รถ","ถนน","จราจร","เดินทาง","ทาง"},  "การเดินทางและที่จอดรถ"),
        ({"สกปรก","ขยะ","กลิ่น","ห้องน้ำ","เหม็น","สะอาด"},      "ความสะอาดและสิ่งแวดล้อม"),
        ({"แพง","ราคา","ค่า","คุ้มค่า","ค่าบริการ","ค่าเข้า"},    "ราคาและความคุ้มค่า"),
        ({"บริการ","พนักงาน","เจ้าหน้าที่","ช้า","รอ","คิว"},     "การบริการและการรอคิว"),
        ({"ลื่น","อันตราย","ชัน","ราวจับ","ปลอดภัย","เสี่ยง"},   "ความปลอดภัย"),
        ({"ที่นั่ง","ร่มเงา","ร้อน","แดด","ที่พัก","นั่ง"},       "สภาพแวดล้อมและที่นั่ง"),
        ({"ป้าย","บอกทาง","หลงทาง","ข้อมูล","แผนที่"},            "ป้ายและข้อมูล"),
        ({"แน่น","คนเยอะ","แออัด","วันหยุด","นักท่องเที่ยว"},     "ความแออัด"),
        ({"กาแฟ","เครื่องดื่ม","เมนู","อาหาร","รสชาติ","ขนม"},   "อาหารและเครื่องดื่ม"),
        ({"wifi","ปลั๊ก","สัญญาณ","อินเทอร์เน็ต","เน็ต"},         "สิ่งอำนวยความสะดวก"),
        ({"บรรยากาศ","ตกแต่ง","สวยงาม","ถ่ายรูป","โฟโต้","วิว"}, "บรรยากาศและการตกแต่ง"),
        ({"จอง","เปิด","ปิด","เวลา","วันจันทร์","วันหยุด"},       "เวลาทำการและการจอง"),
    ]
    for kw_match, label in rules:
        if kw & kw_match:
            return label
    return f"หมวดใหม่: {', '.join(keywords[:3])}"


# ── DB ───────────────────────────────────────────────────────────────────────

async def load_reviews() -> list[dict]:
    url = os.getenv("DATABASE_URL","").replace("postgresql+asyncpg","postgresql")
    conn = await asyncpg.connect(url)
    rows = await conn.fetch("""
        SELECT r.id, r.text, r.rating, p.name AS place_name
        FROM reviews r
        JOIN places p ON p.id = r.place_id
        WHERE r.text IS NOT NULL AND length(r.text) > 20
        ORDER BY r.id
    """)
    await conn.close()
    return [dict(r) for r in rows]


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 55)
    print(" LDA Topic Modeling — ค้นหาหมวดหมู่ Pain Point")
    print(f" จำนวน Topics: {NUM_TOPICS}  |  Keywords/Topic: {TOP_WORDS}")
    print("=" * 55)

    # 1. โหลดข้อมูล
    print("\n[1/5] โหลดรีวิวจาก Database...")
    reviews = await load_reviews()
    print(f"      ได้ {len(reviews)} รีวิว")

    if len(reviews) < 50:
        print("⚠️  ข้อมูลน้อยเกินไป รัน scraper เพิ่มก่อนครับ")
        return

    # 2. Tokenize
    print("\n[2/5] Tokenize ภาษาไทย...")
    docs_raw = []
    valid_reviews = []
    for r in reviews:
        tok = tokenize(r["text"])
        if len(tok.split()) >= 3:
            docs_raw.append(tok)
            valid_reviews.append(r)

    print(f"      ใช้ได้ {len(docs_raw)} รีวิว (ตัด {len(reviews)-len(docs_raw)} สั้นเกินไป)")

    # 3. Vectorize
    print("\n[3/5] สร้าง Vocabulary...")
    vectorizer = CountVectorizer(
        max_features=1000,   # เก็บแค่ 1000 คำที่พบบ่อยที่สุด
        min_df=3,            # ต้องพบในรีวิวอย่างน้อย 3 รีวิว
        max_df=0.85,         # ตัดคำที่พบใน 85%+ ของรีวิว (คำทั่วไปเกินไป)
    )
    X = vectorizer.fit_transform(docs_raw)
    vocab = vectorizer.get_feature_names_out()
    print(f"      Vocabulary: {len(vocab)} คำ")

    # 4. รัน LDA
    print(f"\n[4/5] รัน LDA (อาจใช้เวลา 1-3 นาที)...")
    lda = LatentDirichletAllocation(
        n_components=NUM_TOPICS,
        max_iter=20,
        learning_method="online",
        random_state=42,
        n_jobs=-1,           # ใช้ทุก CPU core
    )
    lda.fit(X)
    print("      เสร็จแล้ว ✅")

    # 5. แสดงผล
    print(f"\n[5/5] ผลลัพธ์")
    print("=" * 55)

    topics_data = []
    for i, topic in enumerate(lda.components_):
        top_idx = topic.argsort()[-TOP_WORDS:][::-1]
        keywords = [vocab[j] for j in top_idx]
        label = label_topic(keywords)
        topics_data.append({"id": i+1, "label": label, "keywords": keywords})

        print(f"\n  หมวด {i+1:2d}: {label}")
        print(f"  คำสำคัญ: {' | '.join(keywords)}")

    # 6. นับสัดส่วนรีวิวในแต่ละหมวด
    print("\n" + "=" * 55)
    print("  สัดส่วนรีวิวในแต่ละหมวด")
    print("=" * 55)
    doc_topics = lda.transform(X)
    dominant = doc_topics.argmax(axis=1)
    counts = Counter(dominant)
    total = len(docs_raw)

    print(f"\n  {'หมวด':<38} {'รีวิว':>6} {'%':>6}")
    print(f"  {'-'*38} {'-'*6} {'-'*6}")
    for i in sorted(counts, key=lambda x: -counts[x]):
        label = topics_data[i]["label"]
        n = counts[i]
        pct = n / total * 100
        bar = "█" * int(pct / 2)
        print(f"  {label:<38} {n:>6} {pct:>5.1f}%  {bar}")

    # 7. บันทึกผล JSON
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result = {
        "num_topics": NUM_TOPICS,
        "total_reviews": total,
        "topics": [
            {
                "id": t["id"],
                "label": t["label"],
                "keywords": t["keywords"],
                "review_count": counts.get(t["id"]-1, 0),
                "percent": round(counts.get(t["id"]-1, 0) / total * 100, 1),
            }
            for t in topics_data
        ]
    }
    out_path = OUTPUT_DIR / "lda_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n💾 บันทึกผลไปที่: {out_path}")
    print("\n✅ เสร็จสิ้น")
    print("\n💡 ถ้าผลยังไม่ดี ลองแก้ NUM_TOPICS = 8 หรือ 15 แล้วรันใหม่")


asyncio.run(main())
