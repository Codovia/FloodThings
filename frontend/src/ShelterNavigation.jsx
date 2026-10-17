import React, { useEffect, useState } from 'react'
import ShelterMap from './ShelterMap.jsx'

export const MODES = [['walking', 'Walking'], ['driving', 'Driving']]
const KEY = /^AIza[0-9A-Za-z_-]{35}$/
const at = p => `${p.latitude},${p.longitude}`

// Official Google Maps Embed API (directions mode): free and unlimited but needs a key.
export function embedUrl(key, origin, shelter, mode) {
  return 'https://www.google.com/maps/embed/v1/directions?' + new URLSearchParams({ key, origin: at(origin), destination: at(shelter), mode, units: 'metric', region: 'IN' })
}
// Official Maps URLs: no key; dir_action=navigate starts turn-by-turn in the Google Maps app where available.
export function navigateUrl(baseUrl, mode) {
  const url = new URL(baseUrl)
  url.searchParams.set('travelmode', mode); url.searchParams.set('dir_action', 'navigate')
  return url.toString()
}

let embedConfig = null  // one configuration request per page load
function useEmbedKey() {
  const [state, setState] = useState(embedConfig || { status: 'loading' })
  useEffect(() => {
    if (embedConfig) return
    let active = true
    fetch('/api/navigation/embed').then(r => r.json()).then(body => {
      embedConfig = body?.status === 'available' && KEY.test(body.embed_key || '') ? { status: 'available', key: body.embed_key } : { status: body?.status === 'invalid_configuration' ? 'invalid_configuration' : 'not_configured' }
    }).catch(() => { embedConfig = { status: 'unavailable' } }).finally(() => { if (active) setState(embedConfig) })
    return () => { active = false }
  }, [])
  return state
}

const PROFILE = { walking: 'foot-walking', driving: 'driving-car' }
// Flood-aware route from our backend (OpenRouteService avoiding approved flood reports), per travel mode.
function useSafeRoute(shelter, origin, mode, enabled) {
  const [routes, setRoutes] = useState({})
  const key = `${shelter.id}:${origin.latitude}:${origin.longitude}:${mode}`
  useEffect(() => {
    if (!enabled || routes[key]) return
    let active = true
    setRoutes(r => ({ ...r, [key]: { status: 'loading' } }))
    const accuracy = origin.kind === 'gps' ? origin.accuracy_m : (origin.uncertainty_m || 250)
    fetch('/api/route', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ shelter_id: shelter.id, profile: PROFILE[mode], origin: { latitude: origin.latitude, longitude: origin.longitude, accuracy_m: accuracy } }) })
      .then(async r => ({ ok: r.ok, body: await r.json() }))
      .then(({ ok, body }) => { if (active) setRoutes(rs => ({ ...rs, [key]: ok && body.status === 'available' && body.geometry?.type === 'LineString' ? body : { status: body.status && body.status !== 'available' ? body.status : 'unavailable', message: (typeof body.detail === 'string' ? body.detail : body.message) || 'Route response could not be validated.' } })) })
      .catch(() => { if (active) setRoutes(rs => ({ ...rs, [key]: { status: 'unavailable', message: 'Routing request failed.' } })) })
    return () => { active = false }
  }, [key, enabled])
  return routes[key] || { status: enabled ? 'loading' : 'idle' }
}

