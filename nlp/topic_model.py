"""
topic_model.py — Pain-point categorization
Primary: rule-based keyword matching (9 categories)
Optional: BERTopic for exploratory clustering (not used in main pipeline)
"""

PAIN_POINT_CATEGORIES: dict[str, list[str]] = {
    "การเดินทางและที่จอดรถ": ["จอดรถ", "เดินทาง", "ถนน", "ทาง", "รถ", "ที่จอด", "จราจร", "สัญญาณ"],
    "ความสะอาดและสิ่งแวดล้อม": ["สกปรก", "ขยะ", "กลิ่น", "ความสะอาด", "ห้องน้ำ", "เหม็น", "ทิ้ง"],
    "ราคาและความคุ้มค่า": ["แพง", "ราคา", "ค่าใช้จ่าย", "คุ้มค่า", "ค่าบริการ", "ค่าเข้า", "ค่า"],
    "การบริการและเจ้าหน้าที่": ["บริการ", "เจ้าหน้าที่", "พนักงาน", "ช่วยเหลือ", "ไม่สุภาพ", "หยาบ", "แนะนำ"],
    "ความปลอดภัย": ["อันตราย", "ลื่น", "ชัน", "ราวจับ", "ไม่ปลอดภัย", "เสี่ยง", "ระวัง"],
    "สิ่งอำนวยความสะดวก": ["ที่นั่ง", "ร้านอาหาร", "ร้านค้า", "อำนวยความสะดวก", "ร่มเงา", "น้ำดื่ม"],
    "ข้อมูลและป้ายบอกทาง": ["ป้าย", "ข้อมูล", "บอกทาง", "แผนที่", "อธิบาย", "ไม่ชัดเจน", "หลงทาง"],
    "ความแออัดและการจัดการ": ["แน่น", "คนเยอะ", "คิวยาว", "รอนาน", "แออัด", "จัดการ"],
    "พ่อค้าแม่ค้าและการรบกวน": ["คนขายของ", "รุม", "หลอก", "รบกวน", "ขายของ", "โฆษณา"],
}

ALL_CATEGORIES = list(PAIN_POINT_CATEGORIES.keys()) + ["อื่นๆ"]


def rule_based_categorize(text: str) -> list[str]:
    """
    Return all matching pain point categories for the given text.
    Falls back to ["อื่นๆ"] when no keywords match.
    """
    found = [
        cat for cat, keywords in PAIN_POINT_CATEGORIES.items()
        if any(kw in text for kw in keywords)
    ]
    return found if found else ["อื่นๆ"]


def severity_from_rating(rating: int | None) -> str:
    if rating is None:
        return "medium"
    if rating == 1:
        return "high"
    if rating == 2:
        return "medium"
    return "low"
