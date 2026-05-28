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
  sentiment: string | null
  pain_point_category: string | null
  pain_point_thai: string | null
  severity: string | null
  keywords: string[] | null
}

export interface CategoryCount {
  category: string
  count: number
}

export interface InsightSummary {
  total_places: number
  total_reviews: number
  total_analyzed: number
  top_pain_point_categories: CategoryCount[]
  severity_distribution: Record<string, number>
  worst_places: { place_name: string; high_count: number }[]
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
