import React, { useState } from 'react'
import LocationDirectorySelector from './LocationDirectorySelector.jsx'
import HomeFloodMap from './HomeFloodMap.jsx'
import useRiverOutlook, {usableRiver} from './useRiverOutlook.js'
import { PageLink } from './AppNavigation.jsx'
import { clock, assessNext24Rainfall, usableCurrent } from './homeEvidence.js'
import DailyForecast, { condition } from './DailyForecast.jsx'
import RainfallOutlook, { supportsRainfallModel } from './RainfallOutlook.jsx'
import { classifyCoverage } from './homeGeography.js'
import useHomeViewport from './useHomeViewport.js'
import { useRiskPoint, useRiskArea, useOfficialWarnings } from './useRisk.js'
import OfficialWarnings, { OfficialSummary } from './OfficialWarnings.jsx'
import RiskAreaDashboard from './RiskAreaDashboard.jsx'
import RiskPanel, { RiskSummary } from './RiskPanel.jsx'
import './HomeEmergencyDashboard.css'
export default function HomeEmergencyDashboard({ point, district, districtId, session, location, choosePoint, chooseDistrict, navigate }) {
  const { dashboard, fits } = useHomeViewport()
  const riverSession = useRiverOutlook(point?.kind === 'network' ? null : point)
  const risk = useRiskPoint(point), area = useRiskArea(point), official = useOfficialWarnings(point)
  const [kind, setKind] = useState('flood'), [focus, setFocus] = useState(null)
  const river = usableRiver(riverSession.data, point, riverSession.now) ? riverSession.data : null
  const now = Date.now(), weather = point ? session.data : null
  const current = usableCurrent(weather, session.freshness, now)
  const rainAssessment = session.freshness === 'fresh' && weather ? assessNext24Rainfall(weather, now) : null
  const rainfall = rainAssessment?.status === 'available' ? rainAssessment : null
  const gpsCoverage = point?.kind === 'gps' ? classifyCoverage(point) : null
  const gpsNotice = gpsCoverage === 'outside' ? 'Your location is outside Karnataka.' : ['uncertain', 'unknown'].includes(gpsCoverage) ? 'State-boundary coverage and district association are unconfirmed for this GPS point.' : null
  const loading = point && session.loading
  const weatherStatus = !point ? 'Select a place for point weather.' : loading ? 'Loading weather…' : !current ? 'Current weather unavailable.' : Number.isFinite(current.temperature_c) ? `${current.temperature_c} °C` : 'Temperature unavailable.'
  const currentDetails = current ? [condition(current.weather_code), [Number.isFinite(current.humidity_percent) && `Humidity: ${current.humidity_percent}%.`, Number.isFinite(current.wind_speed) && current.wind_speed_unit && `Wind: ${current.wind_speed} ${current.wind_speed_unit}.`].filter(Boolean).join(' ')].filter(Boolean).join(' · ') : 'Open-Meteo weather model'
  const riverStatus = riverSession.loading ? 'Checking reviewed river coverage…' : riverSession.error || (riverSession.data?.status==='unsupported' ? 'No verified river-grid association is available for this point.' : riverSession.data?.fresh_until ? 'River forecast is stale; refresh to check again.' : riverSession.data?.message || (point?.kind === 'network' ? 'A network estimate cannot support verified river context. Confirm a locality.' : 'Select a location to check supported river coverage.'))
  return <div ref={dashboard} className={'home-emergency-dashboard' + (fits ? ' home-viewport-fit' : '')}>
    <section className="home-location-bar" aria-label="Home location selection"><div><p className="eyebrow">YOUR LOCATION</p><h2>{point?.name || (location.status === 'coarse' ? 'Approximate location — select your town' : 'Karnataka statewide view')}</h2><p role="status">{location.message}</p>{gpsNotice && !location.message.includes(gpsNotice) && <p role="status">{gpsNotice}</p>}</div><div className="home-location-actions"><button onClick={location.request} disabled={location.status === 'requesting'}>Use my location</button><LocationDirectorySelector onChoose={choosePoint} onDistrict={chooseDistrict} selectedDistrictId={districtId} collapseOnChoose /></div></section>
    <div className="home-summary-cards" aria-label="Essential summaries">
      <section className="home-summary-card"><p className="eyebrow">CURRENT WEATHER</p><h2>{weatherStatus}</h2><small>{currentDetails}{current && ` · valid ${clock(current.valid_at)}`}</small>{point && session.error && <p role="alert">{session.error}</p>}</section>
      <section className="home-summary-card home-rain-summary"><p className="eyebrow">RAINFALL FORECAST</p><h2>{rainfall ? `Next 24 full forecast hours: ${Number(rainfall.mm.toFixed(2))} mm` : 'Next-24-hour total unavailable'}</h2><p>{rainfall ? `${clock(rainfall.start)} to ${clock(rainfall.end)}` : 'Whole-window forecast unavailable.'}</p></section>
      <section className="home-summary-card home-flood-summary" aria-label="Flood and drainage risk"><RiskSummary risk={risk} point={point} /></section>
    </div>
    <div className="home-main-grid">
      <section className="panel workspace-information home-area-summary" aria-labelledby="home-area-title"><div className="home-essential-status"><h2 id="home-area-title">Local Conditions & Flood Outlook</h2><nav className="home-primary-actions" aria-label="Citizen actions"><PageLink to="/report" navigate={navigate} className="button-link">Report flooding or blocked drainage</PageLink><PageLink to="/shelters" navigate={navigate} className="button-link secondary">Find verified shelters</PageLink><PageLink to="/alerts" navigate={navigate}>Telegram alerts</PageLink><PageLink to="/flood-map" navigate={navigate}>Historical flood evidence</PageLink></nav><OfficialSummary official={official} point={point} /></div>
        <div className="home-area-scroll" role="region" aria-label="Additional area information" tabIndex={0}>
        <OfficialWarnings official={official} point={point} />
        <RiskAreaDashboard area={area} point={point} kind={kind} onKind={setKind} onFocus={setFocus} />
        <RiskPanel risk={risk} point={point} />
        {weather && session.freshness === 'fresh' && <article className="home-forecast"><h3>Seven-day forecast</h3><DailyForecast days={weather.forecast} coverage={weather.forecast_coverage} compact /></article>}
        {point && supportsRainfallModel(point) && <RainfallOutlook point={point} weather={weather} freshness={session.freshness} active />}
        <article className="home-river-outlook"><h3>Nearby river outlook</h3>{river ? <><p><strong>{river.reach.name}</strong> · modelled daily discharge (GloFAS v4). Not observed water level or a warning.</p><details className="home-source-details"><summary>River forecast table</summary><table className="home-river-table"><caption>Modelled river discharge (m³/s) · original GMT dates</caption><thead><tr><th>Date (GMT)</th><th>Discharge</th><th>Ensemble mean</th><th>p25–p75</th></tr></thead><tbody>{river.forecast.map(d=><tr key={d.date}><th scope="row">{d.date}</th><td>{d.river_discharge ?? 'Unavailable'}</td><td>{d.river_discharge_mean ?? 'Unavailable'}</td><td>{Number.isFinite(d.river_discharge_p25)&&Number.isFinite(d.river_discharge_p75)?`${d.river_discharge_p25}–${d.river_discharge_p75}`:'Unavailable'}</td></tr>)}</tbody></table></details></> : <p>{riverStatus}</p>}</article>
        <details className="home-source-details home-sources"><summary>Data sources, freshness & privacy</summary>
          <p><strong>Weather.</strong> Freshness: {point ? session.freshness : 'unavailable'}{weather?.retrieved_at && ` · retrieved ${clock(weather.retrieved_at)}`}. Open-Meteo model output, CC BY 4.0 (<a href="https://open-meteo.com/en/docs">documentation</a>) — model estimates, not station observations. The 24-hour window starts at the next full IST hour; rainfall alone cannot confirm flooding. Forecast issue time is not supplied.{rainAssessment?.status === 'unavailable' && ` ${rainAssessment.reason}`}{point && session.retryAt && ` Automatic retry no earlier than ${clock(session.retryAt)}.`}{point && session.paused && ' Automatic retries paused; refresh manually.'}{weather && session.freshness === 'stale' && ' Cached data is stale and is not shown as current.'}</p>
          <p><strong>River.</strong> <a href="https://open-meteo.com/en/docs/flood-api">Open-Meteo Global Flood API</a> · Copernicus GloFAS · CC BY 4.0. ~5 km model cells may select a different river; only reviewed river/cell associations are shown. No flood probabilities are inferred.{river && ` Reviewed scope: ${river.reach.coverage_description}. Retrieved ${clock(river.retrieved_at)}; fresh until ${clock(river.fresh_until)}.`}</p>
          <p><strong>Location & privacy.</strong> Browser location is optional and stays in application memory. For automatic naming, consented coordinates may be sent to BigDataCloud (<a href="https://www.bigdatacloud.com/docs/article/fair-use-policy-for-free-client-side-reverse-geocoding-api">fair-use policy</a>); network estimates have unknown uncertainty, so confirm your town before travel.{point?.name_source && <> Place label: <a href={point.name_source.url || 'https://www.maptiler.com/copyright/'}>{point.name_source.provider}</a>{point.name_accuracy && ' · approximate; not a verified administrative boundary'}.</>}</p>
        </details>
        {point && <div className="home-detail-links"><button onClick={() => session.refresh(point)} disabled={session.loading}>Refresh weather</button><button onClick={riverSession.refresh} disabled={riverSession.loading}>Refresh river outlook</button></div>}
        </div>
      </section>
      <HomeFloodMap fitViewport={fits} point={point} river={river} navigate={navigate} area={area.data} kind={kind} focus={focus} onChoose={choosePoint} />
    </div>
  </div>
}
