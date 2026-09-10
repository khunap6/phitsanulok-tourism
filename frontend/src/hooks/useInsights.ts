import { useQuery } from '@tanstack/react-query'
import client from '../api/client'
import type { GeoCollection, InsightSummary, TopPlace } from '../types'
import type { DateRange } from '../components/DateRangeSelector'

/** แปลง DateRange → params ที่ backend ต้องการ (จะไม่ใส่ถ้าเป็น null) */
function dateParams(dr?: DateRange): Record<string, string> {
  if (!dr || (!dr.from && !dr.to)) return {}
  const p: Record<string, string> = {}
  if (dr.from) p.date_from = dr.from
  if (dr.to) p.date_to = dr.to
  return p
}

/**
 * กุญแจ cache ของช่วงเวลา — ต้องใช้ from/to ไม่ใช่ label
 * label คือข้อความสำหรับแสดงผล ไม่ใช่ตัวระบุตัวตน: preset อย่าง "30 วันย้อนหลัง"
 * มี label คงที่แต่ from/to ขยับทุกวัน ถ้าใช้ label เป็นกุญแจ เปิดเว็บค้างข้ามวัน
 * แล้ว cache จะไม่ invalidate (ได้ข้อมูลของเมื่อวาน)
 */
export function dateKey(dr?: DateRange): string {
  return `${dr?.from ?? 'all'}|${dr?.to ?? 'all'}`
}

/** โหมดมุมมองของ Pain Point Dashboard */
export type ViewMode = 'complaints' | 'praise' | 'all'

export function useInsights(viewMode: ViewMode = 'complaints', status = 'operational', dateRange?: DateRange) {
  return useQuery<InsightSummary>({
    queryKey: ['insights', viewMode, status, dateKey(dateRange)],
    queryFn: () =>
      client
        .get('/insights/summary', {
          params: { view_mode: viewMode, status, ...dateParams(dateRange) },
        })
        .then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * sort='count' → เรียงตามจำนวน (ร้านรีวิวเยอะได้เปรียบ) = พฤติกรรมเดิม
 * sort='rate'  → เรียงตามอัตรา เฉพาะร้านที่มีรีวิว (ที่มีข้อความ) >= minReviews
 */
export function useTopPlaces(
  limit = 5,
  status = 'operational',
  dateRange?: DateRange,
  sort: 'count' | 'rate' = 'count',
  minReviews = 30,
) {
  return useQuery<TopPlace[]>({
    queryKey: ['top-places', limit, status, dateKey(dateRange), sort, minReviews],
    queryFn: () =>
      client
        .get('/insights/top-places', {
          params: { limit, status, sort, min_reviews: minReviews, ...dateParams(dateRange) },
        })
        .then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export interface PositiveHighlight { category: string; count: number }

export function usePositiveHighlights(
  zone?: string,
  limit = 5,
  status = 'operational',
  dateRange?: DateRange,
) {
  return useQuery<PositiveHighlight[]>({
    queryKey: ['positive-highlights', zone ?? 'all', limit, status, dateKey(dateRange)],
    queryFn: () =>
      client
        .get('/insights/positive-highlights', {
          params: { zone, limit, status, ...dateParams(dateRange) },
        })
        .then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * status default = 'all' ให้ตรงกับ backend (แผนที่แสดงทุกร้านรวมร้านปิดมาตลอด)
 * ถ้าจะกรองต้องส่งมาชัด ๆ จาก MapView
 */
export function useMapGeoJSON(dateRange?: DateRange, status = 'all') {
  return useQuery<GeoCollection>({
    queryKey: ['map-geojson', dateKey(dateRange), status],
    queryFn: () =>
      client
        .get('/map/geojson', { params: { status, ...dateParams(dateRange) } })
        .then(r => r.data),
    staleTime: 10 * 60 * 1000,
  })
}
