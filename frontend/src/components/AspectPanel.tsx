import { useState } from 'react'
import AspectChart from './AspectChart'
import { Close, SentimentNeutral, Stars, ViewComplaints, ViewPraise } from './icons'
import {
  useAspectOverview,
  useAspectReviews,
  useCategorySummary,
} from '../hooks/useAspects'
import type { DateRange } from './DateRangeSelector'
import { formatCount, formatPercent } from '../utils/format'
import { formatThaiDayMonth } from '../utils/thaiDate'

/**
 * แผงวิเคราะห์ระดับหมวด (Multi-Aspect)
 *
 * ⚠️ แผงนี้แสดงตัวเลข "สองหน่วย" ที่ห้ามเอามาเทียบกันตรง ๆ
 *   บนสุด  = ระดับรีวิว   1 รีวิวนับครั้งเดียว  รวมได้ 100%
 *   กราฟ   = ระดับหมวด   1 รีวิวนับได้หลายครั้ง รวมเกิน 100%
 *   จึงแยกเป็นสองบล็อกและติดป้ายหน่วยไว้ทุกที่ ไม่วางปนกันในแถวเดียว
 *
 * ⚠️ รายการรีวิวด้านล่างเป็น "ตัวอย่าง" ไม่ใช่ทั้งหมด (backend จำกัด 30 รายการ)
 *   ต้องบอกผู้ใช้เสมอ ไม่งั้นจะเข้าใจว่าหมวดนั้นมีรีวิวแค่นี้
 */

const SENT_LABEL: Record<string, string> = {
  positive: 'ชม', neutral: 'กลางๆ', negative: 'ติ',
}
const SENT_CLS: Record<string, string> = {
  positive: 'text-green-400', neutral: 'text-slate-400', negative: 'text-red-400',
}

interface Props {
  zone?: string | null
  status?: string
  dateRange?: DateRange
  title?: string
}

