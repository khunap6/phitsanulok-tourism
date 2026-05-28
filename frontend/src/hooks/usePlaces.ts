import { useQuery } from '@tanstack/react-query'
import client from '../api/client'
import type { Place, Review } from '../types'

export function usePlaces() {
  return useQuery<Place[]>({
    queryKey: ['places'],
    queryFn: () => client.get('/places').then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}

export function usePlaceReviews(
  placeId: number | null,
  filters: { severity?: string; category?: string } = {},
) {
  return useQuery<Review[]>({
    queryKey: ['reviews', placeId, filters],
    queryFn: () =>
      client
        .get(`/places/${placeId}/reviews`, { params: filters })
        .then(r => r.data),
    enabled: placeId !== null,
    staleTime: 2 * 60 * 1000,
  })
}
