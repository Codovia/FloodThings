import React from 'react'
import './DailyForecast.css'

// Open-Meteo daily weather_code: most severe condition during the local day.
// https://open-meteo.com/en/docs#weathervariables (WMO interpretation table)
const CONDITIONS = {
  0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
  45: 'Fog', 48: 'Depositing rime fog', 51: 'Light drizzle', 53: 'Moderate drizzle', 55: 'Dense drizzle',
  56: 'Light freezing drizzle', 57: 'Dense freezing drizzle', 61: 'Slight rain', 63: 'Moderate rain', 65: 'Heavy rain',
  66: 'Light freezing rain', 67: 'Heavy freezing rain', 71: 'Slight snowfall', 73: 'Moderate snowfall', 75: 'Heavy snowfall',
  77: 'Snow grains', 80: 'Slight rain showers', 81: 'Moderate rain showers', 82: 'Violent rain showers',
  85: 'Slight snow showers', 86: 'Heavy snow showers', 95: 'Thunderstorm',
  96: 'Thunderstorm with slight hail', 97: 'Heavy thunderstorm', 99: 'Thunderstorm with heavy hail',
}
const reading = (value, unit) => value == null ? 'Unavailable' : `${value} ${unit}`
const condition = code => code == null ? 'Unavailable' : CONDITIONS[code] || `Unrecognized weather code (${code})`
const dayLabel = date => new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(date + 'T00:00:00+05:30'))

export default function DailyForecast({ days, coverage }) {
  const validDays = coverage?.valid_days ?? days.filter(day => [day.temperature_min_c, day.temperature_max_c, day.precipitation_mm, day.weather_code].some(value => value != null)).length
  return <section className="daily-forecast" aria-labelledby="daily-forecast-title">
    <h3 id="daily-forecast-title">Seven-day weather forecast</h3>
    <p className="muted">Asia/Kolkata calendar days, starting today; today includes elapsed hours. Daily precipitation totals (mm), temperature ranges (°C) and the most severe daily weather condition.</p>
    {validDays < 7 && <p className="notice" role="status">Incomplete forecast coverage: {validDays} of 7 days have data. Missing days have not been filled.</p>}
    {coverage?.missing_dates?.length > 0 && <p className="muted">Dates without forecast data: {coverage.missing_dates.join(', ')}.</p>}
    {days.length === 0 ? <p className="notice">Daily forecast unavailable. Current model estimates may still be available.</p> :
      <ol className="forecast-days" aria-label="Daily weather forecasts">
        {days.map(day => <li key={day.date}>
          <article aria-label={`Weather forecast for ${day.date}`}>
            <h4><time dateTime={day.date}>{dayLabel(day.date)}</time></h4>
            <p className="forecast-condition">{condition(day.weather_code)}</p>
            <dl>
              <div><dt>Minimum temperature</dt><dd>{reading(day.temperature_min_c, '°C')}</dd></div>
              <div><dt>Maximum temperature</dt><dd>{reading(day.temperature_max_c, '°C')}</dd></div>
              <div><dt>Precipitation total</dt><dd>{reading(day.precipitation_mm, 'mm')}</dd></div>
            </dl>
          </article>
        </li>)}
      </ol>}
    <p className="muted">Environmental weather information; not a seven-day flood prediction.</p>
  </section>
}
