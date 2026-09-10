import { useQuery } from '@tanstack/react-query'
import client from '../api/client'
import type { Place } from '../types'

export function usePlaces() {
  return useQuery<Place[]>({
    queryKey: ['places'],
    queryFn: () => client.get('/places').then(r => r.data),
    staleTime: 5 * 60 * 1000,
  })
}
