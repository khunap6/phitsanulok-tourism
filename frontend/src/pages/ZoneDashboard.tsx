import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import AspectPanel from '../components/AspectPanel'
import CategoryDrilldown from '../components/CategoryDrilldown'
import DateRangeSelector, { type DateRange } from '../components/DateRangeSelector'
import KPICard from '../components/KPICard'
import PainPointChart from '../components/PainPointChart'
import PositiveHighlights from '../components/PositiveHighlights'
import { STATUS_OPTIONS } from '../components/StatusBadge'
import TrendingPanel from '../components/TrendingPanel'
import { dateKey, type ViewMode } from '../hooks/useInsights'
import { formatCount, formatRate } from '../utils/format'
import { useBizStatus } from '../hooks/useBizStatus'
import { useDateRange } from '../hooks/useDateRange'
import type { LucideIcon } from 'lucide-react'
import {
  ClickHint, PlaceAttraction, PlaceCafe, PlaceGeneral, PlaceRestaurant,
  SeverityHigh, SeverityLow, SeverityMedium, ViewAll, ViewComplaints, ViewPraise,
  ZoneCityCenter, ZoneNaresuan, ZoneOther, ZoneRajabhat,
} from '../components/icons'
import { categoryLabel } from '../utils/categoryLabel'

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
  /** ── ฟิลด์เชิงสัดส่วน (ฐานเข้ม: มีข้อความ + วิเคราะห์แล้ว + ผ่านตัวกรองสถานะ) ──
   *  ห้ามจับคู่ % พวกนี้กับ review_count/analyzed_count ซึ่งเป็นฐานหลวม */
  total_with_text?: number | null
  negative_count?: number | null
  complaint_rate?: number | null
}

