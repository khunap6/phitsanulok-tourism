-- ============================================================
--  Run this ONCE before running Alembic migrations
--  psql -U postgres -d phitsanulok_tourism -f db/init.sql
-- ============================================================

-- สร้าง database (ถ้ายังไม่มี — รันใน psql ก่อน connect)
-- CREATE DATABASE phitsanulok_tourism;

-- Enable PostGIS extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- ตรวจสอบว่า PostGIS ติดตั้งสำเร็จ
SELECT PostGIS_Version();

-- ============================================================
--  Spatial Index (Alembic สร้างให้แล้วใน migration)
--  แต่ถ้าต้องการสร้างเองให้รันหลัง migration เสร็จ:
-- ============================================================
-- CREATE INDEX IF NOT EXISTS idx_places_location
--   ON places USING GIST(location);

-- ============================================================
--  ตัวอย่าง Spatial Query (ทดสอบหลังมีข้อมูล)
-- ============================================================

-- หาสถานที่ในรัศมี 5 km จากใจกลางพิษณุโลก (100.26, 16.82)
-- SELECT name, overall_rating
-- FROM places
-- WHERE ST_DWithin(
--   location,
--   ST_MakePoint(100.26, 16.82)::geography,
--   5000
-- );

-- นับ pain point แต่ละหมวดในรัศมี 10 km
-- SELECT ar.pain_point_category, COUNT(*) AS count
-- FROM analyzed_reviews ar
-- JOIN reviews r ON r.id = ar.review_id
-- JOIN places p ON p.id = r.place_id
-- WHERE ST_DWithin(
--   p.location,
--   ST_MakePoint(100.26, 16.82)::geography,
--   10000
-- )
-- GROUP BY ar.pain_point_category
-- ORDER BY count DESC;