export default function ShelterNavigation({ shelter, origin, listed, demonstration, mode, onMode, link, onRecheck, rechecking, onClose }) {
  const embed = useEmbedKey()
  const [source, setSource] = useState('safe')
  const safe = useSafeRoute(shelter, origin, mode, listed && source === 'safe')
  const safeOff = safe.status === 'not_configured'
  const view = safeOff ? 'google' : source
  const start = link ? navigateUrl(link, mode) : null
  return <section className="shelter-navigation" aria-labelledby="shelter-navigation-title">
    <div className="shelter-navigation-head">
      <div><p className="eyebrow">NAVIGATE TO SHELTER</p><h2 id="shelter-navigation-title">Directions to {shelter.name}</h2></div>
      <button type="button" className="secondary" onClick={onClose}>Back to shelter map</button>
    </div>
    {demonstration && <p role="alert" className="notice error"><strong>DEMONSTRATION ONLY — not an actual shelter. Do not travel to this point.</strong></p>}
    {!listed && <p role="alert" className="notice error">This shelter is no longer listed as verified open with free places. Navigation stopped — go back and choose another shelter.</p>}
    {listed && <>
      <div className="shelter-navigation-bar">
        <p>From <strong>{origin.name}</strong>{shelter.straight_line_km !== null && ` · ${Number(shelter.straight_line_km).toFixed(1)} km straight line`}</p>
        <div className="risk-area-toggle" role="group" aria-label="Travel mode">{MODES.map(([value, label]) => <button key={value} type="button" aria-pressed={mode === value} onClick={() => onMode(value)}>{label}</button>)}</div>
      </div>
      {!safeOff && <div className="risk-area-toggle shelter-route-source" role="group" aria-label="Route source">
        <button type="button" aria-pressed={view === 'safe'} onClick={() => setSource('safe')}>Avoids reported flooding</button>
        <button type="button" aria-pressed={view === 'google'} onClick={() => setSource('google')}>Google route</button>
      </div>}
      <div className="shelter-navigation-actions">
        {start
          ? <a className="button-link" href={start} target="_blank" rel="noopener noreferrer">{demonstration ? 'Open Google Maps (demonstration — not for travel)' : 'Start navigation in Google Maps'}</a>
          : <button type="button" onClick={onRecheck} disabled={rechecking}>{rechecking ? 'Rechecking availability…' : 'Recheck and start navigation'}</button>}
        <p className="muted">{start ? 'Availability was just rechecked. This button stays active for five seconds.' : 'Availability is rechecked right before Google Maps opens.'} On phones this opens the Google Maps app for turn-by-turn directions.</p>
      </div>
      {view === 'safe' ? <>
        {safe.status === 'loading' && <p role="status">Planning a route that avoids approved flood reports…</p>}
        {safe.status === 'available' && <div className="route-summary" role="status">
          <p><strong>{(safe.distance_m / 1000).toFixed(1)} km · about {Math.round(safe.duration_s / 60)} min {mode === 'walking' ? 'walking' : 'driving'}</strong> · avoids {safe.avoided_reports} reported flood {safe.avoided_reports === 1 ? 'area' : 'areas'}</p>
          <p className="notice">{safe.label}</p></div>}
        {!['loading', 'available', 'idle'].includes(safe.status) && <p className="notice" role="status">{safe.message} You can use the Google route instead.</p>}
        <ShelterMap points={[{ ...shelter, label: '1', name: shelter.name }]} origin={origin} route={safe.status === 'available' ? safe.geometry : null} label="Flood-aware route to the shelter" />
        {safe.status === 'available' && <><details className="route-steps-details"><summary>Turn-by-turn directions ({safe.steps.length} steps)</summary><ol className="route-steps">{safe.steps.map((step, i) => <li key={i}>{step.instruction} ({step.distance_m} m)</li>)}</ol></details>
          <p className="muted">{safe.attribution}</p></>}
      </> : <>
      {embed.status === 'available'
          ? <iframe key={mode} className="shelter-navigation-frame" title="Google Maps route to the shelter" src={embedUrl(embed.key, origin, shelter, mode)} loading="lazy" referrerPolicy="strict-origin-when-cross-origin" allowFullScreen />
          : <>{embed.status !== 'loading' && <p className="notice" role="status">The in-app Google route preview is not set up{embed.status === 'invalid_configuration' ? ' (the configured key is not valid)' : ''}. Your start point and the shelter are shown below; start navigation in Google Maps for the route.</p>}
            <ShelterMap points={[{ ...shelter, label: '1', name: shelter.name }]} origin={origin} label="Start point and shelter entrance" /></>}
      </>}
      <p className="shelter-safety">Google's route is not checked for flooding, landslides or road closures. Never walk or drive through flood water; follow police and district instructions.</p>
      <p className="muted">Your start point and the shelter location are sent to Google to draw this route. Google Maps · route © Google.</p>
    </>}
  </section>
}
