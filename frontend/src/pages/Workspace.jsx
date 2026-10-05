import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { CompareChart } from '../components/charts'
import SearchBox from '../components/SearchBox'
import { Bell, CheckCheck, Eye, GitCompare, Plus, Search, Trash2, X } from '../components/icons'
import { BandBadge, Button, Card, EmptyState, ErrorState, PageHeader, SeverityDot, Skeleton } from '../components/ui'
import { useAuth } from '../context/AuthContext'
import { api } from '../services/api'
import { fmtDate, fmtPct, PILLAR_ORDER } from '../utils/format'

// ------------------------------------------------------------------------------------------- search
export function SearchResults() {
  const [params] = useSearchParams()
  const q = params.get('q') || ''
  const results = useQuery({ queryKey: ['search', q], queryFn: () => api.get(`/companies/search?q=${encodeURIComponent(q)}`), enabled: q.length >= 2 })
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title={`Results for "${q}"`} />
      <SearchBox />
      {results.isLoading && <Skeleton className="h-40" />}
      {results.error && <ErrorState error={results.error} />}
      {results.data?.length === 0 && <EmptyState icon={Search} title="No matching SEC filer">ECHO covers companies that file with the US SEC.</EmptyState>}
      <ul className="stagger space-y-2">
        {(results.data || []).map((r) => (
          <li key={r.company.id}>
            <Link to={`/company/${r.company.id}`} className="card flex items-center justify-between px-5 py-4 transition duration-300 hover:-translate-y-0.5">
              <div>
                <div className="font-medium text-ink">{r.company.name}</div>
                <div className="text-xs text-muted">CIK {Number(r.company.marketId)}{r.formerNames?.length ? ` - formerly ${r.formerNames.join(', ')}` : ''}</div>
              </div>
              <span className="font-mono text-sm font-medium text-ink-2">{r.company.ticker}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ------------------------------------------------------------------------------------------- compare
const CHART_MAX = 4  // the validated palette has 4 distinct slots for this chart; more companies -> table only

export function Compare() {
  const [params, setParams] = useSearchParams()
  const ids = (params.get('ids') || '').split(',').filter(Boolean)
  const data = useQuery({ queryKey: ['compare', ids.join(',')], queryFn: () => api.get(`/compare?ids=${ids.join(',')}`), enabled: ids.length > 0 })
  const setIds = (next) => { next.length ? params.set('ids', next.join(',')) : params.delete('ids'); setParams(params) }
  const items = data.data || []
  const companies = items.map((i) => i.company)
  const rows = PILLAR_ORDER.map((key) => {
    const row = { pillar: items[0]?.pillars?.find?.((p) => p.key === key)?.label || key }
    items.forEach((i) => { row[`c${i.company.id}`] = (i.pillars || []).find((p) => p.key === key)?.score ?? null })
    return row
  })
  const missing = items.filter((i) => !i.reportId)

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Workspace // compare" title="Compare companies"
                  action={<div className="w-full max-w-md"><SearchBox onPick={(c) => !ids.includes(String(c.id)) && setIds([...ids, String(c.id)])} /></div>}>
        Pillar scores side by side, each from the company's latest report.
      </PageHeader>
      {ids.length === 0 && <EmptyState icon={GitCompare} title="Pick companies to compare">Search above to add companies. Free: 2, Pro: 4, Enterprise: 8.</EmptyState>}
      {data.error && <ErrorState error={data.error} />}
      {data.isLoading && <Skeleton className="h-80" />}
      {missing.length > 0 && (
        <p className="text-sm text-ink-2">No report yet for {missing.map((m) => <Link key={m.company.id} className="link" to={`/company/${m.company.id}`}>{m.company.name} </Link>)} - open it once to generate one.</p>
      )}
      {items.length > 0 && (
        <>
          {items.length <= CHART_MAX ? (
            <Card title="Pillar scores" subtitle="0-100 per pillar; missing pillars are not drawn"><CompareChart rows={rows} companies={companies} /></Card>
          ) : <p className="text-sm text-ink-2">More than {CHART_MAX} companies: shown as a table only, so every company keeps a distinguishable colour.</p>}
          <Card title="Side by side" bodyClass="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm tabular">
              <thead><tr className="border-b border-line text-left text-xs text-muted">
                <th className="px-5 py-2 font-medium">Company</th><th className="px-2 py-2 font-medium">Score</th><th className="px-2 py-2 font-medium">Band</th>
                <th className="px-2 py-2 font-medium">Distress (ML)</th><th className="px-2 py-2 font-medium">Segment</th>
                {PILLAR_ORDER.map((k) => <th key={k} className="px-2 py-2 font-medium capitalize">{k}</th>)}
                <th className="px-2 py-2 font-medium">Signals</th><th /></tr></thead>
              <tbody>
                {items.map((i) => (
                  <tr key={i.company.id} className="border-b border-line last:border-0">
                    <td className="px-5 py-2"><Link to={`/company/${i.company.id}`} className="font-medium text-ink hover:underline">{i.company.name}</Link><div className="text-xs text-muted">{i.asOf ? `as of ${fmtDate(i.asOf)}` : 'no report'}</div></td>
                    <td className="px-2 py-2 font-mono font-medium text-ink">{i.healthScore ?? '-'}</td>
                    <td className="px-2 py-2">{i.band && <BandBadge band={i.band} />}</td>
                    <td className="px-2 py-2 text-ink-2">{i.distressProbability != null ? fmtPct(Number(i.distressProbability), 2) : '-'}</td>
                    <td className="px-2 py-2 text-ink-2">{i.segment?.segment || '-'}</td>
                    {PILLAR_ORDER.map((k) => { const p = (i.pillars || []).find((x) => x.key === k); return <td key={k} className="px-2 py-2 text-ink-2">{p?.score != null ? Math.round(p.score) : '-'}</td> })}
                    <td className="px-2 py-2 text-ink-2">{i.signals}</td>
                    <td className="px-2 py-2"><button aria-label={`Remove ${i.company.name}`} onClick={() => setIds(ids.filter((x) => x !== String(i.company.id)))} className="text-muted hover:text-ink"><X size={15} /></button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  )
}

// ------------------------------------------------------------------------------------------- watchlists
export function Watchlists() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { plan } = useAuth()
  const [name, setName] = useState('')
  const lists = useQuery({ queryKey: ['watchlists'], queryFn: () => api.get('/watchlists') })
  const done = () => qc.invalidateQueries({ queryKey: ['watchlists'] })
  const create = useMutation({ mutationFn: () => api.post('/watchlists', { name }), onSuccess: () => { setName(''); done() } })
  const add = useMutation({ mutationFn: ({ listId, companyId }) => api.post(`/watchlists/${listId}/items`, { companyId }), onSuccess: done })
  const remove = useMutation({ mutationFn: ({ listId, companyId }) => api.del(`/watchlists/${listId}/items/${companyId}`), onSuccess: done })
  const delList = useMutation({ mutationFn: (listId) => api.del(`/watchlists/${listId}`), onSuccess: done })
  const error = create.error || add.error || remove.error || delList.error

  if (lists.isLoading) return <Skeleton className="h-64" />
  if (lists.error) return <ErrorState error={lists.error} onRetry={lists.refetch} />
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Workspace // watchlists" title="Watchlists"
                  action={<form onSubmit={(e) => { e.preventDefault(); if (name.trim()) create.mutate() }} className="flex gap-2">
                    <input value={name} onChange={(e) => setName(e.target.value)} placeholder="New watchlist" className="field h-8 w-48" aria-label="New watchlist name" />
                    <Button type="submit" disabled={!name.trim()}><Plus size={15} /> Create</Button>
                  </form>}>
        Watched companies are re-analysed daily; a score drop at or above the threshold raises an alert. Plan: {plan?.maxWatchlists} list(s) x {plan?.maxWatchlistItems} companies.
      </PageHeader>
      {error && <ErrorState error={error} />}
      {lists.data.map((w) => (
        <Card key={w.id} title={w.name} subtitle={`${w.items.length} companies`}
              action={<div className="flex items-center gap-2"><div className="w-72"><SearchBox onPick={(c) => add.mutate({ listId: w.id, companyId: c.id })} /></div>
                {lists.data.length > 1 && <button onClick={() => delList.mutate(w.id)} aria-label="Delete watchlist" className="p-1 text-muted hover:text-critical"><Trash2 size={16} /></button>}</div>}
              bodyClass="p-0">
          {w.items.length === 0 ? <div className="p-5"><EmptyState icon={Eye} title="Empty watchlist">Search for a company above to start watching it.</EmptyState></div> : (
            <ul className="divide-y divide-line">
              {w.items.map((i) => (
                <li key={i.company.id} className="flex items-center gap-4 px-6 py-3.5 transition-colors duration-200 hover:bg-surface-2/50">
                  <button onClick={() => navigate(`/company/${i.company.id}`)} className="min-w-0 flex-1 text-left">
                    <div className="truncate font-medium text-ink">{i.company.name} <span className="font-mono text-xs text-muted">{i.company.ticker}</span></div>
                    <div className="text-xs text-muted">{i.asOf ? `latest report ${fmtDate(i.asOf)}` : 'no report yet'} - alert if the score drops {i.scoreDropThreshold}+ points</div>
                  </button>
                  <span className="font-mono text-lg font-medium text-ink tabular">{i.latestScore ?? '-'}</span>
                  {i.band && <BandBadge band={i.band} />}
                  <button onClick={() => remove.mutate({ listId: w.id, companyId: i.company.id })} aria-label={`Remove ${i.company.name}`} className="p-1 text-muted hover:text-critical"><X size={16} /></button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      ))}
      <p className="text-xs text-muted">Compare everything on this list: <Link className="link" to={`/compare?ids=${lists.data[0]?.items.slice(0, plan?.maxCompare || 2).map((i) => i.company.id).join(',')}`}>open comparison</Link></p>
    </div>
  )
}

// ------------------------------------------------------------------------------------------- alerts
export function Alerts() {
  const qc = useQueryClient()
  const { refresh } = useAuth()
  const alerts = useQuery({ queryKey: ['alerts'], queryFn: () => api.get('/alerts') })
  const read = useMutation({ mutationFn: (id) => api.patch(`/alerts/${id}/read`), onSuccess: () => { qc.invalidateQueries({ queryKey: ['alerts'] }); refresh() } })
  const readAll = useMutation({ mutationFn: () => api.post('/alerts/read-all'), onSuccess: () => { qc.invalidateQueries({ queryKey: ['alerts'] }); refresh() } })
  if (alerts.isLoading) return <Skeleton className="h-64" />
  if (alerts.error) return <ErrorState error={alerts.error} onRetry={alerts.refetch} />
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader eyebrow="Workspace // alerts" title="Alerts"
                  action={alerts.data.some((a) => !a.read) && <Button variant="secondary" onClick={() => readAll.mutate()}><CheckCheck size={15} /> Mark all read</Button>} />
      {alerts.data.length === 0 ? <EmptyState icon={Bell} title="No alerts yet">Add companies to a watchlist; alerts appear when a score drops or a new high-severity signal appears.</EmptyState> : (
        <Card bodyClass="p-0">
          <ul className="divide-y divide-line">
            {alerts.data.map((a) => (
              <li key={a.id} className={`flex items-start gap-3 px-6 py-3.5 transition-colors duration-200 hover:bg-surface-2/50 ${a.read ? 'opacity-60' : ''}`}>
                <div className="w-20 shrink-0 pt-0.5"><SeverityDot severity={a.severity} /></div>
                <div className="min-w-0 flex-1">
                  <Link to={`/company/${a.company.id}`} className="text-sm text-ink hover:underline">{a.message}</Link>
                  <div className="text-xs text-muted">{a.type.replaceAll('_', ' ')} - {new Date(a.createdAt).toLocaleString()}</div>
                </div>
                {!a.read && <button onClick={() => read.mutate(a.id)} className="link text-xs">Mark read</button>}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  )
}
