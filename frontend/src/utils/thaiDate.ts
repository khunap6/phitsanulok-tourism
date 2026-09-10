/**
 * thaiDate.ts — จัดรูปวันที่แบบไทย (แหล่งเดียวของโปรเจกต์)
 *
 * กฎเหล็ก: แปลง พ.ศ. **ตอนเรนเดอร์เท่านั้น**
 *
 *   เก็บ / เทียบ / ใช้เป็นกุญแจ cache / ส่งเข้า API  →  ค.ศ. (ISO) เสมอ
 *   แสดงผลบนจอ                                      →  พ.ศ.
 *
 * ห้ามให้ +543 หลุดเข้าไปในตรรกะหรือ state เด็ดขาด และห้ามเขียน `+ 543`
 * กระจายหลายที่ — ให้เรียกฟังก์ชันในไฟล์นี้จากทุกจุดที่แสดงผล
 * (ฝั่ง backend มี thai_month_label() ใน reports/report_data.py ทำหน้าที่เดียวกัน)
 */

const BE_OFFSET = 543

export const TH_MONTH_SHORT = [
  'ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
  'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.',
] as const

/** 2025 → "2568" (สำหรับแสดงผล ห้ามเอาค่าไปคำนวณต่อ) */
export function formatThaiYear(gregorianYear: number): string {
  return String(gregorianYear + BE_OFFSET)
}

/** 2025 → "68" (ใช้ในที่แคบ ๆ เช่นหัวตารางแนวโน้ม) */
export function formatThaiYearShort(gregorianYear: number): string {
  return String((gregorianYear + BE_OFFSET) % 100)
}

function toDate(value: string | Date): Date | null {
  const d = value instanceof Date ? value : new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

/** "2022-03-01" → "มี.ค. 2565" */
export function formatThaiMonthYear(value: string | Date): string | null {
  const d = toDate(value)
  if (!d) return null
  return `${TH_MONTH_SHORT[d.getMonth()]} ${formatThaiYear(d.getFullYear())}`
}

/** "2026-08-01" → "ส.ค. 69" */
export function formatThaiMonthYearShort(value: string | Date): string | null {
  const d = toDate(value)
  if (!d) return null
  return `${TH_MONTH_SHORT[d.getMonth()]} ${formatThaiYearShort(d.getFullYear())}`
}

/** "2026-08-14" → "14 ส.ค." (ใช้กับ bucket รายสัปดาห์) */
export function formatThaiDayMonth(value: string | Date): string | null {
  const d = toDate(value)
  if (!d) return null
  return `${d.getDate()} ${TH_MONTH_SHORT[d.getMonth()]}`
}
