import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ClickHint, SentimentNeutral, ViewComplaints, ViewPraise } from './icons'
import type { CategorySummary, CategorySummaryItem } from '../hooks/useAspects'
import { formatCount, formatPercent } from '../utils/format'

/**
 * กราฟแท่งซ้อน 👍😐👎 รายหมวด
 *
 * ⚠️ ทำไมเป็นแท่งซ้อน ไม่ใช่วงกลม
 *   วงกลมสื่อว่า "ส่วนย่อยรวมกันเป็น 100%" ซึ่งไม่จริงที่นี่
 *   1 รีวิวพูดถึงได้หลายหมวด ผลรวมรายหมวดจึงเกินจำนวนรีวิวทั้งหมด (วัดได้ 1.93 เท่า)
 *   แท่งแยกกันต่อหมวดสื่อความถูกต้องกว่า และยังเทียบ "สัดส่วนอารมณ์ในหมวดเดียวกัน" ได้
 *
 * ⚠️ แต่ละแท่ง = จำนวน "รีวิว" ที่พูดถึงหมวดนั้น ไม่ใช่จำนวนครั้งที่ถูกพูดถึง
 *   (review_aspects มี PK = review_id + category_id รีวิวหนึ่งจึงนับได้ครั้งเดียวต่อหมวด)
 *
 * ⚠️ ร้อยละมาจาก backend (share_of_reviews) ห้ามคำนวณเองในหน้าเว็บ
 *   backend หารด้วยตัวส่วนชุดเดียวกับตัวตั้ง ถ้าหารเองจะเสี่ยงใช้คนละตัวส่วน (กฎ 1)
 */

const C_POS = '#22c55e'
const C_NEU = '#94a3b8'
const C_NEG = '#ef4444'

interface Props {
  data: CategorySummary
  /** คลิกแท่งย่อย -> ส่ง (หมวด, อารมณ์) กลับไปให้หน้าแม่กรองรีวิว */
  onSelect?: (categoryId: number, sentiment: 'positive' | 'neutral' | 'negative') => void
  selected?: { categoryId: number; sentiment: string } | null
  title?: string
  /** ซ่อนหมวดที่ไม่ใช่ปัญหา (2 ความคิดเห็นทั่วไป, 11 อื่นๆ) */
  hideNonProblem?: boolean
}

interface Row extends CategorySummaryItem {
  label: string
}

