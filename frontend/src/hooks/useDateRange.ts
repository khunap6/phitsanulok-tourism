import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ALL_TIME, type DateRange } from '../components/DateRangeSelector'

/**
 * ช่วงเวลาที่เลือก เก็บไว้ใน URL search params เป็นแหล่งความจริงเดียว
 *
 *   /?from=2025-01-01&to=2025-12-31&label=ปี%202025
 *
 * ทำไมใช้ URL ไม่ใช่ Context:
 *   - ช่วงเวลาที่เลือกกลายเป็นลิงก์ที่ส่งต่อได้ (แนบในเล่มวิทยานิพนธ์เป็นหลักฐานได้)
 *   - ทนต่อ refresh
 *   - เปลี่ยนหน้า /map ↔ /zones ค่าไม่หาย เพราะ query string ติดไปกับ URL
 *
 * ไม่มี param → คืน ALL_TIME
 * ตั้งค่าเป็น ALL_TIME → ลบ param ออกจาก URL (URL สะอาด และตรงกับ "ทั้งหมด")
 */
export function useDateRange(): [DateRange, (dr: DateRange) => void] {
  const [searchParams, setSearchParams] = useSearchParams()

  const from = searchParams.get('from')
  const to = searchParams.get('to')
  const label = searchParams.get('label')

  // ไม่มีทั้ง from และ to = ไม่ได้กรอง (label เดี่ยว ๆ ไม่มีความหมาย)
  const range: DateRange =
    !from && !to
      ? ALL_TIME
      : {
          from: from || null,
          to: to || null,
          // label มาจาก URL ที่ผู้ใช้แก้ได้ → จำกัดความยาว และมี fallback ให้เสมอ
          label: (label || `${from ?? '—'} ถึง ${to ?? '—'}`).slice(0, 60),
        }

  const setRange = useCallback(
    (dr: DateRange) => {
      // แก้เฉพาะ param ของเรา ตัวอื่นใน URL ต้องอยู่ครบ
      const next = new URLSearchParams(searchParams)
      if (!dr.from && !dr.to) {
        next.delete('from')
        next.delete('to')
        next.delete('label')
      } else {
        if (dr.from) next.set('from', dr.from)
        else next.delete('from')
        if (dr.to) next.set('to', dr.to)
        else next.delete('to')
        next.set('label', dr.label)
      }
      // replace: ไม่ทับถม history — ไม่งั้นกดกรอง 5 ครั้งแล้วต้องกด back 5 ที
      setSearchParams(next, { replace: true })
    },
    [searchParams, setSearchParams],
  )

  return [range, setRange]
}
