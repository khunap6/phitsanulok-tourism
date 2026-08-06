import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import StatusBadge from './StatusBadge'

// ─── Types ────────────────────────────────────────────────────────────────
interface PlaceRow {
  place_id: number
  place_name: string
  zone: string
  business_status?: string
  total: number
  high: number
  medium: number
  low: number
}
interface ReviewRow {
  text: string
  rating: number | null
  severity: string | null
  date: string | null
}

// ─── Hooks ────────────────────────────────────────────────────────────────
function usePlacesForCategory(category: string, zone?: string, status = 'operational') {
  return useQuery<PlaceRow[]>({
    queryKey: ['cat-places', category, zone ?? 'all', status],
    queryFn: async () => {
      const url = new URL('/api/insights/category-places', window.location.origin)
      url.searchParams.set('category', category)
      if (zone) url.searchParams.set('zone', zone)
      url.searchParams.set('status', status)
      const res = await fetch(url.toString())
      if (!res.ok) return []
      return res.json()
    },
    staleTime: 1000 * 60 * 5,
  })
}

function useReviewsForPlace(category: string, placeId: number | null, severity: string) {
  return useQuery<ReviewRow[]>({
    queryKey: ['cat-reviews', category, placeId, severity],
    queryFn: async () => {
      if (!placeId) return []
      const url = new URL('/api/insights/category-reviews', window.location.origin)
      url.searchParams.set('category', category)
      url.searchParams.set('place_id', String(placeId))
      if (severity) url.searchParams.set('severity', severity)
      const res = await fetch(url.toString())
      if (!res.ok) return []
      return res.json()
    },
    enabled: !!placeId,
    staleTime: 1000 * 60 * 5,
  })
}

// ─── Constants ──────────────────────────────────────────────────────────────
const SEVERITIES = [
  { key: '', label: 'ทั้งหมด', color: '#3b82f6' },
  { key: 'high', label: 'รุนแรงมาก', color: '#ef4444' },
  { key: 'medium', label: 'ปานกลาง', color: '#eab308' },
  { key: 'low', label: 'เล็กน้อย', color: '#22c55e' },
]
const ZONE_LABEL: Record<string, string> = {
  city_center: 'ตัวเมือง', naresuan: 'ม.นเรศวร', rajabhat: 'ม.ราชภัฏ', other: 'อื่นๆ',
}
const SEV_LABEL: Record<string, string> = { high: 'รุนแรงมาก', medium: 'ปานกลาง', low: 'เล็กน้อย' }
const SEV_COLOR: Record<string, string> = { high: '#ef4444', medium: '#eab308', low: '#22c55e' }

// ─── Reviews list (expanded under a place) ───────────────────────────────────
function ReviewsList({ category, placeId, severity }: { category: string; placeId: number; severity: string }) {
  const { data: reviews = [], isLoading } = useReviewsForPlace(category, placeId, severity)
  if (isLoading) return <div className="text-brand-subtext text-xs py-2">กำลังโหลดรีวิว...</div>
  if (reviews.length === 0) return <div className="text-brand-subtext text-xs py-2 italic">ไม่มีรีวิวในระดับนี้</div>
  return (
    <div className="space-y-2 pt-2">
      {reviews.map((rv, i) => (
        <div key={i} className="bg-brand-card rounded-lg p-2.5 border border-brand-border">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-yellow-400 text-xs">{'★'.repeat(rv.rating ?? 0)}</span>
            {rv.severity && (
              <span className="text-xs px-1.5 py-0.5 rounded" style={{ color: SEV_COLOR[rv.severity], background: SEV_COLOR[rv.severity] + '22' }}>
                {SEV_LABEL[rv.severity] ?? rv.severity}
              </span>
            )}
            {rv.date && <span className="text-brand-subtext text-xs ml-auto">{rv.date}</span>}
          </div>
          <p className="text-brand-text text-sm">{rv.text}</p>
        </div>
      ))}
    </div>
  )
}

