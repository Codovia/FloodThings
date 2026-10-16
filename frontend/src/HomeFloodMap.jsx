import React, { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { addBasemap, BASEMAP_NOTICE } from './mapBasemap.js'
import useMapResize from './useMapResize.js'
import { boundary, KARNATAKA_CENTER } from './homeGeography.js'
import { PageLink } from './AppNavigation.jsx'
import { LEVEL_COLORS, LEVEL_NAMES } from './useRisk.js'
import { spotLabel, spotInputs } from './RiskAreaDashboard.jsx'

function popup(text, label, href, action) {
  const box = document.createElement('div'), p = document.createElement('p'), link = document.createElement('a')
  p.textContent = text; link.textContent = label; link.href = href
  link.addEventListener('click', event => { if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); action() } })
  box.append(p, link); return box
}
function choosePopup(lines, label, action) {
  const box = document.createElement('div')
  for (const [tag, text] of lines) { const node = document.createElement(tag); node.textContent = text; box.append(node) }
  const button = document.createElement('button'); button.type = 'button'; button.className = 'map-popup-action'; button.textContent = label
  button.addEventListener('click', action); box.append(button); return box
}
const KIND_NAME = { flood: 'Flood', drainage: 'Drainage' }
export default function HomeFloodMap({ fitViewport, point, river, navigate, area = null, kind = 'flood', focus = null, onChoose = () => {} }) {
  const gps = point?.kind === 'gps' ? point : null
  const element = useRef(null), map = useRef(null), stateBounds = useRef(null), actions = useRef({ navigate, onChoose }), squares = useRef({}), fitted = useRef(null)
  const [tileError, setTileError] = useState(false)
  actions.current = { navigate, onChoose }
  useEffect(() => {
    const view = L.map(element.current, { scrollWheelZoom: false }).setView(KARNATAKA_CENTER, 6); map.current = view
    addBasemap(L, view, () => setTileError(true))
    const outline = L.geoJSON(boundary, { interactive: false, style: { color: '#567c73', weight: 1.5, fillOpacity: 0.025 } }).addTo(view)
    stateBounds.current = outline.getBounds(); view.fitBounds(stateBounds.current, { padding: [20, 20], maxZoom: 7, animate: false })
    view.attributionControl.addAttribution('<a href="https://www.geoboundaries.org/">geoBoundaries</a> / DataMeet / Election Commission of India · <a href="https://creativecommons.org/licenses/by/2.5/in/">CC BY 2.5 IN</a>')
    view.on('click', event => {
      const { lat, lng } = event.latlng
      L.popup().setLatLng(event.latlng).setContent(choosePopup([['p', 'Check the experimental flood and drainage risk for this spot and the area around it.']], 'Check risk here', () => { view.closePopup(); actions.current.onChoose({ name: 'Selected map point', latitude: lat, longitude: lng }) })).openOn(view)
    })
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
      L.circleMarker([gps.latitude, gps.longitude], { bubblingMouseEvents: false, radius: 7, color: '#286ba4', fillOpacity: .9 }).bindPopup(popup(`Actual GPS point · ${Number.isFinite(gps.accuracy_m) ? `browser-reported accuracy ±${Math.round(gps.accuracy_m)} m` : 'accuracy unavailable'}. District unconfirmed.`, 'Report flooding here', '/report', () => actions.current.navigate('/report'))).addTo(layers)
      // Very large uncertainty circles obscure the entire state; report their radius in text instead.
      if (gps.accuracy_m > 0 && gps.accuracy_m <= 10000) L.circle([gps.latitude, gps.longitude], { radius: gps.accuracy_m, color: '#286ba4', weight: 1, fillOpacity: .08, interactive: false }).addTo(layers)
    }
    if (point && point.kind !== 'gps') L.circleMarker([point.latitude, point.longitude], { bubblingMouseEvents: false, radius: 7, color: '#087e7c', fillOpacity: .9 }).bindPopup(popup(`${point.name} · ${point.locality_id ? 'reviewed locality point' : point.kind === 'network' ? 'approximate network estimate; uncertainty unknown' : 'selected point; locality unconfirmed'}.`, 'Report flooding here', '/report', () => actions.current.navigate('/report'))).addTo(layers)
    if (river?.reach?.verified_grid === true) {
      const grid = river.grid_location
      L.circleMarker([grid.latitude, grid.longitude], { bubblingMouseEvents: false, radius: 7, color: '#6951a3', fillOpacity: .9 }).bindPopup(popup(`${river.reach.name} · verified model cell; daily GloFAS v4 discharge, not a flood boundary or observed water level.`, 'Inspect Flood Map context', '/flood-map', () => actions.current.navigate('/flood-map'))).addTo(layers)
    }
    return () => { if (map.current) map.current.removeLayer(layers) }
  }, [point, river])
  useEffect(() => {
    if (!map.current || !point) return
    map.current.setView([point.latitude, point.longitude], point.kind === 'network' || point.accuracy_m > 10000 ? 8 : point.accuracy_m > 1000 ? 11 : 13, { animate: false })
  }, [point?.latitude, point?.longitude, point?.accuracy_m])
  useEffect(() => {
    squares.current = {}
    if (!map.current || !area?.cells?.length) return
    const half = area.cell_size_degrees / 2, layer = L.layerGroup()
    for (const cell of area.cells) {
      const result = cell[kind], color = LEVEL_COLORS[result.level] || LEVEL_COLORS.unavailable
      const square = L.rectangle([[cell.latitude - half, cell.longitude - half], [cell.latitude + half, cell.longitude + half]],
        { color, weight: 1, fillColor: color, fillOpacity: result.level === 'low' ? .12 : result.level === 'unavailable' ? .08 : .38, bubblingMouseEvents: false })
      const reasons = result.reasons.length ? `Why: ${result.reasons.join(', ').toLowerCase()}.` : 'No factor adds points.'
      square.bindPopup(choosePopup([['strong', `${KIND_NAME[kind]} risk: ${LEVEL_NAMES[result.level]}${result.score === null ? '' : ` (score ${result.score} of ${result.max_score})`}`], ['p', spotLabel(cell)], ['p', spotInputs(cell, kind)], ['p', reasons], ['small', 'Experimental index · not an official warning.']],
        'Full assessment here', () => { map.current?.closePopup(); actions.current.onChoose({ name: spotLabel(cell).replace('Your location', 'Grid spot'), latitude: cell.latitude, longitude: cell.longitude }) }))
      square.addTo(layer); squares.current[cell.id] = square
    }
    layer.addTo(map.current)
    // Frame each new area once; switching Flood/Drainage keeps the user's current view.
    if (fitted.current !== area) { fitted.current = area; map.current.fitBounds(layer.getLayers().reduce((b, l) => b.extend(l.getBounds()), L.latLngBounds([])), { padding: [10, 10], animate: false }) }
    return () => { if (map.current) map.current.removeLayer(layer) }
  }, [area, kind])
  useEffect(() => {
    const square = focus && squares.current[focus.id]
    if (!square || !map.current) return
    map.current.fitBounds(square.getBounds(), { maxZoom: 12, animate: false }); square.openPopup()
  }, [focus])
  function statewide() { if (stateBounds.current) map.current?.fitBounds(stateBounds.current, { padding: [20, 20], maxZoom: 7, animate: false }) }
  return <section className="panel workspace-map home-map-stage" aria-labelledby="home-map-title">
    <div className="home-map-toolbar"><div className="home-map-heading"><div><p className="eyebrow">EVIDENCE & ASSISTANCE</p><h2 id="home-map-title">Karnataka Map</h2></div><PageLink to="/flood-map" navigate={navigate}>Full map</PageLink></div>
    <div className="map-actions"><button onClick={statewide}>Show Karnataka</button><button onClick={()=>point&&map.current?.setView([point.latitude,point.longitude],13,{animate:false})} disabled={!point}>Show selected point</button></div></div>
    <div ref={element} className="home-flood-map" role="region" aria-label="Karnataka emergency map" />
    {tileError && <p className="notice home-tile-notice" role="status">{BASEMAP_NOTICE}</p>}
    <div className="home-map-footer"><ul className="home-map-legend" aria-label="Map legend"><li><i className="gps"/>GPS point</li><li><i className="locality"/>Selected place</li>{river&&<li><i className="river"/>Reviewed river model cell</li>}{area?.cells?.length>0&&<li className="home-map-risk-legend">{KIND_NAME[kind]} risk:{['low','moderate','high','severe'].map(l=><span key={l}><i style={{background:LEVEL_COLORS[l]}}/>{LEVEL_NAMES[l]}</span>)}</li>}</ul>
    <details className="home-map-notes"><summary>Map sources & limitations</summary><p className="home-map-limitations">Coloured squares are ~5.5 km experimental risk-index spots for the next 24 hours, not flooded areas or official warning zones. Points are locations, not flooded-area polygons. River cells appear only with a verified association. Official warning geometry is unavailable. State outline: simplified 2011 context; border coverage is uncertain.</p></details></div>
  </section>
}
