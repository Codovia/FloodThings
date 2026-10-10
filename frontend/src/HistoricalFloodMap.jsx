import React, { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { addBasemap } from './mapBasemap.js'
import 'leaflet/dist/leaflet.css'

const SOURCE_URL = 'https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1'
const LICENSE_URL = 'https://creativecommons.org/licenses/by-nc/4.0/'
const historicalNotice = 'Historical event-window maximum satellite observations. This is not current flooding, predicted risk, flooded roads or evacuation advice. It does not establish flooding on every event date.'
const formatDate = (date) => new Intl.DateTimeFormat('en-IN', { timeZone: 'UTC', dateStyle: 'medium' }).format(new Date(`${date}T00:00:00Z`))

async function getJson(url, controller) {
  const response = await fetch(url, { signal: controller.signal })
  const body = await response.json()
  if (!response.ok || body.status !== 'available') throw new Error(body.message || 'Historical geometry is unavailable.')
  return body
}

export function FloodGeography({ boundary, floodwater }) {
  const container = useRef(null)
  const map = useRef(null)
  const waterLayer = useRef(null)
  const districtLayer = useRef(null)
  const [tileError, setTileError] = useState(false)

  useEffect(() => {
    const view = L.map(container.current, { scrollWheelZoom: false })
    map.current = view
    addBasemap(L, view, () => setTileError(true))
    districtLayer.current = L.geoJSON(boundary, { style: { color: '#50736e', weight: 1.5, fillOpacity: 0.035 } }).addTo(view)
    view.fitBounds(districtLayer.current.getBounds(), { padding: [16, 16] })
    return () => { view.remove(); map.current = null; districtLayer.current = null; waterLayer.current = null }
  }, [boundary])

  useEffect(() => {
    if (!map.current) return
    if (waterLayer.current) map.current.removeLayer(waterLayer.current)
    waterLayer.current = null
    if (floodwater) {
      waterLayer.current = L.geoJSON(floodwater, {
        style: { color: '#9c3627', weight: 1.5, fillColor: '#dc6047', fillOpacity: 0.75 },
        onEachFeature: (feature, layer) => {
          const text = document.createElement('span')
          text.textContent = `Event ${feature.properties.event_id} · historical mapped cell · clear_views: ${feature.properties.clear_views}`
          layer.bindPopup(text)
        },
      }).addTo(map.current)
      map.current.fitBounds(waterLayer.current.getBounds(), { padding: [30, 30], maxZoom: 14 })
    }
  }, [boundary, floodwater])

  return <>
    <div className="map-actions">
      <button type="button" onClick={() => map.current?.fitBounds(districtLayer.current.getBounds(), { padding: [16, 16] })}>Show district</button>
      <button type="button" disabled={!floodwater} onClick={() => map.current?.fitBounds(waterLayer.current.getBounds(), { padding: [30, 30], maxZoom: 14 })}>Zoom to mapped water</button>
    </div>
    <div ref={container} className="historical-map" role="region" aria-label="Historical satellite floodwater map of Udupi" />
    <p className="muted map-legend"><span className="water-swatch" /> Historical mapped non-permanent water · District outline: geoBoundaries v6</p>
    {tileError && <p className="notice">Some background map tiles are unavailable. The district outline and historical evidence remain available.</p>}
  </>
}

export default function HistoricalFloodMap() {
  const [catalogue, setCatalogue] = useState(null)
  const [selected, setSelected] = useState('')
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(null); setCatalogue(null); setDetail(null)
    let timedOut = false
    const timeout = setTimeout(() => { timedOut = true; controller.abort() }, 15000)
    getJson('/api/historical-floods', controller).then(body => {
      if (!Array.isArray(body.events) || body.events.length !== 2 || !body.boundary) throw new Error('Historical catalogue is incomplete.')
      if (!controller.signal.aborted) { setCatalogue(body); setSelected(String(body.events[0].event_id)) }
    }).catch(err => {
      if (!controller.signal.aborted) setError(err.message)
      else if (timedOut) setError('Historical request timed out.')
    }).finally(() => { clearTimeout(timeout); if (!controller.signal.aborted || timedOut) setLoading(false) })
    return () => { clearTimeout(timeout); controller.abort() }
  }, [reload])

  useEffect(() => {
    if (!catalogue || !selected) return
    const controller = new AbortController()
    setLoading(true); setError(null); setDetail(null)
    let timedOut = false
    const timeout = setTimeout(() => { timedOut = true; controller.abort() }, 15000)
    getJson(`/api/historical-floods/${selected}`, controller).then(body => {
      if (String(body.event?.event_id) !== selected || body.floodwater?.type !== 'FeatureCollection' ||
          body.floodwater.features.length !== body.event.qualified_pixel_count) throw new Error('Historical map evidence is inconsistent.')
      if (!controller.signal.aborted) setDetail(body)
    }).catch(err => { if (!controller.signal.aborted || timedOut) setError(timedOut ? 'Historical geometry request timed out.' : err.message) })
      .finally(() => { clearTimeout(timeout); if (!controller.signal.aborted || timedOut) setLoading(false) })
    return () => { clearTimeout(timeout); controller.abort() }
  }, [catalogue, selected])

  const event = catalogue?.events.find(item => String(item.event_id) === selected)
  return <section className="panel historical-panel" aria-labelledby="historical-title">
    <p className="eyebrow">HISTORICAL SATELLITE EVIDENCE</p>
    <h2 id="historical-title">Udupi flood event maps</h2>
    <p className="historical-notice">{historicalNotice}</p>
    {catalogue && <div className="event-selector">
      <label htmlFor="historical-event">Recorded event</label>
      <select id="historical-event" value={selected} onChange={e => { setDetail(null); setSelected(e.target.value) }}>
        {catalogue.events.map(item => <option key={item.event_id} value={item.event_id}>Event {item.event_id} · {formatDate(item.start_date)} – {formatDate(item.end_date_inclusive)}</option>)}
      </select>
    </div>}
    {event && <p className="muted">Recorded window (UTC): <strong>{formatDate(event.start_date)} – {formatDate(event.end_date_inclusive)}</strong> · {event.qualified_pixel_count} observation-qualified cells · 250 m processing grid</p>}
    <div aria-live="polite" aria-busy={loading}>
      {loading && <p className="notice">Loading historical flood geometry…</p>}
      {error && <p role="alert" className="notice error">Historical map unavailable. {error} No flood-absence conclusion can be drawn. <button onClick={() => setReload(value => value + 1)}>Retry historical map</button></p>}
    </div>
    {catalogue && <FloodGeography boundary={catalogue.boundary} floodwater={detail?.floodwater || null} />}
    <p className="muted">Satellite evidence: <a href={SOURCE_URL}>Global Flood Database V1, Cloud to Street / Dartmouth Flood Observatory</a> · Tellman et al. (2021) · <a href={LICENSE_URL}>CC BY-NC 4.0</a> — attribution and non-commercial use required.</p>
    <p className="muted">Permanent water is excluded; retained cells have valid source masks and clear-view support. Clouds and map selection limit observations. The absence of a mapped cell does not establish absence of flooding.</p>
    <p className="muted">Boundary: <a href="https://developers.google.com/earth-engine/datasets/catalog/WM_geoLab_geoBoundaries_600_ADM2">geoBoundaries v6, William &amp; Mary geoLab</a> · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>. The modern district boundary is not verified as the historical administrative boundary.</p>
    {detail && <p className="muted">Spatial extraction: {new Date(detail.event.retrieved_at).toISOString()} · Source image: {detail.event.image_id}</p>}
  </section>
}
