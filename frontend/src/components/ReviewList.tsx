import type { Review } from '../types'

const SEVERITY_STYLE: Record<string, string> = {
  high: 'bg-red-500/20 text-red-400 border-red-500/40',
  medium: 'bg-orange-500/20 text-orange-400 border-orange-500/40',
  low: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/40',
}

const SEVERITY_TH: Record<string, string> = {
  high: 'รุนแรงมาก',
  medium: 'ปานกลาง',
  low: 'เล็กน้อย',
}

function Badge({ label, className }: { label: string; className: string }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border ${className}`}>
      {label}
    </span>
  )
}

function StarRating({ rating }: { rating: number | null }) {
  if (!rating) return null
  return (
    <span className="text-yellow-400 text-sm">
      {'★'.repeat(rating)}{'☆'.repeat(5 - rating)}
    </span>
  )
}

interface Props {
  reviews: Review[]
  loading?: boolean
}

export default function ReviewList({ reviews, loading }: Props) {
  if (loading) {
    return (
      <div className="space-y-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-brand-card rounded-xl p-4 animate-pulse h-24 border border-brand-border" />
        ))}
      </div>
    )
  }

  if (reviews.length === 0) {
    return (
      <div className="text-brand-subtext text-center py-10">
        ไม่พบรีวิวที่ตรงกับเงื่อนไข
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {reviews.map(r => (
        <div
          key={r.id}
          className="bg-brand-card rounded-xl p-4 border border-brand-border hover:border-brand-primary/50 transition-colors"
        >
          <div className="flex flex-wrap items-center gap-2 mb-2">
            {r.place_name && (
              <span className="text-brand-primary text-sm font-medium">{r.place_name}</span>
            )}
            <StarRating rating={r.rating} />
            {r.severity && (
              <Badge
                label={SEVERITY_TH[r.severity] ?? r.severity}
                className={SEVERITY_STYLE[r.severity] ?? 'bg-slate-700 text-slate-300 border-slate-600'}
              />
            )}
            {r.pain_point_category && (
              <Badge
                label={r.pain_point_category}
                className="bg-blue-500/20 text-blue-400 border-blue-500/40"
              />
            )}
            {r.review_date && (
              <span className="text-brand-subtext text-xs ml-auto">{r.review_date}</span>
            )}
          </div>
          <p className="text-brand-text text-sm leading-relaxed">{r.text}</p>
          {r.pain_point_thai && (
            <p className="text-brand-subtext text-xs mt-1 italic">{r.pain_point_thai}</p>
          )}
        </div>
      ))}
    </div>
  )
}
