import { useState } from 'react'

export interface DateRange {
  from: string | null
  to: string | null
  /** ป้ายแสดงผลปัจจุบัน — เอาไปโชว์ในแถบ chip */
  label: string
}

export const ALL_TIME: DateRange = { from: null, to: null, label: 'ทั้งหมด' }

// ปีที่มีข้อมูลจริง (จาก DB: 2011-2026 แต่ 2024-2026 มีเยอะสุด)
const YEARS = [2026, 2025, 2024, 2023, 2022]
const MONTHS = [
  '01 มกราคม', '02 กุมภาพันธ์', '03 มีนาคม', '04 เมษายน',
  '05 พฤษภาคม', '06 มิถุนายน', '07 กรกฎาคม', '08 สิงหาคม',
  '09 กันยายน', '10 ตุลาคม', '11 พฤศจิกายน', '12 ธันวาคม',
]

function today(): Date {
  return new Date()
}

function daysAgo(n: number): DateRange {
  const t = today()
  const from = new Date(t.getFullYear(), t.getMonth(), t.getDate() - n)
  return { from: iso(from), to: iso(t), label: `${n} วันย้อนหลัง` }
}

function monthsAgo(n: number): DateRange {
  const t = today()
  const from = new Date(t.getFullYear(), t.getMonth() - n, t.getDate())
  return { from: iso(from), to: iso(t), label: `${n} เดือนย้อนหลัง` }
}

function yearRange(y: number): DateRange {
  return { from: `${y}-01-01`, to: `${y}-12-31`, label: `ปี ${y}` }
}

function monthRange(y: number, m: number): DateRange {
  const last = new Date(y, m, 0).getDate()  // วันสุดท้ายของเดือน
  const mm = String(m).padStart(2, '0')
  const yr = y + 543  // แสดงเป็นพ.ศ.
  return {
    from: `${y}-${mm}-01`,
    to: `${y}-${mm}-${String(last).padStart(2, '0')}`,
    label: `${MONTHS[m - 1].split(' ')[1]} ${yr}`,
  }
}

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

interface Props {
  value: DateRange
  onChange: (range: DateRange) => void
}

export default function DateRangeSelector({ value, onChange }: Props) {
  const [mode, setMode] = useState<'preset' | 'year' | 'month' | 'custom'>('preset')
  const [selectedYear, setSelectedYear] = useState<number>(YEARS[0])
  const [selectedMonth, setSelectedMonth] = useState<number>(new Date().getMonth() + 1)

  const isActive = (label: string) => value.label === label

  const presetBtn = (label: string, range: DateRange) => (
    <button
      key={label}
      onClick={() => { setMode('preset'); onChange(range) }}
      className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
        isActive(label)
          ? 'bg-brand-primary text-white'
          : 'bg-brand-card text-brand-subtext hover:text-brand-text border border-brand-border'
      }`}
    >
      {label}
    </button>
  )

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-brand-subtext text-sm shrink-0">📅 ช่วงเวลา:</span>

      {/* Presets */}
      <div className="flex flex-wrap gap-1.5">
        {presetBtn('ทั้งหมด', ALL_TIME)}
        {presetBtn('30 วันย้อนหลัง', daysAgo(30))}
        {presetBtn('3 เดือนย้อนหลัง', monthsAgo(3))}
        {presetBtn('1 ปีย้อนหลัง', daysAgo(365))}
      </div>

      {/* Year picker */}
      <div className="flex items-center gap-1">
        <span className="text-brand-subtext text-xs">ปี:</span>
        <select
          value={mode === 'year' ? selectedYear : ''}
          onChange={(e) => {
            if (!e.target.value) return
            const y = Number(e.target.value)
            setSelectedYear(y)
            setMode('year')
            onChange(yearRange(y))
          }}
          className="bg-brand-card border border-brand-border text-brand-text rounded-md px-2 py-1 text-xs focus:outline-none focus:border-brand-primary"
        >
          <option value="">— เลือกปี —</option>
          {YEARS.map(y => <option key={y} value={y}>{y + 543}</option>)}
        </select>
      </div>

      {/* Month picker */}
      <div className="flex items-center gap-1">
        <span className="text-brand-subtext text-xs">เดือน:</span>
        <select
          value={mode === 'month' ? selectedYear : ''}
          onChange={(e) => {
            if (!e.target.value) return
            setSelectedYear(Number(e.target.value))
            setMode('month')
            onChange(monthRange(Number(e.target.value), selectedMonth))
          }}
          className="bg-brand-card border border-brand-border text-brand-text rounded-md px-2 py-1 text-xs focus:outline-none focus:border-brand-primary"
        >
          <option value="">— ปี —</option>
          {YEARS.map(y => <option key={y} value={y}>{y + 543}</option>)}
        </select>
        <select
          value={mode === 'month' ? selectedMonth : ''}
          onChange={(e) => {
            if (!e.target.value) return
            const m = Number(e.target.value)
            setSelectedMonth(m)
            setMode('month')
            onChange(monthRange(selectedYear, m))
          }}
          className="bg-brand-card border border-brand-border text-brand-text rounded-md px-2 py-1 text-xs focus:outline-none focus:border-brand-primary"
        >
          <option value="">— เดือน —</option>
          {MONTHS.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
        </select>
      </div>

      {/* Chip แสดงช่วงปัจจุบัน */}
      <div className="ml-auto bg-brand-primary/10 border border-brand-primary/40 text-brand-primary text-xs px-3 py-1 rounded-full">
        📅 กำลังดู: <b>{value.label}</b>
      </div>
    </div>
  )
}
