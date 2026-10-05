import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle, BellPlus, BrainCircuit, Database, Download, ExternalLink, FileText, GitCompare, History as HistoryIcon,
  Loader2, RefreshCw, Users,
} from '../components/icons'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  DriverChart, ForecastChart, HistoryChart, ImpactChart, PillarBars, ScoreGauge, SentimentChart, SeriesBars, SeriesLine,
} from '../components/charts'
import {
  BandBadge, Button, Card, Disclaimer, EmptyState, ErrorState, KindBadge, SeverityDot, Skeleton, StatTile, Tabs,
  UpgradePrompt,
} from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useReport } from '../hooks/useReport'
import { api } from '../services/api'
import { BANDS, RISK_BANDS, fmtDate, fmtMoney, fmtNum, fmtPct, fmtSigned, humanize } from '../utils/format'

// ---------------------------------------------------------------------------------------------- page
export default function CompanyReport() {
  const { id } = useParams()
  const [params, setParams] = useSearchParams()
  const asOf = params.get('asOf')
  const tab = params.get('tab') || 'overview'
  const { report, pending, job, error, isLoading, refetch } = useReport(id, asOf)
  const company = useQuery({ queryKey: ['company', id], queryFn: () => api.get(`/companies/${id}`) })

  const setTab = (t) => { params.set('tab', t); setParams(params, { replace: true }) }
  const r = report?.payload

  if (isLoading) return <PageSkeleton />
  if (error && !report) return <ErrorState error={error} onRetry={refetch} />

  return (
    <div className="space-y-7">
      <ReportHeader company={company.data} report={report} asOf={asOf} />
      {pending && <JobProgress job={job} stale={!!report} />}
      {!report && pending && <PageSkeleton compact />}
      {r && (
        <>
          {r.case_study && (
            <div className="flex items-start gap-3 rounded-md border border-accent/25 bg-accent-soft/60 px-4 py-3.5 text-sm text-ink-2 animate-rise">
              <HistoryIcon size={18} className="mt-px shrink-0 text-accent" aria-hidden />
              <span><b className="text-ink">Historical case study.</b> {r.case_study.note} Only data filed on or before {fmtDate(r.as_of)} is used.</span>
            </div>
          )}
          <Tabs
            active={tab}
            onChange={setTab}
            tabs={[
              { key: 'overview', label: 'Overview' },
              { key: 'why', label: 'Why this score' },
              { key: 'financials', label: 'Financials' },
              { key: 'market', label: 'Market' },
              { key: 'news', label: 'News & sentiment', count: r.news?.articles || null },
              { key: 'workforce', label: 'Workforce' },
              { key: 'events', label: 'Events', count: r.events.length || null },
              { key: 'risk', label: 'Risk & ML' },
              { key: 'history', label: 'History' },
            ]}
          />
          <div key={tab} role="tabpanel">
          {tab === 'overview' && <Overview r={r} onTab={setTab} />}
          {tab === 'why' && <WhyTab r={r} />}
          {tab === 'financials' && <FinancialsTab r={r} />}
          {tab === 'market' && <MarketTab r={r} />}
          {tab === 'news' && <NewsTab r={r} />}
          {tab === 'workforce' && <WorkforceTab r={r} />}
          {tab === 'events' && <EventsTab r={r} />}
          {tab === 'risk' && <RiskTab r={r} />}
          {tab === 'history' && <HistoryTab companyId={id} />}
          </div>
          <Disclaimer text={r.disclaimer} />
        </>
      )}
    </div>
  )
}

function PageSkeleton({ compact }) {
  return (
    <div className="space-y-4">
      {!compact && <Skeleton className="h-56" />}
      <div className="grid gap-4 md:grid-cols-3"><Skeleton className="h-72" /><Skeleton className="h-72 md:col-span-2" /></div>
      <Skeleton className="h-52" />
    </div>
  )
}