// ─── Main drill-down ─────────────────────────────────────────────────────────
export default function CategoryDrilldown({
  category, zone, status = 'operational', onClose,
}: { category: string; zone?: string; status?: string; onClose: () => void }) {
  const [severity, setSeverity] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)
  const { data: places = [], isLoading } = usePlacesForCategory(category, zone, status)

  // เรียง + กรอง ตามระดับที่เลือก
  const sevKey = (severity || 'total') as keyof PlaceRow
  const rows = [...places]
    .filter((p) => (severity ? (p[severity as keyof PlaceRow] as number) > 0 : p.total > 0))
    .sort((a, b) => (b[sevKey] as number) - (a[sevKey] as number))
    .slice(0, 20)

  const maxCount = rows.length ? (rows[0][sevKey] as number) : 1

  return (
    <div className="bg-brand-bg rounded-xl border-2 border-brand-primary p-4 mt-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h4 className="text-brand-text font-semibold">
            🔍 ร้านที่มีปัญหา: <span className="text-brand-primary">{category}</span>
          </h4>
          <p className="text-brand-subtext text-xs mt-0.5">
            {zone ? `เฉพาะโซน ${ZONE_LABEL[zone] ?? zone}` : 'ทั้งจังหวัด'} · คลิกร้านเพื่ออ่านรีวิวจริง
          </p>
        </div>
        <button onClick={onClose} className="text-brand-subtext hover:text-brand-text text-sm">✕ ปิด</button>
      </div>

      {/* Severity tabs */}
      <div className="flex gap-2 mb-3 flex-wrap">
        {SEVERITIES.map((s) => (
          <button
            key={s.key}
            onClick={() => { setSeverity(s.key); setExpanded(null) }}
            className={`px-3 py-1 rounded-lg text-sm transition-colors border ${
              severity === s.key ? 'text-white border-transparent' : 'bg-brand-card text-brand-subtext border-brand-border hover:text-brand-text'
            }`}
            style={severity === s.key ? { background: s.color } : {}}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Place list */}
      {isLoading ? (
        <div className="text-brand-subtext text-sm">กำลังโหลด...</div>
      ) : rows.length === 0 ? (
        <div className="text-brand-subtext text-sm italic">ไม่มีร้านในระดับนี้</div>
      ) : (
        <div className="space-y-1.5">
          {rows.map((p, i) => {
            const cnt = p[sevKey] as number
            const isOpen = expanded === p.place_id
            return (
              <div key={p.place_id} className="bg-brand-card rounded-lg border border-brand-border overflow-hidden">
                <button
                  onClick={() => setExpanded(isOpen ? null : p.place_id)}
                  className="w-full flex items-center gap-3 p-2.5 hover:bg-brand-bg transition-colors text-left"
                >
                  <span className="text-brand-subtext text-sm w-5 shrink-0">{i + 1}.</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-brand-text text-sm truncate">{p.place_name}</span>
                      <span className="text-brand-subtext text-xs shrink-0">· {ZONE_LABEL[p.zone] ?? p.zone}</span>
                      <StatusBadge status={p.business_status} />
                    </div>
                    {/* mini severity bar (เมื่อดู "ทั้งหมด") */}
                    {!severity && (
                      <div className="flex h-1 rounded-full overflow-hidden mt-1 w-40">
                        <div className="bg-red-500" style={{ width: `${(p.high / p.total) * 100}%` }} />
                        <div className="bg-yellow-500" style={{ width: `${(p.medium / p.total) * 100}%` }} />
                        <div className="bg-green-500" style={{ width: `${(p.low / p.total) * 100}%` }} />
                      </div>
                    )}
                  </div>
                  {/* count bar */}
                  <div className="w-24 bg-brand-bg rounded-full h-4 overflow-hidden shrink-0">
                    <div className="h-full bg-brand-primary/60 rounded-full" style={{ width: `${(cnt / maxCount) * 100}%` }} />
                  </div>
                  <span className="text-brand-text text-sm w-12 text-right shrink-0">{cnt} รีวิว</span>
                  <span className="text-brand-subtext text-xs shrink-0">{isOpen ? '▲' : '▼'}</span>
                </button>
                {isOpen && (
                  <div className="px-3 pb-3">
                    <ReviewsList category={category} placeId={p.place_id} severity={severity} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
