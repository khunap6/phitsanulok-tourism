export interface Place {
  id: number
  name: string
  overall_rating: number | null
  lat: number | null
  lng: number | null
  review_count: number
  high_severity_count: number
}

export interface Review {
  id: number
  place_id: number
  place_name: string | null
  rating: number | null
  text: string
  review_date: string | null
  /** วันที่โดยประมาณจากตอน scrape — ใช้แสดงผลแทน review_date ที่เป็นข้อความสัมพัทธ์ */
  review_date_approx: string | null
  sentiment: string | null
  pain_point_category: string | null
  pain_point_thai: string | null
  severity: string | null
  keywords: string[] | null
}

export interface CategoryCount {
  category: string
  count: number
  /** สัดส่วนในหมู่คำบ่น — null เมื่อ view_mode ไม่ใช่ complaints (ชื่อฟิลด์ต้องไม่โกหก) */
  share_of_negative?: number | null
  /** สัดส่วนเทียบรีวิวที่มีข้อความทั้งหมด — ใช้ได้ทุกโหมด */
  rate_of_all?: number | null
}

export interface InsightSummary {
  total_places: number
  total_reviews: number
  total_analyzed: number
  top_pain_point_categories: CategoryCount[]
  /** ฐานหลวม (ไม่กรอง text_clean/status) — เก็บไว้เพื่อความเข้ากันได้ อย่าใช้คู่กับ severity_share */
  severity_distribution: Record<string, number>
  worst_places: { place_name: string; high_count: number }[]
  /** ตัวส่วนหลักของทุกสัดส่วน: รีวิวที่มีข้อความ + วิเคราะห์แล้ว + ผ่านตัวกรองสถานะ */
  total_with_text?: number | null
  sentiment_counts?: { negative: number; positive: number; neutral: number } | null
  complaint_rate?: number | null
  /** severity บนฐานเดียวกับ severity_share — ใช้คู่กันเสมอ */
  severity_counts?: Record<string, number> | null
  severity_share?: Record<string, number | null> | null
}

export interface TopPlace {
  id: number
  name: string
  overall_rating: number | null
  business_status?: string
  review_count: number
  high_count: number
  medium_count: number
  /** ตัวส่วนของ high_rate — review_count ไม่กรอง text_clean จึงใช้เป็นตัวส่วนไม่ได้ */
  review_count_with_text?: number | null
  /** ตัวเศษของ high_rate */
  high_count_with_text?: number | null
  high_rate?: number | null
}

export interface GeoFeatureProperties {
  id: number
  name: string
  rating: number | null
  review_count: number
  high_count: number
  dominant_severity: string | null
  pain_point_categories: string[]
}

export interface GeoFeature {
  type: 'Feature'
  geometry: { type: 'Point'; coordinates: [number, number] }
  properties: GeoFeatureProperties
}

export interface GeoCollection {
  type: 'FeatureCollection'
  features: GeoFeature[]
}
