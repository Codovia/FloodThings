import React, { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import useMapResize from './useMapResize.js'
import { addBasemap, BASEMAP_NOTICE } from './mapBasemap.js'
import 'leaflet/dist/leaflet.css'
import './WeatherLocationSelector.css'
import LocationDirectorySelector from './LocationDirectorySelector.jsx'
import Popup from './Popup.jsx'
import { preciseLocation, locationQuality, QUICK_ACCURACY_M } from './preciseLocation.js'

export const DEFAULT_POINT = { name: 'Bengaluru, Karnataka', latitude: 12.9767936, longitude: 77.5900820 }

export function WeatherPointMap({ point, onSelect, navigationBounds, historical = null }) {
  const container = useRef(null)
  const map = useRef(null)
  const marker = useRef(null)
  const select = useRef(onSelect)
  const [tileError, setTileError] = useState(false)
  select.current = onSelect

  useEffect(() => {
    const view = L.map(container.current, { scrollWheelZoom: false }).setView([15.1, 76.1], 6)
    map.current = view
    addBasemap(L, view, () => setTileError(true))
    view.on('click', event => {
      const { lat, lng } = event.latlng
      const longitude = lng < -180 || lng > 180 ? ((lng + 180) % 360 + 360) % 360 - 180 : lng
      select.current({ name: 'Selected map point', kind: 'map', latitude: lat, longitude })
    })
    return () => { view.remove(); map.current = null; marker.current = null }
  }, [])

  useEffect(() => {
    if (!map.current) return
    if (marker.current) map.current.removeLayer(marker.current)
    marker.current = L.circleMarker([point.latitude, point.longitude], {
      radius: 7, color: '#1b625d', fillOpacity: 0.8,
    }).addTo(map.current)
    if (point.locality_id) map.current.setView([point.latitude, point.longitude], 12, { animate: false })
  }, [point])

  useEffect(() => {
    if (navigationBounds && map.current) map.current.fitBounds(navigationBounds, { animate: false })
  }, [navigationBounds])

  useEffect(() => {
    if (!map.current || !historical) return
    // Historical context is never used to select a weather point or infer risk.
    const layers = []
    if (historical.boundary) layers.push(L.geoJSON(historical.boundary, {style:{color:'#50736e',weight:2,fillOpacity:0.025}}).addTo(map.current))
    if (historical.geojson) layers.push(L.geoJSON(historical.geojson, {bubblingMouseEvents:false,style:{color:'#9c3627',weight:1.5,fillColor:'#dc6047',fillOpacity:0.75}}).addTo(map.current))
    return () => { if (map.current) layers.forEach(layer => map.current.removeLayer(layer)) }
  }, [historical])

  useMapResize(map)
  return <>
    <div ref={container} className="weather-location-map" role="region" aria-label="Weather location selection map" />
    <div className="weather-map-actions">
      <button type="button" onClick={() => map.current?.setView([15.1, 76.1], 6)}>Show Karnataka view</button>
      <button type="button" onClick={() => map.current?.setView([point.latitude, point.longitude], 12)}>Show selected point</button>
    </div>
    <p className="muted">Click the map to select a point for weather. The marker identifies a point; no flood-risk zones or district identities are assigned.</p>
    {tileError && <p className="notice">{BASEMAP_NOTICE}</p>}
  </>
}

export default function WeatherLocationSelector({ point = DEFAULT_POINT, onSelect, mapInitiallyOpen = false, compact = false, overview = false, onDistrict = () => {}, selectedDistrictId, active = true, externalMap = false, chosen = true }) {
  const [showMap, setShowMap] = useState(mapInitiallyOpen)
  const [navigationBounds, setNavigationBounds] = useState(null)
  const [error, setError] = useState(null)
  const [locating, setLocating] = useState(false)
  const [progress, setProgress] = useState(null)
  const selection = useRef(0), watch = useRef(null)

  useEffect(() => { if (mapInitiallyOpen) setShowMap(true) }, [mapInitiallyOpen])
  useEffect(() => () => { selection.current++; watch.current?.abort() }, [])

  function choose(next) {
    selection.current++; watch.current?.abort(); setLocating(false); setError(null)
    setNavigationBounds(null)
    onSelect(next)
  }

  // `done` closes the Change location popup once a point is set; errors keep it open so they stay readable.
  function locate(done = () => {}) {
    if (!navigator.geolocation) { setError('GPS is unavailable in this browser. Select a verified place or the map.'); return }
    const request = ++selection.current
    watch.current?.abort(); watch.current = new AbortController()
    setError(null); setLocating(true); setProgress(null)
    // High accuracy, refined for a few seconds (see preciseLocation.js); progress shows on the button.
    preciseLocation({ good: QUICK_ACCURACY_M, signal: watch.current.signal, onProgress: p => { if (selection.current === request) setProgress(Math.round(p.coords.accuracy)) } }).then(position => {
      if (selection.current !== request) return
      const { latitude: lat, longitude: lon, accuracy } = position.coords
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
        setLocating(false); setError('GPS returned invalid coordinates. Use verified place search or the map.'); return
      }
      choose({ name: 'GPS-selected point', kind: 'gps', latitude: lat, longitude: lon, gps_timestamp: position.timestamp,
        accuracy_m: Number.isFinite(accuracy) && accuracy >= 0 ? accuracy : null }); done()
    }, failure => {
      if (selection.current !== request) return
      setLocating(false)
      setError(failure?.code === 1 ? 'Location permission denied. Use verified place search or the map.' : 'GPS could not determine your location. Use verified place search or the map.')
    })
  }

  const quality = point.kind === 'gps' ? locationQuality(point.accuracy_m) : null
  const controls = (done = () => {}) => <>
    <LocationDirectorySelector active={active} selectedDistrictId={selectedDistrictId} onChoose={next => { setShowMap(true); choose(next); done() }} onDistrict={district => {
      selection.current++; setLocating(false); setError(null)
      onDistrict(district)
      setNavigationBounds(district?.navigation_bounds || null)
      if (district?.navigation_bounds) setShowMap(true)
    }} />
    <div className="weather-map-actions">
      {!compact&&!externalMap&&<button type="button" aria-expanded={showMap} onClick={() => setShowMap(value => !value)}>{showMap ? 'Hide weather map' : 'Open weather map'}</button>}
      <button type="button" onClick={() => locate(done)} disabled={locating}>{!locating ? 'Use my GPS location' : progress !== null ? `±${progress} m, improving…` : 'Locating…'}</button>
      <button type="button" onClick={() => { choose(DEFAULT_POINT); done() }}>Reset to Bengaluru</button>
    </div>
    <p className="muted">GPS is requested only when you choose it. Coordinates are sent through FloodPulse to Open-Meteo for this weather request.</p>
    {error && <p className="notice error" role="alert">{error}</p>}
    {quality && <p className={`location-quality ${quality.level}`}><strong>{quality.label}</strong> GPS {quality.shown} (device-reported)</p>}
    {quality?.advice && <p className="location-advice">{quality.advice}</p>}
    </>
  const mapVisible = overview || showMap
  // One-screen rule: the compact box is one line; changing the place happens in a popup.
  if (compact && !overview) return <section className="panel weather-location-selector compact-location" aria-labelledby="weather-location-title">
    <div className="location-bar"><h2 id="weather-location-title" className="visually-hidden">Location & map</h2><p className="selected-point-name">{chosen ? <><span>Location: {point.name}</span><span className="label-long"> · {Number(point.latitude.toFixed(4))}°, {Number(point.longitude.toFixed(4))}°</span></> : 'Location: not chosen yet. Choose one to sort shelters by distance and get directions.'}</p>
    {!externalMap&&<button type="button" className="secondary" aria-expanded={showMap} onClick={()=>setShowMap(value=>!value)}>{showMap?'Hide weather map':'Open weather map'}</button>}
    <Popup label="Change location" buttonClassName="secondary" title="Change location">{close => <><p className="muted">Search verified places or use GPS. A point does not describe a whole district.</p>{controls(close)}</>}</Popup></div>
    {showMap&&!externalMap&&<div className="point-map"><WeatherPointMap point={point} onSelect={choose} navigationBounds={navigationBounds}/></div>}
  </section>
  return <section className={'panel weather-location-selector'+(compact?' compact-location':'')} aria-labelledby="weather-location-title">
    <div className="location-bar"><div><p className="eyebrow">{overview?'KARNATAKA · SELECTED POINT':'SELECTED POINT'}</p><h2 id="weather-location-title">{compact?'Location & map':'Choose a weather location'}</h2><p className="selected-point-name">{chosen ? `${point.name} · ${Number(point.latitude.toFixed(4))}°, ${Number(point.longitude.toFixed(4))}°` : 'No location chosen yet. Use Change location to sort shelters by distance and get directions.'}</p></div>
    {compact&&!overview&&!externalMap&&<button type="button" aria-expanded={showMap} onClick={()=>setShowMap(value=>!value)}>{showMap?'Hide weather map':'Open weather map'}</button>}</div>
    {compact?null:<>{controls()}</>}
    {mapVisible&&!externalMap&&<div className="point-map"><WeatherPointMap point={point} onSelect={choose} navigationBounds={navigationBounds}/></div>}
  </section>
}
