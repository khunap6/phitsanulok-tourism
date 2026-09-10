import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { DateRange } from './DateRangeSelector'
import { formatThaiMonthYearShort } from '../utils/thaiDate'
import { NO_DATA, formatCount, formatPercent, formatRateOf } from '../utils/format'
import { dateKey } from '../hooks/useInsights'

interface Bucket {
  bucket: string
  counts: Record<string, number>
  total: number
  /** รีวิวที่มีข้อความทั้งหมดใน bucket = ตัวส่วนของ rates */
  bucket_total?: number
  /** คำบ่นทั้งหมดใน bucket = ตัวส่วนของ shares */
  bucket_negative?: number
  rates?: Record<string, number | null>
  shares?: Record<string, number | null>
  low_confidence?: boolean
}
interface TrendingResponse {
  period: 'week' | 'month'
  categories: string[]
  buckets: Bucket[]
  low_confidence_min?: number
}

/**
 * 3 โหมดการแสดงผล — ชื่อปุ่มต้องบอก "ตัวส่วน" ไม่ใช่เขียนแค่ "อัตรา"
 * เพราะ 20% ของคำบ่น กับ 3% ของรีวิวทั้งหมด หน้าตาเหมือนกันแต่คนละความหมาย
 * แสดงทีละโหมดเท่านั้น ห้ามเอาสองตัวมาไว้บนกราฟเดียวกัน
 */
const MODES = [
  { key: 'count', label: 'จำนวน', of: '' },
  { key: 'rate', label: '% ของรีวิวทั้งหมด', of: 'รีวิวทั้งหมด' },
  { key: 'share', label: '% ในหมู่คำบ่น', of: 'คำบ่น' },
] as const
type Mode = (typeof MODES)[number]['key']

/**
 * วิเคราะห์ "รายเดือน" เท่านั้น
 *
 * เดิมมีโหมดรายสัปดาห์ให้เลือกด้วย แต่ Google ให้วันที่รีวิวแบบสัมพัทธ์
 * ("1 เดือนที่แล้ว") ระบบจึงคำนวณย้อนได้ละเอียดระดับเดือน ไม่ใช่วัน
 * การแบ่ง bucket รายสัปดาห์จึงเป็นการซอยข้อมูลที่ไม่มีความละเอียดพอ
 * ทำให้ฐานต่อ bucket เล็กจนอัตราแกว่งอ่านไม่ได้ — ตัดออกเพื่อไม่ให้เข้าใจผิด
 */
const PERIOD = 'month' as const
const BUCKETS = 6

function useTrending(
  buckets: number,
  zone?: string,
  dateRange?: DateRange,
  status?: string,
) {
  const period = PERIOD
  return useQuery<TrendingResponse>({
    // dateKey ต้องอยู่ใน queryKey ไม่งั้นเปลี่ยนช่วงเวลาแล้ว cache ไม่ invalidate
    queryKey: ['trending', period, buckets, zone ?? 'all', dateKey(dateRange),
               status ?? 'all'],
    queryFn: async () => {
      const url = new URL('/api/insights/trending', window.location.origin)
      url.searchParams.set('period', period)
      url.searchParams.set('buckets', String(buckets))
      url.searchParams.set('top', '5')
      if (zone) url.searchParams.set('zone', zone)
      if (dateRange?.from) url.searchParams.set('date_from', dateRange.from)
      if (dateRange?.to) url.searchParams.set('date_to', dateRange.to)
      if (status) url.searchParams.set('status', status)
      const res = await fetch(url.toString())
      if (!res.ok) return { period, categories: [], buckets: [] }
      return res.json()
    },
    staleTime: 1000 * 60 * 5,
  })
}

function label(bucket: string): string {
  return formatThaiMonthYearShort(bucket) ?? bucket
}

/** ลูกศรบอกทิศทางเทียบช่วงก่อนหน้า */
function Delta({ cur, prev }: { cur: number; prev: number | null }) {
  if (prev === null) return null
  const d = cur - prev
  if (d === 0) return <span className="text-brand-subtext text-[10px] ml-1">–</span>
  const up = d > 0
  return (
    <span className={`text-[10px] ml-1 ${up ? 'text-red-400' : 'text-green-400'}`}>
      {up ? '▲' : '▼'}{Math.abs(d)}
    </span>
  )
}

interface Props {
  zone?: string
  zoneLabel?: string
  dateRange?: DateRange
  /** สถานะร้านของหน้า — ส่งมาเพื่อให้ฐานตรงกับการ์ด KPI (กฎ 1) */
  status?: string
}

