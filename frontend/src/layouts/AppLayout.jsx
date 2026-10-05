import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { Bell, LogOut, Moon, Sun } from '../components/icons'
import SearchBox from '../components/SearchBox'
import { Disclaimer } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { api } from '../services/api'

const NAV = [
  { to: '/compare', label: 'Compare' },
  { to: '/watchlists', label: 'Watchlists', auth: true },
  { to: '/models', label: 'Models' },
  { to: '/pricing', label: 'Pricing' },
]

export function Logo({ tagline = false }) {
  return (
    <Link to="/" className="group flex items-center gap-2.5 text-ink">
      <img src="/echo.svg" alt="" className="h-7 w-7 transition-transform duration-500 ease-spring group-hover:scale-105" />
      <span className="text-[15px] font-semibold tracking-[0.04em]">ECHO</span>
      {tagline && <span className="label hidden border-l border-line-strong pl-2.5 xl:inline">Corporate health observatory</span>}
    </Link>
  )
}

/** Real platform status: the API answers /stats and the round trip is measured in the browser. */
function usePlatformPulse() {
  return useQuery({
    queryKey: ['pulse'],
    queryFn: async () => {
      const t0 = performance.now()
      const stats = await api.get('/stats')
      return { ms: Math.round(performance.now() - t0), champions: (stats.models || []).filter((m) => m.is_champion).length, companies: stats.companies }
    },
    refetchInterval: 60_000,
    retry: false,
  })
}

function Burger({ open, onClick }) {
  return (
    <button onClick={onClick} aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open}
            className="relative grid h-8 w-8 place-items-center rounded-[5px] text-ink hover:bg-surface-2 lg:hidden">
      <span className={`absolute h-[1.5px] w-4 bg-current transition-transform duration-500 ease-spring ${open ? 'rotate-45' : '-translate-y-[3px]'}`} />
      <span className={`absolute h-[1.5px] w-4 bg-current transition-transform duration-500 ease-spring ${open ? '-rotate-45' : 'translate-y-[3px]'}`} />
    </button>
  )
}

const iconButton = 'grid h-8 w-8 place-items-center rounded-[5px] text-ink-2 transition duration-200 hover:bg-surface-2 hover:text-ink'

