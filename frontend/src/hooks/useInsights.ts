import { useQuery } from '@tanstack/react-query'
import client from '../api/client'
import type { GeoCollection, InsightSummary } from '../types'

export function useInsights(painOnly = false) {
  return useQuery<InsightSummary>({
    queryKey: ['insights', painOnly],
    queryFn: () =>
      client.get('/insights/summary', { params: { pain_only: painOnly } }).then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function useTopPlaces(limit = 5) {
  return useQuery({
    queryKey: ['top-places', limit],
    queryFn: () =>
      client.get('/insights/top-places', { params: { limit } }).then(r => r.data),
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
