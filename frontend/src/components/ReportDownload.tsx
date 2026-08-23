import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'

interface MonthOption {
  year: number
  month: number
  label: string
  reviews: number
}

function useReportMonths() {
  return useQuery<MonthOption[]>({
    queryKey: ['report-months'],
    queryFn: async () => {
      const res = await fetch('/api/reports/months')
      if (!res.ok) return []
      return res.json()
    },
    staleTime: 1000 * 60 * 10,
  })
}

const FORMATS = [
  { key: 'pdf',  label: '📄 PDF',  hint: 'พร้อมพิมพ์ / ส่งอาจารย์' },
  { key: 'docx', label: '📝 Word', hint: 'แก้ไขต่อเองได้' },
  { key: 'html', label: '🌐 เปิดดู', hint: 'เปิดในแท็บใหม่' },
]

export default function ReportDownload() {
  const { data: months = [], isLoading } = useReportMonths()
  const [selected, setSelected] = useState<string>('')
  const [busy, setBusy] = useState<string | null>(null)

  // ค่าเริ่มต้น = เดือนล่าสุดที่มีข้อมูล
  const current = selected || (months[0] ? `${months[0].year}-${months[0].month}` : '')

  async function handleDownload(fmt: string) {
    if (!current) return
    const [y, m] = current.split('-')
    const url = `/api/reports/download?year=${y}&month=${m}&format=${fmt}`

    if (fmt === 'html') {
      window.open(url, '_blank')
      return
    }

    setBusy(fmt)
    try {
      const res = await fetch(url)
      if (!res.ok) throw new Error('สร้างรายงานไม่สำเร็จ')
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `report_${y}-${String(m).padStart(2, '0')}.${fmt}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(a.href)
    } catch (e) {
      alert('สร้างรายงานไม่สำเร็จ — ลองใหม่อีกครั้ง')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="bg-brand-card rounded-xl p-5 border border-brand-border">
      <h3 className="text-brand-text font-semibold">📑 รายงานประจำเดือน</h3>
      <p className="text-brand-subtext text-xs mt-0.5 mb-4">
        สรุปปัญหา · เปรียบเทียบโซน · ร้านที่ถูกร้องเรียน · จุดเด่น · ตัวอย่างรีวิว
      </p>

      {isLoading && <p className="text-brand-subtext text-sm">กำลังโหลด...</p>}

      {!isLoading && months.length === 0 && (
        <p className="text-brand-subtext text-sm italic">ยังไม่มีเดือนที่มีข้อมูลพอออกรายงาน</p>
      )}

      {!isLoading && months.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <select
            value={current}
            onChange={e => setSelected(e.target.value)}
            className="bg-brand-bg border border-brand-border text-brand-text rounded-lg
                       px-3 py-2 text-sm focus:outline-none focus:border-brand-primary"
          >
            {months.map(m => (
              <option key={`${m.year}-${m.month}`} value={`${m.year}-${m.month}`}>
                {m.label} ({m.reviews.toLocaleString()} รีวิว)
              </option>
            ))}
          </select>

          <div className="flex gap-2 flex-wrap">
            {FORMATS.map(f => (
              <button
                key={f.key}
                onClick={() => handleDownload(f.key)}
                disabled={busy !== null}
                title={f.hint}
                className="px-3 py-2 rounded-lg text-sm border border-brand-border
                           bg-brand-bg text-brand-text hover:border-brand-primary
                           disabled:opacity-50 disabled:cursor-wait transition-colors"
              >
                {busy === f.key ? '⏳ กำลังสร้าง...' : f.label}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
