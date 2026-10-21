import React from 'react'
import { LEVEL_NAMES, rankedSpots } from './useRisk.js'
import { RiskBadge, RiskWhy } from './RiskPanel.jsx'
import Popup from './Popup.jsx'

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

export function KindToggle({ kind, onKind, label = 'Risk type' }) {
  return <div className="risk-area-toggle" role="group" aria-label={label}>{Object.entries(KINDS).map(([k, name]) =>
    <button key={k} type="button" aria-pressed={kind === k} onClick={() => onKind(k)}>{name}</button>)}</div>
}

export default function RiskAreaDashboard({ area, risk = null, point, kind, onKind, onFocus }) {
  const { data, loading, error, refresh } = area
  let body, counts = null
  if (!point) body = <p>Choose your town or use your location to see the riskiest spots around you.</p>
  else if (point.kind === 'network') body = <p>Your location is only a network estimate. Use your location or search your town to rank nearby spots.</p>
  else if (loading && !data) body = <p role="status">Checking rainfall, ground height, past floods and reports around you…</p>
  else if (error || !data) body = <p role="status">Area prediction unavailable{error ? `: ${error}` : ''}. No substitute levels are shown. <button type="button" className="link-button" onClick={refresh}>Try again</button></p>
  else {
    const tally = Object.fromEntries(ORDER.map(l => [l, data.cells.filter(c => c[kind].level === l).length]))
    counts = <p className="risk-area-counts" aria-label={`${KINDS[kind]} risk counts`}>{ORDER.filter(l => tally[l]).map(l => <span key={l}><RiskBadge level={l} /> {tally[l]}</span>)}<small>spots within ~16 km</small></p>
    const top = rankedSpots(data.cells, kind).filter(c => c[kind].level !== 'low').slice(0, 3)
    body = <>
      {top.length ? <ol className="risk-area-list" aria-label={`Highest ${KINDS[kind].toLowerCase()} risk spots`}>{top.map(c => <li key={c.id}>
        <button type="button" onClick={() => onFocus(c)} aria-label={`Show ${spotLabel(c)} on the map: ${LEVEL_NAMES[c[kind].level]} ${kind} risk`}>
          <RiskBadge level={c[kind].level} /><strong>{spotLabel(c)}</strong><small>{spotInputs(c, kind)}</small></button></li>)}</ol>
        : <p className="risk-area-calm">No spot around you is above Low {kind} risk for the next 24 hours{tally.unavailable ? ' (some spots are unavailable)' : ''}.</p>}
      {data.status === 'partial' && <p className="notice">Some spots could not be assessed; their risk is unknown, not low.</p>}
    </>
  }
  return <article className="outlook-card risk-area" aria-labelledby="risk-area-title">
    <header><h3 id="risk-area-title">Flood & drainage risk · next 24 h</h3><span className="source-tag experimental">Experimental</span></header>
    <div className="risk-area-controls"><KindToggle kind={kind} onKind={onKind} />{counts}</div>
    {body}
    {risk && point && <p className="risk-why"><Popup title="Why this risk level? (experimental)" className="risk-why-popup" label={<>Why? At your location: {risk.data ? <>Flood <RiskBadge level={risk.data.flood.level} /> Drainage <RiskBadge level={risk.data.drainage.level} /></> : risk.loading ? 'checking…' : 'unavailable'}</>}><RiskWhy risk={risk} point={point} /></Popup></p>}
    <p className="muted fine">Rule-based index — not a flood probability or an official warning.</p>
  </article>
}
