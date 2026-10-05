import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, ArrowUpRight, History } from '../components/icons'
import { CountUp, Reveal } from '../components/motion'
import SearchBox from '../components/SearchBox'
import SilkShader from '../components/SilkShader'
import { Button, Label, Skeleton } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { api } from '../services/api'
import { fmtDate, humanize } from '../utils/format'

const wrap = 'mx-auto w-full max-w-[1360px] px-4 md:px-6'

// The five scoring pillars, their documented weights and sources (docs/architecture/SCORING.md).
const PILLARS = [
  { label: 'Financial', weight: 30, source: 'SEC XBRL', x: 50, y: 15, text: 'Altman Z, Piotroski F, margins, liquidity and leverage, each ranked against sector peers as of the analysis date.' },
  { label: 'Market', weight: 20, source: 'Alpha Vantage', x: 84, y: 39, text: 'Excess return against the sector ETF, drawdown from the 52-week high and realised volatility.' },
  { label: 'News', weight: 20, source: 'GDELT', x: 71, y: 79, text: 'A fine-tuned transformer scores 90 days of de-duplicated headlines; thin coverage is shrunk toward neutral.' },
  { label: 'Workforce', weight: 15, source: 'Kaggle reviews', x: 29, y: 79, text: 'An Employee Sentiment Index from public review data, plus layoff and restructuring disclosures.' },
  { label: 'Events', weight: 15, source: 'SEC 8-K', x: 16, y: 39, text: '8-K items mapped to decaying penalties; bankruptcy and delisting filings cap the score.' },
]

// Simplified excerpt of the real scoring engine; each method step highlights the lines it describes.
const CODE = [
  ['c', '# ml-service/app/inference/scoring.py (simplified)'],
  ['k', 'WEIGHTS = {"financial": .30, "market": .20, "news": .20,'],
  ['k', '           "workforce": .15, "events": .15}'],
  ['', ''],
  ['f', 'def score_company(features, peers, as_of):'],
  ['', '    evidence = point_in_time(features, as_of)     # filed on or before as_of'],
  ['', '    factors = [score_factor(f, peers.percentile(f, as_of))'],
  ['', '               for f in evidence]                 # 0-100 vs sector peers'],
  ['', '    pillars = renormalise(WEIGHTS, available(factors))'],
  ['', '    impact = {f.key: f.weight * (f.score - 50)     # exact and additive'],
  ['', '              for f in factors}'],
  ['', '    health = 50 + sum(impact.values())'],
  ['', '    confidence = coverage(pillars)                 # no score below 0.40'],
  ['k', '    return cap(health, events), impact, confidence'],
]

const STEPS = [
  { title: 'Collect point-in-time evidence', lines: [4, 5], text: 'SEC filings, 8-K events, headlines, prices and reviews, using only what was public on the analysis date.' },
  { title: 'Rank against sector peers', lines: [6, 7], text: 'Every factor becomes a 0-100 score from its percentile among companies in the same sector.' },
  { title: 'Attribute every point', lines: [9, 10, 11], text: 'The score is 50 plus the sum of factor impacts, so each point traces back to a factor and its source filing.' },
  { title: 'Report confidence, never fill gaps', lines: [8, 12], text: 'Missing pillars are excluded and lower the confidence. Below 40% coverage no score is shown.' },
]

const ROLE_TAG = { healthy: 'Healthy reference', mixed: 'Mixed signals', historical_distress: 'Case study' }

