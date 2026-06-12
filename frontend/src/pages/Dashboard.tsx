import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import KPICard from '../components/KPICard'
import PainPointChart from '../components/PainPointChart'
import PlaceSelector from '../components/PlaceSelector'
import ReviewList from '../components/ReviewList'
import SeverityPie from '../components/SeverityPie'
import { useInsights, useTopPlaces } from '../hooks/useInsights'
import { usePlaceReviews, usePlaces } from '../hooks/usePlaces'
import { useReviews } from '../hooks/useReviews'

// ── LDA hook ──────────────────────────────────────────────────────────────
interface LdaTopic {
  id: number
  label: string
  keywords: string[]
  review_count: number
  percent: number
}
interface LdaResult {
  num_topics: number
  total_reviews: number
  topics: LdaTopic[]
}

function useLdaTopics() {
  return useQuery<LdaResult>({
    queryKey: ['lda-topics'],
    queryFn: async () => {
      const res = await fetch('/api/insights/lda-topics')
      if (!res.ok) return null
      return res.json()
    },
    retry: false,
    staleTime: 1000 * 60 * 10,
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

  const { data: insights, isLoading: insightsLoading } = useInsights()
  const { data: topPlaces } = useTopPlaces(5)
  const { data: places = [] } = usePlaces()
  const { data: ldaData } = useLdaTopics()

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

  const topCategory = insights?.top_pain_point_categories?.[0]?.category ?? '—'

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

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          {insights?.top_pain_point_categories && (
            <PainPointChart data={insights.top_pain_point_categories} />
          )}
        </div>
        <div>
          {insights?.severity_distribution && (
            <SeverityPie data={insights.severity_distribution} />
          )}
        </div>
      </div>

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

      {/* LDA Topic Modeling */}
      {ldaData && ldaData.topics && (
        <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-brand-text font-semibold">
                หมวดหมู่ Pain Point (LDA Topic Modeling)
              </h3>
              <p className="text-brand-subtext text-xs mt-1">
                ค้นพบอัตโนมัติจาก {ldaData.total_reviews.toLocaleString()} รีวิว
                · {ldaData.num_topics} หมวด
              </p>
            </div>
            <span className="text-xs bg-blue-500/20 text-blue-400 px-2 py-1 rounded-full">
              AI-Generated
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {[...ldaData.topics]
              .sort((a, b) => b.review_count - a.review_count)
              .map((topic) => (
                <div
                  key={topic.id}
                  className="bg-brand-bg rounded-lg p-3 border border-brand-border"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-brand-text text-sm font-medium truncate flex-1">
                      {topic.label}
                    </span>
                    <span className="text-brand-subtext text-xs ml-2 shrink-0">
                      {topic.percent}%
                    </span>
                  </div>

                  {/* Progress bar */}
                  <div className="w-full bg-brand-border rounded-full h-1.5 mb-2">
                    <div
                      className="h-1.5 rounded-full bg-blue-500"
                      style={{ width: `${Math.min(100, topic.percent * 2)}%` }}
                    />
                  </div>

                  {/* Keywords */}
                  <div className="flex flex-wrap gap-1">
                    {topic.keywords.slice(0, 5).map((kw) => (
                      <span
                        key={kw}
                        className="text-xs bg-brand-border text-brand-subtext px-1.5 py-0.5 rounded"
                      >
                        {kw}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
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
