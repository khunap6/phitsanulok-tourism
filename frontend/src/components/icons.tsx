import {
  AlertTriangle,
  Camera,
  Coffee,
  Bell,
  BookOpen,
  Building2,
  CalendarDays,
  Check,
  ChevronRight,
  CircleDot,
  Compass,
  FileText,
  FileType,
  Flame,
  Globe,
  GraduationCap,
  Landmark,
  MapPin,
  MessageSquare,
  Minus,
  Pin,
  Pointer,
  School,
  Search,
  Share2,
  Sparkles,
  Target,
  Star,
  Store,
  ThumbsUp,
  UtensilsCrossed,
  TrendingUp,
  X,
} from 'lucide-react'

/**
 * ไอคอนทั้งหมดของหน้าเว็บ — ประกาศไว้ที่เดียว
 *
 * ⚠️ ทำไมต้องรวมไว้ไฟล์เดียว ไม่ import lucide ตรง ๆ ในแต่ละ component
 *   ของเดิมใช้อิโมจิกระจายอยู่ 80 จุดใน 20 ไฟล์ ความหมายเดียวกันแต่เขียนต่างกัน
 *   เช่น "ความรุนแรงสูง" เป็น 🔥 ที่ KPICard, ReviewList, CategoryDrilldown และ
 *   Dashboard รวม 11 จุด พอจะเปลี่ยนทีต้องไล่แก้ทุกไฟล์และมีโอกาสตกหล่น
 *
 *   รวมไว้ที่นี่แล้วทุก component อ้างชื่อเชิงความหมาย (SeverityHigh ไม่ใช่ Flame)
 *   เปลี่ยนรูปทีหลังแก้บรรทัดเดียว และไม่มีทางที่สองหน้าจะใช้ไอคอนคนละตัว
 *   สำหรับความหมายเดียวกัน — หลักเดียวกับ api/filters.py และ useBizStatus.ts
 *
 * ⚠️ ไม่ใช้อิโมจิเพราะหน้าตาต่างกันตามระบบปฏิบัติการและฟอนต์
 *   (🔥 บน Windows กับ Android คนละรูป) ทำให้งานดูไม่เป็นระบบ
 *   ส่วนไอคอน SVG ควบคุมขนาด สี และความหนาเส้นได้เท่ากันทุกเครื่อง
 *
 * ขนาดมาตรฐาน: 14 สำหรับข้อความประกอบ · 16 สำหรับหัวข้อ · 20 ขึ้นไปสำหรับไอคอนเดี่ยว
 */

// ── ระดับความรุนแรงของปัญหา ──
export const SeverityHigh = Flame
export const SeverityMedium = AlertTriangle
export const SeverityLow = MessageSquare

// ── มุมมอง/อารมณ์ของรีวิว ──
export const ViewComplaints = CircleDot
export const ViewPraise = Star
export const ViewAll = TrendingUp
export const SentimentNeutral = Minus
export const Praise = ThumbsUp

// ── สถานะร้าน ──
export const StoreIcon = Store
export const ClosedPermanently = X
export const ClosedTemporarily = AlertTriangle

// ── โซนพื้นที่ ──
export const ZoneCityCenter = Building2
export const ZoneRajabhat = GraduationCap
export const ZoneNaresuan = School
export const ZoneOther = Compass

// ── ประเภทสถานที่ ──
export const PlaceCafe = Coffee
export const PlaceRestaurant = UtensilsCrossed
export const PlaceAttraction = Landmark
export const PlaceGeneral = Pin

// ── ชนิดการแจ้งเตือน ──
export const AlertNewCategory = Sparkles
export const AlertSpike = Target
export const AlertSpread = Share2
export const PhotoIcon = Camera

// ── การกระทำและส่วนประกอบหน้าจอ ──
export const DateRange = CalendarDays
export const Notification = Bell
export const NotificationOk = Check
export const ClickHint = Pointer
export const Close = X
export const SearchIcon = Search
export const Trend = TrendingUp
export const Report = BookOpen
export const ReportPdf = FileText
export const ReportWord = FileType
export const ReportHtml = Globe
export const Location = MapPin
export const Arrow = ChevronRight
export const RatingStar = Star

/**
 * ดาวคะแนน — เดิมเขียน '★'.repeat(n) + '☆'.repeat(5-n) อยู่ 3 ที่คนละแบบ
 * (บางที่ไม่เติมดาวว่าง บางที่เติม) รวมมาไว้ที่เดียวให้หน้าตาเท่ากัน
 */
export function Stars({ value, size = 12 }: { value: number; size?: number }) {
  const n = Math.max(0, Math.min(5, Math.round(value || 0)))
  return (
    <span className="inline-flex items-center gap-0.5 align-middle">
      {Array.from({ length: 5 }, (_, i) => (
        <Star
          key={i}
          size={size}
          className={i < n ? 'text-yellow-400' : 'text-brand-border'}
          fill={i < n ? 'currentColor' : 'none'}
          strokeWidth={1.5}
        />
      ))}
    </span>
  )
}
