import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Check, Copy, KeyRound, Play, ShieldCheck, Trash2 } from '../components/icons'
import { Button, Card, EmptyState, ErrorState, KindBadge, PageHeader, Skeleton, StatTile } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { api } from '../services/api'
import { fmtNum, fmtSigned } from '../utils/format'

const metric = (v) => (v == null || Number.isNaN(Number(v)) ? '-' : Number(v).toFixed(3))

// ------------------------------------------------------------------------------------------- models
export function Models() {
  const { user } = useAuth()
  const cards = useQuery({ queryKey: ['models'], queryFn: () => api.get('/models') })
  const [showAll, setShowAll] = useState(false)
  if (cards.isLoading) return <div className="grid gap-4 lg:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-80" />)}</div>
  if (cards.error) return <ErrorState error={cards.error} onRetry={cards.refetch} />
  const list = cards.data.filter((c) => showAll || c.is_champion || !cards.data.some((o) => o.name === c.name && o.is_champion))
  return (
    <div className="space-y-8">
      <PageHeader eyebrow="MLOps // model registry" title="Models and transparency"
                  action={<label className="flex items-center gap-2 text-sm text-ink-2"><input type="checkbox" className="accent-[var(--accent)]" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> Show all versions</label>}>
        Every model is trained by a reproducible pipeline, evaluated on held-out data against a baseline, and promoted only if it passes the gate.
        A model that fails stays a challenger - for example the market Isolation Forest, which lost to a simple robust z-score rule.
      </PageHeader>
      <div className="stagger grid gap-4 lg:grid-cols-2">
        {list.map((c) => (
          <Card key={`${c.name}-${c.version}`} title={`${c.name.replaceAll('_', ' ')} v${c.version}`}
                subtitle={`${c.params?.algorithm || c.params?.selected || c.params?.model || ''} - trained ${new Date(c.trained_at).toLocaleDateString()}`}
                action={<div className="flex items-center gap-2"><KindBadge kind={c.kind} />
                  <span className={`rounded-[3px] px-1.5 py-px font-mono text-[10px] font-medium uppercase tracking-wider ${c.is_champion ? 'bg-accent-soft text-accent-ink' : 'bg-surface-3 text-ink-2'}`}>{c.is_champion ? 'champion' : c.stage || 'challenger'}</span></div>}>
            <table className="w-full text-sm">
              <thead><tr className="border-b border-line text-left text-xs text-muted"><th className="py-2 font-medium">Test metric</th><th className="py-1 font-medium">Model</th><th className="py-1 font-medium">Baseline ({c.baseline?.name?.replaceAll('_', ' ')})</th></tr></thead>
              <tbody>
                {Object.entries(c.metrics).filter(([k]) => !['tp', 'fp', 'tn', 'fn', 'n', 'positives', 'threshold', 'k'].includes(k)).slice(0, 7).map(([k, v]) => (
                  <tr key={k} className={k === c.primary_metric ? 'font-semibold text-ink' : 'text-ink-2'}>
                    <td className="py-1.5">{k.replaceAll('_', ' ')}{k === c.primary_metric ? ' (primary)' : ''}</td>
                    <td className="py-1.5 font-mono tabular">{metric(v)}</td><td className="py-1.5 font-mono tabular">{metric(c.baseline?.metrics?.[k])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className={`mt-3 flex items-start gap-1.5 text-xs ${c.gate?.passed ? 'text-good-text' : 'text-ink-2'}`}>
              {c.gate?.passed ? <Check size={14} className="mt-px shrink-0" /> : <ShieldCheck size={14} className="mt-px shrink-0" />}
              <span>Gate: {(c.gate?.reasons || []).join('; ')}</span>
            </div>
            <details className="mt-3 text-xs text-ink-2">
              <summary className="link cursor-pointer font-medium">Data, intended use and limitations</summary>
              <p className="mt-2"><b className="text-ink">Intended use.</b> {c.intended_use}</p>
              <p className="mt-1"><b className="text-ink">Limitations.</b> {c.limitations}</p>
              <p className="mt-1"><b className="text-ink">Data.</b> {JSON.stringify(c.data?.rows || c.data?.splits || c.data?.split || c.data).slice(0, 300)}</p>
              <p className="mt-1"><b className="text-ink">Licences.</b> {Object.entries(c.licences || {}).map(([k, v]) => `${k}: ${v}`).join('; ')}</p>
              <p className="mt-1 text-muted">MLflow run {c.mlflow_run_id?.slice(0, 8)} - git {c.git_sha} - {c.hardware}</p>
            </details>
          </Card>
        ))}
      </div>
      {user ? <SentimentPlayground /> : <p className="text-sm text-ink-2"><Link to="/login" className="link">Sign in</Link> to try the sentiment model on your own headlines.</p>}
    </div>
  )
}

function SentimentPlayground() {
  const [text, setText] = useState('Company beats revenue expectations and raises full-year guidance\nShares plunge after regulator opens fraud investigation\nBoard schedules annual shareholder meeting for May')
  const run = useMutation({ mutationFn: () => api.post('/sentiment', { texts: text.split('\n').map((t) => t.trim()).filter(Boolean) }) })
  return (
    <Card title="Try the news-sentiment model" subtitle="One headline per line - scored live by the champion NLP model">
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} aria-label="Headlines"
                className="field" />
      <Button className="mt-3" onClick={() => run.mutate()} disabled={run.isPending}><Play size={15} /> Score headlines</Button>
      {run.error && <div className="mt-3"><ErrorState error={run.error} /></div>}
      {run.data && (
        <table className="mt-5 w-full text-sm">
          <thead><tr className="text-left text-xs text-muted"><th className="py-1 font-medium">Headline</th><th className="py-1 font-medium">Label</th><th className="py-1 font-medium">Polarity</th><th className="py-1 font-medium">P(neg / neu / pos)</th></tr></thead>
          <tbody>{run.data.map((r) => (
            <tr key={r.text} className="border-t border-line"><td className="py-1.5 pr-3 text-ink">{r.text}</td><td className="py-1.5 text-ink-2">{r.label}</td>
              <td className="py-1.5 font-mono text-ink tabular">{fmtSigned(r.polarity, 2)}</td>
              <td className="py-1.5 font-mono text-ink-2 tabular">{r.probabilities.negative.toFixed(2)} / {r.probabilities.neutral.toFixed(2)} / {r.probabilities.positive.toFixed(2)}</td></tr>
          ))}</tbody>
        </table>
      )}
    </Card>
  )
}

// ------------------------------------------------------------------------------------------- pricing
const FEATURES = (p) => [
  `${p.analysesPerDay} fresh analyses per day`,
  `${p.maxWatchlists} watchlist${p.maxWatchlists > 1 ? 's' : ''} x ${p.maxWatchlistItems} companies, with alerts`,
  `Compare up to ${p.maxCompare} companies`,
  p.historyDays > 0 ? `${Math.round(p.historyDays / 30)} months of score history` : 'Full point-in-time score history',
  p.pdfExport ? 'PDF executive reports' : 'CSV export',
  p.maxApiKeys > 0 ? `API access: ${p.maxApiKeys} keys, ${fmtNum(p.apiCallsPerDay)} calls/day` : null,
].filter(Boolean)

export function Pricing() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const plans = useQuery({ queryKey: ['plans'], queryFn: () => api.get('/billing/plans') })
  const checkout = useMutation({ mutationFn: (plan) => api.post('/billing/checkout', { plan }), onSuccess: () => qc.invalidateQueries() })
  if (plans.isLoading) return <div className="grid gap-4 md:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-[28rem]" />)}</div>
  if (plans.error) return <ErrorState error={plans.error} />
  return (
    <div className="space-y-10">
      <PageHeader eyebrow="Pricing" title="Plans for analysts, researchers and teams">
        Every plan gets the same models and the same explanations. Paid plans add depth, volume and automation.
      </PageHeader>
      <div className="stagger grid gap-4 md:grid-cols-3">
        {plans.data.map((p) => {
          const current = user?.plan === p.name
          const featured = p.name === 'PRO'
          return (
            <div key={p.name} className={`card relative flex flex-col overflow-hidden p-7 transition duration-300 hover:-translate-y-0.5 ${featured ? 'border-accent/60 hover:border-accent' : ''}`}>
              {featured && <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 bg-[radial-gradient(closest-side,var(--glow-1),transparent)]" aria-hidden />}
              <div className="relative flex h-6 items-center justify-between">
                <span className="label">{p.name === 'FREE' ? 'Tier 0' : p.name === 'PRO' ? 'Tier 1' : 'Tier 2'}</span>
                {featured && <span className="rounded-[3px] bg-accent px-1.5 py-0.5 font-mono text-[10px] font-medium uppercase tracking-wider text-[var(--on-accent)]">Most popular</span>}
              </div>
              <h2 className="relative mt-3 text-xl font-medium text-ink">{p.label}</h2>
              <div className="relative mt-4 font-mono text-4xl font-medium tracking-tight text-ink">${p.monthlyPriceUsd}<span className="ml-1 font-sans text-sm font-normal text-muted">/month</span></div>
              <ul className="relative mt-7 flex-1 space-y-3 border-t border-line pt-6 text-sm text-ink-2">
                {FEATURES(p).map((f) => <li key={f} className="flex gap-2.5"><Check size={16} weight="bold" className="mt-0.5 shrink-0 text-accent-ink" />{f}</li>)}
              </ul>
              {user ? (
                <Button className="relative mt-8 h-10" variant={current ? 'secondary' : featured ? 'accent' : 'primary'} disabled={current || checkout.isPending} onClick={() => checkout.mutate(p.name)}>
                  {current ? 'Current plan' : `Switch to ${p.label}`}
                </Button>
              ) : <Link to="/register" className="relative mt-8"><Button className="h-10 w-full" variant={featured ? 'accent' : 'secondary'}>Start free</Button></Link>}
            </div>
          )
        })}
      </div>
      {checkout.data && <p className="text-sm text-good-text">{checkout.data.message}</p>}
      {checkout.error && <ErrorState error={checkout.error} />}
      <p className="max-w-3xl text-xs leading-relaxed text-muted">Demo billing: plan changes take effect immediately and no payment is collected. Enterprise adds SSO, custom universes and an SLA in a production deployment.</p>
    </div>
  )
}

