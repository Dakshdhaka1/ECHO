// Formatting helpers and the shared semantic maps (bands, severities, model kinds).

export const fmtPct = (v, digits = 1) => (v == null || Number.isNaN(v) ? '-' : `${(v * 100).toFixed(digits)}%`)
export const fmtNum = (v, digits = 0) => (v == null || Number.isNaN(v) ? '-' : Number(v).toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits }))
export const fmtSigned = (v, digits = 1) => (v == null ? '-' : `${v > 0 ? '+' : ''}${Number(v).toFixed(digits)}`)

export function fmtMoney(v) {
  if (v == null || Number.isNaN(v)) return '-'
  const a = Math.abs(v)
  const s = v < 0 ? '-' : ''
  if (a >= 1e12) return `${s}$${(a / 1e12).toFixed(2)}T`
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(2)}B`
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(1)}M`
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(1)}K`
  return `${s}$${a.toFixed(0)}`
}

export const fmtDate = (d) => (d ? new Date(`${String(d).slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : '-')
export const fmtShortDate = (d) => (d ? new Date(`${String(d).slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { month: 'short', year: '2-digit' }) : '')

// Health bands -> reserved status colours (always rendered with an icon + label, never colour alone).
export const BANDS = {
  STRONG: { label: 'Strong', color: 'var(--good)', icon: 'up' },
  STABLE: { label: 'Stable', color: 'var(--good)', icon: 'check' },
  WATCH: { label: 'Watch', color: 'var(--warning)', icon: 'eye' },
  WEAK: { label: 'Weak', color: 'var(--serious)', icon: 'alert' },
  CRITICAL: { label: 'Critical', color: 'var(--critical)', icon: 'x' },
  INSUFFICIENT_DATA: { label: 'Insufficient data', color: 'var(--muted)', icon: 'help' },
}

export const SEVERITY = {
  CRITICAL: { label: 'Critical', color: 'var(--critical)', rank: 0 },
  HIGH: { label: 'High', color: 'var(--serious)', rank: 1 },
  MEDIUM: { label: 'Medium', color: 'var(--warning)', rank: 2 },
  LOW: { label: 'Low', color: 'var(--muted)', rank: 3 },
}

export const RISK_BANDS = {
  LOW: { label: 'Low', color: 'var(--good)' },
  MODERATE: { label: 'Moderate', color: 'var(--warning)' },
  ELEVATED: { label: 'Elevated', color: 'var(--serious)' },
  HIGH: { label: 'High', color: 'var(--critical)' },
}

export const KIND_HELP = {
  ML: 'Output of a trained, evaluated machine-learning model',
  Stat: 'Documented statistical calculation (no training)',
  Rule: 'Deterministic rule (e.g. an SEC filing code mapping)',
}

// Human labels for snake_case identifiers (data sources, model names): sentence case, acronyms kept.
const ACRONYMS = { sec: 'SEC', xbrl: 'XBRL', gdelt: 'GDELT', ocf: 'OCF', ml: 'ML', api: 'API', esi: 'ESI' }
export const humanize = (key) => String(key || '').split('_').map((w, i) => ACRONYMS[w] || (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w)).join(' ')

export const PILLAR_ORDER = ['financial', 'market', 'news', 'workforce', 'events']
