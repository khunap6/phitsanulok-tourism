import { useQuery } from '@tanstack/react-query'
import client from '../api/client'
import type { Review } from '../types'

interface ReviewListResponse {
  total: number
  page: number
  page_size: number
  items: Review[]
}

export function useReviews(filters: {
  category?: string
  severity?: string
  page?: number
  page_size?: number
}) {
  return useQuery<ReviewListResponse>({
    queryKey: ['reviews-list', filters],
    queryFn: () => client.get('/reviews', { params: filters }).then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
}
