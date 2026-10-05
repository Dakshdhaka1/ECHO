import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import { Search } from './icons'

/** Company search with debounced suggestions (names, tickers and former names via the SEC resolver). */
export default function SearchBox({ autoFocus = false, large = false, hotkey = false, onPick }) {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [debounced, setDebounced] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const box = useRef(null)
  const input = useRef(null)

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q.trim()), 250)
    return () => clearTimeout(t)
  }, [q])
  useEffect(() => {
    const close = (e) => box.current && !box.current.contains(e.target) && setOpen(false)
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])
  useEffect(() => {
    if (!hotkey) return undefined
    const focus = (e) => {
      if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) { e.preventDefault(); input.current?.focus() }
    }
    document.addEventListener('keydown', focus)
    return () => document.removeEventListener('keydown', focus)
  }, [hotkey])

  const results = useQuery({
    queryKey: ['search', debounced],
    queryFn: () => api.get(`/companies/search?q=${encodeURIComponent(debounced)}`),
    enabled: debounced.length >= 2,
    staleTime: 300_000,
  })
  const items = results.data || []

  const pick = (item) => {
    setOpen(false)
    setQ('')
    if (onPick) onPick(item.company)
    else navigate(`/company/${item.company.id}`)
  }
  const submit = () => {
    if (items[active]) pick(items[active])
    else if (q.trim().length >= 2 && !onPick) navigate(`/search?q=${encodeURIComponent(q.trim())}`)
    else input.current?.focus()
  }
  const onKey = (e) => {
    if (e.key === 'ArrowDown') { setActive((a) => Math.min(a + 1, items.length - 1)); e.preventDefault() }
    if (e.key === 'ArrowUp') { setActive((a) => Math.max(a - 1, 0)); e.preventDefault() }
    if (e.key === 'Enter') submit()
    if (e.key === 'Escape') setOpen(false)
  }

  return (
    <div ref={box} className="relative w-full">
      <label className={`group flex items-center gap-2.5 rounded-[5px] border border-line-strong bg-surface transition duration-200 hover:border-muted focus-within:border-accent focus-within:shadow-[0_0_0_1px_var(--accent)] ${large ? 'h-12 pl-4 pr-1.5' : 'h-8 px-2.5'}`}>
        <Search size={large ? 18 : 15} className="shrink-0 text-muted transition-colors group-focus-within:text-accent-ink" aria-hidden />
        <input
          ref={input}
          autoFocus={autoFocus}
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); setActive(0) }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKey}
          placeholder={large ? 'Company, ticker or former name (e.g. Apple, NVDA)' : 'Search companies'}
          aria-label="Search companies"
          className={`w-full min-w-0 bg-transparent text-ink placeholder:text-muted focus:outline-none focus-visible:outline-none ${large ? 'text-[15px]' : 'text-[13px]'}`}
        />
        {hotkey && !q && <kbd className="hidden shrink-0 lg:inline">/</kbd>}
        {large && (
          <button type="button" onClick={submit} className="hidden h-9 shrink-0 rounded-[4px] border border-accent bg-accent px-4 text-[13px] font-medium text-[var(--on-accent)] transition duration-200 hover:brightness-110 active:translate-y-px sm:block">
            Analyse
          </button>
        )}
      </label>
      {open && debounced.length >= 2 && (
        <div className="absolute z-30 mt-1.5 w-full min-w-72 overflow-hidden rounded-md border border-line-strong bg-surface p-1 shadow-[var(--shadow-pop)] animate-[rise_0.35s_var(--ease-fluid)_both]">
          {results.isLoading && <div className="px-4 py-3 text-sm text-muted">Searching SEC filers...</div>}
          {results.error && <div className="px-4 py-3 text-sm text-ink-2">{results.error.message}</div>}
          {!results.isLoading && !results.error && items.length === 0 && <div className="px-4 py-3 text-sm text-muted">No matching SEC filer.</div>}
          {items.map((item, i) => (
            <button
              key={item.company.id}
              onMouseEnter={() => setActive(i)}
              onClick={() => pick(item)}
              className={`flex w-full items-center justify-between gap-3 rounded-[4px] px-3 py-2 text-left transition-colors duration-150 ${i === active ? 'bg-surface-3' : ''}`}
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-ink">{item.company.name}</div>
                {item.formerNames?.length > 0 && <div className="truncate text-xs text-muted">formerly {item.formerNames.slice(0, 2).join(', ')}</div>}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {item.company.demo && <span className="rounded-[3px] bg-accent-soft px-1.5 py-px font-mono text-[10px] font-medium text-accent-ink">DEMO</span>}
                <span className="font-mono text-xs font-medium text-ink-2">{item.company.ticker || `CIK ${Number(item.company.marketId)}`}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
