// Chart components. Rules (dataviz skill): one y-axis per chart, thin marks, hairline grid, 4px rounded bar
// ends, hover tooltips everywhere, legends for >= 2 series, colours from the validated palette tokens.
import {
  Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Scatter, Tooltip, XAxis, YAxis,
} from 'recharts'
import { BANDS, fmtDate, fmtMoney, fmtShortDate, fmtSigned } from '../utils/format'
import { CountUp } from './motion'
import { ChartTooltip } from './ui'

const AXIS = { tickLine: false, axisLine: false, tick: { fontSize: 11 } }

/** Ring gauge for the 0-100 health score (Stitch dossier). The arc colour is the band's status colour, the number
    is ink; the arc draws in and the number counts up on mount (static under reduced motion). */
export function ScoreGauge({ score, band, size = 168 }) {
  const meta = BANDS[band] || BANDS.INSUFFICIENT_DATA
  const c = size / 2
  const r = size / 2 - 8
  const value = score == null ? 0 : Math.max(0, Math.min(100, score))
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" className="shrink-0"
         aria-label={score == null ? 'Health score unavailable' : `Health score ${score} of 100, ${meta.label}`}>
      <circle cx={c} cy={c} r={r} fill="none" stroke="var(--line-strong)" strokeWidth={6} />
      {[25, 40, 55, 70].map((t) => {
        const a = (t / 100) * 2 * Math.PI - Math.PI / 2
        return <line key={t} x1={c + (r - 9) * Math.cos(a)} y1={c + (r - 9) * Math.sin(a)} x2={c + (r - 14) * Math.cos(a)} y2={c + (r - 14) * Math.sin(a)} stroke="var(--axis)" strokeWidth={1} />
      })}
      {score != null && value > 0 && (
        <circle cx={c} cy={c} r={r} fill="none" stroke={meta.color} strokeWidth={6} strokeLinecap="round" pathLength={100}
                transform={`rotate(-90 ${c} ${c})`} strokeDasharray={`${value} 200`}
                style={{ '--gauge-from': value, animation: 'gauge 1.4s var(--ease-fluid) both' }} />
      )}
      <text x={c} y={c + 4} textAnchor="middle" fontSize={size * 0.26} fontWeight={500} letterSpacing="-0.03em" fill="var(--ink)" fontFamily="var(--font-mono)" className="tabular">
        {score == null ? '-' : <CountUp as="tspan" value={score} duration={1400} />}
      </text>
      <text x={c} y={c + size * 0.17} textAnchor="middle" fontSize={11} letterSpacing="0.1em" fill="var(--muted)" fontFamily="var(--font-mono)">/ 100</text>
    </svg>
  )
}

const ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI']
const pillarTag = (score) => (score >= 70 ? ['Strong', 'var(--good)'] : score >= 55 ? ['Stable', 'var(--good)'] : score >= 40 ? ['Watch', 'var(--warning)'] : score >= 25 ? ['Weak', 'var(--serious)'] : ['Critical', 'var(--critical)'])

/** Pillar cards (Stitch "sub-pillar breakdown"): one series, one colour; unavailable pillars are listed, never drawn as 0. */
export function PillarBars({ pillars, context = {} }) {
  return (
    <ul className="stagger grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {pillars.map((p, i) => {
        const [tag, color] = p.score != null ? pillarTag(p.score) : ['Not scored', 'var(--muted)']
        return (
          <li key={p.key} className="card flex flex-col p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="label">Pillar {ROMAN[i]}</span>
              <span className="rounded-[3px] px-1.5 py-px font-mono text-[10px] font-medium uppercase tracking-wider text-ink"
                    style={{ background: `color-mix(in oklab, ${color} 16%, transparent)` }}>{tag}</span>
            </div>
            <div className="mt-3 text-[15px] font-semibold leading-snug text-ink">{p.label}</div>
            <div className="mt-1 font-mono text-[11px] text-muted">
              weight {Math.round((p.effective_weight || 0) * 100)}%
              {p.score != null && p.coverage != null && (
                <> // <span className={p.coverage < 0.5 ? 'text-serious' : ''} title="Share of this pillar's evidence that is available and fresh">coverage {Math.round(p.coverage * 100)}%</span></>
              )}
            </div>
            {context[p.key] && <div className="mt-0.5 font-mono text-[11px] text-muted">{context[p.key]}</div>}
            {p.score != null ? (
              <>
                <div className="mt-auto flex items-baseline justify-between pt-5">
                  <span className="font-mono text-3xl font-medium tracking-tight text-ink tabular">{p.score.toFixed(1)}</span>
                  <span className="font-mono text-[11px] text-muted">/ 100</span>
                </div>
                <div className="mt-2 h-1 overflow-hidden rounded-[2px] bg-surface-3" title={`${p.label}: ${p.score.toFixed(1)} / 100`}>
                  <div className="grow-x h-full" style={{ width: `${p.score}%`, background: 'var(--series-1)', animationDelay: `${200 + i * 90}ms` }} />
                </div>
              </>
            ) : (
              <div className="mt-auto pt-5 text-xs leading-relaxed text-muted">Not scored - {p.unavailable_reason}</div>
            )}
          </li>
        )
      })}
    </ul>
  )
}

