import React, { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { addBasemap, BASEMAP_NOTICE } from './mapBasemap.js'
import useMapResize from './useMapResize.js'
import { boundary, KARNATAKA_CENTER } from './homeGeography.js'
import { PageLink } from './AppNavigation.jsx'

function popup(text, label, href, action) {
  const box = document.createElement('div'), p = document.createElement('p'), link = document.createElement('a')
  p.textContent = text; link.textContent = label; link.href = href
  link.addEventListener('click', event => { if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); action() } })
  box.append(p, link); return box
}
export default function HomeFloodMap({ point, gps, features, shelters, navigate, onEvidence }) {
  gps = point?.kind === 'gps' ? point : gps
  const element = useRef(null), map = useRef(null), stateBounds = useRef(null), actions = useRef({ navigate, onEvidence })
  const [tileError, setTileError] = useState(false)
  actions.current = { navigate, onEvidence }
  useEffect(() => {
    const view = L.map(element.current, { scrollWheelZoom: false }).setView(KARNATAKA_CENTER, 6); map.current = view
    addBasemap(L, view, () => setTileError(true))
    const outline = L.geoJSON(boundary, { interactive: false, style: { color: '#567c73', weight: 1.5, fillOpacity: 0.025 } }).addTo(view)
    stateBounds.current = outline.getBounds(); view.fitBounds(stateBounds.current, { padding: [20, 20], maxZoom: 7, animate: false })
    view.attributionControl.addAttribution('<a href="https://www.geoboundaries.org/">geoBoundaries</a> / DataMeet / Election Commission of India · <a href="https://creativecommons.org/licenses/by/2.5/in/">CC BY 2.5 IN</a>')
    view.on('click', event => L.popup().setLatLng(event.latlng).setContent(popup('No validated flood forecast is available here. Missing evidence does not mean no flood risk.', 'Open Flood Map evidence', '/flood-map', () => actions.current.navigate('/flood-map'))).openOn(view))
    return () => { view.remove(); map.current = null }
  }, [])
  useMapResize(map)
  useEffect(() => {
    if (!map.current) return
    const layers = L.layerGroup().addTo(map.current)
    if (gps) {
      L.circleMarker([gps.latitude, gps.longitude], { bubblingMouseEvents: false, radius: 7, color: '#286ba4', fillOpacity: .9 }).bindPopup(popup(`Actual GPS point · ${Number.isFinite(gps.accuracy_m) ? `browser-reported accuracy ±${Math.round(gps.accuracy_m)} m` : 'accuracy unavailable'}. District unconfirmed.`, 'Point weather details', '/weather', () => actions.current.navigate('/weather'))).addTo(layers)
      // Very large uncertainty circles obscure the entire state; report their radius in text instead.
      if (gps.accuracy_m > 0 && gps.accuracy_m <= 10000) L.circle([gps.latitude, gps.longitude], { radius: gps.accuracy_m, color: '#286ba4', weight: 1, fillOpacity: .08, interactive: false }).addTo(layers)
    }
    if (point && point.kind !== 'gps') L.circleMarker([point.latitude, point.longitude], { bubblingMouseEvents: false, radius: 7, color: '#087e7c', fillOpacity: .9 }).bindPopup(popup(`${point.name} · ${point.locality_id ? 'reviewed locality point' : 'selected weather point; locality unconfirmed'}.`, 'Point weather details', '/weather', () => actions.current.navigate('/weather'))).addTo(layers)
    if (features.length) L.geoJSON({ type: 'FeatureCollection', features }, { bubblingMouseEvents: false, style: { color: '#9c3627', weight: 1.5, fillColor: '#dc6047', fillOpacity: .65 }, onEachFeature: (feature, layer) => { layer.options.bubblingMouseEvents = false; layer.bindPopup(popup(`Historical observed floodwater · ${feature.properties.district} · ${feature.properties.start_date} to ${feature.properties.end_date_inclusive} (UTC source dates). Observation cells, not current flood boundaries.`, 'Inspect historical evidence', '/flood-map', () => { actions.current.onEvidence(feature.id || feature.properties.feature_id); actions.current.navigate('/flood-map') })) } }).addTo(layers)
    for (const s of shelters) L.circleMarker([s.latitude, s.longitude], { bubblingMouseEvents: false, radius: 8, color: '#167044', fillColor: '#3da86e', fillOpacity: .9 }).bindPopup(popup(`${s.name} · ${s.available_capacity} reported spaces. Confirm availability and road access before travel.`, 'Recheck shelter details', '/shelters', () => actions.current.navigate('/shelters'))).addTo(layers)
    return () => { if (map.current) map.current.removeLayer(layers) }
  }, [point, gps, features, shelters])
  useEffect(() => {
    if (!map.current || !point) return
    map.current.setView([point.latitude, point.longitude], point.accuracy_m > 10000 ? 8 : point.accuracy_m > 1000 ? 11 : 13, { animate: false })
  }, [point?.latitude, point?.longitude, point?.accuracy_m])
  function statewide() { if (stateBounds.current) map.current?.fitBounds(stateBounds.current, { padding: [20, 20], maxZoom: 7, animate: false }) }
  function historyView() { if (features.length) map.current?.fitBounds(L.geoJSON({ type: 'FeatureCollection', features }).getBounds(), { padding: [25, 25], maxZoom: 13, animate: false }) }
  return <section className="panel workspace-map home-map-stage" aria-labelledby="home-map-title">
    <div className="home-map-heading"><div><p className="eyebrow">EVIDENCE & ASSISTANCE</p><h2 id="home-map-title">Karnataka Flood Map</h2></div><PageLink to="/flood-map" navigate={navigate}>Full map</PageLink></div>
    <div className="map-actions"><button onClick={statewide}>Show Karnataka</button><button onClick={historyView} disabled={!features.length}>Show historical evidence</button></div>
    <div ref={element} className="home-flood-map" role="region" aria-label="Karnataka emergency map" />
    {tileError && <p className="notice home-tile-notice" role="status">{BASEMAP_NOTICE}</p>}
    <ul className="home-map-legend" aria-label="Map legend"><li><i className="gps"/>GPS point</li><li><i className="locality"/>Selected place</li><li><i className="history"/>Historical floodwater</li><li><i className="shelter"/>Verified Open shelter</li></ul>
    <p className="home-map-limitations">Historical cells are past observations, not live flooding. Hazard and official forecast geometry are unavailable. State outline: simplified 2011 context; border coverage is uncertain.</p>
  </section>
}
