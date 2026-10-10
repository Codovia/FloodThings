import React from 'react'
import { FRESHNESS_MS, retrievalTime } from './useWeatherSession.js'
import DailyForecast from './DailyForecast.jsx'
import RainfallChart from './RainfallChart.jsx'
import './WeatherFreshness.css'
const formatTime = time => time && Number.isFinite(Date.parse(time)) ? new Intl.DateTimeFormat('en-IN', {timeZone:'Asia/Kolkata', dateStyle:'medium', timeStyle:'short'}).format(new Date(time))+' IST' : 'Unavailable'
const value = (reading, unit) => reading == null ? 'Unavailable' : `${reading} ${unit}`
export default function WeatherPanel({point, selectedPoint, session}) {
  const {data,loading,error,freshness,now,retryAt,paused,offline,refresh:load}=session
  return (
    <section className="panel" aria-labelledby="location-title">
      <div className="panel-heading">
        <div><p className="eyebrow">SELECTED LOCATION</p><h2 id="location-title">{point.name}</h2></div>
        <button onClick={() => load()} disabled={loading}>{loading ? 'Loading…' : 'Refresh weather'}</button>
      </div>
      <p className="muted">Requested point: {point.latitude}° latitude, {point.longitude}° longitude · {point.locality_id ? <><a href={point.coordinate_source_url}>Mapped locality point · OpenStreetMap</a> · <a href={point.association_source_url}>{point.district_name} district association</a>. Point weather, not locality-wide or district-wide conditions.</> : selectedPoint ? 'User-selected coordinates; district/locality identity not verified.' : <a href="https://wiki.openstreetmap.org/wiki/Bengaluru">OpenStreetMap location source</a>}</p>
      <p className="notice">Flood prediction is not available. Prediction target and label methodology are not yet validated.</p>
      <div className="weather-freshness" data-freshness={freshness} role="status" aria-label="Weather data freshness">
        <strong>{freshness === 'fresh' ? 'Fresh' : freshness === 'stale' ? 'Stale — previously retrieved information' : freshness === 'refreshing' ? 'Refreshing weather' : 'No weather data available'}</strong>
        {data && <span>Last successful retrieval: {retrievalTime(data.retrieved_at, now) === null ? 'Unavailable — freshness cannot be verified' : formatTime(data.retrieved_at)}</span>}
        {loading && data && <span>Showing previously retrieved information while refreshing.</span>}
        {loading && data && (retrievalTime(data.retrieved_at, now) === null || now - retrievalTime(data.retrieved_at, now) >= FRESHNESS_MS) && <span>Displayed information is stale; the refresh has not succeeded yet.</span>}
        {offline && <span>Browser is offline. Automatic requests are paused.</span>}
        {retryAt && <span>Automatic retry no earlier than {formatTime(new Date(retryAt).toISOString())}. Manual refresh is available.</span>}
        {paused && <span>Automatic retries paused after three failed attempts. Refresh manually to try again.</span>}
        <small>Six-hour browser-session refresh cadence; paused while hidden or offline. No refresh while this application is closed. Retrieval is not forecast issuance or a guarantee of forecast accuracy.</small>
      </div>
      <div aria-live="polite" aria-busy={loading}>
        {loading && <p className="notice">Fetching weather through FloodPulse…</p>}
        {error && <p className="notice error" role="alert">{data ? 'Weather refresh unavailable.' : 'Weather unavailable.'} {error}</p>}
        {data && <>
          {data.message && <p className="notice">{data.message} Missing values are shown as unavailable.</p>}
          {(data.current.stale || (Number.isFinite(Date.parse(data.current.valid_at)) && now - Date.parse(data.current.valid_at) > 90 * 60 * 1000)) && <p className="notice error">Current model estimate is older than 90 minutes. Check its valid time below.</p>}
          <h3>Current conditions <span className="tag">MODEL ESTIMATE</span></h3>
          <p className="muted">Valid at {formatTime(data.current.valid_at)}</p>
          <div className="metrics">
            <article><p>Temperature</p><strong>{value(data.current.temperature_c, '°C')}</strong><small>At 2 metres</small></article>
            <article><p>Relative humidity</p><strong>{value(data.current.humidity_percent, '%')}</strong><small>At 2 metres</small></article>
            <article><p>Precipitation</p><strong>{value(data.current.precipitation_mm, 'mm')}</strong><small>Preceding {data.current.interval_seconds / 60} minutes</small></article>
          </div>
          <DailyForecast days={data.forecast} coverage={data.forecast_coverage} />
          <RainfallChart days={data.forecast} />
          <dl className="metadata">
            <div><dt>Retrieved through FastAPI</dt><dd>{formatTime(data.retrieved_at)}</dd></div>
            <div><dt>Station observation time</dt><dd>Unavailable — model data</dd></div>
            <div><dt>Forecast issue time</dt><dd>Unavailable — provider does not supply it here</dd></div>
            <div><dt>Provider grid point</dt><dd>Latitude {data.grid_location.latitude}°, longitude {data.grid_location.longitude}°</dd></div>
          </dl>
        </>}
      </div>
    </section>
  )
}
