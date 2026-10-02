"""
places_api.py — client กลางสำหรับ Google Places API (legacy endpoints)

ใช้ร่วมกันโดย:
  scripts/backfill_place_id.py   เติม google_place_id + ฟิลด์ API ให้ร้านเดิม
  scripts/discover_api.py        (ยังไม่มี — จะเพิ่ม nearby_search() ตอนทำขั้น 2)

ต้องมีใน .env:  GOOGLE_PLACES_API_KEY=xxxx

⚠️ หมายเหตุเรื่องโค้ดซ้ำ:
  scripts/fetch_hours_api.py มี _get() / _STATUS_MAP ของตัวเองอยู่แล้วและ
  **ทำงานได้ดีอยู่** จึงไม่ไปแก้ให้มา import จากไฟล์นี้ (ไม่มีเหตุให้เสี่ยงกับของที่ใช้ได้)
  ยอมรับว่าซ้ำกัน 2 ที่ ค่อยรวมเมื่อเส้นทางใหม่พิสูจน์แล้วว่าเสถียร

── เรื่อง fields ของ Find Place ที่ต้องพิสูจน์ด้วยการยิงจริง ──
เอกสาร legacy ระบุว่า findplacefromtext รับ fields ได้ทั้ง Basic (place_id, name,
geometry, formatted_address, types, business_status), Contact (opening_hours) และ
Atmosphere (rating, user_ratings_total) — ถ้าจริง จะได้ทุกอย่างในคำขอเดียวต่อร้าน
แต่เราไม่เขียนโค้ดบนสมมติฐาน: lookup_place() ลองฟิลด์เต็มก่อน ถ้า API ตอบ
INVALID_REQUEST จะถอยไปใช้ findplacefromtext(place_id) + place/details แล้ว
**จำการตัดสินใจไว้ในตัวแปรระดับโมดูล** เพื่อไม่ต้องเสียคำขอลองซ้ำทุกร้าน
ผลลัพธ์รายงานผ่านคีย์ "_path" ให้สคริปต์พิมพ์ออกมาได้ว่าใช้เส้นทางไหนจริง
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

from dotenv import load_dotenv

load_dotenv()

# ใช้ตัวเดียวกับ scraper เพื่อให้รูปแบบ opening_hours ตรงกันเป๊ะ
# (รูปแบบมีความหมาย: คั่น 7 วันด้วย '|' / "ทุกวัน HH:MM-HH:MM" / "ไม่ระบุ")
from scraper.scraper_core import _parse_weekly_hours

API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()

FIND_URL = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

# ฟิลด์ที่เราต้องการ — ตรงกับ 6 อย่างที่ต้องเก็บ (ชื่อ พิกัด ที่อยู่ เวลา เรตติ้ง จำนวนรีวิว)
# + types สำหรับจัดหมวด และ business_status สำหรับตัวกรองสถานะร้าน
_WANTED = ("place_id,name,geometry,formatted_address,types,"
           "business_status,rating,user_ratings_total,opening_hours")
_FIND_MINIMAL = "place_id"

# ราคาต่อคำขอ (USD) — ใช้ประเมินคร่าว ๆ เท่านั้น
# ⚠️ Google เปลี่ยนโครงสร้างราคา/โควตาฟรีเป็นระยะ ต้องเปิดหน้า pricing ใน
#    Google Cloud Console ยืนยันเองก่อนยิงจำนวนมาก ตัวเลขนี้ไม่ใช่สัญญา
COST_PER_REQUEST_USD = 0.025

BUSINESS_STATUS_MAP = {
    "OPERATIONAL": "operational",
    "CLOSED_TEMPORARILY": "closed_temporarily",
    "CLOSED_PERMANENTLY": "closed_permanently",
}

# จำว่า Find Place รับฟิลด์เต็มได้ไหม — None = ยังไม่รู้, True/False = พิสูจน์แล้ว
_find_supports_full: bool | None = None

# นับคำขอที่ยิงออกไปจริงทั้งหมดในโปรเซสนี้ (ใช้บังคับเพดาน --max-requests)
request_count = 0


class PlacesApiError(RuntimeError):
    """ยิง API ไม่สำเร็จในระดับ HTTP/JSON (ไม่ใช่กรณี status != OK ซึ่งคืนเป็น dict)"""


def require_api_key() -> None:
    if not API_KEY:
        raise PlacesApiError(
            "ไม่พบ GOOGLE_PLACES_API_KEY ใน .env — ใส่คีย์ก่อน "
            "(เปิด Places API + ผูก billing ใน Google Cloud)"
        )


def _get(url: str, params: dict) -> dict:
    """ยิง GET แล้วคืน JSON — นับคำขอทุกครั้งที่ออกไปจริง"""
    global request_count
    full = url + "?" + urllib.parse.urlencode({**params, "key": API_KEY})
    request_count += 1
    try:
        with urllib.request.urlopen(full, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise PlacesApiError(f"HTTP {e.code} จาก {url.rsplit('/', 2)[-2]}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise PlacesApiError(f"เชื่อมต่อไม่ได้: {e}") from e
    except json.JSONDecodeError as e:
        raise PlacesApiError(f"ตอบกลับไม่ใช่ JSON: {e}") from e


def _normalize(payload: dict) -> dict:
    """แปลงผลจาก API ให้เป็นรูปที่ตรงกับคอลัมน์ในตาราง places"""
    loc = ((payload.get("geometry") or {}).get("location") or {})
    weekday = (payload.get("opening_hours") or {}).get("weekday_text") or []
    types = payload.get("types") or []
    return {
        "place_id": payload.get("place_id"),
        "name": payload.get("name"),
        "lat": loc.get("lat"),
        "lng": loc.get("lng"),
        "formatted_address": payload.get("formatted_address"),
        # เก็บเป็น CSV ตามที่คอลัมน์ google_types เป็น Text
        "types": ",".join(types) if types else None,
        "types_list": types,
        "business_status": BUSINESS_STATUS_MAP.get(payload.get("business_status", "")),
        "rating": payload.get("rating"),
        "user_ratings_total": payload.get("user_ratings_total"),
        # None = Google ไม่ได้ให้เวลามา (ต่างจาก "ไม่ระบุ" ที่สคริปต์เดิมใช้เป็น sentinel)
        "opening_hours": _parse_weekly_hours(weekday) if weekday else None,
    }


def find_place(query: str, lat=None, lng=None, fields: str = _WANTED) -> dict:
    """
    ค้นร้านจากข้อความ คืน {"_status": ..., **ฟิลด์ที่ normalize แล้ว}
    ใส่ locationbias เมื่อมีพิกัด เพื่อกันจับผิดร้านที่ชื่อซ้ำกันต่างจังหวัด
    """
    params = {"input": query, "inputtype": "textquery",
              "fields": fields, "language": "th"}
    if lat is not None and lng is not None:
        # radius 2000 ม. แคบพอจะไม่ข้ามอำเภอ แต่กว้างพอรับพิกัดที่ scrape มาคลาดเคลื่อน
        params["locationbias"] = f"circle:2000@{lat},{lng}"

    data = _get(FIND_URL, params)
    status = data.get("status", "UNKNOWN")
    if status != "OK" or not data.get("candidates"):
        return {"_status": status if status != "OK" else "ZERO_RESULTS"}

    out = _normalize(data["candidates"][0])
    out["_status"] = "OK"
    out["_candidates"] = len(data["candidates"])
    return out


def place_details(place_id: str, fields: str = _WANTED) -> dict:
    """ดึงรายละเอียดจาก place_id คืนรูปเดียวกับ find_place()"""
    data = _get(DETAILS_URL, {"place_id": place_id, "fields": fields, "language": "th"})
    status = data.get("status", "UNKNOWN")
    if status != "OK":
        return {"_status": status}
    out = _normalize(data.get("result") or {})
    out["_status"] = "OK"
    return out


def lookup_place(query: str, lat=None, lng=None) -> dict:
    """
    หาข้อมูลร้านให้ครบในทางที่ถูกที่สุดเท่าที่ API ยอม

    เส้นทาง A (1 คำขอ): find_place ด้วยฟิลด์เต็ม
    เส้นทาง B (2 คำขอ): find_place(place_id) แล้ว place_details — ใช้เมื่อ A ถูกปฏิเสธ

    คืน dict พร้อมคีย์ "_path" = "find_full" | "find+details" ให้ผู้เรียกรายงานได้
    """
    global _find_supports_full

    if _find_supports_full is not False:
        res = find_place(query, lat, lng, fields=_WANTED)
        if res["_status"] != "INVALID_REQUEST":
            # ไม่ใช่ปัญหาเรื่องฟิลด์ → เส้นทาง A ใช้ได้ (แม้ผลจะเป็น ZERO_RESULTS ก็จริง)
            if _find_supports_full is None:
                _find_supports_full = True
            res["_path"] = "find_full"
            return res
        # INVALID_REQUEST = ฟิลด์ชุดนี้ไม่ได้รับอนุญาต → จำไว้ ไม่ลองซ้ำอีก
        _find_supports_full = False

    res = find_place(query, lat, lng, fields=_FIND_MINIMAL)
    if res["_status"] != "OK":
        res["_path"] = "find+details"
        return res

    det = place_details(res["place_id"])
    det["_path"] = "find+details"
    return det


# ---------------------------------------------------------------------------
# Nearby Search — ใช้ตอน discover (ขั้น 2)
# ---------------------------------------------------------------------------

# Nearby Search คืนได้ 20 รายการ/หน้า สูงสุด 3 หน้า = 60 รายการ
NEARBY_PAGE_SIZE = 20
NEARBY_MAX_PAGES = 3
NEARBY_CAP = NEARBY_PAGE_SIZE * NEARBY_MAX_PAGES

# next_page_token ของ Google ใช้งานได้หลังหน่วงสั้น ๆ ถ้ายิงเร็วเกินจะได้
# INVALID_REQUEST ทั้งที่ token ถูก — หน่วงแล้วลองซ้ำก่อนจะสรุปว่าพัง
NEARBY_PAGE_DELAY_SEC = 2.0
NEARBY_PAGE_RETRIES = 3


def nearby_search(lat: float, lng: float, radius_m: int,
                  place_type: str) -> dict:
    """
    ค้นร้านรอบจุดหนึ่งตามประเภท — ดึงทุกหน้าที่มี (สูงสุด 3 หน้า)

    คืน {
        "results": [ผลที่ normalize แล้ว],
        "pages":   จำนวนคำขอที่ยิงจริง (1-3),
        "hit_cap": True ถ้าได้ครบ 60 (= น่าจะถูกตัด ต้องซอยเซลล์ย่อย),
        "_status": "OK" | "ZERO_RESULTS" | สถานะผิดพลาดอื่น,
    }

    ⚠️ ตัวเลข pages คือค่าใช้จ่ายจริง ไม่ใช่ 1 คำขอต่อเซลล์ — เซลล์ที่มีร้าน
    เยอะจะยิง 3 คำขอ ผู้เรียกต้องใช้ค่านี้คุมงบ ไม่ใช่นับจำนวนเซลล์
    """
    import time as _time

    params = {"location": f"{lat},{lng}", "radius": int(radius_m),
              "type": place_type, "language": "th"}

    results: list[dict] = []
    pages = 0
    token: str | None = None
    status = "OK"

    while pages < NEARBY_MAX_PAGES:
        if token:
            # หน้า 2-3 ส่งแค่ pagetoken (Google ไม่สนพารามิเตอร์อื่นแล้ว)
            page_params = {"pagetoken": token}
            data = None
            for attempt in range(NEARBY_PAGE_RETRIES):
                _time.sleep(NEARBY_PAGE_DELAY_SEC)
                data = _get(NEARBY_URL, page_params)
                pages += 1
                if data.get("status") != "INVALID_REQUEST":
                    break
                # token ยังไม่พร้อม — รอนานขึ้นแล้วลองอีก
            if data is None or data.get("status") != "OK":
                # ได้ของหน้าก่อน ๆ มาแล้ว ถือว่าจบแบบไม่สมบูรณ์
                status = (data or {}).get("status", "PAGE_FAIL")
                break
        else:
            data = _get(NEARBY_URL, params)
            pages += 1
            status = data.get("status", "UNKNOWN")
            if status == "ZERO_RESULTS":
                return {"results": [], "pages": pages, "hit_cap": False,
                        "_status": "ZERO_RESULTS"}
            if status != "OK":
                return {"results": [], "pages": pages, "hit_cap": False,
                        "_status": status}

        for item in data.get("results") or []:
            row = _normalize(item)
            # Nearby Search ให้ vicinity (ที่อยู่ย่อ) แทน formatted_address
            row["vicinity"] = item.get("vicinity")
            results.append(row)

        token = data.get("next_page_token")
        if not token:
            break

    return {
        "results": results,
        "pages": pages,
        "hit_cap": len(results) >= NEARBY_CAP,
        "_status": "OK" if results else status,
    }
