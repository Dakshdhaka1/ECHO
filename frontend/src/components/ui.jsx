import { useLayoutEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { BANDS, KIND_HELP, SEVERITY } from '../utils/format'
import { AlertTriangle, ArrowUpRight, CheckCircle2, CircleHelp, Eye, Lock, RefreshCw, XCircle } from './icons'

/** Analytical module: hairline frame, optional 36px header strip (title, metadata, action). */
export function Card({ title, subtitle, action, children, className = '', bodyClass }) {
  const hasHeader = title || action
  return (
    <section className={`card animate-rise ${className}`}>
      {hasHeader && (
        <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 border-b border-line px-5 py-3">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs leading-relaxed text-muted">{subtitle}</p>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </header>
      )}
      <div className={bodyClass ?? 'p-5'}>{children}</div>
    </section>
  )
}

/** Mono micro-label, optionally with a trailing rule (the Stitch "CORE CAPABILITIES ---" eyebrow). */
export function Label({ children, rule = false, className = '' }) {
  return (
    <span className={`label inline-flex items-center gap-3 ${className}`}>
      {children}
      {rule && <span className="h-px w-8 bg-line-strong" aria-hidden />}
    </span>
  )
}

/** Page title block: mono eyebrow, headline, description below, optional action on the right. */
export function PageHeader({ eyebrow, title, children, action }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4 border-b border-line pb-6 animate-rise">
      <div className="max-w-3xl">
        {eyebrow && <Label rule>{eyebrow}</Label>}
        <h1 className={`text-3xl font-light tracking-[-0.02em] text-ink md:text-4xl ${eyebrow ? 'mt-3' : ''}`}>{title}</h1>
        {children && <p className="mt-2 text-sm leading-relaxed text-ink-2">{children}</p>}
      </div>
      {action}
    </div>
  )
}

export function Button({ variant = 'primary', className = '', ...props }) {
  const styles = {
    primary: 'border border-primary bg-primary text-on-primary hover:opacity-90',
    accent: 'border border-accent bg-accent text-[var(--on-accent)] hover:brightness-110',
    inverse: 'border border-on-primary bg-on-primary text-primary hover:opacity-90',
    secondary: 'border border-line-strong bg-surface text-ink hover:border-muted hover:bg-surface-2',
    ghost: 'border border-transparent text-ink-2 hover:bg-surface-2 hover:text-ink',
    danger: 'border border-line-strong bg-surface text-critical hover:border-critical/50',
  }
  return (
    <button
      className={`inline-flex h-8 items-center justify-center gap-2 whitespace-nowrap rounded-[5px] px-3.5 text-[13px] font-medium transition duration-200 ease-fluid active:translate-y-px disabled:pointer-events-none disabled:opacity-45 ${styles[variant]} ${className}`}
      {...props}
    />
  )
}

const BAND_ICONS = { up: ArrowUpRight, check: CheckCircle2, eye: Eye, alert: AlertTriangle, x: XCircle, help: CircleHelp }