// ---------------------------------------------------------------------------------------------- header
function ReportHeader({ company, report, asOf }) {
  const { user } = useAuth()
  const qc = useQueryClient()
  const [actionError, setActionError] = useState(null)
  const [busy, setBusy] = useState(null)
  const c = report?.company || company
  const r = report?.payload

  const refresh = useMutation({
    mutationFn: () => api.post(`/companies/${c.id}/analyze`, asOf ? { asOf } : {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['report', String(c.id)] }),
    onError: setActionError,
  })
  const watch = useMutation({
    mutationFn: async () => {
      const lists = await api.get('/watchlists')
      return api.post(`/watchlists/${lists[0].id}/items`, { companyId: c.id, scoreDropThreshold: 10 })
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['watchlists'] }) },
    onError: setActionError,
  })
  const exportAs = async (format) => {
    setBusy(format)
    setActionError(null)
    try { await api.download(`/reports/${report.id}/export?format=${format}`, `echo-report.${format}`) } catch (e) { setActionError(e) } finally { setBusy(null) }
  }

  if (!c) return <Skeleton className="h-56" />
  const ticker = c.ticker || `CIK${Number(c.marketId)}`
  const band = BANDS[report?.band] || BANDS.INSUFFICIENT_DATA
  return (
    <div className="space-y-4 animate-rise">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <nav className="flex flex-wrap items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-muted" aria-label="Breadcrumb">
          <Link to="/" className="hover:text-ink">Companies</Link><span>/</span>
          <span>{r?.company?.sector || c.sector || 'Sector pending'}</span><span>/</span>
          <span className="text-accent-ink">Dossier // {ticker}-{report ? report.asOf : 'pending'}</span>
        </nav>
        <div className="flex flex-wrap gap-2">
          {user ? (
            <>
              <Button variant="secondary" onClick={() => watch.mutate()} disabled={watch.isPending}>
                <BellPlus size={15} /> {watch.isSuccess ? 'On watchlist' : 'Watch'}
              </Button>
              <Button variant="secondary" onClick={() => refresh.mutate()} disabled={refresh.isPending || !report}>
                <RefreshCw size={15} className={refresh.isPending ? 'animate-spin' : ''} /> Re-analyse
              </Button>
              <Button variant="secondary" onClick={() => exportAs('csv')} disabled={!report || busy}><Download size={15} /> CSV</Button>
              <Button variant="secondary" onClick={() => exportAs('pdf')} disabled={!report || busy}><FileText size={15} /> {busy === 'pdf' ? 'Preparing...' : 'PDF report'}</Button>
            </>
          ) : (
            <Link to="/login" state={{ from: window.location.pathname + window.location.search }}><Button variant="secondary"><BellPlus size={15} /> Sign in to watch & export</Button></Link>
          )}
          <Link to={`/compare?ids=${c.id}`}><Button variant="ghost"><GitCompare size={15} /> Compare</Button></Link>
        </div>
      </div>

      <section className="relative overflow-hidden rounded-lg border border-line-strong bg-surface">
        <div className="pointer-events-none absolute -left-24 -top-40 h-[30rem] w-[40rem] bg-[radial-gradient(closest-side,var(--glow-1),transparent)]" aria-hidden />
        <div className="relative grid items-center gap-8 p-6 md:p-8 lg:grid-cols-[1.35fr_1fr]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 font-mono text-[10.5px] uppercase tracking-wider">
              {c.ticker && <span className="rounded-[3px] bg-accent-soft px-1.5 py-0.5 font-medium text-accent-ink">{c.ticker}</span>}
              {r?.company?.sic && <span className="rounded-[3px] border border-line-strong px-1.5 py-0.5 text-ink-2">SIC {r.company.sic}</span>}
              <span className="text-muted">CIK {Number(c.marketId)}</span>
            </div>
            <h1 className="mt-4 text-4xl font-light tracking-[-0.025em] text-ink md:text-5xl">{r?.company?.name || c.name}</h1>
            <p className="mt-3 text-sm text-ink-2">
              {r?.company?.sector || c.sector || 'Sector pending'}{r?.company?.sic_description && <span className="text-muted"> - {r.company.sic_description}</span>}
            </p>
            {r?.company?.legal_name && r.company.legal_name !== r.company.name && <p className="mt-1 text-xs text-muted">Current SEC legal name: {r.company.legal_name}</p>}
            {r?.company?.former_names?.length > 0 && <p className="mt-1 text-xs text-muted">Formerly: {r.company.former_names.slice(0, 3).join(' / ')}</p>}
            {r && (
              <dl className="mt-7 grid grid-cols-2 gap-x-6 gap-y-4 border-t border-line pt-5 sm:grid-cols-4">
                {[
                  ['As of', fmtDate(report.asOf)],
                  ['Data coverage', fmtPct(r.health.confidence, 0)],
                  ['Distress 12m (ML)', r.distress.available ? fmtPct(r.distress.probability_12m, 2) : 'n/a'],
                  ['Warning signals', String(r.signals.length)],
                ].map(([k, v]) => (
                  <div key={k}><dt className="label">{k}</dt><dd className="mt-1.5 font-mono text-lg text-ink tabular">{v}</dd></div>
                ))}
              </dl>
            )}
          </div>
          {report && (
            <div className="flex flex-col items-center gap-6 rounded-md border border-line bg-surface-2/50 p-6 sm:flex-row sm:items-center">
              <ScoreGauge score={r?.health.score ?? report.healthScore} band={report.band} />
              <div className="min-w-0">
                <div className="label">Composite health rating</div>
                <div className="mt-2"><BandBadge band={report.band} size="lg" /></div>
                <p className="mt-3 text-sm leading-relaxed text-ink-2">{BAND_TEXT[report.band] || BAND_TEXT.INSUFFICIENT_DATA}</p>
                {r?.health.override && <p className="mt-2 text-xs text-ink-2">{r.health.override}</p>}
                <p className="mt-3 font-mono text-[10.5px] uppercase tracking-wider text-muted">
                  Generated {new Date(report.generatedAt).toLocaleString()}{report.stale ? ' // refreshing' : ''}
                </p>
              </div>
            </div>
          )}
        </div>
      </section>
      {actionError && <ErrorState error={actionError} />}
    </div>
  )
}