/** Hero visual: a company at the centre, its five evidence pillars around it, an echo pulse travelling out. */
function EchoField() {
  return (
    <div className="window mx-auto w-full max-w-[520px] bg-surface/85 backdrop-blur-sm">
      <div className="window-bar">
        <span className="flex gap-1.5" aria-hidden>{[0, 1, 2].map((i) => <span key={i} className="h-2.5 w-2.5 rounded-full bg-line-strong" />)}</span>
        <span className="label mx-auto">echo_field.health</span>
        <span className="flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-wider text-accent-ink">
          <span className="live-dot h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />5 pillars
        </span>
      </div>
      <div className="relative aspect-square">
        <svg viewBox="0 0 400 400" className="absolute inset-0 h-full w-full" aria-hidden>
          <defs>
            <radialGradient id="core-glow"><stop offset="0%" stopColor="var(--accent)" stopOpacity="0.2" /><stop offset="100%" stopColor="var(--accent)" stopOpacity="0" /></radialGradient>
          </defs>
          <circle cx="200" cy="200" r="150" fill="url(#core-glow)" />
          {[70, 120, 170].map((r) => <circle key={r} cx="200" cy="200" r={r} fill="none" stroke="var(--line-strong)" strokeDasharray={r === 170 ? '2 6' : undefined} />)}
          <line x1="20" y1="200" x2="380" y2="200" stroke="var(--line)" />
          <line x1="200" y1="20" x2="200" y2="380" stroke="var(--line)" />
          {[0, 1.6, 3.2].map((d) => (
            <circle key={d} className="ping-ring" style={{ animationDelay: `${d}s` }} cx="200" cy="200" r="185" fill="none" stroke="var(--accent)" strokeOpacity="0.5" />
          ))}
          {PILLARS.map((p, i) => (
            <g key={p.label}>
              <path d={`M 200 200 L ${p.x * 4} ${p.y * 4}`} pathLength="1" className="draw" style={{ animationDelay: `${0.4 + i * 0.15}s` }} stroke="var(--accent)" strokeOpacity="0.55" fill="none" />
              <circle cx={p.x * 4} cy={p.y * 4} r="3.5" fill="var(--accent)" />
            </g>
          ))}
          <circle cx="200" cy="200" r="36" fill="var(--surface)" stroke="var(--line-strong)" />
          <path d="M 180 202 h 7 l 4 -10 l 6 18 l 5 -13 l 3 5 h 7" fill="none" stroke="var(--accent)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        {PILLARS.map((p, i) => (
          <div key={p.label} className="absolute -translate-x-1/2 -translate-y-1/2" style={{ left: `${p.x}%`, top: `${p.y}%` }}>
            <div className="animate-rise" style={{ animationDelay: `${0.6 + i * 0.12}s` }}>
              <div className="float flex items-center gap-2 whitespace-nowrap rounded-[4px] border border-line-strong bg-surface px-2 py-1 text-xs font-medium text-ink" style={{ animationDelay: `${i * 0.9}s` }}>
                {p.label}<span className="font-mono text-[11px] text-accent-ink">{p.weight}%</span>
              </div>
            </div>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between border-t border-line px-4 py-2.5 font-mono text-[10.5px] uppercase tracking-wider text-muted">
        <span>score = 50 + sum(impact)</span><span>sector-peer percentiles</span>
      </div>
    </div>
  )
}

function MethodSteps() {
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)
  useEffect(() => {
    if (paused) return undefined
    const t = setInterval(() => setActive((a) => (a + 1) % STEPS.length), 5200)
    return () => clearInterval(t)
  }, [paused])
  const lit = new Set(STEPS[active].lines)
  return (
    <div className="grid gap-8 lg:grid-cols-[0.9fr_1.1fr] lg:gap-14" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <div>
        <Label rule>Methodology // attribution engine</Label>
        <h2 className="mt-4 text-3xl font-light tracking-[-0.02em] text-ink md:text-[2.6rem] md:leading-[1.1]">From public filings to a score you can audit</h2>
        <p className="mt-4 max-w-md text-[15px] leading-relaxed text-ink-2">Models only see information that existed at the analysis date, and each one had to beat a baseline on held-out data before promotion.</p>
        <ol className="mt-8 border-t border-line">
          {STEPS.map((s, i) => (
            <li key={s.title} className="border-b border-line">
              <button onClick={() => { setActive(i); setPaused(true) }} aria-expanded={active === i}
                      className="flex w-full items-center justify-between gap-4 py-4 text-left">
                <span className="flex items-center gap-3">
                  <span className={`font-mono text-[11px] ${active === i ? 'text-accent-ink' : 'text-muted'}`}>0{i + 1}</span>
                  <span className={`text-[15px] transition-colors duration-300 ${active === i ? 'font-medium text-ink' : 'text-ink-2'}`}>{s.title}</span>
                </span>
                <span className={`h-px w-4 transition-all duration-500 ease-spring ${active === i ? 'bg-accent' : 'bg-line-strong'}`} aria-hidden />
              </button>
              {active === i && (
                <div className="pb-5 pl-8">
                  <p className="text-sm leading-relaxed text-ink-2 animate-[rise_0.5s_var(--ease-fluid)_both]">{s.text}</p>
                  {!paused && <div className="mt-4 h-px overflow-hidden bg-line"><div className="h-full bg-accent" style={{ animation: 'grow-x 5.2s linear both', transformOrigin: 'left' }} /></div>}
                </div>
              )}
            </li>
          ))}
        </ol>
      </div>
      <div className="window self-start">
        <div className="window-bar">
          <span className="flex gap-1.5" aria-hidden>{[0, 1, 2].map((i) => <span key={i} className="h-2.5 w-2.5 rounded-full bg-line-strong" />)}</span>
          <span className="label">scoring.py</span>
          <span className="ml-auto rounded-[3px] border border-line-strong px-1.5 font-mono text-[10px] text-muted">python 3.12</span>
        </div>
        <pre tabIndex={0} aria-label="Excerpt of the scoring engine, scoring.py" className="overflow-x-auto py-3 font-mono text-[12.5px] leading-6 focus-visible:outline-1 focus-visible:outline-accent">
          {CODE.map(([kind, line], i) => (
            <div key={i} className={`flex pr-4 transition-colors duration-500 ${lit.has(i) ? 'bg-accent-soft' : ''}`}>
              <span className={`w-10 shrink-0 select-none pr-3 text-right ${lit.has(i) ? 'text-accent-ink' : 'text-muted'}`}>{String(i + 1).padStart(2, '0')}</span>
              <code className={kind === 'c' ? 'text-muted' : kind === 'f' ? 'text-accent-ink' : 'text-ink-2'}>{line || ' '}</code>
            </div>
          ))}
        </pre>
      </div>
    </div>
  )
}

