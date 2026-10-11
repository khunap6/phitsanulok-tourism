# สำรองก่อนเปลี่ยนเป็น Multi-Aspect + Multi-Label

วันที่สำรอง: 2026-10-11
เหตุผล: ก่อนเริ่มงานเปลี่ยนจาก "1 รีวิว = 1 อารมณ์ + 1 หมวด"
เป็น "อารมณ์รวม 1 ป้าย + หลายหมวด แต่ละหมวดมีอารมณ์ของตัวเอง"

## สิ่งที่สำรองไว้

| ไฟล์ | คืออะไร |
|---|---|
| `db/phitsanulok_tourism_full.dump` | ฐานข้อมูลทั้งก้อน รูปแบบ custom (`-Fc`) 16 MB · 13 ตารางมีข้อมูล |
| `shared/category_labels.json` | รายชื่อหมวด 12 หมวดชุดเก่า + กติกาเลือกหมวด |
| `shared/sentiment_labels.json` | นิยามอารมณ์ 3 แบบ |
| `training/category_dataset.json` | **สำเนาเดียวที่เหลือ** ของป้ายหมวดจาก Claude ชุดแรก (10,690 แถว) |
| `training/sentiment_dataset.json` | ป้ายอารมณ์จาก Claude ชุดแรก (2,705 แถว) |

⚠️ ไฟล์ `training/*.json` สำคัญมาก
  ป้าย Claude ชุดแรกที่ใช้เทรนโมเดลปัจจุบัน **ไม่เหลืออยู่ในฐานข้อมูลแล้ว**
  ถูก `wangchanberta-finetuned` เขียนทับไปหมด (93,757 แถว)
  สองไฟล์นี้จึงเป็นหลักฐานเดียวว่าโมเดลถูกเทรนด้วยอะไร ห้ามลบ

## สถานะข้อมูลตอนสำรอง

- `places` 739 · `reviews` 114,295 · `reviews` ที่มีข้อความ 73,013
- `analyzed_reviews` 113,642 (มี `pain_point_category` 93,682)
- `model_used`: wangchanberta-finetuned 93,757 · rating-only 16,476 ·
  rule-based 2,738 · claude-haiku-4-5-20251001 671
- alembic revision ล่าสุด: `017_add_scrape_excluded`

## วิธีกู้คืน

ทับฐานเดิมทั้งก้อน (ลบของใหม่ทิ้งหมด):

```bash
"D:/PostgreSQL/16/bin/pg_restore.exe" -h localhost -p 5432 -U postgres \
  -d phitsanulok_tourism --clean --if-exists \
  backup/pre_multiaspect_20261011/db/phitsanulok_tourism_full.dump
```

กู้แค่บางตาราง เช่น `analyzed_reviews`:

```bash
"D:/PostgreSQL/16/bin/pg_restore.exe" -h localhost -p 5432 -U postgres \
  -d phitsanulok_tourism -t analyzed_reviews --clean --if-exists \
  backup/pre_multiaspect_20261011/db/phitsanulok_tourism_full.dump
```

ดูสารบัญในไฟล์สำรองโดยไม่กู้คืน:

```bash
"D:/PostgreSQL/16/bin/pg_restore.exe" -l \
  backup/pre_multiaspect_20261011/db/phitsanulok_tourism_full.dump
```

หมายเหตุ: ไคลเอนต์ของ PostgreSQL อยู่ที่ `D:\PostgreSQL\16\bin`
(ไม่ได้อยู่ใน PATH และไม่ได้อยู่ใต้ `C:\Program Files\PostgreSQL\16`
ซึ่งมีแต่โฟลเดอร์ `data`)
