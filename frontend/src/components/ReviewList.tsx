import type { Review } from '../types'
import { formatThaiMonthYear } from '../utils/thaiDate'

const SEVERITY_STYLE: Record<string, string> = {
  high: 'bg-red-500/20 text-red-400 border-red-500/40',
  medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/40',
  low: 'bg-green-500/20 text-green-400 border-green-500/40',
}

// severity = ระดับความรุนแรงของปัญหา (ไม่ใช่ตัวบอกว่าชมหรือบ่น — ดูที่ sentiment แทน)
const SEVERITY_TH: Record<string, string> = {
  high: '🔥 สูง',
  medium: '⚠️ กลาง',
  low: '💬 ต่ำ',
}

/**
 * แสดงวันที่จาก review_date_approx เป็น "มี.ค. 2565" (พ.ศ.)
 *
 * ไม่ใช้ review_date เพราะเป็นข้อความสัมพัทธ์ ณ เวลาที่ scrape — "3 ปีที่แล้ว"
 * ที่เก็บมาเมื่อ 2 ปีก่อน วันนี้คือ 5 ปี ยิ่งนานยิ่งผิด
 * เหลือไว้เป็น fallback เฉพาะรีวิวเก่าที่ยังไม่มี approx
 */
function reviewDate(r: Review): string | null {
  return (r.review_date_approx && formatThaiMonthYear(r.review_date_approx)) || r.review_date
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
  /** บรรทัดกำกับว่ากำลังดูอะไรอยู่ — ต้องบอกทุกตัวกรองที่ทำงานอยู่ */
  caption?: string
  /** จำนวนรีวิวที่ถูกซ่อนเพราะให้ดาวอย่างเดียว (ไม่มีข้อความให้วิเคราะห์) */
  hiddenNoText?: number
}

export default function ReviewList({ reviews, loading, caption, hiddenNoText }: Props) {
  // บรรทัดกำกับต้องอยู่นอก early return — ตอน "ไม่พบรีวิว" คือตอนที่ผู้ใช้ต้องรู้
  // มากที่สุดว่ากำลังกรองอะไรอยู่ ถ้าซ่อนไปจะเข้าใจว่าไม่มีข้อมูลเลยทั้งระบบ
  const header = caption ? (
    <p className="text-brand-subtext text-xs border-l-2 border-brand-primary/50 pl-2">
      {caption}
    </p>
  ) : null

  const hiddenNote =
    hiddenNoText != null && hiddenNoText > 0 ? (
      <p className="text-brand-subtext text-xs pt-1">
        ซ่อนรีวิวที่ให้ดาวอย่างเดียว {hiddenNoText.toLocaleString()} รายการ
        (ไม่มีข้อความให้วิเคราะห์)
      </p>
    ) : null

  if (loading) {
    return (
      <div className="space-y-3">
        {header}
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-brand-card rounded-xl p-4 animate-pulse h-24 border border-brand-border" />
        ))}
      </div>
    )
  }

  if (reviews.length === 0) {
    return (
      <div className="space-y-3">
        {header}
        <div className="text-brand-subtext text-center py-10">
          ไม่พบรีวิวที่ตรงกับเงื่อนไข
        </div>
        {hiddenNote}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {header}
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
            {reviewDate(r) && (
              <span className="text-brand-subtext text-xs ml-auto">{reviewDate(r)}</span>
            )}
          </div>
          <p className="text-brand-text text-sm leading-relaxed">{r.text}</p>
          {r.pain_point_thai && (
            <p className="text-brand-subtext text-xs mt-1 italic">{r.pain_point_thai}</p>
          )}
        </div>
      ))}
      {hiddenNote}
    </div>
  )
}
