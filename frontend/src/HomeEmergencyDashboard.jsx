import React, { useState } from 'react'
import LocationDirectorySelector from './LocationDirectorySelector.jsx'
import HomeFloodMap from './HomeFloodMap.jsx'
import useRiverOutlook, {usableRiver} from './useRiverOutlook.js'
import { PageLink } from './AppNavigation.jsx'
import { clock, assessNext24Rainfall, usableCurrent } from './homeEvidence.js'
import { condition } from './DailyForecast.jsx'
import { classifyCoverage } from './homeGeography.js'
import useHomeViewport from './useHomeViewport.js'
import { useRiskPoint, useRiskArea, useOfficialWarnings, useOfficialDistricts } from './useRisk.js'
import { ImdCard, SachetCard } from './OfficialWarnings.jsx'
import RiskAreaDashboard from './RiskAreaDashboard.jsx'
import './HomeEmergencyDashboard.css'

const hour = value => new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: 'numeric', minute: '2-digit' }).format(new Date(value))

export default function HomeEmergencyDashboard({ point, district, districtId, session, location, choosePoint, chooseDistrict, navigate, onNearestShelter = null }) {
  const { dashboard, fits } = useHomeViewport()
  const riverSession = useRiverOutlook(point?.kind === 'network' ? null : point)
  const risk = useRiskPoint(point), area = useRiskArea(point), official = useOfficialWarnings(point), districts = useOfficialDistricts(true)
  const [kind, setKind] = useState('flood'), [focus, setFocus] = useState(null)
  const river = usableRiver(riverSession.data, point, riverSession.now) ? riverSession.data : null
  const now = Date.now(), weather = point ? session.data : null
  const current = usableCurrent(weather, session.freshness, now)
  const rainAssessment = session.freshness === 'fresh' && weather ? assessNext24Rainfall(weather, now) : null
  const rainfall = rainAssessment?.status === 'available' ? rainAssessment : null
  const gpsCoverage = point?.kind === 'gps' ? classifyCoverage(point) : null
  const gpsNotice = gpsCoverage === 'outside' ? 'Your location is outside Karnataka.' : ['uncertain', 'unknown'].includes(gpsCoverage) ? 'State-boundary coverage and district association are unconfirmed for this GPS point.' : null
  const weatherStatus = !point ? null : session.loading ? 'Loading weather…' : !current ? 'Current weather unavailable' : Number.isFinite(current.temperature_c) ? `${current.temperature_c} °C` : 'Temperature unavailable'
  const extras = current ? [condition(current.weather_code), [Number.isFinite(current.humidity_percent) && `Humidity: ${current.humidity_percent}%.`, Number.isFinite(current.wind_speed) && current.wind_speed_unit && `Wind: ${current.wind_speed} ${current.wind_speed_unit}.`].filter(Boolean).join(' ')].filter(Boolean).join(' · ') : ''
  const riverStatus = riverSession.loading ? 'checking reviewed river coverage' : river ? `${river.reach.name} (GloFAS v4 model discharge; not observed water level)` : riverSession.error || (riverSession.data?.status === 'unsupported' ? 'no verified river-grid association for this point' : point?.kind === 'network' ? 'unavailable for a network estimate' : 'unavailable')
  return <div ref={dashboard} className={'home-emergency-dashboard' + (fits ? ' home-viewport-fit' : '')}>
    <section className="home-location-bar" aria-label="Home location selection">
      <div className="home-place"><p className="eyebrow">YOUR LOCATION</p><h2>{point?.name || (location.status === 'coarse' ? 'Approximate location — select your town' : 'Karnataka statewide view')}</h2><p role="status">{location.message}</p>{gpsNotice && !location.message.includes(gpsNotice) && <p role="status">{gpsNotice}</p>}</div>
      {point && <div className="home-weather-line" aria-label="Current weather and rain">
        <h2 className="home-temp">{weatherStatus}</h2>
        <p>{extras}{current && <small> · valid {clock(current.valid_at)}</small>}</p>
        <p className="home-rain"><strong>{rainfall ? `${Number(rainfall.mm.toFixed(1))} mm` : 'Unavailable'}</strong> rain forecast in the next 24 h{rainfall && <small> ({hour(rainfall.start)} – {hour(rainfall.end)})</small>} · <PageLink to="/weather" navigate={navigate}>7-day forecast</PageLink></p>
        {session.error && <p role="alert">{session.error}</p>}
      </div>}
      <div className="home-location-actions"><button onClick={location.request} disabled={location.status === 'requesting'}>Use my location</button><LocationDirectorySelector onChoose={choosePoint} onDistrict={chooseDistrict} selectedDistrictId={districtId} collapseOnChoose /></div>
    </section>
    <div className="home-main-grid">
      <section className="panel workspace-information home-area-summary" aria-labelledby="home-area-title">
        <div className="home-essential-status"><h2 id="home-area-title">Local Conditions & Flood Outlook</h2>
          <nav className="home-primary-actions" aria-label="Citizen actions"><PageLink to="/report" navigate={navigate} className="button-link">Report flooding or blocked drainage</PageLink>{onNearestShelter ? <button type="button" className="button-link secondary" onClick={onNearestShelter}>Go to nearest open shelter</button> : <PageLink to="/shelters" navigate={navigate} className="button-link secondary">Find verified shelters</PageLink>}</nav></div>
        <div className="home-area-scroll" role="region" aria-label="Flood outlook details" tabIndex={0}>
          <ImdCard official={official} point={point} />
          <SachetCard official={official} />
          <RiskAreaDashboard area={area} risk={risk} point={point} kind={kind} onKind={setKind} onFocus={setFocus} />
          <p className="home-river-line"><strong>Reviewed river outlook:</strong> {String(riverStatus).replace(/\.$/, "")}.</p>
          <p className="home-more-links"><PageLink to="/alerts" navigate={navigate}>Get Telegram alerts</PageLink> · <PageLink to="/flood-map" navigate={navigate}>Historical flood evidence</PageLink></p>
          <details className="home-source-details home-sources"><summary>Data sources, freshness & privacy</summary>
            <p><strong>Official warnings</strong> are shown as issued by the India Meteorological Department and NDMA SACHET; FloodPulse does not change them.</p>
            <p><strong>Weather.</strong> Freshness: {point ? session.freshness : 'unavailable'}{weather?.retrieved_at && ` · retrieved ${clock(weather.retrieved_at)}`}. Open-Meteo model output, CC BY 4.0 (<a href="https://open-meteo.com/en/docs">documentation</a>) — model estimates, not station observations. The 24-hour window starts at the next full IST hour; rainfall alone cannot confirm flooding.{rainAssessment?.status === 'unavailable' && ` ${rainAssessment.reason}`}{point && session.retryAt && ` Automatic retry no earlier than ${clock(session.retryAt)}.`}{point && session.paused && ' Automatic retries paused; refresh manually.'}{weather && session.freshness === 'stale' && ' Cached data is stale and is not shown as current.'} {point && <button type="button" className="link-button" onClick={() => session.refresh(point)} disabled={session.loading}>Refresh weather</button>}</p>
            <p><strong>River.</strong> The reviewed river outlook appears only for independently reviewed river cells. River flow for your place is also part of the "Why?" factors (nearest GloFAS model cell).</p>
            <p><strong>Location & privacy.</strong> Browser location is optional and stays in application memory. For automatic naming, consented coordinates may be sent to BigDataCloud (<a href="https://www.bigdatacloud.com/docs/article/fair-use-policy-for-free-client-side-reverse-geocoding-api">fair-use policy</a>); network estimates have unknown uncertainty, so confirm your town before travel.{point?.name_source && <> Place label: <a href={point.name_source.url || 'https://www.maptiler.com/copyright/'}>{point.name_source.provider}</a>{point.name_accuracy && ' · approximate; not a verified administrative boundary'}.</>}</p>
          </details>
        </div>
      </section>
      <HomeFloodMap fitViewport={fits} point={point} river={river} navigate={navigate} area={area.data} kind={kind} onKind={setKind} focus={focus} onChoose={choosePoint} districts={districts.data} userDistrict={official.data?.imd?.imd_name || null} />
    </div>
  </div>
}
