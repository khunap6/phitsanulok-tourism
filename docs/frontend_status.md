# สถานะฝั่ง Frontend — อัปเดต 2026-10-12 (หลัง Phase 7)

สรุปว่าหน้าเว็บถูกแก้อะไรไปแล้ว อะไรนิ่งใช้ได้ และอะไรยังค้าง

⚠️ **Phase 1–7 เสร็จหมดแล้ว** ข้อความเดิมที่เขียนว่า "อย่าลงแรงเพิ่ม เพราะจะต้องรื้อ"
หมดอายุแล้ว — หัวข้อ 5 เขียนใหม่ตามสภาพจริงหลัง Phase 7

branch: `free-absa-baseline` · commit ล่าสุดของฝั่งหน้าเว็บ: `e5503bf`

---

## 1. ไฟล์ใหม่ 3 ไฟล์ — ตัวกลางที่ทำให้เลิกถือสำเนาซ้ำ

| ไฟล์ | หน้าที่ | เหตุผลที่ต้องมี |
|---|---|---|
| `src/utils/categoryLabel.ts` | `categoryLabel()` + `ALL_CATEGORIES` อ่านจาก `shared/category_labels.json` | เดิมหน้าเว็บพิมพ์ลิสต์หมวดเอง 10 หมวด ต่างจากโมเดล 12 หมวด ผู้ใช้จึงกรอง 2 หมวดใหญ่สุด (รสชาติ 27,025 / บรรยากาศ 6,958) ไม่ได้เลย |
| `src/hooks/useBizStatus.ts` | สถานะร้าน (เปิด/ปิด/ทั้งหมด) ผูกกับ URL | เดิมแต่ละหน้าถือ `useState` ของตัวเอง ค่าจึงไม่ตรงกันระหว่างหน้า และ refresh แล้วหาย |
| `src/components/icons.tsx` | รวม lucide icon ไว้ใต้ชื่อเชิงความหมาย (`SeverityHigh`, `ViewPraise`, `ZoneCityCenter`, `PlaceCafe`, `AlertSpike`, …) + `<Stars value>` | เดิมใช้ emoji (🔥 ⚠️ 💬 ⭐) กระจายทั่วไฟล์ ขนาด/สีคุมไม่ได้ และบนบางเครื่องเรนเดอร์ไม่เหมือนกัน |

⚠️ กติกาของ `categoryLabel()`: **แปลงเฉพาะตอนวาด** ห้ามแปลงก่อนเทียบหรือส่งกลับ API
ค่าที่ API รับยังเป็น key เดิม ถ้าแปลงที่ชั้นข้อมูล การกรองแบบ drill-down จะพัง
(ใน `PainPointChart.tsx` จึงใช้ `tickFormatter={categoryLabel}` ไม่ใช่แปลงที่ `data`)

---

## 2. แก้ตามรายการของอาจารย์

### ข้อ 3 — ลดการแสดงข้อมูลซ้ำบนการ์ดเดียว
- `KPICard.tsx` เพิ่ม prop `chart?: ReactNode` ถ้าส่งกราฟมาจะแสดงแทนแถบชิป
  เพราะกราฟวงกลมบอกทั้งจำนวนและสัดส่วนของ 3 ระดับอยู่แล้ว การโชว์ชิป
  "สูง/กลาง/ต่ำ" อีกชุดคือข้อมูลเดียวกันสองที่
- `SeverityPie.tsx` เพิ่มโหมด `embedded` ตัดกรอบ/หัวข้อ/คำอธิบายออก เหลือแต่กราฟ
  (ย่อรัศมี 72→58, สูง 240→190) แล้ว `Dashboard.tsx` ส่งเข้าไปใน `KPICard`
  **ไม่เขียนกราฟวงกลมตัวที่สอง** เพราะกติกาคำนวณ % ของกราฟนี้ (ใช้ `share` จาก API
  ห้ามให้ recharts หารเอง) เป็นจุดที่เคยพลาด ทำตัวใหม่เสี่ยงพลาดซ้ำ

