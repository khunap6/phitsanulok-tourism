import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { CategoryCount } from '../types'
import { formatCount, formatPercent, formatRateOf } from '../utils/format'

const COLORS = [
  '#3b82f6', '#6366f1', '#8b5cf6', '#a855f7', '#d946ef',
  '#ec4899', '#f43f5e', '#ef4444', '#f97316', '#eab308',
]

interface Props {
  data: CategoryCount[]
  onCategoryClick?: (category: string) => void
  title?: string
  /** จำนวนคำบ่นทั้งหมด = ตัวส่วนของ share_of_negative (โหมดคำบ่นเท่านั้น) */
  negativeTotal?: number | null
  /** รีวิวที่มีข้อความทั้งหมด = ตัวส่วนของ rate_of_all */
  totalWithText?: number | null
}

export default function PainPointChart({
  data,
  onCategoryClick,
  title = 'Pain Point ตามหมวดหมู่',
  negativeTotal,
  totalWithText,
}: Props) {
  const sorted = [...data].sort((a, b) => b.count - a.count)
  // ปรับความสูงตามจำนวนหมวด (แต่ละแถวเห็นชัด + ไม่ทับกัน)
  const chartHeight = Math.max(280, sorted.length * 38 + 40)

  /**
   * เลือกตัวส่วนตามโหมด — ชุดเดียวใช้ทั้งป้ายท้ายแท่งและ tooltip
   * โหมดคำบ่น: share_of_negative (÷ คำบ่นทั้งหมด)
   * โหมดอื่น : rate_of_all      (÷ รีวิวที่มีข้อความทั้งหมด)
   */
  const useShare = sorted.some(d => d.share_of_negative != null)
  const denom = useShare ? negativeTotal : totalWithText
  const denomLabel = useShare ? 'คำบ่น' : 'รีวิวทั้งหมด'
  const pctOf = (d: CategoryCount) =>
    (useShare ? d.share_of_negative : d.rate_of_all) ?? null

  /**
   * เตรียมข้อความป้ายไว้ใน data เลย แล้วให้ LabelList อ่านผ่าน dataKey
   *
   * ทำไมไม่ใช้ <LabelList content={...}> ที่วาด <text> เอง: มันวาดได้แค่ render แรก
   * พอ re-render (เช่นสลับโหมดคำบ่น/คำชม) recharts เรียก content ด้วย props ที่ยัง
   * ไม่มี index/x ครบ ป้ายจึงหายทั้งแถบ — วิธีนี้ไม่ต้องพึ่ง index จึงทนกว่า
   */
  const chartData = sorted.map(d => {
    const pct = pctOf(d)
    return {
      ...d,
      // ใช้ non-breaking space ( ) ไม่ใช่ช่องว่างปกติ
      // recharts ตัดคำที่ช่องว่างเมื่อแท่งสั้น ทำให้ป้ายกลายเป็น 2-3 บรรทัดซ้อนกัน
      // (วัดจริง: "38 · 1.6%" ถูกตัดเป็น 3 บรรทัด สูง 37px แทน 15px)
      // NBSP ไม่มีจุดตัดคำ ป้ายจึงอยู่บรรทัดเดียวเสมอ
      _label: pct == null
        ? formatCount(d.count)
        : `${formatCount(d.count)}\u00A0·\u00A0${formatPercent(pct)}`,
    }
  })

  return (
    <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
      <h3 className="text-brand-text font-semibold mb-1">{title}</h3>
      {/* ป้ายท้ายแท่งเขียน % ไม่ได้ทุกแท่งว่า "ของอะไร" (ยาวเกิน) จึงบอกตัวส่วน
          ครั้งเดียวที่นี่ — ทุกแท่งใช้ตัวส่วนเดียวกันจึงไม่กำกวม */}
      <p className="text-brand-subtext text-xs mb-1">
        ตัวเลขท้ายแท่ง = จำนวน · % ของ{denomLabel}
        {denom != null && denom > 0 ? ` (ฐาน ${formatCount(denom)} รายการ)` : ''}
      </p>
      {onCategoryClick && (
        <p className="text-brand-subtext text-xs mb-3">👆 คลิกแท่งเพื่อดูว่ามาจากร้านไหนบ้าง</p>
      )}
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart data={chartData} layout="vertical" margin={{ left: 10, right: 96, top: 5, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fill: '#94a3b8', fontSize: 12 }}
            label={{ value: 'จำนวนคอมเมนต์', position: 'insideBottom', offset: -2, fill: '#94a3b8', fontSize: 11 }}
          />
          <YAxis
            type="category"
            dataKey="category"
            width={210}
            tick={{ fill: '#e2e8f0', fontSize: 12 }}
            interval={0}
          />
          <Tooltip
            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
            labelStyle={{ color: '#e2e8f0' }}
            itemStyle={{ color: '#94a3b8' }}
            cursor={{ fill: '#33415533' }}
            formatter={(v: number, _n: any, item: any) => {
              const d = sorted.find(x => x.category === item?.payload?.category)
              // สัดส่วนของอะไร ต้องเขียนกำกับ — "20% ของคำบ่น" กับ
              // "3% ของรีวิวทั้งหมด" หน้าตาเหมือนกันแต่คนละความหมาย
              const line = formatRateOf(d ? pctOf(d) : null, d?.count, denom, denomLabel)
              return [`${formatCount(v)} คอมเมนต์ · ${line}`, 'จำนวน']
            }}
          />
          {/* isAnimationActive={false}: recharts วาด LabelList ตอน animation จบ
              พอสลับโหมด (คำบ่น/คำชม/ทั้งหมด) ข้อมูลเปลี่ยนกลางทาง animation ไม่จบ
              ป้ายท้ายแท่งจึงหายทั้งแถบ — วัดจริงแล้วหายทุกครั้งที่สลับโหมด */}
          <Bar
            dataKey="count"
            name="จำนวนคอมเมนต์"
            radius={[0, 4, 4, 0]}
            isAnimationActive={false}
            cursor={onCategoryClick ? 'pointer' : undefined}
            onClick={(d: any) => onCategoryClick?.(d?.category ?? d?.payload?.category)}
          >
            {chartData.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
            {/* แสดงทั้งจำนวนและ % ที่ปลายแท่ง อ่านได้ทันทีไม่ต้อง hover
                (tooltip ยังคงไว้ตามเดิม สำหรับดูรายละเอียดพร้อมตัวส่วนเต็ม) */}
            {/* valueAccessor: recharts resolve dataKey ที่ไม่ตรงกับ dataKey ของ Bar ไม่ได้
                (ลองแล้วป้ายไม่ขึ้นเลย) ตัวนี้เป็นทางที่ recharts เตรียมไว้ให้อ่านค่าเอง */}
            <LabelList
              position="right"
              fill="#e2e8f0"
              fontSize={11}
              valueAccessor={(entry: any) =>
                entry?.payload?._label ?? entry?._label ?? entry?.value
              }
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
