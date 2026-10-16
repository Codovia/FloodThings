import React from 'react'
import { LEVEL_NAMES, rankedSpots } from './useRisk.js'
import { RiskBadge } from './RiskPanel.jsx'

const KINDS = { flood: 'Flood', drainage: 'Drainage' }
const ORDER = ['severe', 'high', 'moderate', 'low', 'unavailable']

export function spotLabel(cell) {
  const where = cell.direction ? `${cell.distance_km} km ${cell.direction}` : 'Your location'
  return cell.place ? `${where} · near ${cell.place}` : where
}

export function spotInputs(cell, kind) {
  const i = cell.inputs || {}, parts = []
  if (Number.isFinite(i.rain_24h_mm)) parts.push(`${i.rain_24h_mm} mm rain next 24 h`)
  if (kind === 'drainage' && Number.isFinite(i.peak_mmh)) parts.push(`peak ${i.peak_mmh} mm/h`)
  if (kind === 'flood' && Number.isFinite(i.rain_5d_mm)) parts.push(`${i.rain_5d_mm} mm past 5 days`)
  if (Number.isFinite(i.elevation_m)) parts.push(`ground ${i.elevation_m} m`)
  if (i.historical_flood === true) parts.push('flooded in 2005/2009')
  if (kind === 'drainage' && i.approved_reports > 0) parts.push(`${i.approved_reports} approved report${i.approved_reports > 1 ? 's' : ''}`)
  return parts.join(' · ')
}

export default function RiskAreaDashboard({ area, point, kind, onKind, onFocus }) {
  const { data, loading, error, refresh } = area
  const head = <div className="risk-area-head"><h3 id="risk-area-title">Flood & drainage risk prediction · next 24 h</h3>
    <div className="risk-area-toggle" role="group" aria-label="Risk type">{Object.entries(KINDS).map(([k, name]) => <button key={k} type="button" aria-pressed={kind === k} onClick={() => onKind(k)}>{name}</button>)}</div></div>
  let body
  if (!point) body = <p>Choose your town or use your location to see the riskiest spots around you.</p>
  else if (point.kind === 'network') body = <p>Your location is only a network estimate. Use your location or search your town to rank nearby spots.</p>
  else if (loading && !data) body = <p role="status">Checking rainfall, ground height, past floods and reports around you…</p>
  else if (error || !data) body = <p role="status">Area prediction unavailable{error ? `: ${error}` : ''}. No substitute levels are shown. <button type="button" onClick={refresh}>Try again</button></p>
  else {
    const counts = Object.fromEntries(ORDER.map(l => [l, data.cells.filter(c => c[kind].level === l).length]))
    const spots = rankedSpots(data.cells, kind), top = spots.filter(c => c[kind].level !== 'low').slice(0, 5)
    body = <>
      <p className="risk-area-counts" aria-label={`${KINDS[kind]} risk counts`}>{ORDER.filter(l => counts[l]).map(l => <span key={l}><RiskBadge level={l} /> {counts[l]}</span>)}<small>spots within ~16 km</small></p>
      {top.length ? <ol className="risk-area-list" aria-label={`Highest ${KINDS[kind].toLowerCase()} risk spots`}>{top.map(c => <li key={c.id}>
        <button type="button" onClick={() => onFocus(c)} aria-label={`Show ${spotLabel(c)} on the map: ${LEVEL_NAMES[c[kind].level]} ${kind} risk`}>
          <RiskBadge level={c[kind].level} /><strong>{spotLabel(c)}</strong><small>{spotInputs(c, kind)}</small></button></li>)}</ol>
        : <p className="risk-area-calm">No spot around you is above Low {kind} risk for the next 24 hours{counts.unavailable ? ' (some spots are unavailable)' : ''}.</p>}
      {data.status === 'partial' && <p className="notice">Some spots could not be assessed; their risk is unknown, not low.</p>}
      <p className="muted">Each square on the map is a ~5.5 km grid spot. Rainfall, ground height, mapped past floods and approved reports; river flow is checked in the full assessment of your place. {data.label}</p>
    </>
  }
  return <article className="risk-area" aria-labelledby="risk-area-title">{head}{body}</article>
}
