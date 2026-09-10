import { useQuery } from '@tanstack/react-query'
import client from '../api/client'
import type { DateRange } from '../components/DateRangeSelector'
import { dateKey, type ViewMode } from './useInsights'
import type { Review } from '../types'

interface ReviewListResponse {
  total: number
  /** รีวิวที่เข้าเงื่อนไขครบแต่ไม่มีข้อความ (ให้ดาวอย่างเดียว) — ถูกซ่อนจากรายการ */
  hidden_no_text: number
  page: number
  page_size: number
  items: Review[]
}

export function useReviews(filters: {
  category?: string
  severity?: string
  place_id?: number
  page?: number
  page_size?: number
  /** ตัวกรองหลักของหน้า — ต้องเป็นชุดเดียวกับที่ KPI/กราฟใช้ */
  dateRange?: DateRange
  viewMode?: ViewMode
  status?: string
}) {
  const { dateRange, viewMode, status, ...rest } = filters
  return useQuery<ReviewListResponse>({
    // ใช้ from|to เป็นกุญแจ ไม่ใช่ label (label เป็นข้อความแสดงผล ไม่ใช่ตัวระบุตัวตน)
    queryKey: ['reviews-list', rest, dateKey(dateRange), viewMode ?? 'all', status ?? 'all'],
    queryFn: () =>
      client
        .get('/reviews', {
          params: {
            ...rest,
            view_mode: viewMode,
            status,
            date_from: dateRange?.from ?? undefined,
            date_to: dateRange?.to ?? undefined,
          },
        })
        .then(r => r.data),
    staleTime: 2 * 60 * 1000,
  })
}
