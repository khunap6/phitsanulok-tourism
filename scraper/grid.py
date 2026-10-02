"""
grid.py — ซอยพื้นที่ค้นหาเป็นเซลล์วงกลมเล็ก ๆ สำหรับ Nearby Search

ทำไมต้องซอย:
  Nearby Search คืนผลได้สูงสุด 60 รายการต่อคำขอ (20 ต่อหน้า × 3 หน้า) ถ้ายิง
  จุดเดียวรัศมี 4 กม. ขอ type=cafe ในเขตตัวเมือง จะโดนตัดที่ 60 แน่นอน และ
  **เราจะไม่รู้ว่าขาดอะไรไป** เพราะ API ไม่บอกว่ามีทั้งหมดเท่าไร

  ซอยเป็นวงเล็กแล้วยิงทีละวง ทำให้แต่ละคำขอมีร้านน้อยกว่า 60 จึงได้ครบ
  และถ้าเซลล์ไหนยังได้ครบ 60 = สัญญาณว่ายังถูกตัด ต้องซอยเซลล์นั้นย่อยลงอีก
  (สคริปต์ discover บันทึก hit_cap ไว้ในตาราง discover_cells เพื่อจับกรณีนี้)

คณิตศาสตร์ที่ใช้ — การปูวงกลมให้คลุมพื้นที่แบบไม่มีรูโหว่:
  วางจุดศูนย์กลางบนแลตทิซสามเหลี่ยม (hex) ระยะเพื่อนบ้านใกล้สุด s
  รูที่ลึกที่สุดอยู่ที่จุดศูนย์กลางล้อมวงของสามเหลี่ยมแลตทิซ ห่างจากทั้ง 3 จุด
  เท่ากับ s/sqrt(3) ฉะนั้นวงรัศมี r คลุมครบเมื่อ  s <= r*sqrt(3)
  ใช้ s = r*sqrt(3) (หลวมที่สุดที่ยังคลุมครบ = จำนวนเซลล์น้อยที่สุด)
  ระยะระหว่างแถว = s*sqrt(3)/2 = 1.5r

  r = 1 กม. -> s = 1.732 กม., แถวห่าง 1.5 กม.

⚠️ บทเรียนจากบั๊กที่เคยเขียนผิด 2 จุด:

  (1) ขอบพื้นที่ต้องเผื่อเต็มรัศมีเซลล์ ไม่ใช่ครึ่ง
      จุดที่อยู่ขอบพื้นที่ (ระยะ R) อาจต้องใช้เซลล์ที่ศูนย์กลางห่างออกไปถึง r
      คือที่ระยะ R+r ถ้ากรองเซลล์ทิ้งที่ R+r/2 ขอบพื้นที่จะมีรูโหว่ที่ไม่ถูกค้น
      แล้วเราจะเชื่อผิดว่า "ค้นครบแล้ว" ซึ่งแย่กว่าการรู้ว่าขาด

  (2) หลายโซนต้องใช้แลตทิซ "อันเดียว" ไม่ใช่สร้างแยกโซนแล้วมาตัดที่ซ้ำ
      แลตทิซที่สร้างจากคนละจุดศูนย์กลางจะไม่เรียงตรงกัน เซลล์ในเขตทับซ้อน
      จะเยื้องกันเล็กน้อยจนตัดซ้ำไม่ได้ (วัดแล้วตัดได้ 0 เซลล์) = จ่ายเงินซ้ำฟรี
      ปูแลตทิซเดียวคลุมทุกโซนแล้วเก็บเฉพาะเซลล์ที่แตะพื้นที่เป้าหมาย จะได้
      จำนวนน้อยที่สุดโดยไม่มีรูโหว่ และผลเป็น deterministic (รันซ้ำได้เหมือนเดิม)

หมายเหตุ: ใช้การแปลง กม. -> lat/lng แบบเชิงเส้น ซึ่งคลาดเคลื่อนน้อยมาก
ในสเกลไม่กี่กิโลเมตรที่ละติจูด ~16.8 องศา (พิษณุโลก) จึงพอสำหรับงานนี้
"""
import math

# ความยาว 1 องศาที่ละติจูดกลางของพิษณุโลก
_KM_PER_DEG_LAT = 110.574


def _km_per_deg_lng(lat_deg: float) -> float:
    return 111.320 * math.cos(math.radians(lat_deg))


