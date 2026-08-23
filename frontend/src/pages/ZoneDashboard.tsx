import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import CategoryDrilldown from '../components/CategoryDrilldown'
import DateRangeSelector, { ALL_TIME, type DateRange } from '../components/DateRangeSelector'
import KPICard from '../components/KPICard'
import PainPointChart from '../components/PainPointChart'
import PositiveHighlights from '../components/PositiveHighlights'
import { STATUS_OPTIONS } from '../components/StatusBadge'
import TrendingPanel from '../components/TrendingPanel'
import type { ViewMode } from '../hooks/useInsights'

// ─── Types ────────────────────────────────────────────────────────────────────

interface ZoneSummary {
  zone: string
  label: string
  place_count: number
  review_count: number
  analyzed_count: number
  high_count: number
  medium_count: number
  low_count: number
  top_category: string | null
}

interface PlaceTypeBreakdown {
  type: string
  place_count: number
  high_total: number
  medium_total: number
  low_total: number
  top_places: { name: string; high_count: number }[]
  top_pain_points: { category: string; count: number }[]
}

// ─── Hooks ────────────────────────────────────────────────────────────────────

// เติม date params ให้ URL ถ้ามี dateRange
function withDate(url: URL, dr?: DateRange): URL {
  if (dr?.from) url.searchParams.set('date_from', dr.from)
  if (dr?.to) url.searchParams.set('date_to', dr.to)
  return url
}

function useZones(dr?: DateRange) {
  return useQuery<ZoneSummary[]>({
    queryKey: ['zones', dr?.label ?? 'all'],
    queryFn: async () => {
      const url = withDate(new URL('/api/insights/zones', window.location.origin), dr)
      const res = await fetch(url.toString())
      if (!res.ok) return []
      return res.json()
    },
    staleTime: 1000 * 60 * 5,
  })
}

function useZoneBreakdown(zone: string | null, viewMode: ViewMode, status: string, dr?: DateRange) {
  return useQuery<PlaceTypeBreakdown[]>({
    queryKey: ['zone-breakdown', zone, viewMode, status, dr?.label ?? 'all'],
    queryFn: async () => {
      if (!zone) return []
      const url = withDate(
        new URL(`/api/insights/zones/${zone}/breakdown`, window.location.origin),
        dr,
      )
      url.searchParams.set('view_mode', viewMode)
      url.searchParams.set('status', status)
      const res = await fetch(url.toString())
      if (!res.ok) return []
      return res.json()
    },
    enabled: !!zone,
    staleTime: 1000 * 60 * 5,
  })
}

function useZonePainPoints(zone: string | null, viewMode: ViewMode, status: string, dr?: DateRange) {
  return useQuery<{ category: string; count: number }[]>({
    queryKey: ['zone-pain-points', zone, viewMode, status, dr?.label ?? 'all'],
    queryFn: async () => {
      if (!zone) return []
      const url = withDate(
        new URL(`/api/insights/zones/${zone}/pain-points`, window.location.origin),
        dr,
      )
      url.searchParams.set('view_mode', viewMode)
      url.searchParams.set('status', status)
      const res = await fetch(url.toString())
      if (!res.ok) return []
      return res.json()
    },
    enabled: !!zone,
    staleTime: 1000 * 60 * 5,
  })
}

// ─── Constants ────────────────────────────────────────────────────────────────

const ZONE_ORDER = ['city_center', 'rajabhat', 'naresuan', 'other']

