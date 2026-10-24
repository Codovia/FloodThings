import React from 'react'

// Chart only daily provider totals: missing is a gap, never a zero replacement.
export default function RainfallChart({days=[]}){
 const valid=days.filter(d=>Number.isFinite(d.precipitation_mm) && d.precipitation_mm>=0)
 const maximum=Math.max(1,...valid.map(d=>d.precipitation_mm))
 return <section className="rainfall-chart" aria-labelledby="rainfall-chart-title"><div className="chart-heading"><h3 id="rainfall-chart-title">Forecast rainfall</h3><span className="tag">OPEN-METEO · mm / calendar day</span></div>
 <p className="muted">Provider daily precipitation totals for the forecast dates above. The first calendar day includes elapsed hours; this chart is neither an observation nor an AI prediction.</p>
 {!valid.length?<p className="notice">Rainfall visualization unavailable — no valid daily totals supplied.</p>:<div className="rainfall-bars" role="list" aria-label="Forecast daily precipitation chart">{days.map(day=>{
  const available=Number.isFinite(day.precipitation_mm) && day.precipitation_mm>=0
  return <div key={day.date} role="listitem" aria-label={`${day.date}: ${available?day.precipitation_mm+' mm forecast':'rainfall unavailable'}`}><strong>{available?`${day.precipitation_mm} mm`:'Unavailable'}</strong><div className="bar-track" aria-hidden="true">{available && <div style={{height:`${day.precipitation_mm/maximum*100}%`}}/>}</div><time dateTime={day.date}>{day.date.slice(5)}</time></div>
 })}</div>}
 </section>
}
