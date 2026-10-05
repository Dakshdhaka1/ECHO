import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ScoreGauge } from '../components/charts'
import { BandBadge } from '../components/ui'
import { AuthProvider } from '../context/AuthContext'
import CompanyReport from '../pages/CompanyReport'
import fixture from '../../../backend/src/test/resources/analysis-apple.json'
import { fmtMoney, fmtPct, fmtSigned } from '../utils/format'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

describe('format helpers', () => {
  it('formats money, percentages and signed numbers', () => {
    expect(fmtMoney(416.16e9)).toBe('$416.16B')
    expect(fmtMoney(-2.5e6)).toBe('-$2.5M')
    expect(fmtPct(0.0775, 2)).toBe('7.75%')
    expect(fmtSigned(3.14159, 2)).toBe('+3.14')
    expect(fmtPct(null)).toBe('-')
  })
})

describe('accessible status encoding', () => {
  it('band badge carries a text label, not colour alone', () => {
    render(<BandBadge band="WATCH" />)
    expect(screen.getByText('Watch')).toBeInTheDocument()
  })
  it('gauge exposes the score to screen readers', () => {
    render(<ScoreGauge score={77} band="STRONG" />)
    expect(screen.getByRole('img', { name: 'Health score 77 of 100, Strong' })).toBeInTheDocument()
  })
})

function renderReport() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/company/1']}>
        <AuthProvider>
          <Routes><Route path="/company/:id" element={<CompanyReport />} /></Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('company report page', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('polls the analysis job (202) and then renders the explained report', async () => {
    const company = { id: 1, market: 'US_SEC', marketId: '0000320193', name: 'Apple Inc.', ticker: 'AAPL', sector: 'Information Technology' }
    const report = { id: 9, company, asOf: fixture.as_of, generatedAt: '2026-10-05T07:00:00Z', healthScore: fixture.health.score,
      band: fixture.health.band, confidence: fixture.health.confidence, payload: fixture, stale: false }
    let reportCalls = 0
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (url) => {
      const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
      if (url.endsWith('/companies/1')) return json(company)
      if (url.includes('/companies/1/report')) {
        reportCalls += 1
        return reportCalls === 1
          ? json({ status: 'PENDING', job: { id: 'j1', status: 'RUNNING', startedAt: new Date().toISOString() } }, 202)
          : json({ status: 'READY', report })
      }
      if (url.includes('/jobs/j1')) return json({ id: 'j1', status: 'DONE', reportId: 9 })
      return json({}, 404)
    })
    renderReport()
    expect(await screen.findByText(/Analysing this company/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Executive summary')).toBeInTheDocument(), { timeout: 4000 })
    expect(screen.getByRole('img', { name: `Health score ${fixture.health.score} of 100, Strong` })).toBeInTheDocument()
    expect(screen.getByText(fixture.summary.text)).toBeInTheDocument()
    expect(screen.getAllByText(/Not scored - /, { selector: 'div' }).length).toBeGreaterThan(0)
  })
})