const BAND_TEXT = {
  STRONG: 'Factors rank well above sector peers and no material events weigh on the score.',
  STABLE: 'In line with or above sector peers overall; isolated weaknesses show in the factor breakdown.',
  WATCH: 'Mixed evidence: several factors rank below sector peers or recent events carry penalties.',
  WEAK: 'Most evidence ranks below sector peers; review the warning signals and events.',
  CRITICAL: 'Severe distress evidence, such as a bankruptcy or delisting filing, or very weak fundamentals.',
  INSUFFICIENT_DATA: 'Too little evidence for a reliable score (data coverage below 40%).',
}

function JobProgress({ job, stale }) {
  const steps = ['Fetching SEC filings and news', 'Building point-in-time features', 'Running ML models', 'Scoring and explaining']
  const elapsed = job?.startedAt ? Math.max(0, (Date.now() - new Date(job.startedAt).getTime()) / 1000) : 0
  const current = job?.status === 'QUEUED' ? -1 : Math.min(steps.length - 1, Math.floor(elapsed / 2))
  return (
    <div className="card overflow-hidden p-5 animate-rise" role="status" aria-live="polite">
      <div className="flex items-start gap-3">
        <span className="live-dot mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full bg-accent" aria-hidden />
        <div>
          <div className="text-sm font-semibold text-ink">{stale ? 'Refreshing this report...' : 'Analysing this company...'}</div>
          <div className="mt-0.5 text-sm text-ink-2">
            {job?.status === 'QUEUED' ? 'Queued - waiting for a free analysis worker.' : `${steps[current]}...`}
            {stale && ' The previous report is shown until the new one is ready.'}
          </div>
        </div>
      </div>
      <ol className="mt-4 grid gap-2 sm:grid-cols-4" aria-hidden>
        {steps.map((step, i) => (
          <li key={step}>
            <div className="h-1 overflow-hidden rounded-full bg-surface-2">
              {i < current && <div className="h-full bg-ink-2" />}
              {i === current && <div className="skeleton h-full rounded-none bg-accent/70" />}
            </div>
            <div className={`mt-2 text-xs ${i <= current ? 'text-ink-2' : 'text-muted'}`}>{step}</div>
          </li>
        ))}
      </ol>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------- overview
function Overview({ r, onTab }) {
  return (
    <div className="space-y-6">
      <div className="stagger grid gap-4 lg:grid-cols-3">
        <Card title="Executive summary" className="lg:col-span-2"
              action={<span className="font-mono text-[10.5px] uppercase tracking-wider text-muted">{r.summary.generator === 'template' ? 'Deterministic template' : `${r.summary.generator} // grounding ${r.summary.grounding_check}`}</span>}>
          <p className="max-w-[78ch] border-l-2 border-accent pl-4 text-[15px] leading-relaxed text-ink">{r.summary.text}</p>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <StatTile label="12-month distress (ML)"
                      value={r.distress.available ? fmtPct(r.distress.probability_12m, 2) : 'n/a'}
                      hint={r.distress.available ? `${RISK_BANDS[r.distress.risk_band]?.label} risk band` : r.distress.unavailable_reason} />
            <StatTile label="Segment (ML)" value={r.segment.available ? r.segment.segment : 'n/a'}
                      hint={r.segment.available ? `${fmtPct(r.segment.membership, 0)} membership` : r.segment.unavailable_reason} />
            <StatTile label="Warning signals" value={r.signals.length}
                      hint={r.signals.length ? `${r.signals.filter((s) => ['CRITICAL', 'HIGH'].includes(s.severity)).length} high or critical` : 'none detected'} />
          </div>
        </Card>
        <Card title="Warning signals" subtitle="Documented rules and model alerts">
          <SignalList signals={r.signals} evidence={r.evidence} />
        </Card>
      </div>
      <section>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-lg font-medium text-ink">Pillar breakdown</h2>
            <p className="text-xs text-muted">Missing pillars are excluded and lower the confidence - never filled with defaults.</p>
          </div>
          <button onClick={() => onTab('why')} className="link font-mono text-xs">See every factor's contribution</button>
        </div>
        <PillarBars pillars={r.pillars} context={pillarContext(r)} />
      </section>
      <Card title="Data coverage" subtitle="Where each input came from">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {r.sources.map((s) => (
            <div key={s.source} className="rounded-md border border-line bg-surface-2/40 p-3.5 transition-colors duration-200 hover:border-line-strong">
              <div className="flex items-center gap-1.5 text-sm font-medium text-ink">
                <Database size={14} className={s.available ? 'text-good-text' : 'text-muted'} aria-hidden />
                {humanize(s.source)}
              </div>
              <div className="mt-1 text-xs text-ink-2">
                {s.available ? (<>{s.replayed ? 'Recorded snapshot' : 'Live'}{s.data_as_of ? ` - data to ${fmtDate(s.data_as_of)}` : ''}</>) : `Unavailable: ${s.reason}`}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}

/** Freshness line under each pillar card: how old and how broad the evidence behind the score is. */
function pillarContext(r) {
  const src = Object.fromEntries(r.sources.map((s) => [s.source, s]))
  const dataTo = (key) => (src[key]?.data_as_of ? `data to ${fmtDate(src[key].data_as_of)}` : null)
  return {
    financial: dataTo('sec_xbrl'),
    market: dataTo('prices'),
    news: r.news?.available ? `${r.news.articles} headlines, last 90 days` : null,
    workforce: r.employee?.available ? `reviews to ${r.employee.as_of_quarter} (historical dataset)` : null,
    events: dataTo('sec_submissions'),
  }
}

function Evidence({ ids, evidence }) {
  const items = (ids || []).map((id) => [id, evidence[id]]).filter(([, e]) => e?.url)
  if (!items.length) return null
  return (
    <span className="ml-1 inline-flex flex-wrap gap-2">
      {items.slice(0, 3).map(([id, e]) => (
        <a key={id} href={e.url} target="_blank" rel="noreferrer" className="link inline-flex items-center gap-1 text-xs" title={e.title}>
          <ExternalLink size={11} aria-hidden /> {e.source || 'source'}{e.date ? ` ${e.date}` : ''}
        </a>
      ))}
    </span>
  )
}

function SignalList({ signals, evidence }) {
  if (!signals.length) return <EmptyState icon={AlertTriangle} title="No warning signals">None of the documented warning rules fired for this analysis date.</EmptyState>
  return (
    <ul className="divide-y divide-line">
      {signals.map((s) => (
        <li key={s.code + s.date} className="flex flex-wrap items-start gap-x-3 gap-y-1 py-2.5">
          <div className="w-20 shrink-0"><SeverityDot severity={s.severity} /></div>
          <div className="min-w-0 flex-1">
            <div className="text-sm text-ink">{s.message}</div>
            <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
              <KindBadge kind={s.kind} /> <span>{s.code}</span>{s.date && <span>{fmtDate(s.date)}</span>}
              <Evidence ids={s.evidence} evidence={evidence} />
            </div>
          </div>
        </li>
      ))}
    </ul>
  )
}

// ---------------------------------------------------------------------------------------------- why
function WhyTab({ r }) {
  const factors = r.pillars.flatMap((p) => p.factors.filter((f) => f.score != null).map((f) => ({ ...f, pillar: p.label })))
  const total = factors.reduce((s, f) => s + f.impact, 0)
  return (
    <div className="stagger space-y-4">
      <Card title="Contribution of every factor (points)"
            subtitle={`Score = 50 + sum of impacts = 50 ${fmtSigned(total, 1)} = ${r.health.raw_score ?? '-'}${r.health.override ? ` (then ${r.health.override})` : ''}`}>
        {factors.length ? <ImpactChart factors={factors} /> : <EmptyState title="No scored factors" />}
      </Card>
      {r.pillars.map((p) => (
        <Card key={p.key} title={`${p.label} - ${p.score != null ? Math.round(p.score) : 'not scored'}`}
              subtitle={p.score != null ? `pillar weight ${Math.round(p.weight * 100)}%, effective ${Math.round(p.effective_weight * 100)}%, coverage ${fmtPct(p.coverage, 0)}` : p.unavailable_reason}
              bodyClass="overflow-x-auto">
          {p.factors.length > 0 && (
            <table className="w-full min-w-[720px] text-sm">
              <thead><tr className="border-b border-line text-left text-xs text-muted">
                <th className="px-5 py-2 font-medium">Factor</th><th className="px-2 py-2 font-medium">Kind</th><th className="px-2 py-2 font-medium">Value</th>
                <th className="px-2 py-2 font-medium">Peer pct.</th><th className="px-2 py-2 font-medium">Score</th><th className="px-2 py-2 font-medium">Impact</th>
                <th className="px-5 py-2 font-medium">Note / source</th></tr></thead>
              <tbody className="tabular">
                {p.factors.map((f) => (
                  <tr key={f.key} className="border-b border-line last:border-0">
                    <td className="px-5 py-2 text-ink">{f.label}</td>
                    <td className="px-2 py-2"><KindBadge kind={f.kind} /></td>
                    <td className="px-2 py-2 text-ink-2">{f.display_value || '-'}</td>
                    <td className="px-2 py-2 text-ink-2">{f.peer_percentile != null ? `${Math.round(f.peer_percentile * 100)}th` : '-'}</td>
                    <td className="px-2 py-2 text-ink">{f.score != null ? Math.round(f.score) : '-'}</td>
                    <td className="px-2 py-2 font-medium" style={{ color: f.impact > 0.05 ? 'var(--good-text)' : f.impact < -0.05 ? 'var(--critical)' : 'var(--muted)' }}>{fmtSigned(f.impact, 2)}</td>
                    <td className="px-5 py-2 text-xs text-ink-2">
                      {f.note}{f.peer_group && <span className="block text-muted">peers: {f.peer_group}</span>}
                      <Evidence ids={f.evidence} evidence={r.evidence} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------------------------- financials
function FinancialsTab({ r }) {
  const ts = r.timeseries
  const forecasts = r.forecasts || []
  const q = (k) => (ts[k] || []).map((d) => ({ date: d.period_end, value: d.value }))
  return (
    <div className="stagger grid gap-4 lg:grid-cols-2">
      {forecasts.map((f) => (
        <Card key={f.series} title={`${f.series === 'Revenue' ? 'Quarterly revenue' : 'Quarterly operating cash flow'} - forecast`}
              subtitle={`${f.model}. Bars: reported quarters (Q4 derived as FY - 9M). Band: 80% conformal interval.`}>
          <ForecastChart forecast={f} />
        </Card>
      ))}
      {forecasts.length === 0 && <Card title="Forecasts"><EmptyState title="No forecast">Needs at least 8 consecutive reported quarters.</EmptyState></Card>}
      <Card title="Quarterly net income"><SeriesBars data={q('quarterly_NetIncome')} x="date" y="value" name="Net income" format={fmtMoney} signed /></Card>
      <Card title="Quarterly operating income"><SeriesBars data={q('quarterly_OperatingIncome')} x="date" y="value" name="Operating income" format={fmtMoney} signed /></Card>
      <Card title="Cash and equivalents"><SeriesLine data={q('balance_Cash')} y="value" name="Cash" format={fmtMoney} /></Card>
      <Card title="Total liabilities"><SeriesLine data={q('balance_TotalLiabilities')} y="value" name="Liabilities" format={fmtMoney} /></Card>
      <Card title="Shareholders' equity"><SeriesLine data={q('balance_StockholdersEquity')} y="value" name="Equity" format={fmtMoney} /></Card>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------- market
function MarketTab({ r }) {
  const pillar = r.pillars.find((p) => p.key === 'market')
  const price = r.timeseries.price || []
  const daily = r.timeseries.price_daily || []
  const basis = r.sources.find((s) => s.source === 'prices')
  const mkt = r.anomalies.filter((a) => a.series === 'price_volume')
  if (!price.length) {
    return (
      <EmptyState icon={AlertTriangle} title="Market data not available for this report">
        {pillar?.unavailable_reason}. ECHO does not fabricate prices: record them with a free Alpha Vantage key
        (python -m pipelines.ingestion.record_sample --prices-only), or place {r.company.ticker}.csv (daily OHLCV)
        or {r.company.ticker}_weekly.csv in data/raw/prices/.
      </EmptyState>
    )
  }
  return (
    <div className="stagger grid gap-4 lg:grid-cols-3">
      <Card title="Share price - last 2 years" subtitle={`Weekly close, adjusted for splits and dividends${basis?.data_as_of ? ` - data to ${fmtDate(basis.data_as_of)}` : ''}`} className="lg:col-span-2">
        <SeriesLine data={price} y="close" name="Adjusted close" format={(v) => `$${fmtNum(v, 2)}`} height={260} />
      </Card>
      <Card title="Market factors" subtitle="Excess return vs the sector ETF; absolute score maps"><FactorList factors={pillar.factors} /></Card>
      <Card title={daily.length ? 'Daily volume (recent trading days)' : 'Weekly volume'} className="lg:col-span-2">
        <SeriesBars data={(daily.length ? daily : price).slice(-120)} x="date" y="volume" name="Volume" format={(v) => fmtNum(v / 1e6, 1) + 'M'} />
      </Card>
      <Card title="Market anomalies (daily data)">
        {daily.length ? <AnomalyList items={mkt} /> : <p className="text-sm text-ink-2">Not assessed: daily prices do not cover this analysis date (the free data tier keeps the last 100 trading days).</p>}
      </Card>
    </div>
  )
}

function FactorList({ factors }) {
  return (
    <ul className="space-y-2 text-sm">
      {factors.map((f) => (
        <li key={f.key} className="flex justify-between gap-3">
          <span className="text-ink-2">{f.label}</span>
          <span className="shrink-0 font-medium text-ink tabular">{f.display_value || '-'} <span className="text-muted">({f.score != null ? Math.round(f.score) : '-'})</span></span>
        </li>
      ))}
    </ul>
  )
}

function AnomalyList({ items }) {
  if (!items.length) return <p className="text-sm text-ink-2">No anomalies flagged.</p>
  return (
    <ul className="space-y-2">
      {items.map((a, i) => (
        <li key={i} className="rounded-md border border-line p-3 text-sm transition-colors duration-200 hover:border-line-strong">
          <div className="flex items-center justify-between"><span className="font-medium text-ink">{fmtDate(a.date)}</span><KindBadge kind={a.kind} /></div>
          <div className="mt-0.5 text-xs text-ink-2">{a.note}</div>
          <div className="mt-0.5 text-[11px] text-muted">{a.model}</div>
        </li>
      ))}
    </ul>
  )
}

// ---------------------------------------------------------------------------------------------- news
function NewsTab({ r }) {
  const n = r.news
  if (!n.available) {
    return <EmptyState icon={AlertTriangle} title="News sentiment not available">{n.unavailable_reason}. The GDELT DOC API covers roughly the last 3 months, so historical case studies have no news pillar.</EmptyState>
  }
  const pillar = r.pillars.find((p) => p.key === 'news')
  return (
    <div className="stagger grid gap-4 lg:grid-cols-3">
      <Card title="Headline sentiment timeline" subtitle="Daily mean of P(positive) - P(negative), fine-tuned NLP model" className="lg:col-span-2">
        <SentimentChart data={r.timeseries.news_sentiment || []} />
      </Card>
      <div className="space-y-4">
        <StatTile label="Mean sentiment (90 days)" value={fmtSigned(n.mean_sentiment, 2)} hint={`${n.articles} de-duplicated headlines`} />
        <div className="grid grid-cols-2 gap-3">
          <StatTile label="Positive" value={fmtPct(n.positive_share, 0)} />
          <StatTile label="Negative" value={fmtPct(n.negative_share, 0)} />
        </div>
        {pillar && <Card title="News factors"><FactorList factors={pillar.factors} /></Card>}
      </div>
      {r.timeseries.news_volume?.length > 0 && (
        <Card title="News volume (all matching articles per day, GDELT)" className="lg:col-span-3">
          <SeriesBars data={r.timeseries.news_volume} x="date" y="articles" name="Articles" format={(v) => fmtNum(v)} height={160} />
        </Card>
      )}
      <Card title="Headlines" subtitle="Metadata only - ECHO never stores article text" className="lg:col-span-3" bodyClass="p-0">
        <ul className="divide-y divide-line">
          {n.headlines.map((h) => (
            <li key={h.evidence_id} className="flex flex-wrap items-center gap-3 px-6 py-3 text-sm transition-colors duration-200 hover:bg-surface-2/50">
              <span className="w-24 shrink-0 font-mono text-[11px] text-muted">{fmtDate(h.date)}</span>
              <a href={h.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 text-ink hover:underline">{h.title}</a>
              {h.event_type && <span className="rounded bg-surface-2 px-1.5 py-px text-[10px] font-semibold text-ink-2">{h.event_type.replaceAll('_', ' ')}</span>}
              <span className="w-28 shrink-0 text-right font-mono text-xs text-ink-2 tabular">{h.label} {fmtSigned(h.sentiment, 2)}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------- workforce
function WorkforceTab({ r }) {
  const e = r.employee
  const layoffs = r.events.filter((ev) => ['RESTRUCTURING', 'LAYOFFS'].includes(ev.type))
  return (
    <div className="stagger grid gap-4 lg:grid-cols-3">
      <Card title="Employee Sentiment Index" className="lg:col-span-2">
        {e.available ? (
          <>
            <div className="flex flex-wrap gap-3">
              <StatTile label={`Index (${e.as_of_quarter})`} value={fmtSigned(e.index, 2)} hint={`90% CI ${fmtSigned(e.ci90[0], 2)} to ${fmtSigned(e.ci90[1], 2)}`} />
              <StatTile label="Reviews analysed" value={fmtNum(e.reviews)} />
            </div>
            <div className="mt-4"><SeriesLine data={e.series.map((s) => ({ date: `${s.quarter.slice(0, 4)}-${String(Number(s.quarter.slice(-1)) * 3).padStart(2, '0')}-28`, value: s.index }))} y="value" name="Index" format={(v) => fmtSigned(v, 2)} /></div>
          </>
        ) : (
          <EmptyState icon={Users} title="Employee reviews not available">
            {e.unavailable_reason}. ECHO uses the public Kaggle "Glassdoor Job Reviews" dataset (academic use, 2008-2021, 33 SEC filers) instead of scraping review sites.
          </EmptyState>
        )}
      </Card>
      <Card title="Complaint themes (NMF topics)">
        {e.available && e.themes.length ? (
          <ul className="space-y-2 text-sm">{e.themes.map((t) => (
            <li key={t.theme}><div className="flex justify-between"><span className="text-ink-2">{t.theme}</span><span className="tabular text-ink">{fmtPct(t.share, 0)}</span></div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface-2"><div className="grow-x h-full rounded-full" style={{ width: `${t.share * 100}%`, background: 'var(--series-1)' }} /></div></li>
          ))}</ul>
        ) : <p className="text-sm text-ink-2">Shown when review data is available.</p>}
      </Card>
      <Card title="Layoffs and restructuring (filings and news)" className="lg:col-span-3">
        {layoffs.length ? <EventList events={layoffs} evidence={r.evidence} /> : <p className="text-sm text-ink-2">No layoff or restructuring disclosures in the event history.</p>}
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------- events
function EventsTab({ r }) {
  const [filter, setFilter] = useState('all')
  const events = r.events.filter((e) => filter === 'all' || (filter === 'material' ? e.penalty > 0 : e.origin.startsWith('News')))
  return (
    <Card title="Major events timeline" subtitle="8-K items and event forms (Rule) plus classified headlines; penalties decay with a 180-day time constant"
          action={<select value={filter} onChange={(e) => setFilter(e.target.value)} className="field h-8 w-auto py-0" aria-label="Filter events">
            <option value="all">All events</option><option value="material">Material (penalised)</option><option value="news">From news</option></select>}>
      {events.length ? <EventList events={events} evidence={r.evidence} /> : <EmptyState title="No events" />}
    </Card>
  )
}

function EventList({ events, evidence }) {
  return (
    <ol className="stagger relative space-y-4 border-l border-line pl-6">
      {events.map((e) => (
        <li key={e.id}>
          <span className="absolute -left-[5.5px] mt-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-surface" style={{ background: e.penalty > 0 ? 'var(--serious)' : 'var(--axis)' }} aria-hidden />
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <span className="font-medium text-ink-2">{fmtDate(e.date)}</span><span>{e.origin}</span><SeverityDot severity={e.severity} />
            {e.penalty > 0 && <span>penalty {e.penalty.toFixed(1)}</span>}
          </div>
          <div className="text-sm text-ink">{e.title !== e.label ? <><b className="font-medium">{e.label}:</b> {e.title}</> : e.label}</div>
          <Evidence ids={e.evidence} evidence={evidence} />
        </li>
      ))}
    </ol>
  )
}

// ---------------------------------------------------------------------------------------------- risk & ML
function RiskTab({ r }) {
  const d = r.distress
  return (
    <div className="stagger grid gap-4 lg:grid-cols-3">
      <Card title="Distress probability (12 months)" subtitle={d.model || 'ML model'}>
        {d.available ? (
          <div className="space-y-3">
            <div className="font-mono text-5xl font-medium tracking-tight text-accent-ink tabular">{fmtPct(d.probability_12m, 2)}</div>
            <div className="flex items-center gap-2 text-sm text-ink-2">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: RISK_BANDS[d.risk_band]?.color }} aria-hidden />
              {RISK_BANDS[d.risk_band]?.label} risk band
            </div>
            {d.base_rate != null && <p className="text-xs text-ink-2">Test-set base rate: {fmtPct(d.base_rate, 2)}. Estimated chance of an 8-K Item 1.03 (bankruptcy) filing within 12 months, from point-in-time accounting data and SEC events.</p>}
          </div>
        ) : <p className="text-sm text-ink-2">{d.unavailable_reason}</p>}
      </Card>
      <Card title="Why the model says this (SHAP)" subtitle="Red raises the estimated risk, blue lowers it (log-odds)" className="lg:col-span-2">
        {d.available && d.drivers.length ? <DriverChart drivers={d.drivers} /> : <EmptyState icon={BrainCircuit} title="No model explanation" />}
      </Card>
      <Card title="Company segment">
        {r.segment.available ? (
          <><div className="text-2xl font-semibold tracking-tight text-ink">{r.segment.segment}</div>
            <p className="mt-1 text-sm text-ink-2">{r.segment.description}</p>
            <p className="mt-2 text-xs text-muted">{r.segment.model} - membership {fmtPct(r.segment.membership, 0)}</p></>
        ) : <p className="text-sm text-ink-2">{r.segment.unavailable_reason}</p>}
      </Card>
      <Card title="Anomalies" subtitle="Statement-change (Isolation Forest) and trading anomalies" className="lg:col-span-2">
        <AnomalyList items={r.anomalies} />
      </Card>
      <Card title="Models used for this report" className="lg:col-span-3">
        <div className="flex flex-wrap gap-2">
          {Object.entries(r.models).map(([k, v]) => (
            <span key={k} className="rounded-[4px] border border-line-strong px-2.5 py-1 text-xs text-ink-2">{k.replaceAll('_', ' ')}: <b className="font-mono font-medium text-ink">{v}</b></span>
          ))}
          <Link to="/models" className="link self-center text-xs font-medium">Model cards and evaluation</Link>
        </div>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------------------------- history
function HistoryTab({ companyId }) {
  const { user } = useAuth()
  const history = useQuery({ queryKey: ['history', companyId], queryFn: () => api.get(`/companies/${companyId}/history?from=2015-01-01`) })
  const points = useMemo(() => history.data || [], [history.data])
  if (history.isLoading) return <Skeleton className="h-72" />
  if (history.error) return <ErrorState error={history.error} />
  return (
    <div className="stagger space-y-4">
      <Card title="Score history" subtitle="Full reports (dots) and point-in-time partial scores at each 10-K/10-Q filing (financial + events pillars only)">
        {points.length ? <HistoryChart points={points} /> : <EmptyState title="No history yet" />}
      </Card>
      {(!user || user.plan === 'FREE') && <UpgradePrompt message="The Free plan shows the last 12 months of history. Pro shows the full point-in-time history." />}
    </div>
  )
}
