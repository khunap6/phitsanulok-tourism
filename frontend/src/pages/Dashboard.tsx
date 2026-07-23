import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import CategoryDrilldown from '../components/CategoryDrilldown'
import KPICard from '../components/KPICard'
import PainPointChart from '../components/PainPointChart'
import PlaceSelector from '../components/PlaceSelector'
import ReviewList from '../components/ReviewList'
import SeverityPie from '../components/SeverityPie'
import { useInsights, useTopPlaces } from '../hooks/useInsights'
import { usePlaceReviews, usePlaces } from '../hooks/usePlaces'
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

function useZones() {
  return useQuery<ZoneSummary[]>({
    queryKey: ['zones'],
    queryFn: async () => {
      const res = await fetch('/api/insights/zones')
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
  const [painOnly, setPainOnly] = useState(false)
  const [drillCategory, setDrillCategory] = useState<string | null>(null)

  const { data: insights, isLoading: insightsLoading } = useInsights(painOnly)
  const { data: topPlaces } = useTopPlaces(5)
  const { data: places = [] } = usePlaces()
  const { data: zones = [] } = useZones()

  // รีวิวตาม place ที่เลือก หรือ paginated ทั้งหมด
  const { data: placeReviews = [], isLoading: placeReviewsLoading } = usePlaceReviews(
    selectedPlace,
    { severity: filterSeverity || undefined, category: filterCategory || undefined },
  )
  const { data: allReviews, isLoading: allReviewsLoading } = useReviews({
    severity: filterSeverity || undefined,
    category: filterCategory || undefined,
    page_size: 30,
  })

  const reviews = selectedPlace ? placeReviews : (allReviews?.items ?? [])
  const reviewsLoading = selectedPlace ? placeReviewsLoading : allReviewsLoading

  // "ปัญหาหลัก" = ปัญหาจริงตัวแรก (ข้ามความคิดเห็นทั่วไป/อื่นๆ) เสมอ ไม่ว่าจะกดปุ่มไหน
  const NON_PROBLEM = ['ความคิดเห็นทั่วไป (ไม่ระบุปัญหา)', 'อื่นๆ']
  const topCategory =
    insights?.top_pain_point_categories?.find(c => !NON_PROBLEM.includes(c.category))?.category ?? '—'

  return (
    <div className="min-h-screen bg-brand-bg p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-brand-text">
          Pain Point Dashboard — การท่องเที่ยวพิษณุโลก
        </h1>
        <p className="text-brand-subtext text-sm mt-1">
          วิเคราะห์จากรีวิว Google Maps · มหาวิทยาลัยนเรศวร
        </p>
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
          subtitle={`จากทั้งหมด ${insights?.total_reviews ?? 0} รีวิว`}
          accentColor="#22d3ee"
        />
        <KPICard
          title="ปัญหารุนแรงมาก"
          value={insightsLoading ? '…' : (insights?.severity_distribution?.['high'] ?? 0)}
          subtitle="รีวิวระดับ High severity"
          accentColor="#ef4444"
        />
        <KPICard
          title="Pain Point อันดับ 1"
          value={insightsLoading ? '…' : topCategory}
          subtitle="หมวดที่พบบ่อยที่สุด"
          accentColor="#f97316"
        />
      </div>

      {/* Toggle: รวมทั้งหมด / เฉพาะปัญหาจริง */}
      <div className="flex items-center gap-2">
        <span className="text-brand-subtext text-sm">มุมมองกราฟ Pain Point:</span>
        <div className="inline-flex rounded-lg border border-brand-border overflow-hidden">
          <button
            onClick={() => setPainOnly(false)}
            className={`px-3 py-1.5 text-sm transition-colors ${
              !painOnly ? 'bg-brand-primary text-white' : 'bg-brand-card text-brand-subtext hover:text-brand-text'
            }`}
          >
            รวมทั้งหมด
          </button>
          <button
            onClick={() => setPainOnly(true)}
            className={`px-3 py-1.5 text-sm transition-colors ${
              painOnly ? 'bg-red-500 text-white' : 'bg-brand-card text-brand-subtext hover:text-brand-text'
            }`}
          >
            เฉพาะปัญหาจริง
          </button>
        </div>
        <span className="text-brand-subtext text-xs">
          {painOnly ? 'ตัด "ความคิดเห็นทั่วไป" ออก เหลือเฉพาะปัญหาที่แก้ได้' : 'รวมความเห็นทุกแบบ'}
        </span>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          {insights?.top_pain_point_categories && (
            <PainPointChart
              data={insights.top_pain_point_categories}
              onCategoryClick={(c) => setDrillCategory(c === drillCategory ? null : c)}
            />
          )}
        </div>
        <div>
          {insights?.severity_distribution && (
            <SeverityPie data={insights.severity_distribution} />
          )}
        </div>
      </div>

      {/* Drill-down: ร้านที่มีปัญหาหมวดที่คลิก */}
      {drillCategory && (
        <CategoryDrilldown category={drillCategory} onClose={() => setDrillCategory(null)} />
      )}

      {/* Top problematic places */}
      {topPlaces && topPlaces.length > 0 && (
        <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
          <h3 className="text-brand-text font-semibold mb-4">สถานที่ที่มีปัญหามากสุด (Top 5)</h3>
          <div className="space-y-2">
            {topPlaces.map((p: { id: number; name: string; high_count: number; review_count: number }, i: number) => (
              <div key={p.id} className="flex items-center gap-3">
                <span className="text-brand-subtext w-5 text-sm">{i + 1}.</span>
                <div className="flex-1 bg-brand-bg rounded-full h-5 overflow-hidden">
                  <div
                    className="h-full bg-red-500/70 rounded-full transition-all"
                    style={{
                      width: `${Math.min(100, (p.high_count / (topPlaces[0]?.high_count || 1)) * 100)}%`,
                    }}
                  />
                </div>
                <span className="text-brand-text text-sm w-40 truncate">{p.name}</span>
                <span className="text-red-400 text-sm w-16 text-right">{p.high_count} high</span>
              </div>
            ))}
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

                  <div className="flex justify-between text-xs text-brand-subtext mb-3">
                    <span className="text-red-400">{z.high_count} สูง</span>
                    <span className="text-yellow-400">{z.medium_count} กลาง</span>
                    <span className="text-green-400">{z.low_count} ต่ำ</span>
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
            <option value="high">รุนแรงมาก (High)</option>
            <option value="medium">ปานกลาง (Medium)</option>
            <option value="low">เล็กน้อย (Low)</option>
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

        <ReviewList reviews={reviews} loading={reviewsLoading} />
      </div>
    </div>
  )
}
