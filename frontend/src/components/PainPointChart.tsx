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
import type { CategoryCount } from '../types'

const COLORS = [
  '#3b82f6', '#6366f1', '#8b5cf6', '#a855f7', '#d946ef',
  '#ec4899', '#f43f5e', '#ef4444', '#f97316', '#eab308',
]

interface Props {
  data: CategoryCount[]
  onCategoryClick?: (category: string) => void
}

export default function PainPointChart({ data, onCategoryClick }: Props) {
  const sorted = [...data].sort((a, b) => b.count - a.count)

  return (
    <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
      <h3 className="text-brand-text font-semibold mb-1">Pain Point ตามหมวดหมู่</h3>
      {onCategoryClick && (
        <p className="text-brand-subtext text-xs mb-3">👆 คลิกแท่งเพื่อดูว่ามาจากร้านไหนบ้าง</p>
      )}
      <ResponsiveContainer width="100%" height={280}>
        <BarChart data={sorted} layout="vertical" margin={{ left: 10, right: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" horizontal={false} />
          <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 12 }} />
          <YAxis
            type="category"
            dataKey="category"
            width={160}
            tick={{ fill: '#94a3b8', fontSize: 11 }}
          />
          <Tooltip
            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
            labelStyle={{ color: '#e2e8f0' }}
            itemStyle={{ color: '#94a3b8' }}
            cursor={{ fill: '#33415533' }}
          />
          <Bar
            dataKey="count"
            name="จำนวนรีวิว"
            radius={[0, 4, 4, 0]}
            cursor={onCategoryClick ? 'pointer' : undefined}
            onClick={(d: any) => onCategoryClick?.(d?.category ?? d?.payload?.category)}
          >
            {sorted.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