function CompanyCard({ c }) {
  const dates = (c.asOf || []).filter((d) => d !== 'latest')
  const latest = (c.asOf || []).includes('latest')
  const target = latest ? `/company/${c.companyId}` : `/company/${c.companyId}?asOf=${dates[dates.length - 1]}`
  return (
    <div className="card group flex h-full flex-col p-5 transition duration-300 hover:-translate-y-0.5">
      <div className="flex items-center justify-between gap-2">
        <span className="rounded-[3px] bg-surface-3 px-1.5 py-0.5 font-mono text-[11px] font-medium text-ink">{c.ticker}</span>
        <span className="flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-wider text-muted">
          {c.role === 'historical_distress' && <History size={12} aria-hidden />}{ROLE_TAG[c.role] || c.role}
        </span>
      </div>
      <div className="mt-4 text-lg font-medium tracking-tight text-ink">{c.name}</div>
      {dates.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {dates.map((d) => (
            <Link key={d} to={`/company/${c.companyId}?asOf=${d}`} className="rounded-[4px] border border-line-strong px-2 py-1 font-mono text-[11px] text-ink-2 transition-colors hover:border-accent hover:text-ink">
              as of {fmtDate(d)}
            </Link>
          ))}
        </div>
      )}
      <div className="min-h-5 flex-1" />
      <div className="flex items-center justify-between border-t border-line pt-4">
        <span className="font-mono text-[10.5px] uppercase tracking-wider text-muted">{latest ? 'Latest filings' : `${dates.length} point-in-time reports`}</span>
        <Link to={target} className="inline-flex items-center gap-1.5 font-mono text-xs text-accent-ink">
          Inspect dossier <ArrowUpRight size={12} weight="bold" className="transition-transform duration-300 ease-spring group-hover:-translate-y-px group-hover:translate-x-0.5" />
        </Link>
      </div>
    </div>
  )
}

