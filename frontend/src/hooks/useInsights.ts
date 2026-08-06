import { useQuery } from '@tanstack/react-query'
import client from '../api/client'
import type { GeoCollection, InsightSummary } from '../types'

export function useInsights(painOnly = false, status = 'operational') {
  return useQuery<InsightSummary>({
    queryKey: ['insights', painOnly, status],
    queryFn: () =>
      client.get('/insights/summary', { params: { pain_only: painOnly, status } }).then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function useTopPlaces(limit = 5, status = 'operational') {
  return useQuery({
    queryKey: ['top-places', limit, status],
    queryFn: () =>
      client.get('/insights/top-places', { params: { limit, status } }).then(r => r.data),
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
