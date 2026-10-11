import { usePositiveHighlights } from '../hooks/useInsights'
import type { DateRange } from './DateRangeSelector'
import { Praise, ViewPraise } from './icons'
import { categoryLabel } from '../utils/categoryLabel'
import { formatCount, formatRateOf } from '../utils/format'

interface Props {
  /** ถ้าไม่ระบุ = ภาพรวมทั้งจังหวัด */
  zone?: string
  /** label โซนสำหรับ header */
  zoneLabel?: string
  status?: string
  dateRange?: DateRange
}

/**
 * แผงแสดง "จุดเด่น" ของโซน — หมวดที่มีคำชม (positive) มากที่สุด
 * ใช้คู่กับ pain point เพื่อให้เห็นสองด้าน: จุดที่ต้องปรับ + จุดที่ทำได้ดี
 */
export default function PositiveHighlights({ zone, zoneLabel, status = 'operational', dateRange }: Props) {
  const { data, isLoading } = usePositiveHighlights(zone, 5, status, dateRange)
  const items = data?.items ?? []
  const totalPraise = data?.total_praise ?? 0

  const area = zoneLabel ? `ใน${zoneLabel}` : 'ทั้งจังหวัด'

  return (
    <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
      <div className="flex items-center gap-2 mb-1">
        <ViewPraise size={20} className="text-yellow-400" />
        <h3 className="text-brand-text font-semibold">จุดเด่นของพื้นที่</h3>
      </div>
      <p className="text-brand-subtext text-xs mb-4">
        หมวดที่นักท่องเที่ยว<span className="text-green-400 font-medium"> ชม </span>บ่อยที่สุด {area}
        {/* ⚠️ ต้องเขียนว่า "ที่ระบุหมวด" ไม่ใช่ "ทั้งหมด"
            แผงนี้ตัดหมวดความคิดเห็นทั่วไป/อื่นๆ ออก ตัวส่วนจึงเป็น 41,238
            ขณะที่คำชมทั้งหมดใน /summary คือ 57,905 — คนละฐาน
            ถ้าเขียนว่า "ทั้งหมด" ทั้งสองที่ คนอ่านจะเทียบกันแล้วสรุปผิด */}
        {totalPraise > 0 && ` · ฐาน ${formatCount(totalPraise)} คำชมที่ระบุหมวด`}
      </p>

      {isLoading && <p className="text-brand-subtext text-sm">กำลังโหลด...</p>}

      {!isLoading && items.length === 0 && (
        <p className="text-brand-subtext text-sm italic">ยังไม่มีคำชมในพื้นที่นี้</p>
      )}

      {!isLoading && items.length > 0 && (
        <div className="space-y-2">
          {items.map((item, i) => {
            const max = items[0].count || 1
            const pct = (item.count / max) * 100
            return (
              <div key={item.category} className="flex items-center gap-3">
                <span className="text-brand-subtext w-5 text-sm">{i + 1}.</span>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-baseline mb-0.5">
                    <span className="text-brand-text text-sm truncate">
                      {categoryLabel(item.category)}
                    </span>
                    {/* ห้ามโชว์ % โดยไม่มี n — formatRateOf ใส่ (a/b) ให้เสมอ */}
                    <span className="text-green-400 text-xs shrink-0 ml-2 inline-flex items-center gap-1">
                      <Praise size={12} />
                      {formatRateOf(item.share_of_praise, item.count, totalPraise,
                                    'คำชมที่ระบุหมวด')}
                    </span>
                  </div>
                  <div className="h-1.5 bg-brand-bg rounded-full overflow-hidden">
                    <div
                      className="h-full bg-green-500/70 rounded-full transition-all"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