// ------------------------------------------------------------------------------------------- account
export function Account() {
  const { me, plan } = useAuth()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [secret, setSecret] = useState(null)
  const [copied, setCopied] = useState(false)
  const keys = useQuery({ queryKey: ['api-keys'], queryFn: () => api.get('/me/api-keys') })
  const create = useMutation({ mutationFn: () => api.post('/me/api-keys', { name: name || 'default' }), onSuccess: (d) => { setSecret(d.secret); setName(''); qc.invalidateQueries({ queryKey: ['api-keys'] }) } })
  const revoke = useMutation({ mutationFn: (id) => api.del(`/me/api-keys/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ['api-keys'] }) })
  if (!me) return <Skeleton className="h-64" />
  return (
    <div className="space-y-8">
      <PageHeader title="Account" />
      <div className="stagger grid gap-3 sm:grid-cols-4">
        <StatTile label="Plan" value={plan.label} hint={<Link to="/pricing" className="link">Change plan</Link>} />
        <StatTile label="Analyses today" value={`${me.usage.analysesToday} / ${plan.analysesPerDay}`} />
        <StatTile label="API calls today" value={plan.apiCallsPerDay ? `${me.usage.apiCallsToday} / ${fmtNum(plan.apiCallsPerDay)}` : 'Not included'} />
        <StatTile label="Exports today" value={me.usage.exportsToday} />
      </div>
      <Card title="API keys" subtitle="Send as the X-API-Key header. Docs: /api/swagger-ui">
        {plan.maxApiKeys === 0 ? <EmptyState icon={KeyRound} title="API access is a Pro feature" action={<Link to="/pricing"><Button>Upgrade</Button></Link>} /> : (
          <>
            <form onSubmit={(e) => { e.preventDefault(); create.mutate() }} className="flex gap-2">
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Key name (e.g. research notebook)" aria-label="Key name" className="field h-8 flex-1" />
              <Button type="submit" disabled={create.isPending}><KeyRound size={15} /> Create key</Button>
            </form>
            {create.error && <div className="mt-3"><ErrorState error={create.error} /></div>}
            {secret && (
              <div className="mt-4 rounded-md border border-accent/25 bg-accent-soft/60 p-4 text-sm animate-rise">
                <div className="font-medium text-ink">Copy this key now - it is shown only once.</div>
                <div className="mt-2 flex items-center gap-2"><code className="flex-1 break-all font-mono text-xs text-ink">{secret}</code>
                  <Button variant="secondary" onClick={() => { navigator.clipboard?.writeText(secret); setCopied(true) }}>{copied ? <Check size={15} /> : <Copy size={15} />}</Button></div>
              </div>
            )}
            <ul className="mt-4 divide-y divide-line">
              {(keys.data || []).map((k) => (
                <li key={k.id} className={`flex items-center justify-between py-2 text-sm ${k.active ? '' : 'opacity-50'}`}>
                  <span><b className="font-medium text-ink">{k.name}</b> <code className="font-mono text-xs text-muted">{k.prefix}...</code></span>
                  <span className="flex items-center gap-3 text-xs text-muted">
                    {k.lastUsedAt ? `last used ${new Date(k.lastUsedAt).toLocaleString()}` : 'never used'}
                    {k.active ? <button onClick={() => revoke.mutate(k.id)} aria-label={`Revoke ${k.name}`} className="text-muted hover:text-critical"><Trash2 size={15} /></button> : 'revoked'}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>
    </div>
  )
}

// ------------------------------------------------------------------------------------------- admin
export function Admin() {
  const qc = useQueryClient()
  const users = useQuery({ queryKey: ['admin-users'], queryFn: () => api.get('/admin/users') })
  const jobs = useQuery({ queryKey: ['admin-jobs'], queryFn: () => api.get('/admin/jobs'), refetchInterval: 5000 })
  const monitoring = useQuery({ queryKey: ['admin-monitoring'], queryFn: () => api.get('/admin/monitoring') })
  const retrainJobs = useQuery({ queryKey: ['retrain'], queryFn: () => api.get('/admin/retrain'), refetchInterval: 5000 })
  const runMonitoring = useMutation({ mutationFn: () => api.post('/admin/monitoring/run'), onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-monitoring'] }) })
  const retrain = useMutation({ mutationFn: (model) => api.post('/admin/retrain', { model, promote: true }), onSuccess: () => qc.invalidateQueries({ queryKey: ['retrain'] }) })
  const setPlan = useMutation({ mutationFn: ({ id, plan }) => api.patch(`/admin/users/${id}`, { plan }), onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-users'] }) })
  const m = monitoring.data
  return (
    <div className="space-y-8">
      <PageHeader eyebrow="Operations" title="Admin and MLOps">Drift monitoring, retraining through the promotion gate, analysis jobs and user plans.</PageHeader>
      <div className="stagger grid gap-4 lg:grid-cols-2">
        <Card title="Drift & freshness monitoring" subtitle="PSI of live model inputs vs the training distribution (alert > 0.2)"
              action={<Button variant="secondary" onClick={() => runMonitoring.mutate()} disabled={runMonitoring.isPending}>Run now</Button>}>
          {runMonitoring.error && <ErrorState error={runMonitoring.error} />}
          {!m || m.status ? <p className="text-sm text-ink-2">{m?.status || 'Loading...'}</p> : (
            <div className="space-y-2 text-sm">
              <p className="text-ink-2">{m.rows} inferences in the last {m.window_days} days - generated {new Date(m.generated_at).toLocaleString()}</p>
              {Object.entries(m.models).map(([name, e]) => (
                <div key={name} className="rounded-md border border-line p-3.5">
                  <div className="flex justify-between"><b className="text-ink">{name}</b><span className="text-ink-2">{e.status}</span></div>
                  {e.psi && <div className="mt-1 text-xs text-ink-2">Top PSI: {Object.entries(e.psi).slice(0, 4).map(([f, v]) => `${f} ${Number(v).toFixed(3)}`).join(', ')}</div>}
                </div>
              ))}
              <p className="text-xs text-ink-2">Retraining recommended for: {m.retrain_recommended.length ? m.retrain_recommended.join(', ') : 'none'}</p>
            </div>
          )}
        </Card>
        <Card title="Retraining" subtitle="Runs the training pipeline; the promotion gate decides whether the new version becomes champion">
          <div className="flex flex-wrap gap-2">
            {['distress', 'financial_anomaly', 'peer_clusters', 'revenue_forecast', 'ocf_forecast', 'market_anomaly', 'news_sentiment', 'review_sentiment'].map((name) => (
              <Button key={name} variant="secondary" onClick={() => retrain.mutate(name)}>{name.replaceAll('_', ' ')}</Button>
            ))}
          </div>
          {retrain.error && <div className="mt-3"><ErrorState error={retrain.error} /></div>}
          <ul className="mt-4 space-y-1 text-xs text-ink-2">
            {(retrainJobs.data || []).map((j) => <li key={j.id}>{j.model}: <b className="text-ink">{j.status}</b>{j.champion_version ? ` - champion v${j.champion_version}` : ''}</li>)}
          </ul>
        </Card>
      </div>
      <Card title="Recent analysis jobs" bodyClass="overflow-x-auto p-0">
        <table className="w-full min-w-[640px] text-sm">
          <tbody>{(jobs.data || []).map((j) => (
            <tr key={j.id} className="border-b border-line last:border-0"><td className="px-5 py-2 text-ink">{j.company}</td><td className="px-2 py-2 text-ink-2">{j.asOf}</td>
              <td className="px-2 py-2 text-ink-2">{j.status}</td><td className="px-2 py-2 text-xs text-muted">{new Date(j.createdAt).toLocaleString()}</td><td className="px-5 py-2 text-xs text-critical">{j.error}</td></tr>
          ))}</tbody>
        </table>
      </Card>
      <Card title="Users" bodyClass="overflow-x-auto p-0">
        <table className="w-full min-w-[640px] text-sm">
          <tbody>{(users.data || []).map((u) => (
            <tr key={u.id} className="border-b border-line last:border-0"><td className="px-5 py-2 text-ink">{u.email}</td><td className="px-2 py-2 text-ink-2">{u.role}</td>
              <td className="px-2 py-2"><select value={u.plan} onChange={(e) => setPlan.mutate({ id: u.id, plan: e.target.value })} aria-label={`Plan of ${u.email}`} className="field h-8 w-auto py-0">
                {['FREE', 'PRO', 'ENTERPRISE'].map((p) => <option key={p}>{p}</option>)}</select></td>
              <td className="px-5 py-2 text-xs text-muted">{new Date(u.createdAt).toLocaleDateString()}</td></tr>
          ))}</tbody>
        </table>
      </Card>
    </div>
  )
}

export function NotFound() {
  return (
    <div className="py-16">
      <EmptyState title="Page not found" action={<Link to="/"><Button>Back to the home page</Button></Link>}>
        This address does not match any page. Search for a company from the home page instead.
      </EmptyState>
    </div>
  )
}
