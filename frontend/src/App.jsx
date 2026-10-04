import React, { useEffect, useRef, useState } from 'react'
import HistoricalFloodMap from './HistoricalFloodMap.jsx'
import DrainageResearchLayers from './DrainageResearchLayers.jsx'

const formatTime = (time) => time ? new Intl.DateTimeFormat('en-IN', {
  timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short',
}).format(new Date(time)) + ' IST' : 'Unavailable'
const value = (reading, unit) => reading == null ? 'Unavailable' : `${reading} ${unit}`

export default function App() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const activeRequest = useRef(null)

  async function load() {
    activeRequest.current?.abort()
    const controller = new AbortController()
    activeRequest.current = controller
    setLoading(true)
    setData(null)
    setError(null)
    const timeout = setTimeout(() => controller.abort(), 15000)
    try {
      const response = await fetch('/api/weather', { signal: controller.signal })
      const body = await response.json()
      if (!response.ok || body.status === 'unavailable') {
        throw new Error(body.message || 'Weather is unavailable. Try again later.')
      }
      setData(body)
    } catch (err) {
      if (activeRequest.current === controller) {
        setError(err.name === 'AbortError' ? 'Weather request timed out. Try again.' : err.message)
      }
    } finally {
      clearTimeout(timeout)
      if (activeRequest.current === controller) setLoading(false)
    }
  }

  useEffect(() => {
    load()
    return () => { activeRequest.current?.abort(); activeRequest.current = null }
  }, [])

  return <main>
    <header><a className="brand" href="/">◉ FloodPulse</a><span>KARNATAKA · WEATHER</span></header>
    <section className="intro">
      <p className="eyebrow">ENVIRONMENTAL CONDITIONS</p>
      <h1>A clearer view of the weather.</h1>
      <p>Current model estimates and a three-day forecast for Bengaluru.</p>
    </section>
    <section className="panel" aria-labelledby="location-title">
      <div className="panel-heading">
        <div><p className="eyebrow">SELECTED LOCATION</p><h2 id="location-title">Bengaluru, Karnataka</h2></div>
        <button onClick={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh weather'}</button>
      </div>
      <p className="muted">Reference point: 12.9767936° N, 77.5900820° E · <a href="https://wiki.openstreetmap.org/wiki/Bengaluru">OpenStreetMap location source</a></p>
      <div aria-live="polite" aria-busy={loading}>
        {loading && <p className="notice">Fetching weather through FloodPulse…</p>}
        {error && <p className="notice error" role="alert">Weather unavailable. {error}</p>}
        {data && <>
          {data.message && <p className="notice">{data.message} Missing values are shown as unavailable.</p>}
          {data.current.stale && <p className="notice error">Current model estimate is older than 90 minutes. Check its valid time below.</p>}
          <h3>Current conditions <span className="tag">MODEL ESTIMATE</span></h3>
          <p className="muted">Valid at {formatTime(data.current.valid_at)}</p>
          <div className="metrics">
            <article><p>Temperature</p><strong>{value(data.current.temperature_c, '°C')}</strong><small>At 2 metres</small></article>
            <article><p>Relative humidity</p><strong>{value(data.current.humidity_percent, '%')}</strong><small>At 2 metres</small></article>
            <article><p>Precipitation</p><strong>{value(data.current.precipitation_mm, 'mm')}</strong><small>Preceding {data.current.interval_seconds / 60} minutes</small></article>
          </div>
          <h3>Three-day forecast</h3>
          <p className="muted">Daily totals and temperature ranges · Asia/Kolkata</p>
          <div className="table-wrap"><table>
            <thead><tr><th scope="col">Forecast date (IST)</th><th scope="col">Precipitation</th><th scope="col">Min temperature</th><th scope="col">Max temperature</th></tr></thead>
            <tbody>{data.forecast.map(day => <tr key={day.date}><th scope="row">{day.date}</th><td>{value(day.precipitation_mm, 'mm')}</td><td>{value(day.temperature_min_c, '°C')}</td><td>{value(day.temperature_max_c, '°C')}</td></tr>)}</tbody>
          </table></div>
          <dl className="metadata">
            <div><dt>Retrieved through FastAPI</dt><dd>{formatTime(data.retrieved_at)}</dd></div>
            <div><dt>Station observation time</dt><dd>Unavailable — model data</dd></div>
            <div><dt>Forecast issue time</dt><dd>Unavailable — provider does not supply it here</dd></div>
            <div><dt>Provider grid point</dt><dd>{data.grid_location.latitude}° N, {data.grid_location.longitude}° E</dd></div>
          </dl>
        </>}
      </div>
    </section>
    <HistoricalFloodMap />
    <DrainageResearchLayers />
    <footer>
      <p>Weather data by <a href="https://open-meteo.com/">Open-Meteo</a> · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a> · <a href="https://open-meteo.com/en/docs">API documentation</a></p>
      <p>Weather model output; no station observations are supplied in this slice. This point does not represent all of Karnataka.</p>
      <p>Flood prediction, drainage assessment, alerts and shelter navigation are planned. This dashboard provides weather information, historical satellite flood evidence and optional GIS research layers.</p>
    </footer>
  </main>
}
