import React from 'react'

export const OFFICIAL_COLOURS = { red: '#d32f2f', orange: '#ef6c00', yellow: '#f9d71c', green: '#43a047' }
const NAMES = { red: 'Red', orange: 'Orange', yellow: 'Yellow', green: 'Green' }
const day = value => new Intl.DateTimeFormat('en-IN', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' }).format(new Date(value + 'T12:00:00+05:30'))
const clock = value => value ? new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) + ' IST' : 'unavailable'

export function OfficialChip({ level }) {
  return <span className="official-chip" data-level={level || 'unavailable'} style={{ background: OFFICIAL_COLOURS[level] || '#8a8f98' }}>{NAMES[level] || 'Unavailable'}</span>
}

// One line for the always-visible Home status area.
export function OfficialSummary({ official, point }) {
  const { data, loading, error } = official
  if (loading && !data) return <p className="official-summary" role="status">Checking official IMD and NDMA warnings…</p>
  if (error || !data) return <p className="official-summary" role="status">Official warnings could not be checked. Follow IMD, KSNDMC and district advice.</p>
  const today = data.imd.status === 'available' ? data.imd.days[0] : null, active = data.sachet.alerts.length
  return <p className="official-summary">
    {today ? <>Official IMD warning for <strong>{data.imd.district}</strong> today: <OfficialChip level={today.level} /> {today.warnings.length ? today.warnings.join(', ') : 'no warning'}.</>
      : point ? <>IMD district warning: {data.imd.message || 'unavailable'}</> : <>Choose a place to see its official IMD district warning.</>}
    {' '}{data.sachet.status === 'unavailable' ? 'NDMA SACHET alerts unavailable.' : `${active} active NDMA SACHET alert${active === 1 ? '' : 's'} in Karnataka.`}
  </p>
}

export default function OfficialWarnings({ official, point }) {
  const { data, loading, error, refresh } = official
  let body
  if (loading && !data) body = <p role="status">Checking official IMD and NDMA warnings…</p>
  else if (error || !data) body = <p role="status">Official warnings could not be checked{error ? `: ${error}` : ''}. This does not mean there is no warning. <button type="button" onClick={refresh}>Try again</button></p>
  else {
    const { imd, sachet } = data
    body = <>
      <h4>IMD district warning{imd.district ? ` · ${imd.district}` : ''}</h4>
      {imd.status === 'available' ? <>
        <ol className="official-days" aria-label="IMD five-day district warnings">{imd.days.map(d => <li key={d.date}>
          <span className="official-day">{day(d.date)}</span><OfficialChip level={d.level} />
          <small>{d.status !== 'available' ? 'Unavailable' : d.warnings.length ? d.warnings.join(', ') : 'No warning'}</small></li>)}</ol>
        <p className="muted">Issued {imd.issued_date} · updated {clock(imd.updated_at)}. Red = take action, Orange = be prepared, Yellow = be updated, Green = no warning.{point?.kind === 'network' && ' Your location is an approximate network estimate, so the district may be wrong.'}</p>
      </> : <p>{imd.message}</p>}
      <h4>NDMA SACHET alerts · Karnataka</h4>
      {sachet.status === 'unavailable' ? <p>{sachet.message}</p> : sachet.alerts.length ? <ul className="official-alerts">{sachet.alerts.map(a => <li key={a.identifier} data-severity={a.severity}>
        <strong>{a.event || 'Alert'} · {a.severity}</strong>{a.names_your_district && <span className="official-yours">Names your district</span>}
        <p>{a.headline}</p><small>{a.sender} · until {clock(a.expires)}{a.instruction ? ` · ${a.instruction}` : ''}</small></li>)}</ul>
        : <p>No active SACHET alert for Karnataka right now ({sachet.checked_messages} recent messages checked).</p>}
      {sachet.unreadable_messages > 0 && <p className="notice">{sachet.unreadable_messages} recent SACHET message(s) could not be read; check the SACHET portal.</p>}
      <p className="muted">{data.label} Sources: <a href={imd.source?.url || 'https://mausam.imd.gov.in/'}>IMD</a> · <a href={sachet.source.url}>NDMA SACHET</a>. Checked {clock(sachet.retrieved_at)}.</p>
    </>
  }
  return <article className="official-warnings" aria-labelledby="official-title"><h3 id="official-title">Official warnings</h3>{body}</article>
}
