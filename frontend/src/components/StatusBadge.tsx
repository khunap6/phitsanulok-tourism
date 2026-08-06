// ป้ายสถานะร้าน — แสดงเฉพาะร้านที่ปิด (ร้านเปิดปกติไม่ต้องมีป้าย)
export default function StatusBadge({ status }: { status?: string }) {
  if (status === 'closed_permanently') {
    return (
      <span className="text-xs px-1.5 py-0.5 rounded bg-red-500/20 text-red-400 shrink-0">
        🔴 ปิดถาวร
      </span>
    )
  }
  if (status === 'closed_temporarily') {
    return (
      <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-500/20 text-yellow-400 shrink-0">
        🟡 ปิดชั่วคราว
      </span>
    )
  }
  return null
}

// ตัวเลือกโหมดสถานะร้าน (ใช้ในปุ่ม selector ทั้ง Dashboard และ Zone)
export const STATUS_OPTIONS = [
  { key: 'operational', label: 'ร้านที่เปิด', color: '#22c55e' },
  { key: 'closed', label: 'ร้านที่ปิด', color: '#ef4444' },
  { key: 'all', label: 'ทั้งหมด', color: '#3b82f6' },
]
