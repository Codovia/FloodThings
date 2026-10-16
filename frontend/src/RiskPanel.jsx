import React from 'react'
import { LEVEL_COLORS, LEVEL_NAMES } from './useRisk.js'
import './RiskPanel.css'

const clock = value => value ? new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) + ' IST' : 'unavailable'

export function RiskBadge({ level }) {
  const name = LEVEL_NAMES[level] || 'Unavailable'
  return <span className="risk-badge" data-level={level || 'unavailable'} style={{ background: LEVEL_COLORS[level] || LEVEL_COLORS.unavailable }}>{name}</span>
}

export function RiskSummary({ risk, point }) {
  const { data, loading, error } = risk
  if (!point) return <><p className="eyebrow">RISK AT YOUR LOCATION</p><h2>Choose a location</h2><p>Gaps do not mean no flood risk.</p></>
  if (loading && !data) return <><p className="eyebrow">RISK AT YOUR LOCATION</p><h2>Assessing risk…</h2></>
  if (error || !data) return <><p className="eyebrow">RISK AT YOUR LOCATION</p><h2>Risk unavailable</h2><p title={error || undefined}>Gaps do not mean no flood risk.</p></>
  return <><p className="eyebrow">RISK AT YOUR LOCATION</p>
    <h2 className="risk-summary-levels">Flood <RiskBadge level={data.flood.level} /> Drainage <RiskBadge level={data.drainage.level} /></h2>
    <p>Experimental index · not an official warning.</p></>
}

function FactorTable({ title, result }) {
  return <div className="risk-factors">
    <h4>{title}: <RiskBadge level={result.level} />{result.score !== null && <span className="muted"> score {result.score} of {result.max_score}</span>}</h4>
    <table aria-label={`${title} factors`}><thead><tr><th scope="col">Factor</th><th scope="col">Value</th><th scope="col">Points</th></tr></thead>
      <tbody>{result.factors.map(f => <tr key={f.id} data-status={f.status}>
        <th scope="row">{f.name}<small>{f.detail}{f.source?.url && <> · <a href={f.source.url}>{f.source.name}</a></>}</small></th>
        <td>{f.status === 'available' ? `${f.value}${f.unit ? ' ' + f.unit : ''}` : f.status === 'no_data' ? 'No data' : 'Unavailable'}</td>
        <td>{f.status === 'available' ? `${f.points}/${f.max_points}` : '—'}</td></tr>)}</tbody></table>
    {result.partial && <p className="notice">Some inputs are unavailable, so this level may be too low.</p>}
  </div>
}

export default function RiskPanel({ risk, point }) {
  const { data, loading, error, refresh } = risk
  return <article className="risk-panel" aria-labelledby="risk-panel-title">
    <h3 id="risk-panel-title">Why this risk level?</h3>
    {!point && <p>Select a location to assess flood and drainage risk.</p>}
    {point && loading && !data && <p role="status">Checking rainfall, river, terrain and reports…</p>}
    {point && error && <p role="status">Risk unavailable: {error} No substitute level is shown.</p>}
    {point && data && <>
      <p className="notice">{data.label}</p>
      {data.rain_window && <p className="muted">Rain window {clock(data.rain_window.start)} – {clock(data.rain_window.end)} · checked {clock(data.retrieved_at)}.{point.kind === 'network' && ' Location is an approximate network estimate.'}</p>}
      <details className="risk-factor-details"><summary>Show each factor and its source</summary>
      <FactorTable title="Flood risk" result={data.flood} />
      <FactorTable title="Drainage / waterlogging risk" result={data.drainage} />
      <p className="muted">Levels: {data.level_scale}. Thresholds: IMD rainfall categories and GloFAS-style return levels.</p>
      </details>
      <button type="button" onClick={refresh} disabled={loading}>Refresh risk</button>
    </>}
  </article>
}
