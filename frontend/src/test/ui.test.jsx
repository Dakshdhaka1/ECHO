import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { PillarBars } from '../components/charts'
import SearchBox from '../components/SearchBox'
import { Tabs } from '../components/ui'
import { AuthProvider } from '../context/AuthContext'
import { ThemeProvider } from '../context/ThemeContext'
import Landing from '../pages/Landing'
import { Pricing } from '../pages/Platform'
import { humanize } from '../utils/format'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

function mockApi(routes) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
    const hit = Object.entries(routes).find(([path]) => String(url).includes(path))
    return hit ? json(hit[1]) : json({}, 404)
  })
}

function Where() {
  const loc = useLocation()
  return <div data-testid="where">{loc.pathname}</div>
}

function renderApp(ui, path = '/') {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <ThemeProvider>
          <AuthProvider>
            <Routes><Route path="*" element={<>{ui}<Where /></>} /></Routes>
          </AuthProvider>
        </ThemeProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => vi.restoreAllMocks())
afterEach(() => vi.useRealTimers())

describe('format helpers', () => {
  it('humanizes identifiers in sentence case and keeps acronyms', () => {
    expect(humanize('sec_xbrl')).toBe('SEC XBRL')
    expect(humanize('ocf_forecast')).toBe('OCF forecast')
    expect(humanize('employee_reviews')).toBe('Employee reviews')
  })
})

describe('pillar cards', () => {
  const pillars = [
    { key: 'financial', label: 'Financial stability', score: 69.9, effective_weight: 0.3, coverage: 1 },
    { key: 'workforce', label: 'Workforce', score: 78.8, effective_weight: 0.15, coverage: 0.39 },
    { key: 'market', label: 'Market behaviour', score: null, effective_weight: 0, unavailable_reason: 'no prices' },
  ]
  it('shows coverage, freshness and unavailable pillars without drawing them as zero', () => {
    render(<PillarBars pillars={pillars} context={{ workforce: 'reviews to 2021Q2 (historical dataset)' }} />)
    const workforce = screen.getByText('Workforce').closest('li')
    expect(within(workforce).getByText('coverage 39%')).toHaveClass('text-serious-text')  // low coverage is flagged
    expect(within(workforce).getByText(/reviews to 2021Q2/)).toBeInTheDocument()
    expect(screen.getByText('Not scored - no prices')).toBeInTheDocument()
    expect(screen.getAllByText('/ 100')).toHaveLength(2)
  })
})

describe('tabs', () => {
  it('marks the active tab and reports clicks', async () => {
    const onChange = vi.fn()
    render(<Tabs tabs={[{ key: 'a', label: 'Overview' }, { key: 'b', label: 'Events', count: 3 }]} active="a" onChange={onChange} />)
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true')
    await userEvent.click(screen.getByRole('tab', { name: /Events/ }))
    expect(onChange).toHaveBeenCalledWith('b')
  })
})

describe('search box', () => {
  it('suggests SEC filers as you type and opens the picked company', async () => {
    mockApi({ '/companies/search': [{ company: { id: 5, name: 'Intel Corp', ticker: 'INTC', marketId: '0000050863', demo: true }, formerNames: [] }] })
    renderApp(<SearchBox />)
    await userEvent.type(screen.getByRole('textbox', { name: 'Search companies' }), 'intel')
    const option = await screen.findByText('Intel Corp', {}, { timeout: 2000 })
    expect(screen.getByText('DEMO')).toBeInTheDocument()
    await userEvent.click(option)
    expect(screen.getByTestId('where')).toHaveTextContent('/company/5')
  })
})

describe('landing page', () => {
  it('renders the hero, live platform figures and the demo universe from the API', async () => {
    mockApi({
      '/universe': [
        { companyId: 1, name: 'Apple Inc.', ticker: 'AAPL', role: 'healthy', asOf: ['latest'] },
        { companyId: 10, name: 'Bed Bath & Beyond Inc.', ticker: 'BBBY', role: 'historical_distress', asOf: ['2022-04-30', '2023-01-31'] },
      ],
      '/stats': { companies: 12, reports: 3, users: 2, jobsDone: 3, models: [
        { name: 'distress', version: '2', kind: 'ML', is_champion: true, primary_metric: 'pr_auc', metrics: { pr_auc: 0.1026 }, baseline: { name: 'altman_z2_baseline', metrics: { pr_auc: 0.0238 } } },
      ] },
    })
    renderApp(<Landing />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('See the health of any listed company')
    expect((await screen.findAllByText('Apple Inc.')).length).toBeGreaterThan(0)
    expect(screen.getByText('Bed Bath & Beyond Inc.')).toBeInTheDocument()
    expect(screen.getByText('as of 31 Jan 2023', { exact: false })).toBeInTheDocument()
    expect(await screen.findByText('0.103')).toBeInTheDocument()  // champion metric from the model card
  })
})

describe('pricing page', () => {
  it('lists every plan and highlights the recommended one', async () => {
    mockApi({ '/billing/plans': [
      { name: 'FREE', label: 'Free', monthlyPriceUsd: 0, analysesPerDay: 5, maxWatchlists: 1, maxWatchlistItems: 5, maxCompare: 2, historyDays: 365, pdfExport: false, maxApiKeys: 0, apiCallsPerDay: 0 },
      { name: 'PRO', label: 'Pro', monthlyPriceUsd: 29, analysesPerDay: 100, maxWatchlists: 10, maxWatchlistItems: 50, maxCompare: 4, historyDays: -1, pdfExport: true, maxApiKeys: 2, apiCallsPerDay: 1000 },
    ] })
    renderApp(<Pricing />)
    expect(await screen.findByText('Most popular')).toBeInTheDocument()
    expect(screen.getByText('$29')).toBeInTheDocument()
    expect(screen.getByText('Full point-in-time score history')).toBeInTheDocument()
    expect(screen.getByText('CSV export')).toBeInTheDocument()
  })
})
