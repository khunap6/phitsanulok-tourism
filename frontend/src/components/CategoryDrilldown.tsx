import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import StatusBadge from './StatusBadge'
import type { DateRange } from './DateRangeSelector'
import type { ViewMode } from '../hooks/useInsights'

// เติม date_from/date_to เข้า URL search params ถ้า DateRange ระบุ
function appendDate(url: URL, dr?: DateRange) {
  if (dr?.from) url.searchParams.set('date_from', dr.from)
  if (dr?.to) url.searchParams.set('date_to', dr.to)
}

// ─── Types ────────────────────────────────────────────────────────────────
interface PlaceRow {
  place_id: number
  place_name: string
  zone: string
  business_status?: string
  total: number
  // ระดับความรุนแรง (ใช้ในโหมด complaints)
  high: number
  medium: number
  low: number
  // ประเภทความรู้สึก (ใช้ในโหมด all)
  neg: number
  pos: number
  neu: number
}
interface ReviewRow {
  text: string
  rating: number | null
  severity: string | null
  sentiment: string | null
  date: string | null
}

// ─── Tab config ต่อโหมด ────────────────────────────────────────────────────
// แต่ละโหมดกรองข้อมูลมาแล้วคนละแบบ → แท็บต้องสื่อความหมายให้ตรงกับสิ่งที่เหลืออยู่
//   complaints : กรอง sentiment=negative แล้ว → ทุกอันคือคำบ่น แท็บบอก "ความหนักของปัญหา"
//   praise     : กรอง sentiment=positive แล้ว → ทุกอันคือคำชม ไม่ต้องมีแท็บ
//   all        : ไม่กรอง → รีวิวปนกัน แท็บบอก "ประเภทรีวิว" (ไม่ใช่ severity ที่กำกวม)
interface TabDef {
  key: string
  label: string
  color: string
  field: keyof PlaceRow   // คอลัมน์ที่ใช้นับ/เรียงลำดับร้าน
}

const COMPLAINT_TABS: TabDef[] = [
  { key: '',       label: 'ทั้งหมด',   color: '#3b82f6', field: 'total' },
  { key: 'high',   label: '🔥 สูง',    color: '#ef4444', field: 'high' },
  { key: 'medium', label: '⚠️ กลาง',   color: '#eab308', field: 'medium' },
  { key: 'low',    label: '💬 ต่ำ',    color: '#22c55e', field: 'low' },
]

const ALL_TABS: TabDef[] = [
  { key: '',         label: 'ทั้งหมด',   color: '#3b82f6', field: 'total' },
  { key: 'negative', label: '🔴 คำบ่น',  color: '#ef4444', field: 'neg' },
  { key: 'positive', label: '⭐ คำชม',   color: '#22c55e', field: 'pos' },
  { key: 'neutral',  label: '😐 กลางๆ',  color: '#94a3b8', field: 'neu' },
]

function tabsFor(viewMode: ViewMode): TabDef[] {
  if (viewMode === 'complaints') return COMPLAINT_TABS
  if (viewMode === 'all') return ALL_TABS
  return []   // praise → ไม่มีแท็บ
}

// ─── Hooks ────────────────────────────────────────────────────────────────
function usePlacesForCategory(
  category: string, zone?: string, status = 'operational',
  viewMode: ViewMode = 'complaints', dateRange?: DateRange,
) {
  return useQuery<PlaceRow[]>({
    queryKey: ['cat-places', category, zone ?? 'all', status, viewMode, dateRange?.label ?? 'all'],
    queryFn: async () => {
      const url = new URL('/api/insights/category-places', window.location.origin)
      url.searchParams.set('category', category)
      if (zone) url.searchParams.set('zone', zone)
      url.searchParams.set('status', status)
      url.searchParams.set('view_mode', viewMode)
      appendDate(url, dateRange)
      const res = await fetch(url.toString())
      if (!res.ok) return []
      return res.json()
    },
    staleTime: 1000 * 60 * 5,
  })
}

function useReviewsForPlace(
  category: string, placeId: number | null,
  severity: string, sentiment: string,
  viewMode: ViewMode = 'complaints', dateRange?: DateRange,
) {
  return useQuery<ReviewRow[]>({
    queryKey: ['cat-reviews', category, placeId, severity, sentiment, viewMode, dateRange?.label ?? 'all'],
    queryFn: async () => {
      if (!placeId) return []
      const url = new URL('/api/insights/category-reviews', window.location.origin)
      url.searchParams.set('category', category)
      url.searchParams.set('place_id', String(placeId))
      if (severity) url.searchParams.set('severity', severity)
      if (sentiment) url.searchParams.set('sentiment', sentiment)
      url.searchParams.set('view_mode', viewMode)
      appendDate(url, dateRange)
      const res = await fetch(url.toString())
      if (!res.ok) return []
      return res.json()
    },
    enabled: !!placeId,
    staleTime: 1000 * 60 * 5,
  })
}

