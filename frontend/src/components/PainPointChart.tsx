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

const COLORS = [
  '#3b82f6', '#6366f1', '#8b5cf6', '#a855f7', '#d946ef',
  '#ec4899', '#f43f5e', '#ef4444', '#f97316', '#eab308',
]

interface Props {
  data: CategoryCount[]
  onCategoryClick?: (category: string) => void
  title?: string
}

export default function PainPointChart({ data, onCategoryClick, title = 'Pain Point ตามหมวดหมู่' }: Props) {
  const sorted = [...data].sort((a, b) => b.count - a.count)
  // ปรับความสูงตามจำนวนหมวด (แต่ละแถวเห็นชัด + ไม่ทับกัน)
  const chartHeight = Math.max(280, sorted.length * 38 + 40)

  return (
    <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
      <h3 className="text-brand-text font-semibold mb-1">{title}</h3>
      {onCategoryClick && (
        <p className="text-brand-subtext text-xs mb-3">👆 คลิกแท่งเพื่อดูว่ามาจากร้านไหนบ้าง</p>
      )}
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart data={sorted} layout="vertical" margin={{ left: 10, right: 50, top: 5, bottom: 5 }}>
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
            formatter={(v: number) => [`${v} คอมเมนต์`, 'จำนวน']}
          />
          <Bar
            dataKey="count"
            name="จำนวนคอมเมนต์"
            radius={[0, 4, 4, 0]}
            cursor={onCategoryClick ? 'pointer' : undefined}
            onClick={(d: any) => onCategoryClick?.(d?.category ?? d?.payload?.category)}
          >
            {sorted.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
            {/* แสดงตัวเลขที่ปลายแท่ง อ่านง่ายไม่ต้อง hover */}
            <LabelList dataKey="count" position="right" fill="#e2e8f0" fontSize={11} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