export default function Landing() {
  const { user } = useAuth()
  const { dark } = useTheme()
  const universe = useQuery({ queryKey: ['universe'], queryFn: () => api.get('/universe'), staleTime: 600_000 })
  const stats = useQuery({ queryKey: ['stats'], queryFn: () => api.get('/stats'), staleTime: 60_000 })
  const champions = (stats.data?.models || []).filter((m) => m.is_champion)
  const companies = universe.data || []

  return (
    <div>
      {/* hero over the Stitch silk shader */}
      <section className="relative overflow-hidden border-b border-line">
        <div className="absolute inset-0 animate-[fade_1.6s_var(--ease-fluid)_both]"><SilkShader key={dark ? 'dark' : 'light'} /></div>
        <div className="absolute inset-0 bg-gradient-to-r from-page via-page/80 to-page/10" aria-hidden />
        <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-page to-transparent" aria-hidden />
        <div className={`${wrap} relative grid min-h-[calc(100dvh-3.5rem)] items-center gap-12 py-16 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16`}>
          <div className="stagger">
            <Label rule>Corporate health observatory</Label>
            <h1 className="mt-6 text-[clamp(2.6rem,5.6vw,4.6rem)] font-light leading-[1.04] tracking-[-0.03em] text-ink">
              See the health of any listed company, <span className="text-accent-ink">and exactly why.</span>
            </h1>
            <p className="mt-6 max-w-[34rem] text-[17px] leading-relaxed text-ink-2">
              Filings, events, news and market data become one 0-100 score, with every point traced to its source.
            </p>
            <div className="mt-9 max-w-xl"><SearchBox large autoFocus /></div>
          </div>
          <div className="animate-[rise_1s_var(--ease-fluid)_0.25s_both]"><EchoField /></div>
        </div>
      </section>

      {/* demo universe ticker */}
      {companies.length > 0 && (
        <div className="overflow-hidden border-b border-line bg-surface/60" aria-label="Demo companies">
          <div className="marquee py-2.5">
            {[0, 1].map((copy) => (
              <div key={copy} className="flex shrink-0" aria-hidden={copy === 1}>
                {companies.map((c) => (
                  <Link key={c.companyId} to={`/company/${c.companyId}${(c.asOf || []).includes('latest') ? '' : `?asOf=${c.asOf[c.asOf.length - 1]}`}`} tabIndex={copy ? -1 : 0}
                        className="flex items-center gap-2.5 whitespace-nowrap px-5 font-mono text-[11px] uppercase tracking-wider text-muted transition-colors hover:text-ink">
                    <span className="font-medium text-ink">{c.ticker}</span>
                    <span className={c.role === 'historical_distress' ? 'text-serious-text' : c.role === 'mixed' ? 'text-ink-2' : 'text-accent-ink'}>{ROLE_TAG[c.role]}</span>
                    <span className="text-line-strong">///</span>
                  </Link>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* platform figures (live counts from this deployment) */}
      <section className={`${wrap} grid grid-cols-2 gap-y-8 py-14 md:grid-cols-4`}>
        {[['Companies covered', stats.data?.companies], ['Models in production', champions.length || null], ['Reports generated', stats.data?.reports], ['Analyses run', stats.data?.jobsDone]].map(([label, v], i) => (
          <Reveal key={label} delay={i * 80} className="border-l border-line pl-5">
            <div className="font-mono text-4xl font-medium tracking-tight text-ink md:text-5xl">{v == null ? '-' : <CountUp value={v} />}</div>
            <div className="label mt-2">{label}</div>
          </Reveal>
        ))}
      </section>

      {/* demo universe */}
      <section className={`${wrap} py-16 md:py-24`}>
        <Reveal className="flex flex-wrap items-end justify-between gap-4">
          <div className="max-w-2xl">
            <Label rule>Dossiers // demo universe</Label>
            <h2 className="mt-4 text-3xl font-light tracking-[-0.02em] text-ink md:text-[2.6rem]">Start with a real company</h2>
            <p className="mt-3 text-[15px] leading-relaxed text-ink-2">Demo mode replays recorded SEC data, so no API keys are needed. Case studies use only data that was public before the event.</p>
          </div>
        </Reveal>
        <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {universe.isLoading && Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-44" />)}
          {universe.error && <p className="text-sm text-ink-2">The demo universe is unavailable: {universe.error.message}</p>}
          {companies.map((c, i) => <Reveal key={c.companyId} delay={(i % 3) * 80}><CompanyCard c={c} /></Reveal>)}
        </div>
      </section>

      {/* method */}
      <section className="border-y border-line bg-surface/40">
        <div className={`${wrap} py-16 md:py-24`}><Reveal><MethodSteps /></Reveal></div>
      </section>

      {/* pillars */}
      <section className={`${wrap} py-16 md:py-24`}>
        <Reveal className="max-w-2xl">
          <h2 className="text-3xl font-light tracking-[-0.02em] text-ink md:text-[2.6rem]">How a corporate health score is formed</h2>
          <p className="mt-3 text-[15px] leading-relaxed text-ink-2">Five pillars with documented weights. A pillar without evidence is left out and the remaining weights are renormalised.</p>
        </Reveal>
        <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {PILLARS.map((p, i) => (
            <Reveal key={p.label} delay={i * 70} className="card flex flex-col p-5">
              <div className="flex items-center justify-between font-mono text-[10.5px] uppercase tracking-wider">
                <span className="text-accent-ink">Weight {p.weight}%</span><span className="text-muted">{p.source}</span>
              </div>
              <h3 className="mt-4 text-lg font-medium text-ink">{p.label}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-2">{p.text}</p>
              <div className="mt-auto pt-5"><div className="h-1 bg-surface-3"><div className="h-full bg-accent" style={{ width: `${p.weight / 0.3}%` }} /></div></div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* models */}
      <section className={`${wrap} pb-16 md:pb-24`}>
        <Reveal className="card overflow-hidden">
          <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line px-6 py-5">
            <div>
              <Label>Empirical validation</Label>
              <h2 className="mt-2 text-2xl font-light tracking-[-0.02em] text-ink">Models in production</h2>
            </div>
            <Link to="/models" className="inline-flex items-center gap-1.5 font-mono text-xs text-accent-ink">Read the model cards <ArrowRight size={12} weight="bold" /></Link>
          </div>
          {stats.isLoading ? <div className="p-6"><Skeleton className="h-48" /></div> : champions.length === 0 ? (
            <p className="p-6 text-sm text-ink-2">No model cards available yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead>
                  <tr className="border-b border-line-strong bg-surface-2/60 text-left">
                    {['Model', 'Kind', 'Primary metric', 'Baseline', 'Champion', 'Baseline score'].map((h) => <th key={h} className="label px-6 py-2.5 font-medium">{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {champions.map((m) => {
                    const value = Number(m.metrics[m.primary_metric])
                    const base = Number(m.baseline?.metrics?.[m.primary_metric])
                    return (
                      <tr key={m.name} className="border-b border-line transition-colors last:border-0 hover:bg-surface-2/60">
                        <td className="px-6 py-3 font-medium text-ink">{humanize(m.name)} <span className="font-mono text-xs font-normal text-muted">v{m.version}</span></td>
                        <td className="px-6 py-3 font-mono text-xs text-ink-2">{m.kind}</td>
                        <td className="px-6 py-3 text-ink-2">{m.primary_metric.replaceAll('_', ' ')}</td>
                        <td className="px-6 py-3 text-ink-2">{m.baseline?.name?.replaceAll('_', ' ')}</td>
                        <td className="px-6 py-3 font-mono text-accent-ink tabular">{value.toFixed(3)}</td>
                        <td className="px-6 py-3 font-mono text-muted tabular">{Number.isFinite(base) ? base.toFixed(3) : '-'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Reveal>
      </section>

      {/* call to action */}
      <section className={`${wrap} pb-8`}>
        <Reveal className="relative overflow-hidden rounded-lg border border-line-strong bg-surface px-6 py-14 md:px-14 md:py-20">
          <div className="pointer-events-none absolute -right-32 -top-32 h-[28rem] w-[28rem] rounded-full bg-[radial-gradient(closest-side,var(--glow-1),transparent)]" aria-hidden />
          <div className="relative max-w-2xl">
            <Label rule>Watchlists and alerts</Label>
            <h2 className="mt-4 text-3xl font-light tracking-[-0.02em] text-ink md:text-5xl md:leading-[1.08]">Watch companies, not news feeds.</h2>
            <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-ink-2">
              Free accounts get a watchlist and score-drop alerts. Pro adds PDF reports, full history, wider comparisons and API access.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-5">
              <Link to={user ? '/watchlists' : '/register'}><Button variant="accent" className="h-10 px-5">{user ? 'Open your watchlists' : 'Create a free account'}</Button></Link>
              <Link to="/pricing" className="inline-flex items-center gap-1.5 text-sm text-ink-2 transition-colors hover:text-ink">Compare plans <ArrowRight size={14} weight="bold" /></Link>
            </div>
          </div>
        </Reveal>
      </section>
    </div>
  )
}