// ─── Constants ──────────────────────────────────────────────────────────────
const ZONE_LABEL: Record<string, string> = {
  city_center: 'ตัวเมือง', naresuan: 'ม.นเรศวร', rajabhat: 'ม.ราชภัฏ', other: 'อื่นๆ',
}
// badge ในโหมด complaints — ทุกรีวิวคือคำบ่นแล้ว บอกแค่ระดับความรุนแรง
const SEV_LABEL: Record<string, string> = { high: '🔥 สูง', medium: '⚠️ กลาง', low: '💬 ต่ำ' }
const SEV_COLOR: Record<string, string> = { high: '#ef4444', medium: '#eab308', low: '#22c55e' }
// badge ในโหมด all — รีวิวปนกัน บอกว่าอันนี้เป็นคำบ่นหรือคำชม
const SENT_LABEL: Record<string, string> = { negative: 'คำบ่น', positive: 'คำชม' }
const SENT_COLOR: Record<string, string> = { negative: '#ef4444', positive: '#22c55e' }

/** ป้ายกำกับรีวิวหนึ่งอัน — เปลี่ยนความหมายตามโหมดที่กำลังดู */
function reviewBadge(rv: ReviewRow, viewMode: ViewMode): { label: string; color: string } | null {
  if (viewMode === 'praise') return null            // ทุกอันคือคำชม ไม่ต้องติดป้ายซ้ำ
  if (viewMode === 'complaints') {
    if (!rv.severity) return null
    return { label: SEV_LABEL[rv.severity] ?? rv.severity, color: SEV_COLOR[rv.severity] ?? '#94a3b8' }
  }
  // โหมด all — บอกประเภทรีวิว
  const s = rv.sentiment ?? ''
  if (s === 'negative' || s === 'positive') {
    return { label: SENT_LABEL[s], color: SENT_COLOR[s] }
  }
  return { label: 'กลางๆ', color: '#94a3b8' }
}

// ─── Reviews list (expanded under a place) ───────────────────────────────────
function ReviewsList({
  category, placeId, severity, sentiment, viewMode, dateRange,
}: {
  category: string; placeId: number; severity: string; sentiment: string
  viewMode: ViewMode; dateRange?: DateRange
}) {
  const { data: reviews = [], isLoading } = useReviewsForPlace(
    category, placeId, severity, sentiment, viewMode, dateRange,
  )
  if (isLoading) return <div className="text-brand-subtext text-xs py-2">กำลังโหลดรีวิว...</div>
  if (reviews.length === 0) return <div className="text-brand-subtext text-xs py-2 italic">ไม่มีรีวิวในกลุ่มนี้</div>
  return (
    <div className="space-y-2 pt-2">
      {reviews.map((rv, i) => {
        const badge = reviewBadge(rv, viewMode)
        return (
          <div key={i} className="bg-brand-card rounded-lg p-2.5 border border-brand-border">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-yellow-400 text-xs">{'★'.repeat(rv.rating ?? 0)}</span>
              {badge && (
                <span
                  className="text-xs px-1.5 py-0.5 rounded"
                  style={{ color: badge.color, background: badge.color + '22' }}
                >
                  {badge.label}
                </span>
              )}
              {rv.date && <span className="text-brand-subtext text-xs ml-auto">{rv.date}</span>}
            </div>
            <p className="text-brand-text text-sm">{rv.text}</p>
          </div>
        )
      })}
    </div>
  )
}

