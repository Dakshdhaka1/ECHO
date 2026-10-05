import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Skeleton } from './components/ui'
import { useAuth } from './context/AuthContext'
import AppLayout from './layouts/AppLayout'
import AuthPage from './pages/Auth'
import Landing from './pages/Landing'

// Route-level code splitting: charts and the report page load only when needed.
const CompanyReport = lazy(() => import('./pages/CompanyReport'))
const page = (mod, name) => lazy(() => mod().then((m) => ({ default: m[name] })))
const platform = () => import('./pages/Platform')
const workspace = () => import('./pages/Workspace')
const [Account, Admin, Models, NotFound, Pricing] = ['Account', 'Admin', 'Models', 'NotFound', 'Pricing'].map((n) => page(platform, n))
const [Alerts, Compare, SearchResults, Watchlists] = ['Alerts', 'Compare', 'SearchResults', 'Watchlists'].map((n) => page(workspace, n))

function RequireAuth({ children, admin = false }) {
  const { token, loading, isAdmin } = useAuth()
  const location = useLocation()
  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  if (loading) return <Skeleton className="h-64" />
  if (admin && !isAdmin) return <Navigate to="/" replace />
  return children
}

export default function App() {
  return (
    <Suspense fallback={<Skeleton className="m-6 h-64" />}>
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<Landing />} />
        <Route path="login" element={<AuthPage mode="login" />} />
        <Route path="register" element={<AuthPage mode="register" />} />
        <Route path="search" element={<SearchResults />} />
        <Route path="company/:id" element={<CompanyReport />} />
        <Route path="compare" element={<Compare />} />
        <Route path="models" element={<Models />} />
        <Route path="pricing" element={<Pricing />} />
        <Route path="watchlists" element={<RequireAuth><Watchlists /></RequireAuth>} />
        <Route path="alerts" element={<RequireAuth><Alerts /></RequireAuth>} />
        <Route path="account" element={<RequireAuth><Account /></RequireAuth>} />
        <Route path="admin" element={<RequireAuth admin><Admin /></RequireAuth>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
    </Suspense>
  )
}
