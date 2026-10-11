import labels from '@shared/category_labels.json'

/**
 * ชื่อหมวดที่แสดงต่อผู้ใช้
 *
 * ⚠️ อ่านจาก shared/category_labels.json ไฟล์เดียวกับที่ api/filters.py อ่าน
 *   ไม่ทำสำเนาฝั่ง TypeScript เพราะสำเนาจะเพี้ยนจากกันเมื่อแก้ที่เดียว
 *   แล้วแดชบอร์ดกับรายงาน PDF จะเรียกหมวดเดียวกันคนละชื่อ
 *
 * ⚠️ ใช้ตอนแสดงผลเท่านั้น ห้ามใช้ก่อนเทียบหรือจัดกลุ่ม
 *   ค่าที่ API ส่งมาและค่าใน DB ยังเป็น key เดิม ถ้าแปลงก่อนเทียบ
 *   การกรองตามหมวด (เช่น drill-down ส่ง category กลับไปที่ API) จะพัง
 */
const SHARED = labels as { labels: Record<string, string>; keys: string[] }
const MAP: Record<string, string> = SHARED.labels

/**
 * หมวดทั้งหมดที่โมเดลทำนายได้ — ใช้เป็นตัวเลือกในดรอปดาวน์กรอง
 *
 * ⚠️ ห้ามพิมพ์ลิสต์หมวดไว้ในหน้าเว็บเอง (เคยทำแล้วเพี้ยน)
 *   ของเดิมใน Dashboard.tsx มี 10 หมวด ต่างจากโมเดล 12 หมวด —
 *   มี "พ่อค้าแม่ค้าและการรบกวน" ที่ไม่มีในข้อมูลสักแถว และขาด
 *   "รสชาติและคุณภาพอาหาร/เครื่องดื่ม" (27,025 แถว) กับ
 *   "บรรยากาศและการตกแต่งร้าน" (6,958 แถว) ผู้ใช้จึงกรองสองหมวดใหญ่สุดไม่ได้
 */
export const ALL_CATEGORIES: string[] = SHARED.keys

export function categoryLabel(category: string): string
export function categoryLabel(category: string | null | undefined): string | null
export function categoryLabel(category: string | null | undefined): string | null {
  if (category == null) return null
  return MAP[category] ?? category
}