/** /insights/zones/{zone}/pain-points — คืน object เพราะต้องพก "ตัวส่วน" มาด้วย */
interface ZonePainPoints {
  items: { category: string; count: number
           share_of_negative?: number | null; rate_of_all?: number | null }[]
  total_with_text: number
  sentiment_counts: { negative: number; positive: number; neutral: number }
  complaint_rate: number | null
  severity_counts: Record<string, number>
  severity_share: Record<string, number | null>
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

function useZones(dr?: DateRange, status = 'operational') {
  return useQuery<ZoneSummary[]>({
    queryKey: ['zones', dateKey(dr), status],
    queryFn: async () => {
      const url = withDate(new URL('/api/insights/zones', window.location.origin), dr)
      // ⚠️ default ของ endpoint นี้คือ "all" (รวมร้านปิด) ต่างจาก endpoint อื่น
      // ที่หน้านี้เรียกด้วย operational — ไม่ส่งแล้วตัวเลขจะไม่ตรงกันในหน้าเดียว
      url.searchParams.set('status', status)
      const res = await fetch(url.toString())
      if (!res.ok) return []
      return res.json()
    },
    staleTime: 1000 * 60 * 5,
  })
}

function useZoneBreakdown(zone: string | null, viewMode: ViewMode, status: string, dr?: DateRange) {
  return useQuery<PlaceTypeBreakdown[]>({
    queryKey: ['zone-breakdown', zone, viewMode, status, dateKey(dr)],
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
  return useQuery<ZonePainPoints>({
    queryKey: ['zone-pain-points', zone, viewMode, status, dateKey(dr)],
    queryFn: async () => {
      const url = withDate(
        new URL(`/api/insights/zones/${zone}/pain-points`, window.location.origin), dr)
      url.searchParams.set('view_mode', viewMode)
      url.searchParams.set('status', status)
      const res = await fetch(url.toString())
      // ตัวส่วนเป็น 0 → rate เป็น null ทั้งหมด ฝั่ง UI จะแสดง "—" ไม่ใช่ 0%
      if (!res.ok) {
        return {
          items: [], total_with_text: 0,
          sentiment_counts: { negative: 0, positive: 0, neutral: 0 },
          complaint_rate: null, severity_counts: {}, severity_share: {},
        }
      }
      return res.json()
    },
    enabled: zone !== null,
    staleTime: 1000 * 60 * 5,
  })
}

// ─── Constants ────────────────────────────────────────────────────────────────

const ZONE_ORDER = ['city_center', 'rajabhat', 'naresuan', 'other']

const ZONE_META: Record<string, { Icon: LucideIcon; color: string; bg: string }> = {
  city_center: { Icon: ZoneCityCenter, color: 'text-blue-400',   bg: 'bg-blue-500/10 border-blue-500/30' },
  rajabhat:    { Icon: ZoneRajabhat,   color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/30' },
  naresuan:    { Icon: ZoneNaresuan,   color: 'text-cyan-400',   bg: 'bg-cyan-500/10 border-cyan-500/30' },
  other:       { Icon: ZoneOther,      color: 'text-slate-400',  bg: 'bg-slate-500/10 border-slate-500/30' },
}

const TYPE_META: Record<string, { Icon: LucideIcon; color: string }> = {
  'คาเฟ่':              { Icon: PlaceCafe,       color: '#f97316' },
  'ร้านอาหาร':          { Icon: PlaceRestaurant, color: '#22d3ee' },
  'สถานที่ท่องเที่ยว':  { Icon: PlaceAttraction, color: '#a855f7' },
  'ทั่วไป':             { Icon: PlaceGeneral,    color: '#64748b' },
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

  // ฐานเดียวของทุกสัดส่วนในการ์ดนี้ = คำบ่นทั้งหมดของประเภทนี้ (กฎ 1)
  // ไม่ใส่ `|| 1` แบบเดิม เพราะการแปลงตัวส่วน 0 เป็น 1 ทำให้ได้ "0%"
  // ซึ่งอ่านว่า "มีปัญหาแต่เป็นศูนย์เปอร์เซ็นต์" ทั้งที่ความจริงคือ "ไม่มีข้อมูลให้วัด"
  const total = group.high_total + group.medium_total + group.low_total
  const rate = (n: number) => (total > 0 ? n / total : null)
  const hasProblem = total > 0

  return (
    <div className="bg-brand-bg rounded-xl border border-brand-border p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <meta.Icon size={18} />
          <span className="text-brand-text font-semibold">{group.type}</span>
          <span className="text-brand-subtext text-xs">({group.place_count} แห่ง)</span>
        </div>
        {/* ⚠️ "ไม่มี" กับ "0%" ไม่เหมือนกันสำหรับคนอ่าน
            0% สื่อว่ามีปัญหาอยู่แต่คิดเป็นศูนย์เปอร์เซ็นต์ ส่วนความจริงคือไม่พบเลย
            จึงต้องเขียนเป็นคำ ไม่ใช่ปล่อยให้เป็นตัวเลข (ข้อ 7) */}
        {!hasProblem ? (
          <span className="text-green-400 text-sm font-medium">ไม่พบคำบ่น</span>
        ) : group.high_total === 0 ? (
          <span className="text-green-400 text-sm font-medium">ไม่พบปัญหาระดับสูง</span>
        ) : (
          <span className="text-red-400 text-sm font-medium">
            {formatRate(rate(group.high_total), group.high_total, total)} เป็นปัญหาสูง
          </span>
        )}
      </div>

      {/* Severity bar — ไม่มีคำบ่นก็ไม่มีแถบและชิปให้แสดง */}
      {hasProblem && (
        <>
          <SeverityBar high={group.high_total} medium={group.medium_total} low={group.low_total} />
          {/* แสดงเฉพาะระดับที่มีจริง — ชิป "สูง 0.0% (0/1)" ไม่ให้ข้อมูลอะไร
              นอกจากกินที่และทำให้คนอ่านนึกว่ามีปัญหาระดับนั้นอยู่ */}
          <div className="flex flex-wrap gap-3 text-xs text-brand-subtext">
            {([
              { n: group.high_total,   Icon: SeverityHigh,   cls: 'text-red-400',    label: 'สูง' },
              { n: group.medium_total, Icon: SeverityMedium, cls: 'text-yellow-400', label: 'กลาง' },
              { n: group.low_total,    Icon: SeverityLow,    cls: 'text-green-400',  label: 'ต่ำ' },
            ] as const).filter(x => x.n > 0).map(x => (
              <span key={x.label} className={`${x.cls} inline-flex items-center gap-1`}>
                <x.Icon size={12} /> {x.label} {formatRate(rate(x.n), x.n, total)}
              </span>
            ))}
          </div>
        </>
      )}

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
                      <span className="text-brand-text text-xs truncate">{categoryLabel(pp.category)}</span>
                    </div>
                  </div>
                  <span className="text-brand-subtext text-xs w-28 text-right shrink-0">
                    {formatRate(rate(pp.count), pp.count, total)}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Top places */}
      {/* ⚠️ เงื่อนไขคือ "มีร้านที่ปัญหาระดับสูงมากกว่า 0" ไม่ใช่ "มีคำบ่น"
          เพราะรายการนี้เรียงด้วย high_count — ถ้าทุกร้านเป็น 0 จะได้ลิสต์
          ร้านพร้อมเลข 0 เรียงกันสามบรรทัด ซึ่งไม่บอกอะไรเลย (ข้อ 7) */}
      {group.top_places.some(pl => pl.high_count > 0) && (
        <div>
          <div className="text-brand-subtext text-xs mb-1.5 font-medium">สถานที่ที่มีปัญหามากสุด</div>
          <div className="space-y-1">
            {group.top_places.slice(0, 3).map((place) => (
              <div key={place.name} className="flex items-center justify-between text-xs">
                <span className="text-brand-text truncate flex-1">{place.name}</span>
                <span className="text-red-400 ml-2 shrink-0 inline-flex items-center gap-1">
                  <SeverityHigh size={11} /> {place.high_count} สูง
                </span>
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
  // สถานะร้านอ่านจาก URL ที่เดียวกับหน้าอื่น (ดู hooks/useBizStatus.ts)
  const [bizStatus, setBizStatus] = useBizStatus()
  const [drillCategory, setDrillCategory] = useState<string | null>(null)
  const { data: breakdown = [], isLoading: breakLoading } = useZoneBreakdown(zone, viewMode, bizStatus, dateRange)
  const { data: pp } = useZonePainPoints(zone, viewMode, bizStatus, dateRange)
  const painPoints = pp?.items ?? []
  // ตัวส่วนทั้งหมดมาจาก endpoint เดียวกับตัวเศษ (zone + view_mode + status + ช่วงเวลา)
  // จึงไม่มีทางที่สลับสถานะร้านแล้ว % เพี้ยนเพราะตัวส่วนไม่ได้อัปเดตตาม (กฎ 1)
  const negTotal = pp?.sentiment_counts?.negative ?? null
  const withText = pp?.total_with_text ?? null

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
            { key: 'complaints', label: 'คำบ่น',  Icon: ViewComplaints, color: '#ef4444' },
            { key: 'praise',     label: 'คำชม',   Icon: ViewPraise,     color: '#22c55e' },
            { key: 'all',        label: 'ทั้งหมด', Icon: ViewAll,        color: '#3b82f6' },
          ].map((m) => (
            <button
              key={m.key}
              onClick={() => { setViewMode(m.key as ViewMode); setDrillCategory(null) }}
              className={`px-3 py-1.5 text-sm transition-colors ${
                viewMode === m.key ? 'text-white' : 'bg-brand-card text-brand-subtext hover:text-brand-text'
              }`}
              style={viewMode === m.key ? { background: m.color } : {}}
            >
              <m.Icon size={13} className="inline mr-1 -mt-0.5" />{m.label}
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
          <span className="text-red-300 text-xs inline-flex items-center gap-1">
            <ViewComplaints size={12} /> ดูเฉพาะร้านที่ปิด — หาว่าอาจปิดเพราะอะไร
          </span>
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
          subtitle={
            `จากทั้งหมด ${formatCount(summary.review_count)} รีวิว · `
            + `มีข้อความให้วิเคราะห์ ${formatCount(withText)} รีวิว`
          }
          accentColor="#22d3ee"
        />

        <KPICard
          title="อัตราการบ่น"
          value={
            pp?.complaint_rate == null
              ? '—'
              : `${(pp.complaint_rate * 100).toFixed(1)}%`
          }
          accentColor="#f97316"
          subtitle={
            pp?.complaint_rate == null
              ? '—'
              : `${formatCount(negTotal)}/${formatCount(withText)} ของรีวิวที่มีข้อความ`
          }
        />
        <KPICard
          title="ปัญหาระดับสูง"
          value={pp?.severity_counts?.['high'] ?? 0}
          unit="คอมเมนต์"
          accentColor="#ef4444"
          rate={pp?.severity_share?.['high'] ?? null}
          denominator={negTotal}
          rateOf="คำบ่นทั้งหมด"
          breakdown={{
            high: pp?.severity_counts?.['high'] ?? 0,
            medium: pp?.severity_counts?.['medium'] ?? 0,
            low: pp?.severity_counts?.['low'] ?? 0,
          }}
          riskPlaces={topRiskPlaces}
        />
        <KPICard
          title="ปัญหาหลัก"
          value={categoryLabel(summary.top_category) ?? '—'}
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
              negativeTotal={negTotal}
              totalWithText={withText}
              title={
                viewMode === 'praise'
                  ? `จุดเด่นใน${summary.label}`
                  : viewMode === 'all'
                  ? `หมวดที่พูดถึงใน${summary.label}`
                  : `Pain Point ใน${summary.label}`
              }
              onCategoryClick={(c) => setDrillCategory(c === drillCategory ? null : c)}
            />
          </div>
        )}
        {viewMode !== 'praise' && (
          <PositiveHighlights zone={zone} zoneLabel={summary.label} status={bizStatus} dateRange={dateRange} />
        )}
      </div>

      {/* รายชื่อร้านของโซนนี้ — แสดงตลอดเหมือนหน้าภาพรวม (ข้อ 5) */}
      {/* วิเคราะห์รายหมวดของโซนนี้ — ชุดข้อมูลเดียวกับหน้าภาพรวม
          แต่กรองเฉพาะโซน ตัวส่วนจึงเป็นรีวิวในโซนนี้เท่านั้น (กฎ 1) */}
      <AspectPanel zone={zone} status={bizStatus} dateRange={dateRange}
                   title={`วิเคราะห์รายหมวด — ${summary.label}`} />

      <CategoryDrilldown
        category={drillCategory}
        zone={zone}
        status={bizStatus}
        viewMode={viewMode}
        dateRange={dateRange}
        onClose={drillCategory ? () => setDrillCategory(null) : undefined}
        onCategoryChange={setDrillCategory}
      />

      {/* แนวโน้มปัญหาของโซนนี้ */}
      <TrendingPanel zone={zone} zoneLabel={summary.label} dateRange={dateRange}
                     status={bizStatus} />

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
  // ช่วงเวลาอยู่ใน URL — ค่าตรงกับหน้าอื่นอัตโนมัติ (ดู hooks/useDateRange.ts)
  const [dateRange, setDateRange] = useDateRange()
  // อ่านจาก URL ที่เดียวกับปุ่มเลือกสถานะที่อยู่ใน ZoneDetail (component ลูก)
  // จึงไม่ต้องส่ง prop ลงไปและไม่มีทางหลุดจากกัน
  const [bizStatus] = useBizStatus()
  const { data: zones = [], isLoading } = useZones(dateRange, bizStatus)
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
                <meta.Icon size={22} />
                <span className={`font-semibold text-sm ${isActive ? meta.color : 'text-brand-text'}`}>
                  {z.label}
                </span>
              </div>
              <div className="text-brand-subtext text-xs mb-2">
                {z.place_count} สถานที่ · {formatCount(z.analyzed_count)} รีวิว
              </div>
              {/* อัตราการบ่นของโซน — ตัวเลขที่เทียบข้ามโซนได้จริง ต่างจากจำนวนดิบ
                  ที่โซนใหญ่ชนะเสมอ · formatRate ใส่ (a/b) ให้เองตามกฎ */}
              <div className="text-brand-subtext text-[11px] mb-1.5">
                บ่น {formatRate(z.complaint_rate, z.negative_count, z.total_with_text)}
              </div>
              <SeverityBar high={z.high_count} medium={z.medium_count} low={z.low_count} />
              <div className="flex justify-between text-xs mt-1.5">
                <span className="text-red-400 inline-flex items-center gap-1">
                  <SeverityHigh size={11} /> {z.high_count} สูง
                </span>
                {z.top_category && (
                  <span className="text-brand-subtext truncate ml-1 max-w-[100px]">{categoryLabel(z.top_category)}</span>
                )}
              </div>
              {z.analyzed_count === 0 && (
                <div className="text-xs text-yellow-500 mt-1 inline-flex items-center gap-1">
                  <SeverityMedium size={11} /> ยังไม่มีข้อมูล
                </div>
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
                        <meta.Icon size={14} className="inline mr-2 -mt-0.5" />
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
                      <td className="pl-4 text-brand-subtext text-xs">{categoryLabel(z.top_category) ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="text-brand-subtext text-xs mt-4 inline-flex items-center gap-1">
            <ClickHint size={13} /> คลิกที่การ์ดหรือแถวด้านบนเพื่อดู insight เฉพาะโซน
          </p>
        </div>
      )}

      {/* Zone detail */}
      {currentZone && (
        <div className="space-y-1">
          <div className="flex items-center gap-2 mb-4">
            {(() => {
              const Icon = ZONE_META[currentZone.zone]?.Icon
              return Icon ? <Icon size={22} /> : null
            })()}
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
