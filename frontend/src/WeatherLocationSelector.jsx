import React, { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import './WeatherLocationSelector.css'

export const DEFAULT_POINT = { name: 'Bengaluru, Karnataka', latitude: 12.9767936, longitude: 77.5900820 }

function WeatherPointMap({ point, onSelect }) {
  const container = useRef(null)
  const map = useRef(null)
  const marker = useRef(null)
  const select = useRef(onSelect)
  const [tileError, setTileError] = useState(false)
  select.current = onSelect

  useEffect(() => {
    const view = L.map(container.current, { scrollWheelZoom: false }).setView([15.1, 76.1], 6)
    map.current = view
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(view)
    tiles.on('tileerror', () => setTileError(true))
    view.on('click', event => {
      const { lat, lng } = event.latlng
      const longitude = lng < -180 || lng > 180 ? ((lng + 180) % 360 + 360) % 360 - 180 : lng
      select.current({ name: 'Selected map point', latitude: lat, longitude })
    })
    return () => { view.remove(); map.current = null; marker.current = null }
  }, [])

  useEffect(() => {
    if (!map.current) return
    if (marker.current) map.current.removeLayer(marker.current)
    marker.current = L.circleMarker([point.latitude, point.longitude], {
      radius: 7, color: '#1b625d', fillOpacity: 0.8,
    }).addTo(map.current)
  }, [point])

  return <>
    <div ref={container} className="weather-location-map" role="region" aria-label="Weather location selection map" />
    <div className="weather-map-actions">
      <button type="button" onClick={() => map.current?.setView([15.1, 76.1], 6)}>Show Karnataka view</button>
      <button type="button" onClick={() => map.current?.setView([point.latitude, point.longitude], 12)}>Show selected point</button>
    </div>
    <p className="muted">Click the map to choose weather coordinates. The marker identifies a point; no flood-risk zones or district identities are assigned.</p>
    {tileError && <p className="notice">Background tiles are unavailable. Coordinate entry and the selected-point marker remain usable.</p>}
  </>
}

export default function WeatherLocationSelector({ point = DEFAULT_POINT, onSelect }) {
  const [latitude, setLatitude] = useState(String(point.latitude))
  const [longitude, setLongitude] = useState(String(point.longitude))
  const [showMap, setShowMap] = useState(false)
  const [error, setError] = useState(null)
  const [locating, setLocating] = useState(false)
  const selection = useRef(0)

  useEffect(() => { setLatitude(String(point.latitude)); setLongitude(String(point.longitude)) }, [point])
  useEffect(() => () => { selection.current++ }, [])

  function choose(next) {
    selection.current++; setLocating(false); setError(null)
    onSelect(next)
  }

  function submit(event) {
    event.preventDefault()
    const lat = latitude.trim() === '' ? NaN : Number(latitude)
    const lon = longitude.trim() === '' ? NaN : Number(longitude)
    if (!Number.isFinite(lat) || lat < -90 || lat > 90 || !Number.isFinite(lon) || lon < -180 || lon > 180) {
      setError('Enter latitude from −90 to 90 and longitude from −180 to 180.'); return
    }
    choose({ name: 'Entered coordinates', latitude: lat, longitude: lon })
  }

  function locate() {
    if (!navigator.geolocation) { setError('GPS is unavailable in this browser. Enter coordinates or select the map.'); return }
    const request = ++selection.current
    setError(null); setLocating(true)
    navigator.geolocation.getCurrentPosition(position => {
      if (selection.current !== request) return
      const { latitude: lat, longitude: lon, accuracy } = position.coords
      if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
        setLocating(false); setError('GPS returned invalid coordinates. Use the map or coordinate entry.'); return
      }
      choose({ name: 'GPS-selected point', latitude: lat, longitude: lon,
        accuracy_m: Number.isFinite(accuracy) && accuracy >= 0 ? accuracy : null })
    }, failure => {
      if (selection.current !== request) return
      setLocating(false)
      setError(failure.code === 1 ? 'Location permission denied. Use the map or coordinate entry.' : 'GPS could not determine your location. Use the map or coordinate entry.')
    }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 0 })
  }

  return <section className="panel weather-location-selector" aria-labelledby="weather-location-title">
    <p className="eyebrow">EXPLORE WEATHER</p>
    <h2 id="weather-location-title">Choose a weather location</h2>
    <p>Start from Karnataka, select a map point or enter WGS84 coordinates. Point weather does not verify administrative boundaries.</p>
    <form onSubmit={submit} className="weather-coordinate-form">
      <label>Latitude<input aria-label="Weather latitude" type="number" step="any" min="-90" max="90" required value={latitude} onChange={e => setLatitude(e.target.value)} /></label>
      <label>Longitude<input aria-label="Weather longitude" type="number" step="any" min="-180" max="180" required value={longitude} onChange={e => setLongitude(e.target.value)} /></label>
      <button type="submit">Get point weather</button>
    </form>
    <div className="weather-map-actions">
      <button type="button" aria-expanded={showMap} onClick={() => setShowMap(value => !value)}>{showMap ? 'Hide weather map' : 'Open weather map'}</button>
      <button type="button" onClick={locate} disabled={locating}>{locating ? 'Locating…' : 'Use my GPS location'}</button>
      <button type="button" onClick={() => choose(DEFAULT_POINT)}>Reset to Bengaluru</button>
    </div>
    <p className="muted">GPS is requested only when you choose it. Coordinates are sent through FloodPulse to Open-Meteo for this weather request.</p>
    {error && <p className="notice error" role="alert">{error}</p>}
    {point.accuracy_m != null && <p className="muted">Device-reported location accuracy: approximately {Math.round(point.accuracy_m)} metres.</p>}
    {showMap && <WeatherPointMap point={point} onSelect={choose} />}
  </section>
}
