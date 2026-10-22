import React from 'react'

export const OFFICIAL_COLOURS = { red: '#d32f2f', orange: '#ef6c00', yellow: '#f9d71c', green: '#43a047' }
const NAMES = { red: 'Red', orange: 'Orange', yellow: 'Yellow', green: 'Green' }
export const MEANING = { red: 'Take action', orange: 'Be prepared', yellow: 'Be updated', green: 'No warning' }
const weekday = value => new Intl.DateTimeFormat('en-IN', { weekday: 'short', timeZone: 'Asia/Kolkata' }).format(new Date(value + 'T12:00:00+05:30'))
const clock = value => value ? new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) + ' IST' : 'unavailable'

export function OfficialChip({ level }) {
  return <span className="official-chip" data-level={level || 'unavailable'} style={{ background: OFFICIAL_COLOURS[level] || '#8a8f98' }}>{NAMES[level] || 'Unavailable'}</span>
}

function Failure({ official }) {
  return <p role="status">Official warnings could not be checked{official.error ? `: ${official.error}` : ''}. This does not mean there is no warning. <button type="button" className="link-button" onClick={official.refresh}>Try again</button></p>
}

const hour = value => new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', timeStyle: 'short' }).format(new Date(value))

// IMD district nowcast (about the next three hours), wording as published by IMD; never shown when expired.
export function NowcastLine({ nowcast }) {
  if (!nowcast || nowcast.status === 'not_requested') return null
  const current = nowcast.status === 'available' && Array.isArray(nowcast.categories) && Number.isFinite(Date.parse(nowcast.issued_at))
  if (!current) return <p className="imd-nowcast" data-active="false"><strong>Next 3 hours</strong> <span className="muted">{nowcast.message || 'IMD nowcast unavailable.'}</span></p>
  const items = [...nowcast.categories, ...(nowcast.other ? [nowcast.other] : [])]
  const full = items.length ? items.join(' · ') : 'No significant weather'
  // Phones show IMD's category names without the bracketed thresholds; the full wording stays in the tooltip.
  const short = items.length ? [...nowcast.categories.map(c => c.replace(/ \(.*\)$/, '')), ...(nowcast.other ? [nowcast.other] : [])].join(' · ') : full
  return <p className="imd-nowcast" data-active={items.length > 0} title={[full, nowcast.message].filter(Boolean).join(' — ')}>
    <strong>Next 3 hours</strong> <span><span className="label-long">{full}</span><span className="label-short">{short}</span></span> <small>IMD nowcast · {hour(nowcast.issued_at)}<span className="label-long"> IST</span></small></p>
}

// IMD district warning, displayed as issued: today prominently, then the remaining bulletin days.
export function ImdCard({ official, point }) {
  const { data, loading, error } = official, imd = data?.imd
  const today = imd?.status === 'available' ? imd.days[0] : null
  return <article className="outlook-card imd-card" data-level={today?.level || 'none'} aria-labelledby="imd-title">
    <header><h3 id="imd-title" aria-label={`Official IMD warning${imd?.district ? ` · ${imd.district}` : ''}`}><span className="label-long">Official </span>IMD warning{imd?.district ? ` · ${imd.district}` : ''}</h3><span className="source-tag official">Official</span></header>
    {loading && !data ? <p role="status">Checking official IMD and NDMA warnings…</p> : error || !data ? <Failure official={official} />
      : today ? <>
        <p className="imd-today"><OfficialChip level={today.level} /> <strong>Today · {MEANING[today.level]}</strong>{today.warnings.length > 0 && <span>{today.warnings.join(', ')}</span>}</p>
        <ol className="imd-days" aria-label="IMD district warnings, next days">{imd.days.slice(1).map(d => <li key={d.date} title={d.warnings.join(', ') || (d.status === 'available' ? 'No warning' : 'Unavailable')}>
          <span>{weekday(d.date)}</span><i style={{ background: OFFICIAL_COLOURS[d.level] || '#8a8f98' }} aria-hidden="true" /><small>{NAMES[d.level] || 'Unavailable'}</small></li>)}</ol>
        <NowcastLine nowcast={data.nowcast} />
        {point?.kind === 'network' && <p className="muted"><span className="label-long">Approximate network location — the district may be wrong.</span><span className="label-short">Approximate location; district may be wrong.</span></p>}
      </> : <p>{point ? imd?.message || 'IMD district warning unavailable.' : 'Choose your place to see its official IMD district warning.'}</p>}
  </article>
}

// NDMA SACHET CAP alerts for Karnataka; only Actual, unexpired, uncancelled alerts arrive here.
export function SachetCard({ official }) {
  const { data, loading, error } = official, sachet = data?.sachet
  const alerts = sachet?.alerts || []
  return <article className="outlook-card sachet-card" data-active={alerts.length > 0} aria-labelledby="sachet-title">
    <header><h3 id="sachet-title">NDMA SACHET alerts · Karnataka</h3><span className="source-tag official">Official</span></header>
    {loading && !data ? <p role="status">Checking NDMA SACHET…</p> : error || !data ? <Failure official={official} />
      : sachet.status === 'unavailable' ? <p>{sachet.message}</p>
      : alerts.length ? <ul className="sachet-alerts">{alerts.slice(0, 3).map(a => <li key={a.identifier}>
        <strong>{a.event || 'Alert'} · {a.severity}</strong>{a.names_your_district && <span className="official-yours">Your district</span>}
        <p>{a.headline}</p><small>{a.sender} · until {clock(a.expires)}</small></li>)}
        {alerts.length > 3 && <li className="muted">+{alerts.length - 3} more on <a href={sachet.source.url}>SACHET</a></li>}</ul>
      : <p className="quiet-line">No active alert right now <small><span className="label-long">({sachet.checked_messages} recent messages checked · {clock(sachet.retrieved_at)})</span><span className="label-short">({sachet.checked_messages} checked · {hour(sachet.retrieved_at)})</span></small></p>}
    {sachet?.unreadable_messages > 0 && <p className="notice">{sachet.unreadable_messages} recent message(s) could not be read; check the SACHET portal.</p>}
  </article>
}
