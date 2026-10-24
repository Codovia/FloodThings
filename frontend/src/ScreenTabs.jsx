import React, { useEffect, useId, useState } from 'react'

const WIDE = '(min-width: 1100px)'
export function useWide() {
  const [wide, setWide] = useState(() => !!window.matchMedia?.(WIDE)?.matches)
  useEffect(() => {
    const m = window.matchMedia?.(WIDE); if (!m) return
    const on = () => setWide(m.matches); m.addEventListener?.('change', on); return () => m.removeEventListener?.('change', on)
  }, [])
  return wide
}

// Splits a page into tabs so each part fits one screen without scrolling (one-screen rule).
// mode 'phone': tabs below 1100 px; wider screens show every panel and the page CSS lays them out.
// mode 'always': tabs at every size. Hidden panels stay mounted, so typed input and map state survive.
export default function ScreenTabs({ tabs, label, mode = 'phone', active, onActive, className = '' }) {
  const wide = useWide(), id = useId().replace(/:/g, '')
  const shown = tabs.filter(Boolean)
  const [own, setOwn] = useState(shown[0]?.id)
  const current = shown.some(t => t.id === (active ?? own)) ? (active ?? own) : shown[0]?.id
  const choose = onActive ?? setOwn
  const tabbed = mode === 'always' || !wide
  function key(event, index) {
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key]
    if (!step) return
    event.preventDefault()
    const next = shown[(index + step + shown.length) % shown.length]
    choose(next.id); document.getElementById(`${id}-${next.id}`)?.focus()
  }
  return <div className={`screen-tabs-wrap ${tabbed ? 'tabbed' : 'untabbed'} ${className}`}>
    {tabbed && <div role="tablist" aria-label={label} className="screen-tabs">{shown.map((t, i) =>
      <button key={t.id} type="button" role="tab" id={`${id}-${t.id}`} aria-label={t.ariaLabel} aria-selected={t.id === current} aria-controls={`${id}-${t.id}-panel`} tabIndex={t.id === current ? 0 : -1} onClick={() => choose(t.id)} onKeyDown={e => key(e, i)}>{t.label}</button>)}</div>}
    {shown.map(t => <div key={t.id} id={`${id}-${t.id}-panel`} role={tabbed ? 'tabpanel' : undefined} aria-labelledby={tabbed ? `${id}-${t.id}` : undefined} hidden={tabbed && t.id !== current} className={`screen-panel panel-${t.id}`}>{t.content}</div>)}
  </div>
}

// Shows a fixed number of items per page with Previous/Next, instead of a scrolling list.
export function usePaged(items, perPage) {
  const [page, setPage] = useState(0)
  const pages = Math.max(1, Math.ceil(items.length / perPage))
  const safe = Math.min(page, pages - 1)
  useEffect(() => { if (page !== safe) setPage(safe) }, [page, safe])
  return { items: items.slice(safe * perPage, safe * perPage + perPage), page: safe, pages, setPage }
}
export function Pager({ paged, label }) {
  if (paged.pages < 2) return null
  return <nav className="pager" aria-label={label}>
    <button type="button" className="secondary" disabled={paged.page === 0} onClick={() => paged.setPage(paged.page - 1)}>‹ Previous</button>
    <span aria-live="polite">{paged.page + 1} of {paged.pages}</span>
    <button type="button" className="secondary" disabled={paged.page >= paged.pages - 1} onClick={() => paged.setPage(paged.page + 1)}>Next ›</button>
  </nav>
}
