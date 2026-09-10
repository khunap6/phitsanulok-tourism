import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { Link, Route, BrowserRouter as Router, Routes, useLocation } from 'react-router-dom'
import NotificationBell from './components/NotificationBell'
import Dashboard from './pages/Dashboard'
import MapView from './pages/MapView'
import ZoneDashboard from './pages/ZoneDashboard'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

function NavLink({ to, label }: { to: string; label: string }) {
  const { pathname, search } = useLocation()
  const active = pathname === to
  return (
    <Link
      // พา search params ไปด้วย — ช่วงเวลาที่เลือกเก็บไว้ใน URL (hooks/useDateRange.ts)
      // ถ้าใช้ to={to} เปล่า ๆ query string จะหลุด แล้วเปลี่ยนหน้าทีก็รีเซ็ตเป็น "ทั้งหมด" ทุกที
      to={{ pathname: to, search }}
      className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
        active
          ? 'bg-brand-primary text-white'
          : 'text-brand-subtext hover:text-brand-text hover:bg-brand-card'
      }`}
    >
      {label}
    </Link>
  )
}

function Layout() {
  return (
    <div className="min-h-screen bg-brand-bg">
      <nav className="bg-brand-card border-b border-brand-border px-6 py-3 flex items-center gap-4">
        <span className="text-brand-text font-bold text-sm mr-4">
          Phitsanulok Tourism
        </span>
        <NavLink to="/" label="ภาพรวม" />
        <NavLink to="/zones" label="วิเคราะห์ตามโซน" />
        <NavLink to="/map" label="แผนที่" />
        {/* กระดิ่งแจ้งเตือน — ชิดขวาสุด */}
        <div className="ml-auto">
          <NotificationBell />
        </div>
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/zones" element={<ZoneDashboard />} />
        <Route path="/map" element={<MapView />} />
      </Routes>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <Layout />
      </Router>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  )
}