export default function TrendingPanel({ zone, zoneLabel, dateRange, status }: Props) {
  const [mode, setMode] = useState<Mode>('count')
  const { data, isLoading } = useTrending(BUCKETS, zone, dateRange, status)

  const cats = data?.categories ?? []
  const buckets = data?.buckets ?? []
  const enough = buckets.length >= 2
  const minBase = data?.low_confidence_min ?? 30
  const modeMeta = MODES.find(m => m.key === mode) ?? MODES[0]

  /** ค่าที่จะแสดงในเซลล์ตามโหมดที่เลือก — null → "—" ห้ามแสดง 0% */
  function cell(b: Bucket, c: string): { text: string; title: string } {
    const n = b.counts[c] ?? 0
    if (mode === 'count') {
      return { text: formatCount(n), title: `${formatCount(n)} คอมเมนต์` }
    }
    const rate = mode === 'rate' ? (b.rates?.[c] ?? null) : (b.shares?.[c] ?? null)
    const denom = mode === 'rate' ? b.bucket_total : b.bucket_negative
    return {
      text: rate == null ? NO_DATA : formatPercent(rate),
      title: formatRateOf(rate, n, denom, modeMeta.of),
    }
  }

  return (
    <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
      <div className="flex items-start justify-between gap-3 flex-wrap mb-1">
        <div>
          <h3 className="text-brand-text font-semibold">📈 แนวโน้มปัญหา Top 5</h3>
          <p className="text-brand-subtext text-xs mt-0.5">
            รายเดือน · นับจาก<b>วันที่เขียนรีวิว</b>
            {zoneLabel ? ` · ${zoneLabel}` : ' · ทั้งจังหวัด'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
        <div className="inline-flex rounded-lg border border-brand-border overflow-hidden">
          {MODES.map(m => (
            <button
              key={m.key}
              onClick={() => setMode(m.key)}
              className={`px-3 py-1 text-xs transition-colors ${
                mode === m.key ? 'bg-brand-primary text-white'
                               : 'bg-brand-card text-brand-subtext hover:text-brand-text'
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
        </div>
      </div>

      {isLoading && <p className="text-brand-subtext text-sm py-4">กำลังโหลด...</p>}

      {!isLoading && !enough && (
        <div className="text-brand-subtext text-sm py-4 italic">
          ยังมีข้อมูลไม่พอสำหรับแสดงแนวโน้ม (ต้องมีอย่างน้อย 2 เดือน)
        </div>
      )}

      {!isLoading && enough && (
        <div className="overflow-x-auto mt-3">
          <table className="w-full text-sm min-w-[520px]">
            <thead>
              <tr className="text-brand-subtext text-xs border-b border-brand-border">
                <th className="text-left font-medium py-2 pr-3">หมวดปัญหา</th>
                {buckets.map(b => (
                  <th
                    key={b.bucket}
                    className={`text-right font-medium py-2 px-2 whitespace-nowrap ${
                      b.low_confidence ? 'opacity-40' : ''
                    }`}
                    title={b.low_confidence
                      ? `ฐานน้อยกว่า ${minBase} รีวิว ตัวเลขอาจไม่น่าเชื่อถือ (ฐาน ${formatCount(b.bucket_total ?? 0)} รีวิว)`
                      : `ฐาน ${formatCount(b.bucket_total ?? 0)} รีวิว`}
                  >
                    {label(b.bucket)}{b.low_confidence ? ' ⚠' : ''}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {cats.map((c, i) => (
                <tr key={c} className="border-b border-brand-border/50 last:border-0">
                  <td className="py-2 pr-3 text-brand-text">
                    <span className="text-brand-subtext text-xs mr-1.5">{i + 1}.</span>
                    {c}
                  </td>
                  {buckets.map((b, bi) => {
                    const cur = b.counts[c] ?? 0
                    const prev = bi > 0 ? (buckets[bi - 1].counts[c] ?? 0) : null
                    const v = cell(b, c)
                    return (
                      <td
                        key={b.bucket}
                        title={v.title}
                        className={`text-right py-2 px-2 whitespace-nowrap ${
                          b.low_confidence ? 'opacity-40' : ''
                        }`}
                      >
                        <span className="text-brand-text">{v.text}</span>
                        {mode === 'count' && <Delta cur={cur} prev={prev} />}
                      </td>
                    )
                  })}
                </tr>
              ))}
              <tr className="text-brand-subtext text-xs">
                <td className="py-2 pr-3 font-medium">รวมคำบ่นทั้งหมด</td>
                {buckets.map(b => (
                  <td key={b.bucket} className="text-right py-2 px-2">
                    {formatCount(b.total)}
                  </td>
                ))}
              </tr>
              <tr className="text-brand-subtext text-xs">
                <td className="py-2 pr-3 font-medium">ฐาน (รีวิวที่มีข้อความ)</td>
                {buckets.map(b => (
                  <td key={b.bucket}
                      className={`text-right py-2 px-2 ${b.low_confidence ? 'opacity-40' : ''}`}>
                    {formatCount(b.bucket_total ?? 0)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
          <p className="text-brand-subtext text-[11px] mt-2">
            {mode === 'count'
              ? '▲ = เพิ่มขึ้นจากช่วงก่อน · ▼ = ลดลง'
              : `ตัวเลขคือสัดส่วนของ${modeMeta.of} · ชี้ที่ตัวเลขเพื่อดู n และตัวส่วน`}
            {buckets.some(b => b.low_confidence)
              ? ` · ช่วงที่จางลง = ฐานน้อยกว่า ${minBase} รีวิว ตัวเลขอาจไม่น่าเชื่อถือ`
              : ''}
          </p>
        </div>
      )}
    </div>
  )
}
