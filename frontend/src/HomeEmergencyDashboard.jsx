import React, { useMemo } from 'react'
import LocationDirectorySelector from './LocationDirectorySelector.jsx'
import HomeFloodMap from './HomeFloodMap.jsx'
import useShelterDirectory from './useShelterDirectory.js'
import { PageLink } from './AppNavigation.jsx'
import { clock, next24Rainfall, usableCurrent, validHistoricalFeature } from './homeEvidence.js'
import { classifyCoverage } from './homeGeography.js'
import useHomeViewport from './useHomeViewport.js'
import './HomeEmergencyDashboard.css'
const FLOOD_UNAVAILABLE = 'Validated flood forecast unavailable for this location.'
export default function HomeEmergencyDashboard({ point, district, districtId, session, overview, location, choosePoint, chooseDistrict, navigate, onEvidence }) {
  const { dashboard, fits } = useHomeViewport()
  const directory = useShelterDirectory(point, true)
  const shelters = useMemo(() => directory.data?.mode === 'live' ? directory.data.shelters.filter(s => !districtId || s.district_id === districtId) : [], [directory.data, districtId])
  const features = useMemo(() => (overview.data?.geojson?.features || []).filter(validHistoricalFeature), [overview.data])
  const now = Date.now(), weather = point ? session.data : null
  const current = usableCurrent(weather, session.freshness, now)
  const rainfall = session.freshness === 'fresh' && weather ? next24Rainfall(weather, now) : null
  const gpsCoverage = point?.kind === 'gps' ? classifyCoverage(point) : null
  const gpsNotice = gpsCoverage === 'outside' ? 'Your location is outside Karnataka. Point weather may be available; Karnataka flood evidence does not cover this location.' : ['uncertain', 'unknown'].includes(gpsCoverage) ? 'State-boundary coverage and district association are unconfirmed for this GPS point.' : null
  const loading = point && session.loading
  const weatherStatus = !point ? 'Select a place for point weather.' : loading ? 'Loading weather…' : !current ? 'Current weather unavailable.' : `${current.temperature_c} °C`
  const currentRain = current && Number.isFinite(current.precipitation_mm) && current.precipitation_mm >= 0 && Number.isFinite(current.interval_seconds) && current.interval_seconds > 0 ? `${current.precipitation_mm} mm precipitation in the preceding ${current.interval_seconds / 60} minutes.` : 'Current conditions description unavailable.'
  return <div ref={dashboard} className={'home-emergency-dashboard' + (fits ? ' home-viewport-fit' : '')}>
    <section className="home-location-bar" aria-label="Home location selection"><div><p className="eyebrow">YOUR LOCATION</p><h2>{point?.name || 'Karnataka statewide view'}</h2><p role="status">{location.message}</p>{gpsNotice && !location.message.includes(gpsNotice) && <p role="status">{gpsNotice}</p>}</div><div className="home-location-actions"><button onClick={location.request} disabled={location.status === 'requesting'}>Use my location</button><LocationDirectorySelector onChoose={choosePoint} onDistrict={chooseDistrict} selectedDistrictId={districtId} collapseOnChoose /></div></section>
    <div className="home-summary-cards" aria-label="Essential summaries">
      <section className="home-summary-card"><p className="eyebrow">CURRENT WEATHER</p><h2>{weatherStatus}</h2><small>{current ? `Valid ${clock(current.valid_at)} · model estimate` : 'Open-Meteo weather model'}</small></section>
      <section className="home-summary-card"><p className="eyebrow">RAINFALL FORECAST</p><h2>{rainfall ? `${Number(rainfall.mm.toFixed(2))} mm` : 'Next-24-hour total unavailable'}</h2><p>{rainfall ? `${clock(rainfall.start)} to ${clock(rainfall.end)}` : 'Whole-window forecast unavailable.'}</p></section>
      <section className="home-summary-card home-flood-summary"><p className="eyebrow">FLOOD FORECAST</p><h2>{FLOOD_UNAVAILABLE}</h2><p>Missing forecasts do not mean no flood risk.</p></section>
    </div>
    <div className="home-main-grid">
      <section className="panel workspace-information home-area-summary" aria-labelledby="home-area-title"><div className="home-essential-status"><h2 id="home-area-title">Your Area Emergency Summary</h2><p><strong>Flood forecast unavailable.</strong> Rainfall alone cannot confirm flooding.</p><p>Official warning feed: <strong>Not connected</strong>. This does not establish that no emergency exists. Follow official local advice.</p></div>
        <div className="home-area-scroll" role="region" aria-label="Additional area information" tabIndex={0}>
        <article><h3>Weather & upcoming rain</h3><p>{current ? `The weather model estimates ${current.temperature_c} °C at your selected point. ${currentRain}` : weatherStatus}</p><p>{rainfall ? `Forecast precipitation: ${Number(rainfall.mm.toFixed(2))} mm over the displayed 24-hour window. Local conditions can differ.` : 'An exact next-24-hour rainfall total is unavailable. Calendar-day forecasts are available on Weather & AI.'}</p>{point && session.error && <p role="alert">{session.error}</p>}<details className="home-source-details"><summary>Weather source & freshness</summary><p>Weather freshness: {point ? session.freshness : 'unavailable'}{weather?.retrieved_at && ` · retrieved ${clock(weather.retrieved_at)}`}. Forecast issue time is not supplied. Open-Meteo model output, CC BY 4.0.</p></details><div className="home-detail-links"><PageLink to="/weather" navigate={navigate}>Weather details</PageLink>{point && <button onClick={() => session.refresh(point)} disabled={session.loading}>Refresh weather</button>}</div></article>
        <article><h3>Historical flood evidence</h3><p>{overview.data ? `${features.length} reviewed historical cells` : 'Historical coverage unavailable'}. {overview.data && features.length < overview.data.total && `${overview.data.total} source records reported; only eligible returned cells are shown.`}</p>{districtId && <p>Historical and shelter district filter: <strong>{district?.name || districtId}</strong>. Weather remains specific to the selected point.</p>}<p>Reviewed satellite observations currently cover selected Udupi event cells. They do not establish current conditions or coverage across Karnataka.</p>{overview.error && <p role="status">{overview.error}</p>}<p>Published hazard zones: <strong>No verified polygons</strong>.</p><details className="home-source-details"><summary>Historical sources & limitations</summary><p>History: <a href="https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1">Global Flood Database V1</a> · Cloud to Street / Dartmouth Flood Observatory · Tellman et al. (2021) · CC BY-NC 4.0. Past event-window observations; missing observations remain unknown.</p></details><div className="home-detail-links"><PageLink to="/flood-map" navigate={navigate}>Inspect sources and historical evidence</PageLink></div></article>
        <article><div className="home-shelter-heading"><h3>{point ? 'Verified Open shelters near your point' : 'Verified Open shelters'}</h3><button onClick={() => directory.refresh()} disabled={directory.loading}>Refresh shelters</button></div>
          {directory.loading && <p role="status">Checking shelter directory…</p>}{directory.error && <p role="alert">{directory.error}. No substitute destinations are shown.</p>}
          {directory.data?.mode === 'demonstration' && <p role="alert">DEMONSTRATION ONLY — test assignments are excluded from emergency destinations.</p>}
          {directory.data?.mode === 'live' && !shelters.length && <p role="status">No currently verified open shelters are available in this directory.</p>}
          {!!shelters.length && <ul className="home-shelter-list" aria-label="Nearby verified shelter destinations">{shelters.slice(0, 3).map(s => <li key={s.id}><strong>{s.name}</strong><span>{s.available_capacity} reported spaces{point && Number.isFinite(s.straight_line_km) ? ` · ${s.straight_line_km} km straight-line distance` : ''}</span><small>Verified {clock(s.verified_at)} · expires {clock(s.verification_expires_at)}</small></li>)}</ul>}
          <p>Capacity is not a reservation. Confirm availability and road access before travel. Directions are not verified flood-safe.</p><small>Administrator-reported availability: {directory.freshness}{directory.checkedAt && ` · checked ${clock(directory.checkedAt)}`}. Rechecked at least every minute while active.</small><div className="home-detail-links"><PageLink to="/shelters" navigate={navigate}>View shelter details and recheck directions</PageLink></div>
        </article>
        </div>
      </section>
      <HomeFloodMap fitViewport={fits} point={point} gps={location.gps} features={features} shelters={shelters} navigate={navigate} onEvidence={onEvidence} />
    </div>
  </div>
}