### ข้อ 4 — เลือกหมวดได้จากในแผงเลย
- `CategoryDrilldown.tsx` (+150 บรรทัด) หัวแผงมี `<select>` ครบ 12 หมวด
  `value` = key ใน DB, ข้อความ = ชื่อที่แสดง · เพิ่ม prop `onCategoryChange`
  `category` รับ `null` ได้ (= ทุกหมวด) · `onClose` เป็น optional
- ยังกดแท่งกราฟเพื่อ drill-down ได้เหมือนเดิม เป็นทางเลือกเสริม

### ข้อ 5 — รายชื่อร้านแสดงตลอด
- `Dashboard.tsx` ไม่ต้องให้ผู้ใช้กดแท่งกราฟก่อนจึงจะเห็นรายชื่อร้าน

### หน้าโซนให้เหมือน Dashboard หลัก
- `ZoneDashboard.tsx` (+169 บรรทัด) ใช้ `KPICard`, `SeverityBar`, `CategoryDrilldown`,
  ชุดไอคอนและ `useBizStatus` ชุดเดียวกับหน้าหลัก

---

## 3. แก้ตัวเลขให้ถูก (กฎข้อ 1)

กฎข้อ 1 ของโปรเจกต์: **ตัวเศษกับตัวส่วนต้องผ่านตัวกรองชุดเดียวกัน**
ส่วนที่แก้ที่ backend ไปแล้ว แต่ frontend ต้องเปลี่ยนตามเพราะรูปร่างข้อมูลเปลี่ยน

| ไฟล์ | เปลี่ยนอะไร |
|---|---|
| `PositiveHighlights.tsx` | `/positive-highlights` คืน `{items, total_praise}` แทน array เปล่า จึงแก้เป็น `data?.items ?? []` · แสดงฐานว่า "คำชม**ที่ระบุหมวด**" ไม่ใช่ "ทั้งหมด" เพราะแผงนี้ตัดหมวดทั่วไป/อื่นๆ ออก ตัวส่วนคือ 41,238 ขณะที่คำชมทั้งหมดใน `/summary` คือ 57,905 — **คนละฐาน** ถ้าเขียน "ทั้งหมด" ทั้งสองที่ คนอ่านจะเทียบกันแล้วสรุปผิด |
| `Dashboard.tsx` | `useZones()` **ส่ง `status` เสมอ** เพราะ default ของ endpoint นั้นคือ `all` ซึ่งรวมร้านที่ปิดแล้ว · เลิกใช้ `useState` ภายใน เปลี่ยนไปใช้ `useBizStatus` |
| `TrendingPanel.tsx` | หัวข้อเป็น "แนวโน้มของปัญหา" · เพิ่มกราฟเส้นภาพรวมจาก `bucket_negative` · แยกแถวตารางเป็น "รวม 5 หมวดนี้" (`b.total`) กับ "คำบ่นทั้งหมด" (`b.bucket_negative`) เพราะแถวเดิมชื่อ "รวมคำบ่นทั้งหมด" แต่คิดจาก 5 หมวดที่โชว์ |
| `useInsights.ts`, `types.ts` | ตาม field ที่ backend รวบ (`_with_text` คู่แฝดถูกตัดออก) |
| `KPICard.tsx` | prop บังคับระบุว่าตัวส่วนคืออะไร — **ห้ามละ** |

---

## 4. ไฟล์ที่แก้เล็กน้อย

`ReviewList.tsx` (+19) · `NotificationBell.tsx` (+20) · `ReportDownload.tsx` (+15) ·
`StatusBadge.tsx` (+10) · `MapView.tsx` (+10) · `PainPointChart.tsx` (+9) ·
`DateRangeSelector.tsx` (+8) · `PlaceSelector.tsx` (+2)
ส่วนใหญ่คือเปลี่ยน emoji → ไอคอน และรับ prop `status` / `dateRange` เพิ่ม

---

## 5. สภาพหลัง Phase 7 — มีสองชั้นข้อมูลอยู่บนหน้าเดียวกัน

หน้า Dashboard กับ ZoneDashboard ตอนนี้แสดงตัวเลข **สองชุดที่มาจากคนละตาราง**
และ **ตัวเลขสองชุดนี้ไม่เท่ากันโดยตั้งใจ ไม่ใช่บั๊ก**

