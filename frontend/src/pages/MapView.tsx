import {
  GoogleMap,
  InfoWindow,
  LoadScript,
  Marker,
} from '@react-google-maps/api'
import { useState } from 'react'
import DateRangeSelector from '../components/DateRangeSelector'
import { STATUS_OPTIONS } from '../components/StatusBadge'
import { useDateRange } from '../hooks/useDateRange'
import { useMapGeoJSON } from '../hooks/useInsights'
import type { GeoFeatureProperties } from '../types'

const PHITSANULOK_CENTER = { lat: 16.82, lng: 100.26 }

const SEVERITY_COLOR: Record<string, string> = {
  high: '#EF4444',
  medium: '#F97316',
  low: '#EAB308',
}

const SEVERITY_TH: Record<string, string> = {
  high: 'สูง',
  medium: 'กลาง',
  low: 'ต่ำ',
}

const MAP_STYLES = [
  { elementType: 'geometry', stylers: [{ color: '#1e293b' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#94a3b8' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#0f172a' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#334155' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#0f172a' }] },
  { featureType: 'poi', stylers: [{ visibility: 'off' }] },
]

const MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_KEY ?? ''

interface SelectedFeature {
  position: google.maps.LatLngLiteral
  properties: GeoFeatureProperties
}

export default function MapView() {
  // ช่วงเวลาอยู่ใน URL — ค่าตรงกับหน้าอื่นอัตโนมัติ (ดู hooks/useDateRange.ts)
  const [dateRange, setDateRange] = useDateRange()
  // default 'all' ให้ตรงกับพฤติกรรมเดิมของแผนที่ (แสดงร้านปิดด้วย)
  const [bizStatus, setBizStatus] = useState('all')
  const { data: geoJSON, isLoading } = useMapGeoJSON(dateRange, bizStatus)
  // ฐานเทียบ "จาก N สถานที่" — ไม่กรองอะไรเลย
  // ตอนไม่ได้กรอง queryKey ตรงกับคิวรีข้างบน react-query จึงยิงครั้งเดียว
  const { data: allGeoJSON } = useMapGeoJSON()
  const [selected, setSelected] = useState<SelectedFeature | null>(null)
  const [severityFilter, setSeverityFilter] = useState<string>('all')

  const features = geoJSON?.features ?? []
  const totalPlaces = allGeoJSON?.features.length ?? 0
  const isFiltered = Boolean(dateRange.from || dateRange.to) || bizStatus !== 'all'
  const filtered =
    severityFilter === 'all'
      ? features
      : features.filter(f => f.properties.dominant_severity === severityFilter)

  if (!MAPS_API_KEY) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-brand-bg">
        <div className="bg-brand-card border border-brand-border rounded-xl p-8 max-w-md text-center">
          <p className="text-red-400 text-lg font-semibold mb-2">ไม่พบ Google Maps API Key</p>
          <p className="text-brand-subtext text-sm">
            กรุณาตั้งค่า <code className="text-blue-400">VITE_GOOGLE_MAPS_KEY</code> ใน{' '}
            <code className="text-blue-400">frontend/.env</code>
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-screen bg-brand-bg overflow-hidden">
      {/* แถบเครื่องมือ — flex-none: สูงเท่าเนื้อหา ไม่ hardcode px จอเล็กจึงไม่พัง */}
      <div className="flex-none bg-brand-card border-b border-brand-border px-4 py-2 space-y-2">
        <DateRangeSelector value={dateRange} onChange={setDateRange} />
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-brand-subtext text-sm shrink-0">🏪 สถานะร้าน:</span>
          <div className="flex flex-wrap gap-1.5">
            {STATUS_OPTIONS.map(opt => (
              <button
                key={opt.key}
                onClick={() => setBizStatus(opt.key)}
                className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                  bizStatus === opt.key
                    ? 'bg-brand-primary text-white'
                    : 'bg-brand-card text-brand-subtext hover:text-brand-text border border-brand-border'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <span className="text-brand-subtext text-xs ml-auto">
            แสดง <b className="text-brand-text">{filtered.length}</b>
            {isFiltered && totalPlaces > 0 ? ` จาก ${totalPlaces}` : ''} สถานที่
            {isFiltered ? ' (เฉพาะที่มีรีวิวในช่วงที่เลือก)' : ''}
          </span>
        </div>
      </div>

      {/* เนื้อหา: sidebar + แผนที่ — flex-1 กินพื้นที่ที่เหลือทั้งหมด */}
      <div className="flex flex-1 min-h-0">
      {/* Sidebar */}
      <aside className="w-64 bg-brand-card border-r border-brand-border p-4 flex flex-col gap-4 z-10">
        <div>
          <h2 className="text-brand-text font-bold text-lg">แผนที่พิษณุโลก</h2>
          <p className="text-brand-subtext text-xs mt-1">
            {filtered.length} สถานที่{severityFilter !== 'all' ? ` (${SEVERITY_TH[severityFilter]})` : ''}
          </p>
        </div>

        <div>
          <p className="text-brand-subtext text-xs mb-2 uppercase tracking-wider">กรองตามระดับ</p>
          <div className="space-y-2">
            {['all', 'high', 'medium', 'low'].map(s => (
              <button
                key={s}
                onClick={() => setSeverityFilter(s)}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors flex items-center gap-2 ${
                  severityFilter === s
                    ? 'bg-brand-primary/20 text-brand-primary border border-brand-primary/40'
                    : 'text-brand-subtext hover:bg-brand-bg'
                }`}
              >
                {s !== 'all' && (
                  <span
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ background: SEVERITY_COLOR[s] }}
                  />
                )}
                {s === 'all' ? 'ทั้งหมด' : SEVERITY_TH[s]}
              </button>
            ))}
          </div>
        </div>

        {/* Legend */}
        <div className="mt-auto">
          <p className="text-brand-subtext text-xs mb-2 uppercase tracking-wider">คำอธิบาย</p>
          {Object.entries(SEVERITY_COLOR).map(([key, color]) => (
            <div key={key} className="flex items-center gap-2 mb-1">
              <span className="w-3 h-3 rounded-full" style={{ background: color }} />
              <span className="text-brand-subtext text-xs">{SEVERITY_TH[key]}</span>
            </div>
          ))}
        </div>
      </aside>

      {/* Map */}
      <div className="flex-1 relative">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-brand-bg/80 z-20">
            <p className="text-brand-subtext">กำลังโหลดข้อมูล…</p>
          </div>
        )}

        <LoadScript googleMapsApiKey={MAPS_API_KEY}>
          <GoogleMap
            mapContainerStyle={{ width: '100%', height: '100%' }}
            center={PHITSANULOK_CENTER}
            zoom={10}
            options={{
              styles: MAP_STYLES,
              disableDefaultUI: false,
              zoomControl: true,
              mapTypeControl: false,
              streetViewControl: false,
              fullscreenControl: true,
            }}
          >
            {filtered.map(feature => {
              const [lng, lat] = feature.geometry.coordinates
              const sev = feature.properties.dominant_severity ?? 'low'
              return (
                <Marker
                  key={feature.properties.id}
                  position={{ lat, lng }}
                  icon={{
                    path: google.maps.SymbolPath.CIRCLE,
                    scale: 8,
                    fillColor: SEVERITY_COLOR[sev] ?? '#94a3b8',
                    fillOpacity: 0.9,
                    strokeColor: '#0f172a',
                    strokeWeight: 1.5,
                  }}
                  onClick={() =>
                    setSelected({ position: { lat, lng }, properties: feature.properties })
                  }
                />
              )
            })}

            {selected && (
              <InfoWindow
                position={selected.position}
                onCloseClick={() => setSelected(null)}
              >
                <div className="bg-white text-gray-800 p-1 max-w-xs">
                  <p className="font-bold text-sm">{selected.properties.name}</p>
                  {selected.properties.rating && (
                    <p className="text-yellow-500 text-xs">
                      {'★'.repeat(Math.round(selected.properties.rating))} {selected.properties.rating}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-1 mt-1">
                    {selected.properties.pain_point_categories.slice(0, 3).map(cat => (
                      <span
                        key={cat}
                        className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded"
                      >
                        {cat}
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-3 mt-2 text-xs text-gray-600">
                    <span className="text-red-500 font-medium">
                      🔥 {selected.properties.high_count} สูง
                    </span>
                    <span>{selected.properties.review_count} รีวิว</span>
                  </div>
                </div>
              </InfoWindow>
            )}
          </GoogleMap>
        </LoadScript>
      </div>
      </div>
    </div>
  )
}