export default function AppLayout() {
  const { user, me, isAdmin, logout } = useAuth()
  const { dark, toggle } = useTheme()
  const [menu, setMenu] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const pulse = usePlatformPulse()
  const links = [...NAV.filter((n) => !n.auth || user), ...(isAdmin ? [{ to: '/admin', label: 'Admin' }] : [])]
  const landing = location.pathname === '/'
  const online = pulse.isSuccess

  useEffect(() => { setMenu(false) }, [location.pathname])

  return (
    <div className="flex min-h-[100dvh] flex-col">
      <div className="ambient" aria-hidden />
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-[5px] focus:bg-primary focus:px-4 focus:py-2 focus:text-on-primary">Skip to content</a>

      <header className="sticky top-0 z-40 border-b border-line bg-page/95">
        <div className="mx-auto flex h-14 max-w-[1360px] items-center gap-4 px-4 md:px-6">
          <Logo tagline />
          <nav className="ml-4 hidden items-center gap-0.5 lg:flex" aria-label="Main">
            {links.map((n) => (
              <NavLink key={n.to} to={n.to}
                       className={({ isActive }) => `relative px-3 py-4 text-sm transition-colors duration-200 ${isActive ? 'text-ink after:absolute after:inset-x-3 after:-bottom-px after:h-[2px] after:bg-accent' : 'text-ink-2 hover:text-ink'}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {!landing && <div className="hidden w-64 md:block xl:w-72"><SearchBox hotkey /></div>}
            <span className={`hidden items-center gap-1.5 rounded-[4px] border px-2 py-1 font-mono text-[10.5px] uppercase tracking-[0.08em] xl:inline-flex ${online ? 'border-accent/30 text-accent-ink' : 'border-line-strong text-muted'}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${online ? 'live-dot bg-accent' : 'bg-muted'}`} aria-hidden />
              {online ? `API online // ${pulse.data.ms}ms` : pulse.isError ? 'API unreachable' : 'Connecting'}
            </span>
            <button onClick={toggle} className={iconButton} aria-label={dark ? 'Light theme' : 'Dark theme'}>
              <span key={dark ? 'sun' : 'moon'} className="grid animate-[rise_0.4s_var(--ease-fluid)_both]">{dark ? <Sun size={17} /> : <Moon size={17} />}</span>
            </button>
            {user ? (
              <>
                <Link to="/alerts" className={`relative ${iconButton}`} aria-label="Alerts">
                  <Bell size={17} />
                  {me?.unreadAlerts > 0 && (
                    <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-[3px] bg-critical px-1 text-center font-mono text-[10px] font-semibold leading-4 text-white">{me.unreadAlerts}</span>
                  )}
                </Link>
                <Link to="/account" className="hidden items-center gap-2 rounded-[5px] py-1 pl-1 pr-2.5 text-sm text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink sm:flex">
                  <span className="grid h-6 w-6 place-items-center rounded-[4px] bg-accent-soft font-mono text-xs font-semibold text-accent-ink">{(user.displayName || '?').slice(0, 1).toUpperCase()}</span>
                  <span className="max-w-28 truncate">{user.displayName}</span>
                  <span className="rounded-[3px] border border-line-strong px-1 font-mono text-[10px] uppercase tracking-wider">{user.plan}</span>
                </Link>
                <button onClick={() => { logout(); navigate('/') }} className={`hidden sm:grid ${iconButton}`} aria-label="Sign out"><LogOut size={17} /></button>
              </>
            ) : (
              <>
                <Link to="/login" className="hidden px-2 py-1.5 text-sm text-ink-2 transition-colors hover:text-ink sm:block">Sign in</Link>
                <Link to="/register" className="inline-flex h-8 items-center rounded-[5px] border border-accent bg-accent px-3.5 text-[13px] font-medium text-[var(--on-accent)] transition duration-200 hover:brightness-110 active:translate-y-px">Get started</Link>
              </>
            )}
            <Burger open={menu} onClick={() => setMenu(!menu)} />
          </div>
        </div>

        {menu && (
          <div className="absolute inset-x-0 top-full border-b border-line bg-page p-4 animate-[rise_0.4s_var(--ease-fluid)_both] lg:hidden">
            <SearchBox onPick={(c) => { setMenu(false); navigate(`/company/${c.id}`) }} />
            <nav className="stagger mt-3 grid divide-y divide-line" aria-label="Mobile">
              {links.map((n) => <Link key={n.to} to={n.to} className="py-3.5 text-lg font-light text-ink">{n.label}</Link>)}
              {user ? (
                <>
                  <Link to="/account" className="py-3.5 text-lg font-light text-ink">Account</Link>
                  <button onClick={() => { logout(); navigate('/') }} className="py-3.5 text-left text-lg font-light text-ink-2">Sign out</button>
                </>
              ) : <Link to="/login" className="py-3.5 text-lg font-light text-ink">Sign in</Link>}
            </nav>
          </div>
        )}
      </header>

      <main id="main" key={location.pathname} className={`w-full flex-1 animate-fade ${landing ? '' : 'mx-auto max-w-[1360px] px-4 py-8 md:px-6 md:py-10'}`}>
        <Outlet />
      </main>

      <footer className="mt-16 border-t border-line">
        <div className="mx-auto grid max-w-[1360px] gap-6 px-4 py-8 md:grid-cols-[1fr_auto] md:px-6">
          <div className="space-y-3">
            <Logo />
            <Disclaimer />
          </div>
          <nav className="flex gap-5 text-sm text-ink-2 md:justify-end" aria-label="Footer">
            <Link to="/models" className="hover:text-ink">Model cards</Link>
            <Link to="/pricing" className="hover:text-ink">Pricing</Link>
            <a href="/api/swagger-ui" className="hover:text-ink">API docs</a>
          </nav>
        </div>
        <div className="border-t border-line">
          <div className="mx-auto flex max-w-[1360px] flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 font-mono text-[10.5px] uppercase tracking-[0.08em] text-muted md:px-6">
            <span className="inline-flex items-center gap-1.5">
              <span className={`h-1.5 w-1.5 rounded-full ${online ? 'bg-accent' : 'bg-critical'}`} aria-hidden />
              <span className={online ? 'text-accent-ink' : ''}>{online ? 'Sys ok' : 'Sys offline'}</span> // ECHO platform
            </span>
            {online && <span>Latency: <span className="text-ink-2">{pulse.data.ms}ms</span></span>}
            {online && <span>Models in production: <span className="text-ink-2">{pulse.data.champions}</span></span>}
            <span>Data: SEC EDGAR / GDELT / Alpha Vantage</span>
            <span className="md:ml-auto">No scraping of sites whose terms forbid it</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
