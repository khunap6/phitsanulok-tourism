import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { formatCount, formatPercent, formatRateOf } from '../utils/format'

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
  /** จำนวนต่อระดับ — ต้องเป็นฐานเดียวกับ share (ใช้ severity_counts ไม่ใช่ severity_distribution) */
  data: Record<string, number>
  /** สัดส่วนต่อระดับ จาก API (ตัวส่วน = คำบ่นทั้งหมด ไม่ใช่รีวิวทั้งหมด) */
  share?: Record<string, number | null> | null
  /** จำนวนคำบ่นทั้งหมด = ตัวส่วนของ share — ต้องส่งมาเพื่อโชว์ n คู่กับ % */
  negativeTotal?: number | null
}

export default function SeverityPie({ data, share, negativeTotal }: Props) {
  const chartData = Object.entries(data).map(([key, value]) => ({
    key,
    name: SEVERITY_LABELS[key] ?? key,
    value,
    // ใช้ share จาก API ถ้ามี — ห้ามให้ recharts คำนวณ percent เอง
    // เพราะ recharts หารด้วยผลรวมของ 3 ก้อนในกราฟ ซึ่งไม่ใช่ "คำบ่นทั้งหมด"
    // (คำบ่นที่ severity เป็น NULL จะหายไปจากตัวส่วน → % สูงเกินจริง)
    share: share?.[key] ?? null,
    color: SEVERITY_COLORS[key] ?? '#94a3b8',
  }))

  return (
    <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
      <h3 className="text-brand-text font-semibold mb-1">ระดับความรุนแรง</h3>
      <p className="text-brand-subtext text-xs mb-3">
        จากรีวิวเชิงลบ (คำบ่น) ทั้งหมด
        {negativeTotal != null ? ` ${formatCount(negativeTotal)} รายการ` : ''}
      </p>
      <ResponsiveContainer width="100%" height={240}>
        <PieChart>
          <Pie
            data={chartData}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy="50%"
            outerRadius={72}
            label={(p: any) => {
              const d = chartData[p.index]
              // แสดงทั้งจำนวนและ % ในกราฟเลย — % มี share จาก API เท่านั้น
              // (ฐาน = คำบ่นทั้งหมด) ไม่มีก็โชว์แค่จำนวน ดีกว่าโชว์ % ที่ฐานผิด
              if (!d) return p.name
              if (d.share == null) return `${d.name} ${formatCount(d.value)}`
              return `${d.name} ${formatCount(d.value)} · ${formatPercent(d.share, 0)}`
            }}
            labelLine={{ stroke: '#475569' }}
          >
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
            itemStyle={{ color: '#e2e8f0' }}
            formatter={(v: number, _n, item: any) => {
              const d = chartData.find(x => x.name === item?.payload?.name)
              return [formatRateOf(d?.share ?? null, v, negativeTotal, 'คำบ่นทั้งหมด'), 'สัดส่วน']
            }}
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
