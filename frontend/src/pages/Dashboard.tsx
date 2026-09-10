import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import CategoryDrilldown from '../components/CategoryDrilldown'
import DateRangeSelector, { type DateRange } from '../components/DateRangeSelector'
import KPICard from '../components/KPICard'
import PainPointChart from '../components/PainPointChart'
import PositiveHighlights from '../components/PositiveHighlights'
import ReportDownload from '../components/ReportDownload'
import StatusBadge, { STATUS_OPTIONS } from '../components/StatusBadge'
import TrendingPanel from '../components/TrendingPanel'
import PlaceSelector from '../components/PlaceSelector'
import ReviewList from '../components/ReviewList'
import SeverityPie from '../components/SeverityPie'
import { dateKey, useInsights, useTopPlaces, type ViewMode } from '../hooks/useInsights'
import { formatCount, formatRate } from '../utils/format'
import { useDateRange } from '../hooks/useDateRange'
import { usePlaces } from '../hooks/usePlaces'
import { useReviews } from '../hooks/useReviews'

// ── Zone hooks ────────────────────────────────────────────────────────────
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

function useZones(dateRange?: DateRange) {
  return useQuery<ZoneSummary[]>({
    queryKey: ['zones', dateKey(dateRange)],
    queryFn: async () => {
      const url = new URL('/api/insights/zones', window.location.origin)
      if (dateRange?.from) url.searchParams.set('date_from', dateRange.from)
      if (dateRange?.to) url.searchParams.set('date_to', dateRange.to)
      const res = await fetch(url.toString())
      if (!res.ok) return []
      return res.json()
    },
    staleTime: 1000 * 60 * 5,
  })
}

const ALL_CATEGORIES = [
  'การเดินทางและที่จอดรถ',
  'ความสะอาดและสิ่งแวดล้อม',
  'ราคาและความคุ้มค่า',
  'การบริการและเจ้าหน้าที่',
  'ความปลอดภัย',
  'สิ่งอำนวยความสะดวก',
  'ข้อมูลและป้ายบอกทาง',
  'ความแออัดและการจัดการ',
  'พ่อค้าแม่ค้าและการรบกวน',
  'อื่นๆ',
]