export default function AspectPanel({
  zone, status = 'operational', dateRange, title = 'วิเคราะห์รายหมวด',
}: Props) {
  const [sel, setSel] = useState<
    { categoryId: number; sentiment: 'positive' | 'neutral' | 'negative' } | null
  >(null)

  const { data: ov } = useAspectOverview(zone, status, dateRange)
  const { data: summary, isLoading } = useCategorySummary(zone, status, dateRange)
  const { data: reviews = [], isLoading: loadingReviews } = useAspectReviews(
    sel?.categoryId ?? null, sel?.sentiment ?? null, zone, status, dateRange,
  )

  const selName = sel
    ? summary?.items.find((i) => i.category_id === sel.categoryId)?.category_name
    : null

  return (
    <section className="space-y-4">
      <h2 className="text-brand-text text-lg font-semibold">{title}</h2>

      {/* ── หน่วยที่ 1: ระดับรีวิว (รวมได้ 100%) ── */}
      {ov && (
        <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
          <div className="flex items-baseline justify-between mb-3">
            <h3 className="text-brand-text font-semibold">ภาพรวมระดับรีวิว</h3>
            <span className="text-brand-subtext text-xs">
              1 รีวิว = 1 ป้าย · รวมได้ 100%
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {([
              ['รีวิวทั้งหมด', ov.total_reviews, null, 'text-brand-text'],
              ['ชม', ov.reviews_positive, ov.total_reviews, 'text-green-400'],
              ['กลางๆ', ov.reviews_neutral, ov.total_reviews, 'text-slate-400'],
              ['ติ', ov.reviews_negative, ov.total_reviews, 'text-red-400'],
            ] as const).map(([label, n, denom, cls]) => (
              <div key={label} className="bg-brand-bg rounded-lg p-3">
                <p className="text-brand-subtext text-xs">{label}</p>
                <p className={`text-xl font-semibold ${cls}`}>{formatCount(n)}</p>
                {denom ? (
                  <p className="text-brand-subtext text-xs">
                    {formatPercent(n / denom)} ของรีวิวทั้งหมด
                  </p>
                ) : (
                  <p className="text-brand-subtext text-xs">ในช่วงที่เลือก</p>
                )}
              </div>
            ))}
          </div>

          {/* ── หน่วยที่ 2: ระดับการกล่าวถึง (รวมเกิน 100%) ── */}
          <div className="mt-4 pt-3 border-t border-brand-border">
            <div className="flex items-baseline justify-between mb-2">
              <h4 className="text-brand-text text-sm font-semibold">
                ภาพรวมระดับการกล่าวถึง
              </h4>
              <span className="text-brand-subtext text-xs">
                1 รีวิวนับได้หลายครั้ง · รวมเกิน 100%
              </span>
            </div>
            <p className="text-brand-subtext text-sm">
              รีวิว {formatCount(ov.total_reviews)} รายการ พูดถึงหมวดต่าง ๆ รวม{' '}
              <span className="text-brand-text font-semibold">
                {formatCount(ov.total_mentions)} ครั้ง
              </span>{' '}
              ({ov.mentions_per_review.toFixed(2)} หมวด/รีวิว) ในจำนวนนี้เป็นคำติ{' '}
              <span className="text-red-400 font-semibold">
                {formatCount(ov.mentions_negative)} ครั้ง
              </span>
            </p>
            <p className="text-brand-subtext text-xs mt-2 leading-relaxed">
              {ov.unit_note}
            </p>
          </div>
        </div>
      )}

      {isLoading && (
        <div className="bg-brand-card rounded-xl p-5 border border-brand-border
                        text-brand-subtext text-sm">กำลังโหลด…</div>
      )}
      {summary && (
        <AspectChart
          data={summary}
          selected={sel}
          onSelect={(categoryId, sentiment) =>
            setSel((cur) =>
              cur?.categoryId === categoryId && cur?.sentiment === sentiment
                ? null
                : { categoryId, sentiment })}
        />
      )}

      {sel && (
        <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
          <div className="flex items-start justify-between gap-3 mb-1">
            <h3 className="text-brand-text font-semibold">
              {selName}{' '}
              <span className={SENT_CLS[sel.sentiment]}>
                — เฉพาะที่{SENT_LABEL[sel.sentiment]}
              </span>
            </h3>
            <button onClick={() => setSel(null)}
                    className="text-brand-subtext hover:text-brand-text">
              <Close size={16} />
            </button>
          </div>
          <p className="text-brand-subtext text-xs mb-3">
            แสดงตัวอย่างสูงสุด 30 รายการ เรียงจากใหม่ไปเก่า — ไม่ใช่ทั้งหมด
          </p>
          {loadingReviews && (
            <p className="text-brand-subtext text-sm">กำลังโหลด…</p>
          )}
          {!loadingReviews && reviews.length === 0 && (
            <p className="text-brand-subtext text-sm">ไม่พบรีวิวในเงื่อนไขนี้</p>
          )}
          <div className="space-y-2">
            {reviews.map((r) => (
              <div key={`${r.review_id}-${r.category_id}`}
                   className="bg-brand-bg rounded-lg p-3">
                <div className="flex items-center gap-2 flex-wrap text-xs mb-1">
                  <span className="text-brand-text">{r.place_name}</span>
                  {r.rating != null && <Stars value={r.rating} />}
                  <span className={SENT_CLS[r.aspect_sentiment]}>
                    {r.aspect_sentiment === 'negative'
                      ? <ViewComplaints size={12} className="inline" />
                      : r.aspect_sentiment === 'positive'
                        ? <ViewPraise size={12} className="inline" />
                        : <SentimentNeutral size={12} className="inline" />}
                    {' '}{SENT_LABEL[r.aspect_sentiment]}หมวดนี้
                  </span>
                  {r.overall_sentiment && r.overall_sentiment !== r.aspect_sentiment && (
                    <span className="text-brand-subtext">
                      (อารมณ์รวมของรีวิว: {SENT_LABEL[r.overall_sentiment]})
                    </span>
                  )}
                  {r.is_primary && (
                    <span className="text-brand-subtext">· หมวดหลัก</span>
                  )}
                  <span className="text-brand-subtext ml-auto">
                    {r.review_date
                      ? formatThaiDayMonth(r.review_date)
                      : r.review_date_text}
                  </span>
                </div>
                <p className="text-brand-text text-sm leading-relaxed">{r.text}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