export function BandBadge({ band, size = 'sm' }) {
  const meta = BANDS[band] || BANDS.INSUFFICIENT_DATA
  const Icon = BAND_ICONS[meta.icon]
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-[4px] font-mono font-medium uppercase tracking-[0.06em] text-ink ${size === 'lg' ? 'h-7 px-2.5 text-xs' : 'h-5 px-1.5 text-[10.5px]'}`}
      style={{ background: `color-mix(in oklab, ${meta.color} 16%, transparent)`, boxShadow: `inset 0 0 0 1px color-mix(in oklab, ${meta.color} 30%, transparent)` }}
    >
      <Icon size={size === 'lg' ? 14 : 12} weight="bold" style={{ color: meta.color }} aria-hidden />
      {meta.label}
    </span>
  )
}

export function KindBadge({ kind }) {
  return (
    <span title={KIND_HELP[kind]} className="rounded-[3px] border border-line-strong px-1.5 py-px font-mono text-[10px] font-medium uppercase tracking-wider text-ink-2">
      {kind}
    </span>
  )
}

export function SeverityDot({ severity }) {
  const meta = SEVERITY[severity] || SEVERITY.LOW
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-2">
      <span className="status-dot h-2 w-2 rounded-full" style={{ background: meta.color }} aria-hidden />
      {meta.label}
    </span>
  )
}

export function StatTile({ label, value, hint, tone }) {
  const numeric = /^[-+$]?\d/.test(String(value))
  return (
    <div className="rounded-md border border-line bg-surface-2/60 p-4 transition-colors duration-200 hover:border-line-strong">
      <div className="label">{label}</div>
      <div className={`mt-2 text-2xl text-ink tabular ${numeric ? 'font-mono font-medium tracking-tight' : 'font-semibold'}`} style={tone ? { color: tone } : undefined}>{value}</div>
      {hint && <div className="mt-1 text-xs text-ink-2">{hint}</div>}
    </div>
  )
}

export function Skeleton({ className = '' }) {
  return <div className={`skeleton ${className}`} aria-hidden />
}

export function EmptyState({ icon: Icon = CircleHelp, title, children, action }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-md border border-dashed border-line-strong px-6 py-12 text-center animate-rise">
      <span className="float grid h-11 w-11 place-items-center rounded-md border border-line-strong bg-surface-2 text-accent-ink">
        <Icon size={20} aria-hidden />
      </span>
      <h3 className="mt-4 text-sm font-semibold text-ink">{title}</h3>
      {children && <p className="mt-1.5 max-w-md text-sm leading-relaxed text-ink-2">{children}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  if (error?.isPlanLimit) return <UpgradePrompt message={error.message} />
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border border-critical/30 bg-critical/[0.06] p-4 animate-rise">
      <XCircle className="mt-0.5 shrink-0" size={18} weight="fill" style={{ color: 'var(--critical)' }} aria-hidden />
      <div className="flex-1">
        <div className="text-sm font-semibold text-ink">Something went wrong</div>
        <div className="mt-0.5 text-sm text-ink-2">{error?.message || 'Unexpected error'}</div>
      </div>
      {onRetry && <Button variant="secondary" onClick={onRetry}><RefreshCw size={14} /> Retry</Button>}
    </div>
  )
}

export function UpgradePrompt({ message }) {
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-md border border-line bg-surface p-4 animate-rise">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md bg-accent-soft text-accent-ink"><Lock size={17} weight="bold" aria-hidden /></span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-ink">Available on a higher plan</div>
        <div className="mt-0.5 text-sm text-ink-2">{message}</div>
      </div>
      <Link to="/pricing"><Button>See plans</Button></Link>
    </div>
  )
}

/** Underline tabs; the emerald indicator glides between tabs (transform only). */
export function Tabs({ tabs, active, onChange }) {
  const list = useRef(null)
  const [bar, setBar] = useState(null)
  useLayoutEffect(() => {
    const el = list.current?.querySelector('[aria-selected="true"]')
    if (el) setBar({ x: el.offsetLeft, w: el.offsetWidth })
  }, [active, tabs.length])
  return (
    <div ref={list} role="tablist" className="relative flex gap-1 overflow-x-auto border-b border-line [scrollbar-width:none]">
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          aria-selected={active === t.key}
          onClick={() => onChange(t.key)}
          className={`whitespace-nowrap px-3 pb-3 pt-2 text-[13px] font-medium transition-colors duration-200 ${active === t.key ? 'text-ink' : 'text-muted hover:text-ink'}`}
        >
          {t.label}
          {t.count != null && <span className="ml-1.5 rounded-[3px] bg-surface-3 px-1.5 font-mono text-[10.5px] text-ink-2">{t.count}</span>}
        </button>
      ))}
      {bar && (
        <span aria-hidden className="absolute bottom-0 left-0 h-[2px] w-px origin-left bg-accent transition-transform duration-500 ease-spring"
              style={{ transform: `translateX(${bar.x}px) scaleX(${bar.w})` }} />
      )}
    </div>
  )
}

/** Recharts tooltip in the app's surface style (text in ink tokens, never the series colour). */
export function ChartTooltip({ active, payload, label, formatter = (v) => v, labelFormatter = (l) => l }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-md border border-line-strong bg-surface px-3 py-2 text-xs shadow-[var(--shadow-pop)]">
      <div className="mb-1 font-mono text-[11px] text-muted">{labelFormatter(label)}</div>
      {payload.filter((p) => p.value != null).map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-ink-2">
          <span className="h-2 w-2 rounded-[2px]" style={{ background: p.color || p.stroke || p.fill }} aria-hidden />
          <span>{p.name}</span>
          <span className="ml-auto pl-3 font-mono font-medium text-ink tabular">{formatter(p.value, p.dataKey, p.payload)}</span>
        </div>
      ))}
    </div>
  )
}

export function Disclaimer({ text }) {
  return (
    <p className="max-w-3xl text-xs leading-relaxed text-muted">
      {text || 'ECHO reports observable public signals and model estimates. It is not financial advice and does not predict with certainty whether a company will succeed or fail.'}
    </p>
  )
}
