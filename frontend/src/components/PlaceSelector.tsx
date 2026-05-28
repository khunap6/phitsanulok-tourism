import type { Place } from '../types'

interface Props {
  places: Place[]
  selectedId: number | null
  onChange: (id: number | null) => void
}

export default function PlaceSelector({ places, selectedId, onChange }: Props) {
  return (
    <select
      className="bg-brand-card border border-brand-border text-brand-text rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-brand-primary w-full"
      value={selectedId ?? ''}
      onChange={e => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">— ทุกสถานที่ —</option>
      {places.map(p => (
        <option key={p.id} value={p.id}>
          {p.name}
          {p.overall_rating ? ` (${p.overall_rating}★)` : ''}
        </option>
      ))}
    </select>
  )
}
