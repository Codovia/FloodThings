import React from 'react'
import { FRESHNESS_MS, retrievalTime } from './useWeatherSession.js'
import { condition } from './DailyForecast.jsx'
import RainfallChart from './RainfallChart.jsx'
import { usePaged, Pager, useWide } from './ScreenTabs.jsx'
import Popup from './Popup.jsx'
import './WeatherStrip.css'

// Home's seven-day weather strip (it replaced the separate Weather page). Open-Meteo model output for the selected
// point: missing values stay "unavailable", missing days are never filled, and it is not a flood prediction.
const formatTime = time => time && Number.isFinite(Date.parse(time)) ? new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }).format(new Date(time)) + ' IST' : 'Unavailable'
const shortTime = time => new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: 'numeric', minute: '2-digit' }).format(new Date(time))
const weekday = date => new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', weekday: 'short' }).format(new Date(date + 'T00:00:00+05:30'))
const dayOfMonth = date => new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short' }).format(new Date(date + 'T00:00:00+05:30'))
const has = value => Number.isFinite(value)
const istDate = ms => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date(ms))  // YYYY-MM-DD

// WMO weather code → small icon group.
function iconFor(code) {
  if (!has(code)) return 'none'
  if (code >= 95) return 'storm'
  if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) return 'rain'
  if (code === 45 || code === 48) return 'fog'
  if (code === 3) return 'cloud'
  if (code === 2) return 'partly'
  if (code <= 1) return 'sun'
  return 'cloud'
}
const ICONS = {
  sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-5v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4',
  partly: 'M8 5v1.5M3.5 9.5H5M4.8 5.8l1 1M12 6.8a3.5 3.5 0 0 0-6.3 2.6M8 19h9a3.5 3.5 0 0 0 .5-7 5 5 0 0 0-9.6 1A3 3 0 0 0 8 19Z',
  cloud: 'M7 18h10a4 4 0 0 0 .6-7.9A6 6 0 0 0 6 11a3.5 3.5 0 0 0 1 7Z',
  rain: 'M7 14h10a4 4 0 0 0 .6-7.9A6 6 0 0 0 6 7a3.5 3.5 0 0 0 1 7Zm1 3-1 3m5-3-1 3m5-3-1 3',
  storm: 'M7 13h10a4 4 0 0 0 .6-7.9A6 6 0 0 0 6 6a3.5 3.5 0 0 0 1 7Zm5.5 1-2 4h3l-2 4',
  fog: 'M4 9h16M6 13h12M4 17h16',
  none: 'M9 9a3 3 0 1 1 4 2.8c-.6.3-1 .8-1 1.5V14m0 3h.01',
}
const WeatherIcon = ({ code }) => <svg className="strip-icon" aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={ICONS[iconFor(code)]} /></svg>

