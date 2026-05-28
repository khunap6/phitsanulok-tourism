import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { Link, Route, BrowserRouter as Router, Routes, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import MapView from './pages/MapView'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
})

function NavLink({ to, label }: { to: string; label: string }) {
  const { pathname } = useLocation()
  const active = pathname === to
  return (
    <Link
      to={to}
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
        <NavLink to="/" label="Dashboard" />
        <NavLink to="/map" label="แผนที่" />
      </nav>
      <Routes>
        <Route path="/" element={<Dashboard />} />
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
