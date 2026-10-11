import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { STATUS_OPTIONS } from '../components/StatusBadge'

/**
 * โหมดสถานะร้านที่เลือก (operational / closed / all) — แหล่งความจริงเดียว
 *
 *   /?status=all
 *
 * ⚠️ ทำไมต้องมีไฟล์นี้ (วัดเมื่อ 2026-10-10)
 *   เดิมแต่ละหน้าถือ useState('operational') ของตัวเอง แล้วส่งต่อเป็น prop
 *   ทีละ component — Dashboard.tsx:66 และ ZoneDashboard.tsx:234 คนละก้อนกัน
 *
 *   ผลคือถ้าลืมส่งที่จุดไหน จุดนั้นจะเงียบ ๆ ใช้ค่า default ของ endpoint แทน
 *   ซึ่งไม่เท่ากันทุกตัว เกิดเป็นบั๊กจริงที่วัดได้:
 *     หน้าเว็บเรียก /insights/zones โดยไม่ส่ง status
 *     -> ได้ default ของ endpoint นั้นคือ "all" (รวมร้านที่ปิดแล้ว)
 *     -> การ์ดโซนนับร้านปิด 25 แห่ง รีวิว 3,352 อัน คำบ่น 236 อัน
 *        ขณะที่การ์ด KPI บนหน้าจอเดียวกันไม่นับ (ผิดกฎ 1)
 *
 *   แก้อาการอย่างเดียว = ไปเติม status ที่จุดนั้น แล้วรอให้พลาดซ้ำที่จุดใหม่
 *   แก้ต้นเหตุ = ให้ค่ามีที่อยู่เดียว ทุกหน้าดึงจากที่เดียวกัน
 *   หลักเดียวกับ api/filters.py ที่รวมตัวกรองไว้ไฟล์เดียวฝั่ง backend
 *
 * ใช้ URL ไม่ใช่ Context ด้วยเหตุผลเดียวกับ useDateRange:
 *   ส่งลิงก์ต่อได้ · ทนต่อ refresh · เปลี่ยนหน้า /zones ↔ / ค่าไม่หาย
 *
 * ค่าที่ไม่รู้จักใน URL (ผู้ใช้แก้เอง) → ถอยกลับเป็น operational
 * ตั้งเป็น operational → ลบ param ออกจาก URL ให้สะอาด (ตรงกับ default)
 */
export const DEFAULT_BIZ_STATUS = 'operational'

const VALID = STATUS_OPTIONS.map(o => o.key)

export function useBizStatus(): [string, (s: string) => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  const raw = searchParams.get('status')
  const status = raw && VALID.includes(raw) ? raw : DEFAULT_BIZ_STATUS

  const setStatus = useCallback(
    (s: string) => {
      // แก้เฉพาะ param ของเรา ตัวอื่นใน URL (from/to/label) ต้องอยู่ครบ
      const next = new URLSearchParams(searchParams)
      if (!VALID.includes(s) || s === DEFAULT_BIZ_STATUS) next.delete('status')
      else next.set('status', s)
      // replace: ไม่ทับถม history — กดสลับ 5 ครั้งแล้วต้องกด back 5 ทีไม่ไหว
      setSearchParams(next, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  return [status, setStatus]
}