export default function Dashboard() {
  const [selectedPlace, setSelectedPlace] = useState<number | null>(null)
  const [filterSeverity, setFilterSeverity] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('complaints')
  const [bizStatus, setBizStatus] = useState('operational')
  // ช่วงเวลาอยู่ใน URL — เปลี่ยนหน้า/refresh แล้วไม่หาย (ดู hooks/useDateRange.ts)
  const [dateRange, setDateRange] = useDateRange()
  const [drillCategory, setDrillCategory] = useState<string | null>(null)
  // จัดอันดับร้าน: จำนวนมากสุด vs อัตราสูงสุด (คนละคำถาม ต้องเลือกดูทีละแบบ)
  const [placeSort, setPlaceSort] = useState<'count' | 'rate'>('count')
  const MIN_REVIEWS_FOR_RATE = 30

  const { data: insights, isLoading: insightsLoading } = useInsights(viewMode, bizStatus, dateRange)
  const { data: topPlaces } = useTopPlaces(
    5, bizStatus, dateRange, placeSort, MIN_REVIEWS_FOR_RATE,
  )
  const { data: places = [] } = usePlaces()
  const { data: zones = [] } = useZones(dateRange)

  // รายการรีวิว — ใช้ /reviews ตัวเดียวทั้งโหมด "ทุกร้าน" และ "เลือกร้าน"
  // (ส่ง place_id) เพื่อให้ตัวกรองหลักของหน้า ลำดับ และยอดรวม เป็นชุดเดียวกันเสมอ
  const { data: reviewData, isLoading: reviewsLoading } = useReviews({
    severity: filterSeverity || undefined,
    category: filterCategory || undefined,
    place_id: selectedPlace ?? undefined,
    page_size: 30,
    dateRange,
    viewMode,
    status: bizStatus,
  })
  const reviews = reviewData?.items ?? []

  // ── บรรทัดกำกับเหนือรายการรีวิว ─────────────────────────────────────────
  // กฎ: ต้องบอก "ทุกตัวกรองที่กำลังทำงานอยู่" ห้ามละตัวใดตัวหนึ่ง เรียงลำดับคงที่
  // เพื่อให้อ่านซ้ำได้ง่าย — ตัวที่ไม่ได้เลือกไม่ต้องเขียนถึง แต่ห้ามมีกรณีที่กรองอยู่
  // แล้วไม่ปรากฏ เพราะคนอ่านจะเข้าใจว่าเห็นภาพกว้างกว่าความจริง
  const VIEW_NOUN: Record<ViewMode, string> = {
    complaints: 'คำบ่น', praise: 'คำชม', all: 'รีวิว',
  }
  const SEVERITY_NOUN: Record<string, string> = {
    high: 'ระดับสูง', medium: 'ระดับกลาง', low: 'ระดับต่ำ',
  }
  const activeFilters = [
    dateRange.from || dateRange.to ? dateRange.label : null,
    bizStatus !== 'all' ? STATUS_OPTIONS.find(o => o.key === bizStatus)?.label : null,
    selectedPlace ? places.find(p => p.id === selectedPlace)?.name : null,
    filterCategory ? `หมวด${filterCategory}` : null,
    filterSeverity ? SEVERITY_NOUN[filterSeverity] : null,
  ].filter(Boolean)
  const reviewCaption =
    `${VIEW_NOUN[viewMode]} ${(reviewData?.total ?? 0).toLocaleString()} รายการ` +
    (activeFilters.length ? ` · ${activeFilters.join(' · ')}` : '')

  // "ปัญหาหลัก" = ปัญหาจริงตัวแรก (ข้ามความคิดเห็นทั่วไป/อื่นๆ) เสมอ ไม่ว่าจะกดปุ่มไหน
  const NON_PROBLEM = ['ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)', 'อื่นๆ']
  const topCategory =
    insights?.top_pain_point_categories?.find(c => !NON_PROBLEM.includes(c.category))?.category ?? '—'

  return (
    <div className="min-h-screen bg-brand-bg p-6 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-brand-text">
            Pain Point Dashboard — การท่องเที่ยวพิษณุโลก
          </h1>
          <p className="text-brand-subtext text-sm mt-1">
            วิเคราะห์จากรีวิว Google Maps · มหาวิทยาลัยนเรศวร
          </p>
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
        </div>
      </div>
      {bizStatus === 'closed' && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-2 text-sm text-red-300">
          🔴 กำลังดูเฉพาะ<b>ร้านที่ปิด</b> — วิเคราะห์รีวิวเพื่อหาว่าอาจปิดเพราะเหตุใด (คลิกกราฟเพื่อเจาะดูรีวิว)
        </div>
      )}

      {/* Date range filter */}
      <div className="bg-brand-card rounded-xl p-3 border border-brand-border">
        <DateRangeSelector value={dateRange} onChange={(dr) => { setDateRange(dr); setDrillCategory(null) }} />
      </div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="สถานที่ทั้งหมด"
          value={insightsLoading ? '…' : (insights?.total_places ?? 0)}
          subtitle="สถานที่ท่องเที่ยวในพิษณุโลก"
          accentColor="#3b82f6"
        />
        <KPICard
          title="รีวิวที่วิเคราะห์แล้ว"
          value={insightsLoading ? '…' : (insights?.total_analyzed ?? 0)}
          subtitle={
            `จากทั้งหมด ${formatCount(insights?.total_reviews)} รีวิว · `
            + `มีข้อความให้วิเคราะห์ ${formatCount(insights?.total_with_text)} รีวิว`
          }
          accentColor="#22d3ee"
        />
        <KPICard
          title="อัตราการบ่น"
          value={
            insights?.complaint_rate == null
              ? '—'
              : `${(insights.complaint_rate * 100).toFixed(1)}%`
          }
          accentColor="#f97316"
          // ตัวเลขหลักเป็น % แล้ว บรรทัดรองจึงเขียนแค่ n/ตัวส่วน ไม่ซ้ำ % อีก
          // (กฎคือ % ต้องมี n ควบคู่ ไม่ใช่ต้องเขียน % สองรอบ)
          subtitle={
            insights?.complaint_rate == null
              ? '—'
              : `${formatCount(insights.sentiment_counts?.negative)}`
                + `/${formatCount(insights.total_with_text)} ของรีวิวที่มีข้อความ`
          }
        />

        <KPICard
          title="ปัญหาระดับสูง"
          value={insightsLoading ? '…' : (insights?.severity_counts?.['high'] ?? 0)}
          rate={insights?.severity_share?.['high'] ?? null}
          denominator={insights?.sentiment_counts?.negative ?? null}
          rateOf="คำบ่นทั้งหมด"
          unit="คอมเมนต์"
          accentColor="#ef4444"
          breakdown={{
            high: insights?.severity_counts?.['high'] ?? 0,
            medium: insights?.severity_counts?.['medium'] ?? 0,
            low: insights?.severity_counts?.['low'] ?? 0,
          }}
          riskPlaces={topPlaces?.slice(0, 3).map((p: any) => ({
            name: p.name,
            high_count: p.high_count,
          }))}
        />
        <KPICard
          title="Pain Point อันดับ 1"
          value={insightsLoading ? '…' : topCategory}
          subtitle="หมวดที่พบบ่อยที่สุด"
          accentColor="#f97316"
        />
      </div>

      {/* View mode toggle — 3 โหมด: คำบ่น / คำชม / ทั้งหมด (คุมกราฟ + drill-down + จุดเด่นให้ตรงกัน) */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-brand-subtext text-sm">มุมมอง:</span>
        <div className="inline-flex rounded-lg border border-brand-border overflow-hidden">
          {[
            { key: 'complaints', label: '🔴 คำบ่น', color: '#ef4444', hint: 'เห็นเฉพาะรีวิวเชิงลบ = pain point จริง' },
            { key: 'praise',     label: '⭐ คำชม',  color: '#22c55e', hint: 'เห็นเฉพาะรีวิวเชิงบวก = จุดแข็ง' },
            { key: 'all',        label: '📊 ทั้งหมด', color: '#3b82f6', hint: 'รวมทุกรีวิว ทุกอารมณ์ ทุกหมวด' },
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
          {viewMode === 'complaints' && 'รีวิวเชิงลบเท่านั้น — หมวดที่ถูกบ่นมากสุด'}
          {viewMode === 'praise'     && 'รีวิวเชิงบวกเท่านั้น — หมวดที่ถูกชมมากสุด'}
          {viewMode === 'all'        && 'ไม่กรอง — เห็นทุกรีวิวทุกอารมณ์'}
        </span>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          {insights?.top_pain_point_categories && (
            <PainPointChart
              data={insights.top_pain_point_categories}
              negativeTotal={insights.sentiment_counts?.negative ?? null}
              totalWithText={insights.total_with_text ?? null}
              title={
                viewMode === 'praise'
                  ? '⭐ หมวดที่ถูกชมมากที่สุด'
                  : viewMode === 'all'
                  ? '📊 หมวดที่พูดถึงมากที่สุด'
                  : '🔴 Pain Point ตามหมวดหมู่'
              }
              onCategoryClick={(c) => setDrillCategory(c === drillCategory ? null : c)}
            />
          )}
        </div>
        <div>
          {insights?.severity_counts && (
            <SeverityPie
              data={insights.severity_counts}
              share={insights.severity_share}
              negativeTotal={insights.sentiment_counts?.negative ?? null}
            />
          )}
        </div>
      </div>

      {/* Drill-down: ร้านที่มีปัญหาหมวดที่คลิก */}
      {drillCategory && (
        <CategoryDrilldown category={drillCategory} status={bizStatus} viewMode={viewMode} dateRange={dateRange} onClose={() => setDrillCategory(null)} />
      )}

      {/* จุดเด่น (positive) — โชว์ในโหมด "คำบ่น" และ "ทั้งหมด" (ให้เห็นสองด้าน) — ซ่อนใน "คำชม" (เพราะซ้ำกับกราฟ) */}
      {viewMode !== 'praise' && (
        <PositiveHighlights status={bizStatus} dateRange={dateRange} />
      )}

      {/* แนวโน้มปัญหาตามช่วงเวลา (นับจากวันที่เขียนรีวิว — ไม่ขึ้นกับตัวกรองด้านบน) */}
      <TrendingPanel dateRange={dateRange} status={bizStatus} />

      {/* ดาวน์โหลดรายงานประจำเดือน */}
      <ReportDownload />

      {/* Top problematic places — สลับดู "จำนวนมากสุด" กับ "อัตราสูงสุด" ได้ */}
      {topPlaces && topPlaces.length > 0 && (
        <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
          <div className="flex items-start justify-between gap-3 flex-wrap mb-1">
            <div>
              <h3 className="text-brand-text font-semibold">สถานที่ที่มีปัญหามากสุด (Top 5)</h3>
              <p className="text-brand-subtext text-xs mt-0.5">
                {placeSort === 'count'
                  ? 'เรียงตามจำนวนคำบ่นระดับสูง — ร้านที่มีรีวิวเยอะจะได้เปรียบ'
                  : `เรียงตามอัตรา = คำบ่นระดับสูง ÷ รีวิวที่มีข้อความ · `
                    + `เฉพาะร้านที่มีรีวิวตั้งแต่ ${MIN_REVIEWS_FOR_RATE} ขึ้นไป`}
              </p>
            </div>
            <div className="inline-flex rounded-lg border border-brand-border overflow-hidden">
              {([['count', 'จำนวนมากสุด'], ['rate', 'อัตราสูงสุด']] as const).map(([k, lbl]) => (
                <button
                  key={k}
                  onClick={() => setPlaceSort(k)}
                  className={`px-3 py-1 text-xs transition-colors ${
                    placeSort === k ? 'bg-brand-primary text-white'
                                    : 'bg-brand-card text-brand-subtext hover:text-brand-text'
                  }`}
                >
                  {lbl}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-2 mt-3">
            {topPlaces.map((p, i) => {
              // ความยาวแท่งอ้างกับตัวชี้วัดที่กำลังเรียงอยู่ ไม่ใช่จำนวนดิบเสมอ
              const metric = placeSort === 'rate' ? (p.high_rate ?? 0) : p.high_count
              const top = placeSort === 'rate'
                ? (topPlaces[0]?.high_rate ?? 1)
                : (topPlaces[0]?.high_count || 1)
              return (
                <div key={p.id} className="flex items-center gap-3">
                  <span className="text-brand-subtext w-5 text-sm">{i + 1}.</span>
                  <div className="flex-1 bg-brand-bg rounded-full h-5 overflow-hidden">
                    <div
                      className="h-full bg-red-500/70 rounded-full transition-all"
                      style={{ width: `${Math.min(100, (metric / (top || 1)) * 100)}%` }}
                    />
                  </div>
                  <span className="text-brand-text text-sm w-40 truncate">{p.name}</span>
                  <StatusBadge status={p.business_status} />
                  {/* ห้ามโชว์ % โดยไม่มี n — formatRate ใส่ (a/b) ให้เสมอ */}
                  <span className="text-red-400 text-sm w-40 text-right whitespace-nowrap">
                    {placeSort === 'rate'
                      ? formatRate(p.high_rate, p.high_count_with_text, p.review_count_with_text)
                      : `🔥 ${formatCount(p.high_count)} สูง`}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Zone Comparison */}
      {zones.length > 0 && (
        <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-brand-text font-semibold">Pain Point ตามพื้นที่</h3>
              <p className="text-brand-subtext text-xs mt-1">
                เปรียบเทียบปัญหาของแต่ละโซนในพิษณุโลก
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {zones.map((z) => {
              const total = z.high_count + z.medium_count + z.low_count || 1
              const highPct = Math.round((z.high_count / total) * 100)
              return (
                <div key={z.zone} className="bg-brand-bg rounded-lg p-4 border border-brand-border">
                  <div className="text-brand-text font-medium text-sm mb-1">{z.label}</div>
                  <div className="text-brand-subtext text-xs mb-3">
                    {z.place_count} สถานที่ · {z.analyzed_count} รีวิว
                  </div>

                  {/* Severity bar */}
                  <div className="flex h-2 rounded-full overflow-hidden mb-2">
                    <div className="bg-red-500" style={{ width: `${Math.round((z.high_count / total) * 100)}%` }} />
                    <div className="bg-yellow-500" style={{ width: `${Math.round((z.medium_count / total) * 100)}%` }} />
                    <div className="bg-green-500" style={{ width: `${Math.round((z.low_count / total) * 100)}%` }} />
                  </div>

                  {/* ระดับความรุนแรง: สูง / กลาง / ต่ำ (ใช้คำเดียวกันทั้งเว็บ) */}
                  <div className="flex justify-between text-xs text-brand-subtext mb-3">
                    <span className="text-red-400">🔥 {z.high_count} สูง</span>
                    <span className="text-yellow-400">⚠️ {z.medium_count} กลาง</span>
                    <span className="text-green-400">💬 {z.low_count} ต่ำ</span>
                  </div>

                  {z.top_category && (
                    <div className="text-xs bg-brand-border text-brand-subtext px-2 py-1 rounded truncate">
                      🔴 {z.top_category}
                    </div>
                  )}

                  {z.analyzed_count === 0 && (
                    <div className="text-xs text-brand-subtext italic">ยังไม่มีข้อมูล</div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Filters + Review List */}
      <div className="bg-brand-card rounded-xl p-5 border border-brand-border space-y-4">
        <h3 className="text-brand-text font-semibold">รีวิว</h3>

        {/* Filter controls */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <PlaceSelector
            places={places}
            selectedId={selectedPlace}
            onChange={setSelectedPlace}
          />
          <select
            className="bg-brand-bg border border-brand-border text-brand-text rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-primary"
            value={filterSeverity}
            onChange={e => setFilterSeverity(e.target.value)}
          >
            <option value="">— ทุกระดับ —</option>
            <option value="high">🔥 สูง</option>
            <option value="medium">⚠️ กลาง</option>
            <option value="low">💬 ต่ำ</option>
          </select>
          <select
            className="bg-brand-bg border border-brand-border text-brand-text rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-primary"
            value={filterCategory}
            onChange={e => setFilterCategory(e.target.value)}
          >
            <option value="">— ทุกหมวด —</option>
            {ALL_CATEGORIES.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        <ReviewList
          reviews={reviews}
          loading={reviewsLoading}
          caption={reviewCaption}
          hiddenNoText={reviewData?.hidden_no_text}
        />
      </div>
    </div>
  )
}