/** Diverging bars: each factor's exact contribution to the score (points vs a neutral 50). */
export function ImpactChart({ factors, height }) {
  const data = [...factors].sort((a, b) => a.impact - b.impact).map((f) => ({ ...f, name: f.label }))
  const h = height || Math.max(160, data.length * 30 + 40)
  return (
    <ResponsiveContainer width="100%" height={h}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 4 }} barCategoryGap={6}>
        <CartesianGrid horizontal={false} />
        <XAxis type="number" {...AXIS} tickFormatter={(v) => fmtSigned(v, 0)} />
        <YAxis type="category" dataKey="name" width={210} {...AXIS} tick={{ fontSize: 11, fill: 'var(--ink-2)' }} />
        <ReferenceLine x={0} stroke="var(--axis)" />
        <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip formatter={(v, k, row) => `${fmtSigned(v, 2)} pts${row.display_value ? `  (value ${row.display_value})` : ''}`} />} />
        <Bar dataKey="impact" name="Impact on score" radius={4}>
          {data.map((d) => <Cell key={d.key} fill={d.impact >= 0 ? 'var(--div-pos)' : 'var(--div-neg)'} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** SHAP drivers of the distress model: red raises estimated risk, blue lowers it. */
export function DriverChart({ drivers }) {
  const data = [...drivers].sort((a, b) => b.contribution - a.contribution).map((d) => ({ ...d, name: d.label }))
  return (
    <ResponsiveContainer width="100%" height={Math.max(160, data.length * 30 + 40)}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 4 }} barCategoryGap={6}>
        <CartesianGrid horizontal={false} />
        <XAxis type="number" {...AXIS} tickFormatter={(v) => fmtSigned(v, 1)} />
        <YAxis type="category" dataKey="name" width={220} {...AXIS} tick={{ fontSize: 11, fill: 'var(--ink-2)' }} />
        <ReferenceLine x={0} stroke="var(--axis)" />
        <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip formatter={(v, k, row) => `${fmtSigned(v, 3)} log-odds (value ${row.value == null ? 'n/a' : Number(row.value).toPrecision(3)})`} />} />
        <Bar dataKey="contribution" name="SHAP contribution" radius={4}>
          {data.map((d) => <Cell key={d.feature} fill={d.contribution >= 0 ? 'var(--div-neg)' : 'var(--div-pos)'} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Quarterly history (bars) + forecast median (line) and 80% interval (band) on one axis. */
export function ForecastChart({ forecast, height = 260 }) {
  const hist = forecast.history.map((h) => ({ date: h.period_end, actual: h.value }))
  const last = hist[hist.length - 1]
  const fc = forecast.points.map((p) => ({ date: p.period_end, p50: p.p50, band: [p.p10, p.p90] }))
  const data = [...hist, ...(last ? [{ date: last.date, p50: last.actual, band: [last.actual, last.actual], bridge: true }] : []), ...fc]
    .sort((a, b) => a.date.localeCompare(b.date))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ left: 4, right: 12, top: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="date" {...AXIS} tickFormatter={fmtShortDate} minTickGap={24} />
        <YAxis {...AXIS} tickFormatter={fmtMoney} width={64} />
        <Tooltip content={<ChartTooltip labelFormatter={fmtDate} formatter={(v) => (Array.isArray(v) ? `${fmtMoney(v[0])} - ${fmtMoney(v[1])}` : fmtMoney(v))} />} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Bar dataKey="actual" name="Reported" fill="var(--series-1)" radius={[4, 4, 0, 0]} maxBarSize={22} />
        <Area dataKey="band" name="80% interval" stroke="none" fill="var(--band)" fillOpacity={0.6} isAnimationActive={false} />
        <Line dataKey="p50" name="Forecast (median)" stroke="var(--series-2)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** One-series line over time (price, a balance item, ...). */
export function SeriesLine({ data, x = 'date', y, name, format = (v) => v, height = 220, color = 'var(--series-1)' }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ left: 4, right: 12, top: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={x} {...AXIS} tickFormatter={fmtShortDate} minTickGap={32} />
        <YAxis {...AXIS} tickFormatter={format} width={64} domain={['auto', 'auto']} />
        <Tooltip content={<ChartTooltip labelFormatter={fmtDate} formatter={(v) => format(v)} />} />
        <Line dataKey={y} name={name} stroke={color} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
      </LineChart>
    </ResponsiveContainer>
  )
}

/** Single-series bars (quarterly values, article counts). */
export function SeriesBars({ data, x, y, name, format = (v) => v, height = 200, signed = false }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ left: 4, right: 12, top: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey={x} {...AXIS} tickFormatter={fmtShortDate} minTickGap={24} />
        <YAxis {...AXIS} tickFormatter={format} width={64} />
        {signed && <ReferenceLine y={0} stroke="var(--axis)" />}
        <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip labelFormatter={fmtDate} formatter={(v) => format(v)} />} />
        <Bar dataKey={y} name={name} radius={4} maxBarSize={22}>
          {data.map((d, i) => <Cell key={i} fill={signed && d[y] < 0 ? 'var(--div-neg)' : 'var(--series-1)'} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Daily mean headline sentiment (-1..+1) with a zero reference; volume is a separate chart (never dual-axis). */
export function SentimentChart({ data, height = 220 }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ left: 4, right: 12, top: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="date" {...AXIS} tickFormatter={fmtShortDate} minTickGap={32} />
        <YAxis {...AXIS} domain={[-1, 1]} ticks={[-1, -0.5, 0, 0.5, 1]} width={40} />
        <ReferenceLine y={0} stroke="var(--axis)" />
        <Tooltip content={<ChartTooltip labelFormatter={fmtDate} formatter={(v, k, row) => `${fmtSigned(v, 2)} (${row.articles} headlines)`} />} />
        <Line dataKey="sentiment" name="Mean headline sentiment" stroke="var(--series-1)" strokeWidth={2} dot={{ r: 2 }} activeDot={{ r: 4 }} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** Score history: LIVE reports (slot 1) and point-in-time BACKFILL partial scores (slot 2), one 0-100 axis. */
export function HistoryChart({ points, height = 260 }) {
  const data = points.map((p) => ({ date: p.asOf, live: p.source === 'LIVE' ? p.healthScore : null, backfill: p.source === 'BACKFILL' ? p.healthScore : null }))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data} margin={{ left: 4, right: 12, top: 8, bottom: 0 }}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="date" {...AXIS} tickFormatter={fmtShortDate} minTickGap={24} />
        <YAxis {...AXIS} domain={[0, 100]} ticks={[0, 25, 40, 55, 70, 100]} width={36} />
        <ReferenceLine y={55} stroke="var(--line)" />
        <ReferenceLine y={40} stroke="var(--line)" />
        <Tooltip content={<ChartTooltip labelFormatter={fmtDate} />} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line dataKey="backfill" name="Point-in-time (financial + events)" stroke="var(--series-2)" strokeWidth={2} dot={{ r: 3 }} connectNulls />
        <Scatter dataKey="live" name="Full report" fill="var(--series-1)" shape="circle" />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

/** Grouped bars: pillar scores per company (categorical slots in selection order; legend + table view). */
export function CompareChart({ rows, companies, height = 300 }) {
  const slots = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)']
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={rows} margin={{ left: 4, right: 12, top: 8, bottom: 0 }} barGap={2}>
        <CartesianGrid vertical={false} />
        <XAxis dataKey="pillar" {...AXIS} tick={{ fontSize: 11, fill: 'var(--ink-2)' }} />
        <YAxis {...AXIS} domain={[0, 100]} width={36} />
        <Tooltip cursor={{ fill: 'var(--surface-2)' }} content={<ChartTooltip formatter={(v) => Math.round(v)} />} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {companies.map((c, i) => (
          <Bar key={c.id} dataKey={`c${c.id}`} name={c.ticker || c.name} fill={slots[i % slots.length]} radius={[4, 4, 0, 0]} maxBarSize={28} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}
