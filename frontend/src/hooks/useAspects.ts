import { useQuery } from '@tanstack/react-query'
import client from '../api/client'
import { dateKey } from './useInsights'
import type { DateRange } from '../components/DateRangeSelector'

/**
 * ชั้นข้อมูลระดับ "หมวดของรีวิว" (aspect) — คนละชั้นกับ useInsights
 *
 * ⚠️ สองหน่วยนับที่ห้ามเอามาเทียบกันตรง ๆ
 *   จำนวนรีวิว    1 รีวิวนับครั้งเดียว  → รวมได้ 100%
 *   การกล่าวถึง   1 รีวิวนับได้หลายครั้ง → รวมเกิน 100% (วัดได้ 1.93 เท่า)
 *   ทุกที่ที่แสดงตัวเลขต้องบอกให้ชัดว่าเป็นหน่วยไหน ไม่งั้นคนอ่านจะสรุปผิด
 *
 * ⚠️ backend คำนวณตัวตั้งกับตัวส่วนจาก CTE ชุดเดียวกันอยู่แล้ว
 *   ฝั่งนี้จึง "ห้ามคำนวณสัดส่วนเอง" ให้ใช้ share_of_reviews ที่ส่งมา
 *   ถ้าหารเองจะเสี่ยงหารด้วยตัวส่วนคนละชุดกับที่ backend ใช้ (ละเมิดกฎ 1)
 */

function dateParams(dr?: DateRange): Record<string, string> {
  if (!dr || (!dr.from && !dr.to)) return {}
  const p: Record<string, string> = {}
  if (dr.from) p.date_from = dr.from
  if (dr.to) p.date_to = dr.to
  return p
}

export interface CategorySummaryItem {
  category_id: number
  category_name: string
  /** จำนวน "รีวิว" ที่พูดถึงหมวดนี้ — ไม่ใช่จำนวนครั้งที่ถูกพูดถึง */
  n_reviews: number
  n_positive: number
  n_neutral: number
  n_negative: number
  /** หารด้วยจำนวนรีวิวทั้งหมด ไม่ใช่ผลรวมของทุกหมวด */
  share_of_reviews: number
  /** n_negative / n_reviews */
  negative_rate: number
  /** จำนวนรีวิวที่ "หมวดหลัก" คือหมวดนี้ — ผลรวมทุกหมวด = จำนวนรีวิวพอดี */
  n_primary: number
  share_as_primary: number
  np_positive: number
  np_neutral: number
  np_negative: number
  low_data: boolean
  is_non_problem: boolean
}

export interface CategorySummary {
  items: CategorySummaryItem[]
  total_reviews: number
  total_mentions: number
  total_primary: number
  low_data_threshold: number
  denominator_note: string
}

export interface AspectOverview {
  total_reviews: number
  reviews_positive: number
  reviews_neutral: number
  reviews_negative: number
  complaint_rate: number
  total_mentions: number
  mentions_negative: number
  mentions_per_review: number
  unit_note: string
}

export interface AspectReview {
  review_id: number
  text: string
  rating: number | null
  review_date: string | null
  review_date_text: string | null
  place_name: string | null
  category_id: number
  category_name: string
  aspect_sentiment: 'positive' | 'neutral' | 'negative'
  is_primary: boolean
  overall_sentiment: string | null
}

function common(zone?: string | null, status = 'operational', dr?: DateRange) {
  const p: Record<string, string> = { status, ...dateParams(dr) }
  if (zone) p.zone = zone
  return p
}

export function useCategorySummary(
  zone?: string | null, status = 'operational', dateRange?: DateRange,
) {
  return useQuery<CategorySummary>({
    queryKey: ['aspect-summary', zone ?? 'all', status, dateKey(dateRange)],
    queryFn: async () => {
      const { data } = await client.get('/aspects/summary', {
        params: common(zone, status, dateRange),
      })
      return data
    },
  })
}

export function useAspectOverview(
  zone?: string | null, status = 'operational', dateRange?: DateRange,
) {
  return useQuery<AspectOverview>({
    queryKey: ['aspect-overview', zone ?? 'all', status, dateKey(dateRange)],
    queryFn: async () => {
      const { data } = await client.get('/aspects/overview', {
        params: common(zone, status, dateRange),
      })
      return data
    },
  })
}

/**
 * รีวิวของหมวด+อารมณ์หนึ่ง — ใช้ตอนคลิกแท่งกราฟ
 * ส่ง null ทั้งคู่ = ไม่ยิง (ยังไม่ได้เลือกอะไร)
 */
export function useAspectReviews(
  categoryId: number | null,
  sentiment: 'positive' | 'neutral' | 'negative' | null,
  zone?: string | null, status = 'operational', dateRange?: DateRange,
  limit = 30,
) {
  return useQuery<AspectReview[]>({
    enabled: categoryId != null && sentiment != null,
    queryKey: ['aspect-reviews', categoryId, sentiment, zone ?? 'all', status,
               dateKey(dateRange), limit],
    queryFn: async () => {
      const { data } = await client.get('/aspects/reviews', {
        params: {
          ...common(zone, status, dateRange),
          category_id: categoryId,
          aspect_sentiment: sentiment,
          limit,
        },
      })
      return data
    },
  })
}
