"""
zones.py — Zone definitions for Phitsanulok area-based analysis

Zones:
  naresuan   — รอบมหาวิทยาลัยนเรศวร (~2 km)
  rajabhat   — รอบมหาวิทยาลัยราชภัฏพิบูลสงคราม ส่วนทะเลแก้ว (~2 km)
  city_center — ตัวเมืองพิษณุโลก (ริมน้ำน่าน / วัดใหญ่)
  other      — พื้นที่อื่นในพิษณุโลก

หมายเหตุ: พิกัด rajabhat แก้ไขจากเดิม (16.8301, 100.2544) ซึ่งชี้ไปที่
campus เก่า "วังจันทน์" (ใกล้ตัวเมือง ทับซ้อนกับ city_center) เป็นพิกัด
campus หลัก "ทะเลแก้ว" (16.8299369, 100.2075576) ที่มีนักศึกษาส่วนใหญ่จริง
ตรวจสอบผ่าน Google Maps เมื่อ 2026-07-15
"""

import math

# ---------------------------------------------------------------------------
# Zone definitions
# ---------------------------------------------------------------------------

ZONES: dict[str, dict] = {
    "naresuan": {
        "name_th": "รอบมหาวิทยาลัยนเรศวร",
        "center_lat": 16.7442,
        "center_lng": 100.1956,
        "radius_km": 2.0,
        "queries": [
            "คาเฟ่ มหาวิทยาลัยนเรศวร พิษณุโลก",
            "ร้านอาหาร มหาวิทยาลัยนเรศวร พิษณุโลก",
            "คาเฟ่ ท่าโพธิ์ พิษณุโลก",
            "สถานที่ท่องเที่ยว ใกล้มหาวิทยาลัยนเรศวร",
            "จุดถ่ายรูป ท่าโพธิ์ พิษณุโลก",
            "สวนสาธารณะ มหาวิทยาลัยนเรศวร",
        ],
    },
    "rajabhat": {
        "name_th": "รอบมหาวิทยาลัยราชภัฏพิบูลสงคราม (ทะเลแก้ว)",
        "center_lat": 16.8299369,
        "center_lng": 100.2075576,
        "radius_km": 2.0,
        "queries": [
            "คาเฟ่ ทะเลแก้ว พิษณุโลก",
            "ร้านอาหาร ทะเลแก้ว พิษณุโลก",
            "คาเฟ่ ใกล้ ราชภัฏพิบูลสงคราม",
            "สถานที่ท่องเที่ยว ใกล้ ราชภัฏพิบูลสงคราม ทะเลแก้ว",
        ],
    },
    "city_center": {
        "name_th": "ตัวเมืองพิษณุโลก",
        "center_lat": 16.8258,
        "center_lng": 100.2654,
        "radius_km": 2.0,
        "queries": [
            "คาเฟ่ ตัวเมืองพิษณุโลก",
            "สถานที่ท่องเที่ยว พิษณุโลก",
            "ร้านอาหาร ใจกลางเมือง พิษณุโลก",
            "ถนนคนเดิน พิษณุโลก",
        ],
    },
}

ZONE_LABELS = {
    "naresuan": "รอบ ม.นเรศวร",
    "rajabhat": "รอบ ม.ราชภัฏ",
    "city_center": "ตัวเมือง",
    "other": "อื่นๆ พิษณุโลก",
}


# ---------------------------------------------------------------------------
# Haversine distance
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """คำนวณระยะทางระหว่างสองจุดบนโลก (กิโลเมตร)"""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Zone assignment
# ---------------------------------------------------------------------------

def assign_zone(lat: float | None, lng: float | None) -> str:
    """
    กำหนดโซนจาก GPS coordinates
    คืน zone key ("naresuan" / "rajabhat" / "city_center" / "other")
    """
    if lat is None or lng is None:
        return "other"

    best_zone = "other"
    best_dist = float("inf")

    for zone_key, zone in ZONES.items():
        dist = _haversine_km(lat, lng, zone["center_lat"], zone["center_lng"])
        if dist <= zone["radius_km"] and dist < best_dist:
            best_dist = dist
            best_zone = zone_key

    return best_zone


def get_zone_label(zone: str) -> str:
    """คืนชื่อภาษาไทยของโซน"""
    return ZONE_LABELS.get(zone, "อื่นๆ")


def all_zone_queries() -> list[tuple[str, str]]:
    """คืน list ของ (zone_key, query) ทุกโซน"""
    pairs = []
    for zone_key, zone in ZONES.items():
        for q in zone["queries"]:
            pairs.append((zone_key, q))
    return pairs