// ─── Main drill-down ─────────────────────────────────────────────────────────
export default function CategoryDrilldown({
  category, zone, status = 'operational', viewMode = 'complaints', dateRange, onClose,
}: { category: string; zone?: string; status?: string; viewMode?: ViewMode; dateRange?: DateRange; onClose: () => void }) {
  const [filterKey, setFilterKey] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)
  const { data: places = [], isLoading } = usePlacesForCategory(category, zone, status, viewMode, dateRange)

  const tabs = tabsFor(viewMode)
  // ถ้าสลับโหมดแล้ว filterKey เดิมไม่มีในแท็บชุดใหม่ → กลับไป "ทั้งหมด" อัตโนมัติ
  const activeTab = tabs.find((t) => t.key === filterKey) ?? tabs[0]
  const sortField = (activeTab?.field ?? 'total') as keyof PlaceRow
  const isFiltered = !!activeTab?.key

  // complaints → ส่ง severity, all → ส่ง sentiment, praise → ไม่ส่งอะไร
  const severityParam = viewMode === 'complaints' ? (activeTab?.key ?? '') : ''
  const sentimentParam = viewMode === 'all' ? (activeTab?.key ?? '') : ''

  const rows = [...places]
    .filter((p) => (p[sortField] as number) > 0)
    .sort((a, b) => (b[sortField] as number) - (a[sortField] as number))
    .slice(0, 20)

  const maxCount = rows.length ? (rows[0][sortField] as number) : 1

  return (
    <div className="bg-brand-bg rounded-xl border-2 border-brand-primary p-4 mt-3">
      {/* Header — เปลี่ยนหัวข้อตามโหมด */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h4 className="text-brand-text font-semibold">
            {viewMode === 'praise'     && <>⭐ ร้านที่ถูกชม: <span className="text-green-400">{category}</span></>}
            {viewMode === 'complaints' && <>🔍 ร้านที่มีปัญหา: <span className="text-brand-primary">{category}</span></>}
            {viewMode === 'all'        && <>📊 ร้านในหมวด: <span className="text-brand-primary">{category}</span></>}
          </h4>
          <p className="text-brand-subtext text-xs mt-0.5">
            {zone ? `เฉพาะโซน ${ZONE_LABEL[zone] ?? zone}` : 'ทั้งจังหวัด'} · คลิกร้านเพื่ออ่านรีวิวจริง
          </p>
        </div>
        <button onClick={onClose} className="text-brand-subtext hover:text-brand-text text-sm">✕ ปิด</button>
      </div>

      {/* Tabs — ความหมายเปลี่ยนตามโหมด (ซ่อนในโหมด praise) */}
      {tabs.length > 0 && (
        <>
          <div className="flex gap-2 mb-1 flex-wrap">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => { setFilterKey(t.key); setExpanded(null) }}
                className={`px-3 py-1 rounded-lg text-sm transition-colors border ${
                  activeTab?.key === t.key
                    ? 'text-white border-transparent'
                    : 'bg-brand-card text-brand-subtext border-brand-border hover:text-brand-text'
                }`}
                style={activeTab?.key === t.key ? { background: t.color } : {}}
              >
                {t.label}
              </button>
            ))}
          </div>
          <p className="text-brand-subtext text-xs mb-3">
            {viewMode === 'complaints'
              ? 'ทุกรีวิวในหน้านี้คือคำบ่น — แท็บแบ่งตามความหนักของปัญหา'
              : 'รีวิวปนกันทุกแบบ — แท็บแบ่งตามประเภทรีวิว'}
          </p>
        </>
      )}

      {/* Place list */}
      {isLoading ? (
        <div className="text-brand-subtext text-sm">กำลังโหลด...</div>
      ) : rows.length === 0 ? (
        <div className="text-brand-subtext text-sm italic">ไม่มีร้านในกลุ่มนี้</div>
      ) : (
        <div className="space-y-1.5">
          {rows.map((p, i) => {
            const cnt = p[sortField] as number
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
                    {/* mini bar สัดส่วน (เมื่อดู "ทั้งหมด") — โหมด complaints=ความรุนแรง, all=ประเภทรีวิว */}
                    {!isFiltered && viewMode === 'complaints' && (
                      <div className="flex h-1 rounded-full overflow-hidden mt-1 w-40">
                        <div className="bg-red-500"    style={{ width: `${(p.high / p.total) * 100}%` }} />
                        <div className="bg-yellow-500" style={{ width: `${(p.medium / p.total) * 100}%` }} />
                        <div className="bg-green-500"  style={{ width: `${(p.low / p.total) * 100}%` }} />
                      </div>
                    )}
                    {!isFiltered && viewMode === 'all' && (
                      <div className="flex h-1 rounded-full overflow-hidden mt-1 w-40">
                        <div className="bg-red-500"   style={{ width: `${(p.neg / p.total) * 100}%` }} />
                        <div className="bg-green-500" style={{ width: `${(p.pos / p.total) * 100}%` }} />
                        <div className="bg-slate-500" style={{ width: `${(p.neu / p.total) * 100}%` }} />
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
                    <ReviewsList
                      category={category}
                      placeId={p.place_id}
                      severity={severityParam}
                      sentiment={sentimentParam}
                      viewMode={viewMode}
                      dateRange={dateRange}
                    />
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
