import catsV2 from '@shared/categories.json'
import labels from '@shared/category_labels.json'

/**
 * ชื่อหมวดที่แสดงต่อผู้ใช้
 *
 * ⚠️ อ่านจากไฟล์ใน shared/ ไฟล์เดียวกับที่ api/filters.py อ่าน
 *   ไม่ทำสำเนาฝั่ง TypeScript เพราะสำเนาจะเพี้ยนจากกันเมื่อแก้ที่เดียว
 *   แล้วแดชบอร์ดกับรายงาน PDF จะเรียกหมวดเดียวกันคนละชื่อ
 *
 * ⚠️ ใช้ตอนแสดงผลเท่านั้น ห้ามใช้ก่อนเทียบหรือจัดกลุ่ม
 *   ค่าที่ API ส่งมาและค่าใน DB ยังเป็น key เดิม ถ้าแปลงก่อนเทียบ
 *   การกรองตามหมวด (เช่น drill-down ส่ง category กลับไปที่ API) จะพัง
 *
 * ⚠️ ย้ายมาชุด v2 แล้ว (Phase 8)
 *   backend คืนชื่อหมวดชุด v2 (11 หมวด จาก shared/categories.json) แล้ว
 *   ส่วน category_labels.json เป็นชุด v1 (12 หมวด) ซึ่งยัง import ไว้
 *   เพื่อให้ค่าเก่าที่อาจติดอยู่ใน URL ที่ผู้ใช้ bookmark หรือใน snapshot
 *   ยังแสดงชื่อที่อ่านออก ไม่กลายเป็นคีย์ดิบ
 */
const SHARED_V1 = labels as { labels: Record<string, string>; keys: string[] }
const V1_LABELS: Record<string, string> = SHARED_V1.labels

interface CatV2 { id: number; name: string; is_non_problem: boolean; old_names: string[] }
const V2 = catsV2 as { categories: CatV2[]; non_problem_ids: number[] }

/**
 * หมวดทั้งหมดที่โมเดลทำนายได้ — ใช้เป็นตัวเลือกในดรอปดาวน์กรอง
 *
 * ⚠️ ห้ามพิมพ์ลิสต์หมวดไว้ในหน้าเว็บเอง (เคยทำแล้วเพี้ยน)
 *   ของเดิมใน Dashboard.tsx มี 10 หมวด ต่างจากโมเดล 12 หมวด —
 *   มี "พ่อค้าแม่ค้าและการรบกวน" ที่ไม่มีในข้อมูลสักแถว และขาด
 *   "รสชาติและคุณภาพอาหาร/เครื่องดื่ม" (27,025 แถว) กับ
 *   "บรรยากาศและการตกแต่งร้าน" (6,958 แถว) ผู้ใช้จึงกรองสองหมวดใหญ่สุดไม่ได้
 *
 * ⚠️ เปลี่ยนมาเป็นชุด v2 (11 หมวด) ตอนย้าย endpoint
 *   ลิสต์ v1 มีชื่อสองคู่ที่ยุบเป็นหมวดเดียวกันใน v2
 *   ("การเดินทางและที่จอดรถ" + "ข้อมูลและป้ายบอกทาง" -> หมวด 7 และ
 *    "สิ่งอำนวยความสะดวก" + "ความปลอดภัย" -> หมวด 9)
 *   ถ้าคงลิสต์ v1 ไว้ ดรอปดาวน์จะมีสองตัวเลือกที่กรองได้ผลเหมือนกันเป๊ะ
 *   ซึ่งทำให้ผู้ใช้คิดว่าระบบพัง
 */
export const ALL_CATEGORIES: string[] = V2.categories.map((c) => c.name)

/** หมวดที่ไม่ใช่ปัญหา (2 ความคิดเห็นทั่วไป, 11 อื่นๆ) — ใช้ซ่อนในมุมมองปัญหา */
export const NON_PROBLEM_CATEGORIES: string[] = V2.categories
  .filter((c) => c.is_non_problem)
  .map((c) => c.name)

// ชื่อหมวด v2 -> ตัวมันเอง (เป็นชื่อที่อ่านออกอยู่แล้ว ไม่ต้องแปลง)
// ชื่อหมวด v1 -> ชื่อที่อ่านออกของ v1 (เผื่อค่าเก่าหลงมา)
const MAP: Record<string, string> = { ...V1_LABELS }
for (const c of V2.categories) MAP[c.name] = c.name

export function categoryLabel(category: string): string
export function categoryLabel(category: string | null | undefined): string | null
export function categoryLabel(category: string | null | undefined): string | null {
  if (category == null) return null
  return MAP[category] ?? category
}