| ชั้น | อ่านจาก | หน่วยนับ | คอมโพเนนต์ |
|---|---|---|---|
| เดิม (legacy) | `analyzed_reviews` 1 หมวด/รีวิว | รีวิว | `PainPointChart`, `CategoryDrilldown`, `SeverityPie`, `KPICard` |
| ใหม่ (aspect) | `review_aspects` ~1.93 หมวด/รีวิว | รีวิว **และ** การกล่าวถึง | `AspectPanel`, `AspectChart` |

ผมใส่คอมเมนต์เตือนไว้ใน `Dashboard.tsx` ตรงจุดที่วาง `AspectPanel` แล้ว
ว่าทำไมตัวเลขสองที่ถึงต่างกัน

### ของใหม่ใน Phase 7

| ไฟล์ | หน้าที่ |
|---|---|
| `hooks/useAspects.ts` | `useCategorySummary` / `useAspectOverview` / `useAspectReviews` |
| `components/AspectChart.tsx` | แท่งซ้อน 👍😐👎 รายหมวด · สลับโหมด "ทุกหมวดที่พูดถึง" (รวมเกิน 100%) กับ "หมวดหลัก" (รวม 100% พอดี) · ป้าย "ข้อมูลน้อย" · คลิกช่วงสีเพื่อกรอง |
| `components/AspectPanel.tsx` | ตัวเลขสองหน่วย + กราฟ + รายการรีวิวที่กรองแล้ว · ใช้ทั้งหน้าภาพรวมและหน้าโซน |

⚠️ **ห้ามคำนวณสัดส่วนเองในหน้าเว็บ** ให้ใช้ `share_of_reviews` / `share_as_primary`
ที่ backend ส่งมา เพราะ backend หารด้วยตัวส่วนชุดเดียวกับตัวตั้ง (กฎข้อ 1)
ถ้าหารเองจะเสี่ยงใช้คนละตัวส่วน

### แก้ความเข้าใจผิดในฉบับก่อน

ฉบับก่อนเขียนว่า `SeverityPie.tsx` "ต้องเลิกใช้" — **ไม่ถูกต้อง**
โจทย์ห้ามกราฟวงกลมเฉพาะ *สัดส่วนรายหมวด* ส่วนกราฟนั้นแสดงระดับความรุนแรงของคำบ่น
(สูง/กลาง/ต่ำ) ซึ่งรวมได้ 100% จริงและไม่ใช่รายหมวด **จึงคงไว้ได้**

### ที่ยังค้างจริง

| ค้างอะไร | รายละเอียด |
|---|---|
| ชั้นเดิมยังไม่ย้าย | `PainPointChart` / `CategoryDrilldown` / `KPICard` ยังอ่าน `analyzed_reviews` และหมวดชุด 12 หมวดเดิม ถ้าจะให้เหลือชุดเดียวต้องย้ายมาอ่าน `/aspects/*` |
| `categoryLabel.ts` | ยังอ่าน `shared/category_labels.json` (12 หมวด v1) ส่วนชั้นใหม่อ่าน `shared/categories.json` (11 หมวด v2) — สองไฟล์อยู่คู่กันโดยตั้งใจระหว่างที่ยังมีสองชั้น |
| `types.ts` | ยังไม่มี type ของชั้น aspect (อยู่ใน `hooks/useAspects.ts` แทน) |

ส่วนที่ **นิ่งแล้ว ใช้ต่อได้เลย**: `icons.tsx`, `useBizStatus.ts`, `useDateRange.ts`,
`KPICard.tsx` (โครง), `ReviewList.tsx`, `DateRangeSelector.tsx`, `PlaceSelector.tsx`,
`StatusBadge.tsx`, `ReportDownload.tsx`, `NotificationBell.tsx`,
`AspectChart.tsx`, `AspectPanel.tsx`, `useAspects.ts`

---

## 6. วิธีรันตรวจ

```bash
cd frontend && npx tsc --noEmit
```

ล่าสุดผ่าน (exit 0) · เปิดหน้าเว็บด้วย `.claude/launch.json` config ชื่อ `web`
