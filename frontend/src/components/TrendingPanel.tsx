import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

interface Bucket {
  bucket: string
  counts: Record<string, number>
  total: number
}
interface TrendingResponse {
  period: 'week' | 'month'
  categories: string[]
  buckets: Bucket[]
}

function useTrending(period: 'week' | 'month', buckets: number, zone?: string) {
  return useQuery<TrendingResponse>({
    queryKey: ['trending', period, buckets, zone ?? 'all'],
    queryFn: async () => {
      const url = new URL('/api/insights/trending', window.location.origin)
      url.searchParams.set('period', period)
      url.searchParams.set('buckets', String(buckets))
      url.searchParams.set('top', '5')
      if (zone) url.searchParams.set('zone', zone)
      const res = await fetch(url.toString())
      if (!res.ok) return { period, categories: [], buckets: [] }
      return res.json()
    },
    staleTime: 1000 * 60 * 5,
  })
}

const TH_MONTH = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
                  'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']

function label(bucket: string, period: 'week' | 'month'): string {
  const d = new Date(bucket)
  if (period === 'month') return `${TH_MONTH[d.getMonth()]} ${(d.getFullYear() + 543) % 100}`
  return `${d.getDate()} ${TH_MONTH[d.getMonth()]}`
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

interface Props { zone?: string; zoneLabel?: string }

export default function TrendingPanel({ zone, zoneLabel }: Props) {
  const [period, setPeriod] = useState<'week' | 'month'>('month')
  const { data, isLoading } = useTrending(period, period === 'month' ? 6 : 8, zone)

  const cats = data?.categories ?? []
  const buckets = data?.buckets ?? []
  const enough = buckets.length >= 2

  return (
    <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
      <div className="flex items-start justify-between gap-3 flex-wrap mb-1">
        <div>
          <h3 className="text-brand-text font-semibold">📈 แนวโน้มปัญหา Top 5</h3>
          <p className="text-brand-subtext text-xs mt-0.5">
            นับจาก<b>วันที่เขียนรีวิว</b>{zoneLabel ? ` · ${zoneLabel}` : ' · ทั้งจังหวัด'}
          </p>
        </div>
        <div className="inline-flex rounded-lg border border-brand-border overflow-hidden">
          {(['month', 'week'] as const).map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1 text-xs transition-colors ${
                period === p ? 'bg-brand-primary text-white'
                             : 'bg-brand-card text-brand-subtext hover:text-brand-text'
              }`}
            >
              {p === 'month' ? 'รายเดือน' : 'รายสัปดาห์'}
            </button>
          ))}
        </div>
      </div>

      {isLoading && <p className="text-brand-subtext text-sm py-4">กำลังโหลด...</p>}

      {!isLoading && !enough && (
        <div className="text-brand-subtext text-sm py-4 italic">
          {period === 'week'
            ? 'ข้อมูลรายสัปดาห์ไม่พอ — Google แสดงวันที่รีวิวแบบคร่าว ("1 เดือนที่แล้ว") จึงแยกรายสัปดาห์ไม่ได้ ลองดูรายเดือนแทน'
            : 'ยังมีข้อมูลไม่พอสำหรับแสดงแนวโน้ม'}
        </div>
      )}

      {!isLoading && enough && (
        <div className="overflow-x-auto mt-3">
          <table className="w-full text-sm min-w-[520px]">
            <thead>
              <tr className="text-brand-subtext text-xs border-b border-brand-border">
                <th className="text-left font-medium py-2 pr-3">หมวดปัญหา</th>
                {buckets.map(b => (
                  <th key={b.bucket} className="text-right font-medium py-2 px-2 whitespace-nowrap">
                    {label(b.bucket, period)}
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
                    return (
                      <td key={b.bucket} className="text-right py-2 px-2 whitespace-nowrap">
                        <span className="text-brand-text">{cur}</span>
                        <Delta cur={cur} prev={prev} />
                      </td>
                    )
                  })}
                </tr>
              ))}
              <tr className="text-brand-subtext text-xs">
                <td className="py-2 pr-3 font-medium">รวมคำบ่นทั้งหมด</td>
                {buckets.map(b => (
                  <td key={b.bucket} className="text-right py-2 px-2">{b.total}</td>
                ))}
              </tr>
            </tbody>
          </table>
          <p className="text-brand-subtext text-[11px] mt-2">
            ▲ = เพิ่มขึ้นจากช่วงก่อน · ▼ = ลดลง
          </p>
        </div>
      )}
    </div>
  )
}
