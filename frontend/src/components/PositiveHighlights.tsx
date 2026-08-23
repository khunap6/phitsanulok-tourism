import { usePositiveHighlights } from '../hooks/useInsights'
import type { DateRange } from './DateRangeSelector'

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
  const { data = [], isLoading } = usePositiveHighlights(zone, 5, status, dateRange)

  const area = zoneLabel ? `ใน${zoneLabel}` : 'ทั้งจังหวัด'

  return (
    <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-2xl">⭐</span>
        <h3 className="text-brand-text font-semibold">จุดเด่นของพื้นที่</h3>
      </div>
      <p className="text-brand-subtext text-xs mb-4">
        หมวดที่นักท่องเที่ยว<span className="text-green-400 font-medium"> ชม </span>บ่อยที่สุด {area}
      </p>

      {isLoading && <p className="text-brand-subtext text-sm">กำลังโหลด...</p>}

      {!isLoading && data.length === 0 && (
        <p className="text-brand-subtext text-sm italic">ยังไม่มีคำชมในพื้นที่นี้</p>
      )}

      {!isLoading && data.length > 0 && (
        <div className="space-y-2">
          {data.map((item, i) => {
            const max = data[0].count || 1
            const pct = (item.count / max) * 100
            return (
              <div key={item.category} className="flex items-center gap-3">
                <span className="text-brand-subtext w-5 text-sm">{i + 1}.</span>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-baseline mb-0.5">
                    <span className="text-brand-text text-sm truncate">{item.category}</span>
                    <span className="text-green-400 text-xs shrink-0 ml-2">
                      👍 {item.count} คอมเมนต์
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
