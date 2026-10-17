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

export default function ShelterNavigation({ shelter, origin, listed, demonstration, mode, onMode, link, onRecheck, rechecking, onClose }) {
  const embed = useEmbedKey()
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
        <p>From <strong>{origin.name}</strong>{shelter.straight_line_km !== null && ` · ${shelter.straight_line_km} km straight line`}</p>
        <div className="risk-area-toggle" role="group" aria-label="Travel mode">{MODES.map(([value, label]) => <button key={value} type="button" aria-pressed={mode === value} onClick={() => onMode(value)}>{label}</button>)}</div>
      </div>
      {embed.status === 'available'
        ? <iframe key={mode} className="shelter-navigation-frame" title="Google Maps route to the shelter" src={embedUrl(embed.key, origin, shelter, mode)} loading="lazy" referrerPolicy="strict-origin-when-cross-origin" allowFullScreen />
        : <>{embed.status !== 'loading' && <p className="notice" role="status">The in-app Google route preview is not set up{embed.status === 'invalid_configuration' ? ' (the configured key is not valid)' : ''}. Your start point and the shelter are shown below; start navigation in Google Maps for the route.</p>}
          <ShelterMap points={[{ ...shelter, label: '1', name: shelter.name }]} origin={origin} label="Start point and shelter entrance" /></>}
      <div className="shelter-navigation-actions">
        {start
          ? <a className="button-link" href={start} target="_blank" rel="noopener noreferrer">{demonstration ? 'Open Google Maps (demonstration — not for travel)' : 'Start navigation in Google Maps'}</a>
          : <button type="button" onClick={onRecheck} disabled={rechecking}>{rechecking ? 'Rechecking availability…' : 'Recheck and start navigation'}</button>}
        <p className="muted">{start ? 'Availability was just rechecked. This button stays active for five seconds.' : 'Availability is rechecked right before Google Maps opens.'} On phones this opens the Google Maps app for turn-by-turn directions.</p>
      </div>
      <p className="shelter-safety">Google's route is not checked for flooding, landslides or road closures. Never walk or drive through flood water; follow police and district instructions.</p>
      <p className="muted">Your start point and the shelter location are sent to Google to draw this route. Google Maps · route © Google.</p>
    </>}
  </section>
}