export default function AspectChart({
  data, onSelect, selected, title = 'หมวดที่ถูกพูดถึง', hideNonProblem = false,
}: Props) {
  const items = (hideNonProblem
    ? data.items.filter((i) => !i.is_non_problem)
    : data.items)
  // โหมด 'mention' = ทุกหมวดที่รีวิวพูดถึง  -> ผลรวมเกิน 100%
  // โหมด 'primary' = เฉพาะหมวดหลักของรีวิว -> ผลรวมได้ 100% พอดี
  const [mode, setMode] = useState<'mention' | 'primary'>('mention')
  const K = mode === 'mention'
    ? { tot: 'n_reviews', pos: 'n_positive', neu: 'n_neutral', neg: 'n_negative',
        share: 'share_of_reviews' } as const
    : { tot: 'n_primary', pos: 'np_positive', neu: 'np_neutral', neg: 'np_negative',
        share: 'share_as_primary' } as const

  const rows: Row[] = [...items]
    .sort((a, b) => (b[K.tot] as number) - (a[K.tot] as number))
    .map((i) => ({ ...i, label: i.category_name + (i.low_data ? ' *' : '') }))

  const height = Math.max(300, rows.length * 42 + 48)

  const tip = ({ active, payload }: any) => {
    if (!active || !payload?.length) return null
    const r: Row = payload[0].payload
    return (
      <div className="bg-brand-card border border-brand-border rounded-lg p-3 text-xs">
        <p className="text-brand-text font-semibold mb-1">{r.category_name}</p>
        <p className="text-brand-subtext mb-2">
          {formatCount(r[K.tot] as number)}{' '}
          {mode === 'mention' ? 'รีวิวพูดถึงหมวดนี้' : 'รีวิวที่หมวดนี้เป็นหมวดหลัก'}
          {' · '}
          {formatPercent(r[K.share] as number)} ของรีวิวทั้งหมด
          {' '}({formatCount(data.total_reviews)})
        </p>
        <p className="text-green-400">👍 ชม {formatCount(r[K.pos] as number)}</p>
        <p className="text-slate-400">😐 กลางๆ {formatCount(r[K.neu] as number)}</p>
        <p className="text-red-400">
          👎 ติ {formatCount(r[K.neg] as number)}
          {mode === 'mention' && r.n_reviews > 0
            && ` (${formatPercent(r.negative_rate)} ของหมวดนี้)`}
        </p>
        {r.low_data && (
          <p className="text-yellow-400 mt-1">
            ข้อมูลน้อย (&lt; {data.low_data_threshold} รีวิว) — ไม่ควรสรุปเชิงสถิติ
          </p>
        )}
      </div>
    )
  }

  const isSel = (r: Row, s: string) =>
    selected?.categoryId === r.category_id && selected?.sentiment === s

  return (
    <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
      <div className="flex items-start justify-between gap-3 mb-1 flex-wrap">
        <h3 className="text-brand-text font-semibold">{title}</h3>
        {/* ⚠️ สองโหมดนี้ตอบคำถามคนละข้อ ไม่ใช่มุมมองสวยงามของข้อมูลชุดเดียวกัน
            'ทุกหมวดที่พูดถึง' ตอบว่า "หมวดนี้ถูกพูดถึงบ่อยแค่ไหน" (รวมเกิน 100%)
            'หมวดหลัก'        ตอบว่า "รีวิวส่วนใหญ่มีประเด็นหลักเรื่องอะไร" (รวม 100%)
            ต้องให้ผู้ใช้เลือกได้ และต้องบอกว่าตัวเลขสองโหมดเทียบกันตรง ๆ ไม่ได้ */}
        <div className="flex gap-1 text-xs">
          {([['mention', 'ทุกหมวดที่พูดถึง'],
             ['primary', 'หมวดหลัก (รวม 100%)']] as const).map(([k, lbl]) => (
            <button key={k} onClick={() => setMode(k)}
              className={`px-2 py-1 rounded ${mode === k
                ? 'bg-brand-accent text-white'
                : 'bg-brand-bg text-brand-subtext hover:text-brand-text'}`}>
              {lbl}
            </button>
          ))}
        </div>
      </div>
      <p className="text-brand-subtext text-xs mb-1">
        แต่ละแท่งคือ <span className="text-brand-text">จำนวนรีวิว</span>
        {mode === 'mention' ? 'ที่พูดถึงหมวดนั้น' : 'ที่มีหมวดนั้นเป็นประเด็นหลัก'}
        {' · '}สีแบ่งตามอารมณ์ที่มีต่อหมวดนั้นโดยเฉพาะ
      </p>
      {onSelect && (
        <p className="text-brand-subtext text-xs mb-3 inline-flex items-center gap-1">
          <ClickHint size={13} /> คลิกช่วงสีเพื่อดูรีวิวของหมวดนั้นเฉพาะอารมณ์นั้น
        </p>
      )}

      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={rows} layout="vertical"
                  margin={{ top: 4, right: 56, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
          <XAxis type="number" stroke="#94a3b8" fontSize={11} />
          <YAxis type="category" dataKey="label" width={190}
                 stroke="#94a3b8" fontSize={11} />
          <Tooltip content={tip} cursor={{ fill: '#1e293b55' }} />
          {([
            [K.pos, C_POS, 'positive'],
            [K.neu, C_NEU, 'neutral'],
            [K.neg, C_NEG, 'negative'],
          ] as const).map(([key, color, sent]) => (
            <Bar key={key} dataKey={key} stackId="a" fill={color}
                 cursor={onSelect ? 'pointer' : undefined}
                 onClick={(d: any) => onSelect?.(d.category_id, sent)}>
              {rows.map((r) => (
                <Cell key={`${key}-${r.category_id}`} fill={color}
                      fillOpacity={selected && !isSel(r, sent) ? 0.35 : 1} />
              ))}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs mt-2">
        <span className="inline-flex items-center gap-1 text-green-400">
          <ViewPraise size={12} /> ชม
        </span>
        <span className="inline-flex items-center gap-1 text-slate-400">
          <SentimentNeutral size={12} /> กลางๆ
        </span>
        <span className="inline-flex items-center gap-1 text-red-400">
          <ViewComplaints size={12} /> ติ
        </span>
        {rows.some((r) => r.low_data) && (
          <span className="text-yellow-400">
            * ข้อมูลน้อย (&lt; {data.low_data_threshold} รีวิว)
          </span>
        )}
      </div>

      {/* ⚠️ ข้อความนี้ต้องมีเสมอ ห้ามตัดทิ้ง
          ถ้าไม่บอก ผู้อ่านจะบวกตัวเลขรายหมวดแล้วงงว่าทำไมเกินจำนวนรีวิวทั้งหมด
          หรือแย่กว่านั้นคือคิดว่าระบบคำนวณผิด */}
      <p className="text-brand-subtext text-xs mt-3 leading-relaxed">
        {mode === 'mention' ? (
          <>
            1 รีวิวอาจพูดถึงได้หลายหมวด ตัวเลขแต่ละหมวดจึงรวมกันได้เกินจำนวนรีวิวทั้งหมด
            {' — '}ร้อยละของแต่ละหมวดคิดจาก <span className="text-brand-text">
            จำนวนรีวิวทั้งหมด {formatCount(data.total_reviews)} รีวิว</span>{' '}
            ไม่ใช่จากผลรวมของทุกหมวด
          </>
        ) : (
          <>
            โหมดนี้นับรีวิวละ 1 หมวดเท่านั้น (ประเด็นหลักของรีวิวนั้น){' '}
            ตัวเลขทุกหมวดจึงรวมกันได้ <span className="text-brand-text">
            {formatCount(data.total_primary)} รีวิว = 100% พอดี</span>{' '}
            — เทียบกับโหมด “ทุกหมวดที่พูดถึง” ตรง ๆ ไม่ได้ เพราะคนละหน่วยนับ
          </>
        )}
      </p>
    </div>
  )
}
