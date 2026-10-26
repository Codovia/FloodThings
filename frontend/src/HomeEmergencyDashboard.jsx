import React, { useState } from 'react'
import AddressLine, { usePlaceLookup } from './AddressLine.jsx'
import LocationDirectorySelector from './LocationDirectorySelector.jsx'
import HomeFloodMap from './HomeFloodMap.jsx'
import { PageLink } from './AppNavigation.jsx'
import { clock, assessNext24Rainfall, usableCurrent } from './homeEvidence.js'
import { condition } from './DailyForecast.jsx'
import { classifyCoverage } from './homeGeography.js'
import ScreenTabs, { useWide } from './ScreenTabs.jsx'
import WeatherStrip from './WeatherStrip.jsx'
import Popup from './Popup.jsx'
import { useRiskPoint, useRiskArea, useOfficialWarnings, useOfficialDistricts } from './useRisk.js'
import { ImdCard, SachetCard } from './OfficialWarnings.jsx'
import RiskAreaDashboard from './RiskAreaDashboard.jsx'
import './HomeEmergencyDashboard.css'

const hour = value => new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: 'numeric', minute: '2-digit' }).format(new Date(value))

export default function HomeEmergencyDashboard({ point, district, districtId, session, location, choosePoint, chooseDistrict, navigate, onNearestShelter = null, onReportHere = null }) {
  const risk = useRiskPoint(point), area = useRiskArea(point), official = useOfficialWarnings(point), districts = useOfficialDistricts(true)
  const [kind, setKind] = useState('flood'), [focus, setFocus] = useState(null), [tab, setTab] = useState('warnings'), wide = useWide()
  const now = Date.now(), weather = point ? session.data : null
  const current = usableCurrent(weather, session.freshness, now)
  const rainAssessment = session.freshness === 'fresh' && weather ? assessNext24Rainfall(weather, now) : null
  const rainfall = rainAssessment?.status === 'available' ? rainAssessment : null
  const gpsCoverage = point?.kind === 'gps' ? classifyCoverage(point) : null
  const placeLookup = usePlaceLookup(point)
  const gpsNotice = gpsCoverage === 'outside' ? 'Your location is outside Karnataka.' : ['uncertain', 'unknown'].includes(gpsCoverage) ? 'State-boundary coverage and district association are unconfirmed for this GPS point.' : null
  const weatherStatus = !point ? null : session.loading ? 'Loading weather…' : !current ? 'Current weather unavailable' : Number.isFinite(current.temperature_c) ? `${current.temperature_c} °C` : 'Temperature unavailable'
  const extras = current ? [condition(current.weather_code), [Number.isFinite(current.humidity_percent) && `Humidity: ${current.humidity_percent}%.`, Number.isFinite(current.wind_speed) && current.wind_speed_unit && `Wind: ${current.wind_speed} ${current.wind_speed_unit}.`].filter(Boolean).join(' ')].filter(Boolean).join(' · ') : ''
  return <div className="home-emergency-dashboard home-viewport-fit">
    <section className="home-location-bar" aria-label="Home location selection">
      <div className="home-place"><p className="eyebrow">YOUR LOCATION</p><h2>{placeLookup.place || point?.name || (location.status === 'coarse' ? 'Approximate location — select your town' : 'Karnataka statewide view')}</h2><p role="status">{placeLookup.place ? (point.kind === 'gps' ? `Your location (±${Math.round(point.accuracy_m)} m) · name and PIN from OpenStreetMap, approximate.` : 'Place you picked on the map · name and PIN from OpenStreetMap, approximate.') : point && location.status === 'idle' ? 'Place you selected. Location access is optional.' : location.message}</p>{gpsNotice && !location.message.includes(gpsNotice) && <p role="status">{gpsNotice}</p>}<AddressLine lookup={placeLookup} /></div>
      {point && <div className="home-weather-line" aria-label="Current weather and rain">
        <h2 className="home-temp">{weatherStatus}</h2>
        <p>{extras}{current && <small> · valid {clock(current.valid_at)}</small>}</p>
        <p className="home-rain"><strong>{rainfall ? `${Number(rainfall.mm.toFixed(1))} mm` : 'Unavailable'}</strong> rain forecast in the next 24 h{rainfall && <small className="rain-window"> ({hour(rainfall.start)} – {hour(rainfall.end)})</small>}</p>
        {session.error && <p role="alert">{session.error}</p>}
      </div>}
      <div className="home-location-actions"><button onClick={location.request} disabled={location.status === 'requesting'}>Use my location</button><LocationDirectorySelector onChoose={choosePoint} onDistrict={chooseDistrict} selectedDistrictId={districtId} collapseOnChoose /></div>
    </section>
    {/* Laptops: the seven-day strip sits under the location bar. Phones: it is the Weather tab (one-screen rule). */}
    {point && wide && <WeatherStrip point={point} session={session} />}
    <div className="home-body">
      <div className="home-essential-status"><h2 id="home-area-title">Local Conditions & Flood Outlook</h2>
        <nav className="home-primary-actions" aria-label="Citizen actions"><PageLink to="/report" navigate={navigate} className="button-link" aria-label="Report flooding or blocked drainage"><span className="label-long">Report flooding or blocked drainage</span><span className="label-short">Report flooding</span></PageLink>{onNearestShelter ? <button type="button" className="button-link secondary" aria-label="Go to nearest open shelter" onClick={onNearestShelter}><span className="label-long">Go to nearest open shelter</span><span className="label-short">Nearest shelter</span></button> : <PageLink to="/shelters" navigate={navigate} className="button-link secondary">Find verified shelters</PageLink>}</nav></div>
      {/* Phones: tabs. Laptops: outlook on the left, map on the right, nothing scrolls. */}
      <ScreenTabs className="home-tabs" label="Home sections" active={tab} onActive={setTab} tabs={[
        { id: 'warnings', label: 'Warnings', content: <section className="home-warnings" aria-label="Official warnings">
          <ImdCard official={official} point={point} />
          <SachetCard official={official} />
          <p className="home-more-links"><PageLink to="/alerts" navigate={navigate} aria-label="Get Telegram alerts"><span className="label-long">Get Telegram alerts</span><span className="label-short">Telegram alerts</span></PageLink> · <PageLink to="/flood-map" navigate={navigate} aria-label="Historical flood evidence"><span className="label-long">Historical flood evidence</span><span className="label-short">Past floods</span></PageLink> · <PageLink to="/how-it-works" navigate={navigate} aria-label="How the prediction works"><span className="label-long">How the prediction works</span><span className="label-short">How it works</span></PageLink> · <Popup label="Data sources & privacy" title="Data sources, freshness & privacy">
            <p><strong>Official warnings</strong> are shown as issued by the India Meteorological Department and NDMA SACHET; FloodPulse does not change them.</p>
            <p><strong>Weather.</strong> Freshness: {point ? session.freshness : 'unavailable'}{weather?.retrieved_at && ` · retrieved ${clock(weather.retrieved_at)}`}. Open-Meteo model output, CC BY 4.0 (<a href="https://open-meteo.com/en/docs">documentation</a>) — model estimates, not station observations. The 24-hour window starts at the next full IST hour; rainfall alone cannot confirm flooding.{rainAssessment?.status === 'unavailable' && ` ${rainAssessment.reason}`}{point && session.retryAt && ` Automatic retry no earlier than ${clock(session.retryAt)}.`}{point && session.paused && ' Automatic retries paused; refresh manually.'}{weather && session.freshness === 'stale' && ' Cached data is stale and is not shown as current.'} {point && <button type="button" className="link-button" onClick={() => session.refresh(point)} disabled={session.loading}>Refresh weather</button>}</p>
            <p><strong>River.</strong> River flow for your place is one of the "Why?" factors: the nearest GloFAS model grid cell (~5 km); river identity not verified.</p>
            <p><strong>Location & privacy.</strong> Browser location is optional and stays in application memory. To name the place and its PIN code, your located or tapped point, rounded to about 11 m, goes through FloodPulse to OpenStreetMap Nominatim; nothing is stored. For automatic naming, consented coordinates may be sent to BigDataCloud (<a href="https://www.bigdatacloud.com/docs/article/fair-use-policy-for-free-client-side-reverse-geocoding-api">fair-use policy</a>); network estimates have unknown uncertainty, so confirm your town before travel.{point?.name_source && <> Place label: <a href={point.name_source.url || 'https://www.maptiler.com/copyright/'}>{point.name_source.provider}</a>{point.name_accuracy && ' · approximate; not a verified administrative boundary'}.</>}</p>
          </Popup></p></section> },
        !wide && point && { id: 'weather', label: 'Weather', content: <WeatherStrip point={point} session={session} /> },
        { id: 'risk', label: 'Risk', content: <RiskAreaDashboard area={area} risk={risk} point={point} kind={kind} onKind={setKind} onFocus={c => { setFocus(c); setTab('map') }} /> },
        { id: 'map', label: 'Map', content: <HomeFloodMap fitViewport point={point} navigate={navigate} onReportHere={onReportHere} area={area.data} kind={kind} onKind={setKind} focus={focus} onChoose={choosePoint} districts={districts.data} userDistrict={official.data?.imd?.imd_name || null} /> },
      ]} />
    </div>
  </div>
}
