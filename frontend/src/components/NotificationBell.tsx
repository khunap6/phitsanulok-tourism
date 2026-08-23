import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'

interface AlertPlace { place_name: string; delta: number }
interface AlertItem {
  id: string
  type: 'new_category' | 'spike' | 'increase'
  level: 'high' | 'medium' | 'low'
  title: string
  detail: string
  category: string
  delta: number
  pct_change: number | null
  spread: 'concentrated' | 'widespread'
  places_increased: number
  top_places: AlertPlace[]
}
interface AlertResponse {
  unread_count: number
  from?: { label: string | null; taken_at: string | null } | null
  to?: { label: string | null; taken_at: string | null } | null
  alerts: AlertItem[]
  message?: string
}

const LEVEL_COLOR: Record<string, string> = {
  high: '#ef4444', medium: '#eab308', low: '#3b82f6',
}
const TYPE_ICON: Record<string, string> = {
  new_category: '🆕', spike: '📍', increase: '🌐',
}
const TYPE_LABEL: Record<string, string> = {
  new_category: 'ปัญหาใหม่', spike: 'กระจุกร้านเดียว', increase: 'กระจายหลายร้าน',
}

function useAlerts() {
  return useQuery<AlertResponse>({
    queryKey: ['alerts'],
    queryFn: async () => {
      const res = await fetch('/api/insights/alerts')
      if (!res.ok) return { unread_count: 0, alerts: [] }
      return res.json()
    },
    staleTime: 1000 * 60 * 5,
  })
}

/** เก็บ id ที่อ่านแล้วไว้ใน localStorage — refresh แล้วไม่เด้งซ้ำ */
function useReadIds() {
  const [ids, setIds] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem('alert_read_ids') || '[]') } catch { return [] }
  })
  const markAllRead = (all: string[]) => {
    setIds(all)
    localStorage.setItem('alert_read_ids', JSON.stringify(all))
  }
  return { readIds: ids, markAllRead }
}

export default function NotificationBell() {
  const { data } = useAlerts()
  const [open, setOpen] = useState(false)
  const { readIds, markAllRead } = useReadIds()
  const ref = useRef<HTMLDivElement>(null)

  const alerts = data?.alerts ?? []
  const unread = alerts.filter(a => !readIds.includes(a.id))

  // คลิกนอกกล่อง → ปิด
  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [open])

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => {
          const next = !open
          setOpen(next)
          if (next && alerts.length) markAllRead(alerts.map(a => a.id))
        }}
        className="relative p-2 rounded-lg hover:bg-brand-card transition-colors"
        title="การแจ้งเตือน"
        aria-label={`การแจ้งเตือน ${unread.length} รายการใหม่`}
      >
        <span className="text-xl">🔔</span>
        {unread.length > 0 && (
          <span className="absolute -top-0.5 -right-0.5 bg-red-500 text-white text-[10px] font-bold
                           min-w-[18px] h-[18px] px-1 rounded-full flex items-center justify-center">
            {unread.length > 9 ? '9+' : unread.length}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-[380px] max-h-[70vh] overflow-y-auto z-50
                        bg-brand-card border border-brand-border rounded-xl shadow-2xl">
          <div className="px-4 py-3 border-b border-brand-border sticky top-0 bg-brand-card">
            <div className="flex items-center justify-between">
              <h4 className="text-brand-text font-semibold text-sm">🔔 การแจ้งเตือน</h4>
              <span className="text-brand-subtext text-xs">{alerts.length} รายการ</span>
            </div>
            {data?.from?.label && data?.to?.label && (
              <p className="text-brand-subtext text-[11px] mt-0.5">
                เทียบ <b>{data.from.label}</b> → <b>{data.to.label}</b>
              </p>
            )}
          </div>

          {data?.message && (
            <div className="px-4 py-6 text-brand-subtext text-sm text-center">{data.message}</div>
          )}

          {!data?.message && alerts.length === 0 && (
            <div className="px-4 py-6 text-brand-subtext text-sm text-center">
              ✅ ไม่มีปัญหาเพิ่มขึ้นในรอบล่าสุด
            </div>
          )}

          <div className="divide-y divide-brand-border">
            {alerts.map(a => (
              <div key={a.id} className="px-4 py-3 hover:bg-brand-bg transition-colors">
                <div className="flex items-start gap-2">
                  <span className="text-base leading-5">{TYPE_ICON[a.type]}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className="text-[10px] px-1.5 py-0.5 rounded"
                        style={{ color: LEVEL_COLOR[a.level], background: LEVEL_COLOR[a.level] + '22' }}
                      >
                        {TYPE_LABEL[a.type]}
                      </span>
                      {a.pct_change !== null && (
                        <span className="text-[10px] text-brand-subtext">+{a.pct_change}%</span>
                      )}
                    </div>
                    <p className="text-brand-text text-sm mt-1 leading-snug">{a.title}</p>
                    <p className="text-brand-subtext text-xs mt-0.5">{a.detail}</p>
                    {a.top_places.length > 1 && (
                      <p className="text-brand-subtext text-[11px] mt-1">
                        ร้านอื่น: {a.top_places.slice(1, 3).map(p => `${p.place_name} (+${p.delta})`).join(', ')}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