export default function WeatherStrip({ point, session }) {
  const { data, loading, freshness, now, retryAt, paused, offline, refresh } = session
  const wide = useWide()
  const days = data?.forecast || []
  const paged = usePaged(days, wide ? 7 : 4)
  const coverage = data?.forecast_coverage
  const validDays = coverage?.valid_days ?? days.filter(day => [day.temperature_min_c, day.temperature_max_c, day.precipitation_mm, day.weather_code].some(value => value != null)).length
  const wettest = Math.max(1, ...days.map(day => has(day.precipitation_mm) && day.precipitation_mm >= 0 ? day.precipitation_mm : 0))
  const retrieved = data && retrievalTime(data.retrieved_at, now)
  const label = freshness === 'fresh' ? 'Fresh' : freshness === 'stale' ? 'Stale — previously retrieved information' : freshness === 'refreshing' ? 'Refreshing weather' : 'No weather data available'
  return <section className="weather-strip" aria-labelledby="weather-strip-title">
    <div className="strip-head">
      <h2 id="weather-strip-title">Next 7 days</h2>
      <p className="strip-freshness" data-freshness={freshness} role="status" aria-label="Weather data freshness">
        <strong>{label}</strong>
        {data && <span>{retrieved === null ? ' · Retrieval time: Unavailable — freshness cannot be verified' : ` · retrieved ${shortTime(data.retrieved_at)}`}</span>}
        {loading && data && <span> · Showing previously retrieved information while refreshing.</span>}
        {loading && data && (retrieved === null || now - retrieved >= FRESHNESS_MS) && <span> Displayed information is stale; the refresh has not succeeded yet.</span>}
        {offline && <span> · Browser is offline. Automatic requests are paused.</span>}
        {retryAt && <span> · Automatic retry no earlier than {formatTime(new Date(retryAt).toISOString())}. Manual refresh is available.</span>}
        {paused && <span> · Automatic retries paused after three failed attempts. Refresh manually to try again.</span>}
      </p>
      <div className="strip-actions">
        <button type="button" className="link-button" aria-label="Refresh weather" onClick={() => refresh()} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
        {days.length > 0 && <Popup label="Rain chart" title="Forecast rainfall, next 7 days"><RainfallChart days={days} /></Popup>}
        <Popup label="Details" title="Weather details & sources">
          <p><strong>Freshness.</strong> Six-hour browser-session refresh cadence; paused while hidden or offline. No refresh while this application is closed. Retrieval is not forecast issuance or a guarantee of forecast accuracy.</p>
          {data && <p>Requested point: {point.latitude}° latitude, {point.longitude}° longitude · {point.locality_id ? <><a href={point.coordinate_source_url}>Mapped locality point · OpenStreetMap</a> · <a href={point.association_source_url}>{point.district_name} district association</a>. Point weather, not locality-wide or district-wide conditions.</> : 'User-selected coordinates; district/locality identity not verified.'}</p>}
          {data && <dl className="strip-sources">
            <div><dt>Provider grid point</dt><dd>{data.grid_location ? `${data.grid_location.latitude}°, ${data.grid_location.longitude}°` : 'Unavailable'}</dd></div>
            <div><dt>Retrieved through FloodPulse</dt><dd>{formatTime(data.retrieved_at)}</dd></div>
            <div><dt>Forecast issue time</dt><dd>Unavailable — provider does not supply it here</dd></div>
          </dl>}
          <p>Days are in India time; the first day includes hours already passed. Daily rain totals (mm), temperature ranges (°C) and the most severe condition of the day. Open-Meteo model data, CC BY 4.0 — model estimates, not station observations.</p>
          <p>Environmental weather information; not a seven-day flood prediction.</p>
        </Popup>
      </div>
    </div>
    <div aria-live="polite" aria-busy={loading}>
      {!data && loading && <p className="strip-note">Fetching weather through FloodPulse…</p>}
      {/* Errors are announced once, in Home's location bar; here the freshness line says what is shown. */}
      {data?.message && <p className="strip-note">{data.message} Missing values are shown as unavailable.</p>}
      {data && validDays < 7 && <p className="strip-note" role="status">Incomplete forecast coverage: {validDays} of 7 days have data. Missing days have not been filled.{coverage?.missing_dates?.length > 0 && ` Dates without forecast data: ${coverage.missing_dates.join(', ')}.`}</p>}
      {data && (days.length === 0 ? <p className="strip-note">Daily forecast unavailable. Current model estimates may still be available.</p> :
        <ol className="strip-days" aria-label="Daily weather forecasts">
          {paged.items.map(day => {
            const rain = has(day.precipitation_mm) && day.precipitation_mm >= 0 ? day.precipitation_mm : null
            return <li key={day.date}><article aria-label={`Weather forecast for ${day.date}`} title={condition(day.weather_code)}>
              <h3><time dateTime={day.date}>{day.date === istDate(now) ? 'Today' : weekday(day.date)}</time> <small>{dayOfMonth(day.date)}</small></h3>
              <WeatherIcon code={day.weather_code} />
              <p className="strip-temp"><strong>{has(day.temperature_max_c) ? `${Math.round(day.temperature_max_c)}°` : '–'}</strong> <span>{has(day.temperature_min_c) ? `${Math.round(day.temperature_min_c)}°` : '–'}</span></p>
              <p className="strip-rain" aria-label={rain === null ? 'Rain unavailable' : `Rain ${rain} mm`}>{rain === null ? 'Unavailable' : `${rain} mm`}</p>
              <span className="strip-rain-bar" aria-hidden="true"><span style={{ width: `${rain === null ? 0 : Math.max(4, Math.round(rain / wettest * 100))}%` }} /></span>
              <p className="visually-hidden">{condition(day.weather_code)}</p>
            </article></li>
          })}
        </ol>)}
      <Pager paged={paged} label="More forecast days" />
    </div>
  </section>
}
