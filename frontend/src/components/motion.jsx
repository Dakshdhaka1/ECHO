import { useEffect, useLayoutEffect, useRef, useState } from 'react'

const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

/** Fades and lifts its content in once it scrolls into view (IntersectionObserver, never scroll listeners). */
export function Reveal({ as: Tag = 'div', delay = 0, className = '', children, ...rest }) {
  const ref = useRef(null)
  const [shown, setShown] = useState(() => typeof IntersectionObserver === 'undefined')
  useEffect(() => {
    if (shown || !ref.current) return undefined
    const io = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) { setShown(true); io.disconnect() }
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.12 })
    io.observe(ref.current)
    return () => io.disconnect()
  }, [shown])
  return (
    <Tag ref={ref} data-reveal data-in={shown} style={{ '--delay': `${delay}ms` }} className={className} {...rest}>
      {children}
    </Tag>
  )
}

/** Counts a number up on mount by writing to the DOM directly (no React re-render per frame). */
export function CountUp({ as: Tag = 'span', value, duration = 1200, format = (v) => Math.round(v).toLocaleString() }) {
  const ref = useRef(null)
  const target = Number(value)
  useLayoutEffect(() => {
    const node = ref.current
    if (!node || !Number.isFinite(target)) return undefined
    if (reducedMotion()) { node.textContent = format(target); return undefined }
    node.textContent = format(0)
    let frame
    const start = performance.now()
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      node.textContent = format(target * (1 - (1 - t) ** 4))
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, duration]) // eslint-disable-line react-hooks/exhaustive-deps
  if (!Number.isFinite(target)) return <Tag>{value ?? '-'}</Tag>
  return <Tag ref={ref} className="tabular">{format(target)}</Tag>
}