def _lattice_spacing(cell_radius_km: float) -> tuple[float, float]:
    """คืน (ระยะเพื่อนบ้าน s, ระยะระหว่างแถว) ที่คลุมครบแบบประหยัดสุด"""
    s = cell_radius_km * math.sqrt(3)
    return s, s * math.sqrt(3) / 2   # row_h = 1.5 * r


def hex_cells(
    center_lat: float,
    center_lng: float,
    area_radius_km: float,
    cell_radius_km: float = 1.0,
) -> list[tuple[float, float]]:
    """
    เซลล์ที่ปูคลุมวงกลม (center, area_radius_km) ให้ครบแบบไม่มีรูโหว่

    ใช้กับโซนเดียว — หลายโซนให้ใช้ union_cells() เพื่อไม่ให้เซลล์ซ้ำ
    """
    return union_cells([(center_lat, center_lng)], area_radius_km, cell_radius_km)


def union_cells(
    centers: list[tuple[float, float]],
    area_radius_km: float,
    cell_radius_km: float = 1.0,
) -> list[tuple[float, float]]:
    """
    ปูแลตทิซ "อันเดียว" คลุมทุกโซน แล้วเก็บเฉพาะเซลล์ที่จำเป็น

    เก็บเซลล์ที่ศูนย์กลางอยู่ในระยะ (area_radius + cell_radius) จากศูนย์โซนใดโซนหนึ่ง
    — เผื่อเต็มรัศมีเซลล์เพื่อให้ขอบพื้นที่ถูกคลุมครบ (ดูบทเรียนข้อ 1 หัวไฟล์)

    เพราะเป็นแลตทิซเดียว เซลล์ในเขตที่โซนทับกันจึงถูกนับครั้งเดียวโดยอัตโนมัติ
    ไม่ต้องตัดซ้ำด้วยระยะห่าง (ซึ่งทำไม่ได้จริง — ดูบทเรียนข้อ 2)
    """
    if cell_radius_km <= 0:
        raise ValueError("cell_radius_km ต้องมากกว่า 0")
    if not centers:
        return []

    s, row_h = _lattice_spacing(cell_radius_km)
    reach = area_radius_km + cell_radius_km

    # จุดยึดแลตทิซ = ค่ากลางของทุกศูนย์โซน (คงที่ -> ผลลัพธ์ deterministic)
    anchor_lat = sum(c[0] for c in centers) / len(centers)
    anchor_lng = sum(c[1] for c in centers) / len(centers)
    km_lng = _km_per_deg_lng(anchor_lat)

    # ระยะจากจุดยึดถึงศูนย์โซนที่ไกลสุด + reach = ขนาดแลตทิซที่ต้องปู
    span = reach + max(
        math.hypot((c[1] - anchor_lng) * km_lng, (c[0] - anchor_lat) * _KM_PER_DEG_LAT)
        for c in centers
    )

    # ศูนย์โซนในหน่วย กม. เทียบจุดยึด (ใช้เทียบระยะให้เร็ว)
    targets = [
        ((c[1] - anchor_lng) * km_lng, (c[0] - anchor_lat) * _KM_PER_DEG_LAT)
        for c in centers
    ]

    n_rows = int(span / row_h) + 2
    n_cols = int(span / s) + 2

    cells: list[tuple[float, float]] = []
    for i in range(-n_rows, n_rows + 1):
        y = i * row_h
        x_offset = s / 2 if i % 2 else 0.0
        for j in range(-n_cols, n_cols + 1):
            x = j * s + x_offset
            if not any(math.hypot(x - tx, y - ty) <= reach for tx, ty in targets):
                continue
            cells.append((
                round(anchor_lat + y / _KM_PER_DEG_LAT, 6),
                round(anchor_lng + x / km_lng, 6),
            ))
    return cells


def covers(
    cells: list[tuple[float, float]],
    point_lat: float,
    point_lng: float,
    cell_radius_km: float,
) -> bool:
    """จุดนี้ถูกเซลล์ใดเซลล์หนึ่งคลุมไหม — ใช้พิสูจน์ว่าไม่มีรูโหว่"""
    km_lng = _km_per_deg_lng(point_lat)
    for c_lat, c_lng in cells:
        dy = (point_lat - c_lat) * _KM_PER_DEG_LAT
        dx = (point_lng - c_lng) * km_lng
        if math.hypot(dx, dy) <= cell_radius_km:
            return True
    return False


def cell_key(lat: float, lng: float, radius_m: int) -> str:
    """คีย์ข้อความของเซลล์ — ใช้เก็บใน place_candidates.source_cell"""
    return f"{lat:.5f},{lng:.5f},{radius_m}"
