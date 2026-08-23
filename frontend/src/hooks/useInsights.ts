import { useQuery } from '@tanstack/react-query'
import client from '../api/client'
import type { GeoCollection, InsightSummary } from '../types'
import type { DateRange } from '../components/DateRangeSelector'

/** แปลง DateRange → params ที่ backend ต้องการ (จะไม่ใส่ถ้าเป็น null) */
function dateParams(dr?: DateRange): Record<string, string> {
  if (!dr || (!dr.from && !dr.to)) return {}
  const p: Record<string, string> = {}
  if (dr.from) p.date_from = dr.from
  if (dr.to) p.date_to = dr.to
  return p
}

/** โหมดมุมมองของ Pain Point Dashboard */
export type ViewMode = 'complaints' | 'praise' | 'all'

export function useInsights(viewMode: ViewMode = 'complaints', status = 'operational', dateRange?: DateRange) {
  return useQuery<InsightSummary>({
    queryKey: ['insights', viewMode, status, dateRange?.label ?? 'all'],
    queryFn: () =>
      client
        .get('/insights/summary', {
          params: { view_mode: viewMode, status, ...dateParams(dateRange) },
        })
        .then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function useTopPlaces(limit = 5, status = 'operational', dateRange?: DateRange) {
  return useQuery({
    queryKey: ['top-places', limit, status, dateRange?.label ?? 'all'],
    queryFn: () =>
      client
        .get('/insights/top-places', {
          params: { limit, status, ...dateParams(dateRange) },
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
    queryKey: ['positive-highlights', zone ?? 'all', limit, status, dateRange?.label ?? 'all'],
    queryFn: () =>
      client
        .get('/insights/positive-highlights', {
          params: { zone, limit, status, ...dateParams(dateRange) },
        })
        .then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function useMapGeoJSON() {
  return useQuery<GeoCollection>({
    queryKey: ['map-geojson'],
    queryFn: () => client.get('/map/geojson').then(r => r.data),
    staleTime: 10 * 60 * 1000,
  })
}
