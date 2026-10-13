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
export default function HomeFloodMap({ fitViewport, point, river, navigate }) {
  const gps = point?.kind === 'gps' ? point : null
  const element = useRef(null), map = useRef(null), stateBounds = useRef(null), actions = useRef({ navigate })
  const [tileError, setTileError] = useState(false)
  actions.current = { navigate }
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
    if (point?.name_source?.provider !== 'MapTiler' || !map.current) return
    const attribution = '<a href="https://www.maptiler.com/copyright/">© MapTiler place label</a>'
    map.current.attributionControl.addAttribution(attribution)
    return () => map.current?.attributionControl.removeAttribution(attribution)
  }, [point?.name_source?.provider])
  useEffect(() => {
    if (!map.current) return
    // The first viewport fit changes the canvas after Leaflet's initial bounds.
    // Refresh its size before framing statewide fallback; selected points stay put.
    map.current.invalidateSize({ pan: false })
    if (!point && stateBounds.current) map.current.fitBounds(stateBounds.current, { padding: [20, 20], maxZoom: 7, animate: false })
  }, [fitViewport])
  useEffect(() => {
    if (!map.current) return
    const layers = L.layerGroup().addTo(map.current)
    if (gps) {
      L.circleMarker([gps.latitude, gps.longitude], { bubblingMouseEvents: false, radius: 7, color: '#286ba4', fillOpacity: .9 }).bindPopup(popup(`Actual GPS point · ${Number.isFinite(gps.accuracy_m) ? `browser-reported accuracy ±${Math.round(gps.accuracy_m)} m` : 'accuracy unavailable'}. District unconfirmed.`, 'Point weather details', '/weather', () => actions.current.navigate('/weather'))).addTo(layers)
      // Very large uncertainty circles obscure the entire state; report their radius in text instead.
      if (gps.accuracy_m > 0 && gps.accuracy_m <= 10000) L.circle([gps.latitude, gps.longitude], { radius: gps.accuracy_m, color: '#286ba4', weight: 1, fillOpacity: .08, interactive: false }).addTo(layers)
    }
    if (point && point.kind !== 'gps') L.circleMarker([point.latitude, point.longitude], { bubblingMouseEvents: false, radius: 7, color: '#087e7c', fillOpacity: .9 }).bindPopup(popup(`${point.name} · ${point.locality_id ? 'reviewed locality point' : 'selected weather point; locality unconfirmed'}.`, 'Point weather details', '/weather', () => actions.current.navigate('/weather'))).addTo(layers)
    if (river?.reach?.verified_grid === true) {
      const grid = river.grid_location
      L.circleMarker([grid.latitude, grid.longitude], { bubblingMouseEvents: false, radius: 7, color: '#6951a3', fillOpacity: .9 }).bindPopup(popup(`${river.reach.name} · verified model cell; daily GloFAS v4 discharge, not a flood boundary or observed water level.`, 'Inspect Flood Map context', '/flood-map', () => actions.current.navigate('/flood-map'))).addTo(layers)
    }
    return () => { if (map.current) map.current.removeLayer(layers) }
  }, [point, river])
  useEffect(() => {
    if (!map.current || !point) return
    map.current.setView([point.latitude, point.longitude], point.accuracy_m > 10000 ? 8 : point.accuracy_m > 1000 ? 11 : 13, { animate: false })
  }, [point?.latitude, point?.longitude, point?.accuracy_m])
  function statewide() { if (stateBounds.current) map.current?.fitBounds(stateBounds.current, { padding: [20, 20], maxZoom: 7, animate: false }) }
  return <section className="panel workspace-map home-map-stage" aria-labelledby="home-map-title">
    <div className="home-map-toolbar"><div className="home-map-heading"><div><p className="eyebrow">EVIDENCE & ASSISTANCE</p><h2 id="home-map-title">Karnataka Map</h2></div><PageLink to="/flood-map" navigate={navigate}>Full map</PageLink></div>
    <div className="map-actions"><button onClick={statewide}>Show Karnataka</button><button onClick={()=>point&&map.current?.setView([point.latitude,point.longitude],13,{animate:false})} disabled={!point}>Show selected point</button></div></div>
    <div ref={element} className="home-flood-map" role="region" aria-label="Karnataka emergency map" />
    {tileError && <p className="notice home-tile-notice" role="status">{BASEMAP_NOTICE}</p>}
    <div className="home-map-footer"><ul className="home-map-legend" aria-label="Map legend"><li><i className="gps"/>GPS point</li><li><i className="locality"/>Selected place</li>{river&&<li><i className="river"/>Reviewed river model cell</li>}</ul>
    <details className="home-map-notes"><summary>Map sources & limitations</summary><p className="home-map-limitations">Points are locations, not flooded-area polygons. River cells appear only with a verified association. Official warning geometry is unavailable. State outline: simplified 2011 context; border coverage is uncertain.</p></details></div>
  </section>
}
