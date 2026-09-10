import { formatRateOf } from '../utils/format'

interface SeverityBreakdown {
  high: number
  medium: number
  low: number
}

interface RiskPlace {
  name: string
  high_count: number
}

interface KPICardProps {
  title: string
  value: string | number
  subtitle?: string
  accentColor?: string
  /** เมื่อ value เป็นจำนวนคอมเมนต์ ให้ใส่หน่วยต่อท้าย (เช่น "คอมเมนต์") */
  unit?: string
  /** แจกแจงตามระดับความรุนแรง — แสดงใต้ตัวเลขหลัก */
  breakdown?: SeverityBreakdown
  /** ร้านที่เสี่ยงสูงสุด — โชว์รายชื่อกันเข้าใจผิดว่าคอมมาจากร้านเดียว */
  riskPlaces?: RiskPlace[]
  /**
   * สัดส่วนของตัวเลขหลัก — ต้องส่ง denominator มาด้วยเสมอ
   * เพราะกฎของโปรเจกต์คือห้ามโชว์ % โดยไม่มี n ควบคู่ (utils/format.ts)
   * rate = null → แสดง "—" ไม่ใช่ 0%
   */
  rate?: number | null
  denominator?: number | null
  /** ตัวส่วนคืออะไร เช่น "รีวิวที่มีข้อความ" / "คำบ่นทั้งหมด" — ห้ามละ */
  rateOf?: string
}

export default function KPICard({
  title,
  value,
  subtitle,
  accentColor = '#3b82f6',
  unit,
  breakdown,
  riskPlaces,
  rate,
  denominator,
  rateOf = 'รีวิวที่มีข้อความ',
}: KPICardProps) {
  return (
    <div className="bg-brand-card rounded-xl p-5 border border-brand-border flex flex-col gap-1">
      <p className="text-brand-subtext text-sm">{title}</p>
      <p className="text-3xl font-bold flex items-baseline gap-1.5" style={{ color: accentColor }}>
        {value}
        {unit && typeof value === 'number' && (
          <span className="text-sm font-normal text-brand-subtext">{unit}</span>
        )}
      </p>

      {rate !== undefined && (
        <p className="text-brand-subtext text-xs">
          {formatRateOf(rate, typeof value === 'number' ? value : null, denominator, rateOf)}
        </p>
      )}

      {breakdown && (
        <div className="flex flex-wrap gap-3 text-xs mt-1">
          <span className="text-red-400">🔥 สูง {breakdown.high}</span>
          <span className="text-yellow-400">⚠️ กลาง {breakdown.medium}</span>
          <span className="text-green-400">💬 ต่ำ {breakdown.low}</span>
        </div>
      )}

      {subtitle && !breakdown && (
        <p className="text-brand-subtext text-xs">{subtitle}</p>
      )}

      {riskPlaces && riskPlaces.length > 0 && (
        <div className="mt-2 pt-2 border-t border-brand-border">
          <p className="text-brand-subtext text-[11px] mb-1">ร้านที่เสี่ยงสูงสุด:</p>
          <ul className="space-y-0.5">
            {riskPlaces.slice(0, 3).map((p, i) => (
              <li key={i} className="text-xs text-brand-text flex justify-between gap-2">
                <span className="truncate">{i + 1}. {p.name}</span>
                <span className="text-red-400 shrink-0">{p.high_count}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
