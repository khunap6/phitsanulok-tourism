import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'

// ข้อมูลที่เข้ามาเป็นรีวิวเชิงลบ (คำบ่น) แล้ว → แบ่งตามความหนักของปัญหา
const SEVERITY_COLORS: Record<string, string> = {
  high: '#ef4444',   // แดง = สูง
  medium: '#eab308', // เหลือง = กลาง
  low: '#22c55e',    // เขียว = ต่ำ
}

const SEVERITY_LABELS: Record<string, string> = {
  high: 'สูง',
  medium: 'กลาง',
  low: 'ต่ำ',
}

interface Props {
  data: Record<string, number>
}

export default function SeverityPie({ data }: Props) {
  const chartData = Object.entries(data).map(([key, value]) => ({
    name: SEVERITY_LABELS[key] ?? key,
    value,
    color: SEVERITY_COLORS[key] ?? '#94a3b8',
  }))

  return (
    <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
      <h3 className="text-brand-text font-semibold mb-1">ระดับความรุนแรง</h3>
      <p className="text-brand-subtext text-xs mb-3">จากรีวิวเชิงลบ (คำบ่น) ทั้งหมด</p>
      <ResponsiveContainer width="100%" height={240}>
        <PieChart>
          <Pie
            data={chartData}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            outerRadius={85}
            label={({ name, percent }) =>
              `${name} ${(percent * 100).toFixed(0)}%`
            }
            labelLine={{ stroke: '#475569' }}
          >
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
            itemStyle={{ color: '#e2e8f0' }}
          />
          <Legend
            formatter={(value) => (
              <span style={{ color: '#94a3b8', fontSize: 13 }}>{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
