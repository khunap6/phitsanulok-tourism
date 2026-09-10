/**
 * format.ts — จัดรูปตัวเลขเชิงสัดส่วน (แหล่งเดียวของโปรเจกต์)
 *
 * กฎเหล็ก: ห้ามโชว์ % โดยไม่มี n ควบคู่ ทุกที่ ไม่มีข้อยกเว้น
 *
 *   ถูก:  "12.4% (298/2,401)"
 *   ผิด:  "12.4%"
 *
 * เหตุผล: 12.4% จากฐาน 2,401 กับ 12.4% จากฐาน 8 คนละเรื่องกันโดยสิ้นเชิง
 * ถ้าไม่เขียนตัวส่วนกำกับ คนอ่านจะเทียบข้ามช่วงเวลา/ข้ามโซนแล้วสรุปผิด
 *
 * ฟังก์ชันเหล่านี้บังคับกฎที่ระดับ signature — ต้องส่งทั้ง numerator และ
 * denominator เข้ามา ไม่มีทางเรนเดอร์ % เปล่าได้
 *
 * rate เป็น null = "ไม่มีข้อมูลให้วัด" (ตัวส่วนเป็น 0) → แสดง "—" ห้ามแสดง 0%
 */

/** "—" มาตรฐานของโปรเจกต์เมื่อไม่มีข้อมูลให้วัด */
export const NO_DATA = '—'

export function formatCount(n: number | null | undefined): string {
  return n == null ? NO_DATA : n.toLocaleString('th-TH')
}

/** 0.1237 → "12.4%" · null → "—" (ใช้เดี่ยว ๆ ได้เฉพาะในที่ที่ n อยู่ข้าง ๆ แล้ว) */
export function formatPercent(rate: number | null | undefined, digits = 1): string {
  return rate == null ? NO_DATA : `${(rate * 100).toFixed(digits)}%`
}

/**
 * รูปแบบมาตรฐาน: "12.4% (298/2,401)" · null → "—"
 * ใช้ตัวนี้เป็นค่าเริ่มต้นทุกครั้งที่จะแสดงสัดส่วน
 */
export function formatRate(
  rate: number | null | undefined,
  numerator: number | null | undefined,
  denominator: number | null | undefined,
  digits = 1,
): string {
  if (rate == null || denominator == null || denominator === 0) return NO_DATA
  return `${formatPercent(rate, digits)} (${formatCount(numerator)}/${formatCount(denominator)})`
}

/**
 * เติมคำกำกับว่าเป็นสัดส่วน "ของอะไร" — 20% ของคำบ่น กับ 3% ของรีวิวทั้งหมด
 * หน้าตาเหมือนกันแต่คนละความหมาย ถ้าไม่เขียนตัวส่วนกำกับคนอ่านจะเทียบข้ามโหมดแล้วสรุปผิด
 */
export function formatRateOf(
  rate: number | null | undefined,
  numerator: number | null | undefined,
  denominator: number | null | undefined,
  ofLabel: string,
  digits = 1,
): string {
  const base = formatRate(rate, numerator, denominator, digits)
  return base === NO_DATA ? NO_DATA : `${base} ของ${ofLabel}`
}