const ZONE_META: Record<string, { icon: string; color: string; bg: string }> = {
  city_center: { icon: '🏙️', color: 'text-blue-400',   bg: 'bg-blue-500/10 border-blue-500/30' },
  rajabhat:    { icon: '🎓', color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/30' },
  naresuan:    { icon: '🏛️', color: 'text-cyan-400',   bg: 'bg-cyan-500/10 border-cyan-500/30' },
  other:       { icon: '📍', color: 'text-slate-400',  bg: 'bg-slate-500/10 border-slate-500/30' },
}

const TYPE_META: Record<string, { icon: string; color: string }> = {
  'คาเฟ่':              { icon: '☕', color: '#f97316' },
  'ร้านอาหาร':          { icon: '🍜', color: '#22d3ee' },
  'สถานที่ท่องเที่ยว':  { icon: '🏯', color: '#a855f7' },
  'ทั่วไป':             { icon: '📌', color: '#64748b' },
}

const CHART_COLORS = ['#3b82f6', '#6366f1', '#8b5cf6', '#ec4899', '#f43f5e', '#f97316', '#eab308']

// ─── Sub-components ───────────────────────────────────────────────────────────

function SeverityBar({ high, medium, low }: { high: number; medium: number; low: number }) {
  const total = high + medium + low || 1
  return (
    <div className="flex h-1.5 rounded-full overflow-hidden w-full">
      <div className="bg-red-500 transition-all"    style={{ width: `${(high / total) * 100}%` }} />
      <div className="bg-yellow-500 transition-all" style={{ width: `${(medium / total) * 100}%` }} />
      <div className="bg-green-500 transition-all"  style={{ width: `${(low / total) * 100}%` }} />
    </div>
  )
}

function PlaceTypeCard({ group }: { group: PlaceTypeBreakdown }) {
  const meta = TYPE_META[group.type] ?? TYPE_META['ทั่วไป']
  const total = group.high_total + group.medium_total + group.low_total || 1
  const highPct = Math.round((group.high_total / total) * 100)

  return (
    <div className="bg-brand-bg rounded-xl border border-brand-border p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl">{meta.icon}</span>
          <span className="text-brand-text font-semibold">{group.type}</span>
          <span className="text-brand-subtext text-xs">({group.place_count} แห่ง)</span>
        </div>
        <span className="text-red-400 text-sm font-medium">{highPct}% ปัญหาสูง</span>
      </div>

      {/* Severity bar */}
      <SeverityBar high={group.high_total} medium={group.medium_total} low={group.low_total} />
      <div className="flex flex-wrap gap-3 text-xs text-brand-subtext">
        <span className="text-red-400">🔥 สูง {group.high_total}</span>
        <span className="text-yellow-400">⚠️ กลาง {group.medium_total}</span>
        <span className="text-green-400">💬 ต่ำ {group.low_total}</span>
      </div>

      {/* Top pain points */}
      {group.top_pain_points.length > 0 && (
        <div>
          <div className="text-brand-subtext text-xs mb-2 font-medium">ปัญหาที่พบบ่อย</div>
          <div className="space-y-1.5">
            {group.top_pain_points.map((pp, i) => {
              const maxCount = group.top_pain_points[0]?.count || 1
              return (
                <div key={pp.category} className="flex items-center gap-2">
                  <span className="text-brand-subtext text-xs w-4 shrink-0">{i + 1}.</span>
                  <div className="flex-1 bg-brand-border rounded-full h-4 overflow-hidden">
                    <div
                      className="h-full rounded-full flex items-center px-2 transition-all"
                      style={{
                        width: `${Math.max(20, (pp.count / maxCount) * 100)}%`,
                        backgroundColor: meta.color + '33',
                        borderLeft: `2px solid ${meta.color}`,
                      }}
                    >
                      <span className="text-brand-text text-xs truncate">{pp.category}</span>
                    </div>
                  </div>
                  <span className="text-brand-subtext text-xs w-8 text-right shrink-0">{pp.count}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Top places */}
      {group.top_places.length > 0 && (
        <div>
          <div className="text-brand-subtext text-xs mb-1.5 font-medium">สถานที่ที่มีปัญหามากสุด</div>
          <div className="space-y-1">
            {group.top_places.slice(0, 3).map((place) => (
              <div key={place.name} className="flex items-center justify-between text-xs">
                <span className="text-brand-text truncate flex-1">{place.name}</span>
                <span className="text-red-400 ml-2 shrink-0">🔥 {place.high_count} สูง</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {group.top_pain_points.length === 0 && (
        <div className="text-brand-subtext text-xs italic">ยังไม่มีข้อมูลเพียงพอ</div>
      )}
    </div>
  )
}

function ZoneDetail({ zone, summary, dateRange }: { zone: string; summary: ZoneSummary; dateRange: DateRange }) {
  const [viewMode, setViewMode] = useState<ViewMode>('complaints')
  const [bizStatus, setBizStatus] = useState('operational')
  const [drillCategory, setDrillCategory] = useState<string | null>(null)
  const { data: breakdown = [], isLoading: breakLoading } = useZoneBreakdown(zone, viewMode, bizStatus, dateRange)
  const { data: painPoints = [] } = useZonePainPoints(zone, viewMode, bizStatus, dateRange)

  // รวม top places จากทุกประเภทสถานที่ใน zone → เอา 3 ร้านที่เสี่ยงสูงสุดโชว์บน KPI card
  const topRiskPlaces = breakdown
    .flatMap((g) => g.top_places)
    .filter((p) => p.high_count > 0)
    .sort((a, b) => b.high_count - a.high_count)
    .slice(0, 3)

  return (
    <div className="space-y-5">
      {/* View mode toggle — 3 โหมด (คุมกราฟ + drill-down ให้ตรงกัน) */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-brand-subtext text-sm">มุมมอง:</span>
        <div className="inline-flex rounded-lg border border-brand-border overflow-hidden">
          {[
            { key: 'complaints', label: '🔴 คำบ่น', color: '#ef4444' },
            { key: 'praise',     label: '⭐ คำชม',  color: '#22c55e' },
            { key: 'all',        label: '📊 ทั้งหมด', color: '#3b82f6' },
          ].map((m) => (
            <button
              key={m.key}
              onClick={() => { setViewMode(m.key as ViewMode); setDrillCategory(null) }}
              className={`px-3 py-1.5 text-sm transition-colors ${
                viewMode === m.key ? 'text-white' : 'bg-brand-card text-brand-subtext hover:text-brand-text'
              }`}
              style={viewMode === m.key ? { background: m.color } : {}}
            >
              {m.label}
            </button>
          ))}
        </div>
        <span className="text-brand-subtext text-xs">
          {viewMode === 'complaints' && 'รีวิวเชิงลบเท่านั้น'}
          {viewMode === 'praise'     && 'รีวิวเชิงบวกเท่านั้น'}
          {viewMode === 'all'        && 'รวมทุกรีวิว ทุกอารมณ์'}
        </span>
      </div>

      {/* สถานะร้าน: เปิด / ปิด / ทั้งหมด */}
      <div className="flex items-center gap-2">
        <span className="text-brand-subtext text-sm">สถานะร้าน:</span>
        <div className="inline-flex rounded-lg border border-brand-border overflow-hidden">
          {STATUS_OPTIONS.map((s) => (
            <button
              key={s.key}
              onClick={() => { setBizStatus(s.key); setDrillCategory(null) }}
              className={`px-3 py-1.5 text-sm transition-colors ${
                bizStatus === s.key ? 'text-white' : 'bg-brand-card text-brand-subtext hover:text-brand-text'
              }`}
              style={bizStatus === s.key ? { background: s.color } : {}}
            >
              {s.label}
            </button>
          ))}
        </div>
        {bizStatus === 'closed' && (
          <span className="text-red-300 text-xs">🔴 ดูเฉพาะร้านที่ปิด — หาว่าอาจปิดเพราะอะไร</span>
        )}
      </div>

      {/* Zone KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KPICard
          title="สถานที่ทั้งหมด"
          value={summary.place_count}
          subtitle="แห่งในโซนนี้"
          accentColor="#3b82f6"
        />
        <KPICard
          title="รีวิวที่วิเคราะห์"
          value={summary.analyzed_count}
          subtitle={`จากทั้งหมด ${summary.review_count} รีวิว`}
          accentColor="#22d3ee"
        />
        <KPICard
          title="ปัญหาระดับสูง"
          value={summary.high_count}
          unit="คอมเมนต์"
          accentColor="#ef4444"
          breakdown={{
            high: summary.high_count,
            medium: summary.medium_count,
            low: summary.low_count,
          }}
          riskPlaces={topRiskPlaces}
        />
        <KPICard
          title="ปัญหาหลัก"
          value={summary.top_category ?? '—'}
          subtitle="หมวดคำบ่นที่พบบ่อยสุด"
          accentColor="#f97316"
        />
      </div>

      {/* กราฟหลัก + Positive highlights — title/panel เปลี่ยนตาม viewMode */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {painPoints.length > 0 && (
          <div>
            <PainPointChart
              data={painPoints}
              title={
                viewMode === 'praise'
                  ? `⭐ จุดเด่นใน${summary.label}`
                  : viewMode === 'all'
                  ? `📊 หมวดที่พูดถึงใน${summary.label}`
                  : `🔴 Pain Point ใน${summary.label}`
              }
              onCategoryClick={(c) => setDrillCategory(c === drillCategory ? null : c)}
            />
          </div>
        )}
        {viewMode !== 'praise' && (
          <PositiveHighlights zone={zone} zoneLabel={summary.label} status={bizStatus} dateRange={dateRange} />
        )}
      </div>

      {/* Drill-down เฉพาะโซนนี้ */}
      {drillCategory && (
        <CategoryDrilldown category={drillCategory} zone={zone} status={bizStatus} viewMode={viewMode} dateRange={dateRange} onClose={() => setDrillCategory(null)} />
      )}

      {/* แนวโน้มปัญหาของโซนนี้ */}
      <TrendingPanel zone={zone} zoneLabel={summary.label} />

      {/* Place type breakdown */}
      <div>
        <h4 className="text-brand-text font-semibold mb-3">
          Insight ตามประเภทสถานที่
          <span className="text-brand-subtext text-xs font-normal ml-2">แต่ละประเภทมีปัญหาอะไรมากที่สุด</span>
        </h4>
        {breakLoading ? (
          <div className="text-brand-subtext text-sm">กำลังโหลด...</div>
        ) : breakdown.length === 0 ? (
          <div className="text-brand-subtext text-sm italic">ยังไม่มีข้อมูล — รัน discover แล้ว analyze ก่อนนะครับ</div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {breakdown.map((group) => (
              <PlaceTypeCard key={group.type} group={group} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function ZoneDashboard() {
  const [dateRange, setDateRange] = useState<DateRange>(ALL_TIME)
  const { data: zones = [], isLoading } = useZones(dateRange)
  const [activeZone, setActiveZone] = useState<string | null>(null)

  const sortedZones = [...zones].sort(
    (a, b) => ZONE_ORDER.indexOf(a.zone) - ZONE_ORDER.indexOf(b.zone)
  )

  const currentZone = activeZone
    ? sortedZones.find((z) => z.zone === activeZone) ?? null
    : null

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-brand-subtext">
        กำลังโหลดข้อมูลโซน...
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-brand-bg p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-brand-text">วิเคราะห์ตามพื้นที่ (Zone Analysis)</h1>
        <p className="text-brand-subtext text-sm mt-1">
          เปรียบเทียบ pain point ของแต่ละโซนในพิษณุโลก — คาเฟ่, ร้านอาหาร, สถานที่ท่องเที่ยว
        </p>
      </div>

      {/* Date range filter (share ตลอดทุกโซน) */}
      <div className="bg-brand-card rounded-xl p-3 border border-brand-border">
        <DateRangeSelector value={dateRange} onChange={setDateRange} />
      </div>

      {/* Zone selector cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {sortedZones.map((z) => {
          const meta = ZONE_META[z.zone] ?? ZONE_META['other']
          const isActive = activeZone === z.zone
          const total = z.high_count + z.medium_count + z.low_count || 1
          return (
            <button
              key={z.zone}
              onClick={() => setActiveZone(isActive ? null : z.zone)}
              className={`rounded-xl p-4 border text-left transition-all ${
                isActive
                  ? meta.bg + ' ring-2 ring-offset-1 ring-offset-brand-bg ring-current ' + meta.color
                  : 'bg-brand-card border-brand-border hover:border-brand-primary'
              }`}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-2xl">{meta.icon}</span>
                <span className={`font-semibold text-sm ${isActive ? meta.color : 'text-brand-text'}`}>
                  {z.label}
                </span>
              </div>
              <div className="text-brand-subtext text-xs mb-2">
                {z.place_count} สถานที่ · {z.analyzed_count} รีวิว
              </div>
              <SeverityBar high={z.high_count} medium={z.medium_count} low={z.low_count} />
              <div className="flex justify-between text-xs mt-1.5">
                <span className="text-red-400">🔥 {z.high_count} สูง</span>
                {z.top_category && (
                  <span className="text-brand-subtext truncate ml-1 max-w-[100px]">{z.top_category}</span>
                )}
              </div>
              {z.analyzed_count === 0 && (
                <div className="text-xs text-yellow-500 mt-1">⚠ ยังไม่มีข้อมูล</div>
              )}
            </button>
          )
        })}
      </div>

      {/* No zone selected — show comparison overview */}
      {!currentZone && (
        <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
          <h3 className="text-brand-text font-semibold mb-4">เปรียบเทียบทุกโซน</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-brand-subtext text-xs border-b border-brand-border">
                  <th className="text-left pb-2">โซน</th>
                  <th className="text-right pb-2">สถานที่</th>
                  <th className="text-right pb-2">รีวิว</th>
                  <th className="text-right pb-2">สูง</th>
                  <th className="text-left pb-2 pl-4">สัดส่วนความรุนแรง</th>
                  <th className="text-left pb-2 pl-4">ปัญหาหลัก</th>
                </tr>
              </thead>
              <tbody>
                {sortedZones.map((z) => {
                  const meta = ZONE_META[z.zone] ?? ZONE_META['other']
                  const total = z.high_count + z.medium_count + z.low_count || 1
                  return (
                    <tr
                      key={z.zone}
                      onClick={() => setActiveZone(z.zone)}
                      className="border-b border-brand-border/50 hover:bg-brand-bg cursor-pointer transition-colors"
                    >
                      <td className="py-2.5">
                        <span className="mr-2">{meta.icon}</span>
                        <span className={`font-medium ${meta.color}`}>{z.label}</span>
                      </td>
                      <td className="text-right text-brand-text">{z.place_count}</td>
                      <td className="text-right text-brand-text">{z.analyzed_count}</td>
                      <td className="text-right text-red-400 font-medium">{z.high_count}</td>
                      <td className="pl-4">
                        <div className="w-32">
                          <SeverityBar high={z.high_count} medium={z.medium_count} low={z.low_count} />
                        </div>
                      </td>
                      <td className="pl-4 text-brand-subtext text-xs">{z.top_category ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="text-brand-subtext text-xs mt-4">👆 คลิกที่การ์ดหรือแถวด้านบนเพื่อดู insight เฉพาะโซน</p>
        </div>
      )}

      {/* Zone detail */}
      {currentZone && (
        <div className="space-y-1">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-2xl">{ZONE_META[currentZone.zone]?.icon}</span>
            <h2 className={`text-xl font-bold ${ZONE_META[currentZone.zone]?.color}`}>
              {currentZone.label}
            </h2>
            <button
              onClick={() => setActiveZone(null)}
              className="ml-auto text-brand-subtext text-sm hover:text-brand-text"
            >
              ← กลับภาพรวม
            </button>
          </div>
          <ZoneDetail zone={currentZone.zone} summary={currentZone} dateRange={dateRange} />
        </div>
      )}
    </div>
  )
}
