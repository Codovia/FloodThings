import React, { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { addBasemap, BASEMAP_NOTICE } from './mapBasemap.js'
import useMapResize from './useMapResize.js'
import { boundary, KARNATAKA_CENTER } from './homeGeography.js'
import { PageLink } from './AppNavigation.jsx'
import { LEVEL_COLORS, LEVEL_NAMES } from './useRisk.js'
import { spotLabel, spotInputs, KindToggle } from './RiskAreaDashboard.jsx'
import { OFFICIAL_COLOURS, MEANING } from './OfficialWarnings.jsx'
import Popup from './Popup.jsx'

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
// Soft zones: only Moderate and above are shaded; Low stays clear so calm days do not look like a grid.
const ZONE = { moderate: .32, high: .45, severe: .55 }
const cap = s => s[0].toUpperCase() + s.slice(1)

export default function HomeFloodMap({ fitViewport, point, navigate, onReportHere = null, area = null, kind = 'flood', onKind = () => {}, focus = null, onChoose = () => {}, districts = null, userDistrict = null }) {
  const gps = point?.kind === 'gps' ? point : null
  const element = useRef(null), map = useRef(null), stateBounds = useRef(null), actions = useRef({ navigate, onChoose, onReportHere }), zones = useRef({}), fitted = useRef(null), renderer = useRef(null)
  const [tileError, setTileError] = useState(false), [showOfficial, setShowOfficial] = useState(true), [showRisk, setShowRisk] = useState(true)
  actions.current = { navigate, onChoose, onReportHere }
  useEffect(() => {
    const view = L.map(element.current, { scrollWheelZoom: false, zoomControl: false }).setView(KARNATAKA_CENTER, 6); map.current = view
    L.control.zoom({ position: 'bottomright' }).addTo(view)
    addBasemap(L, view, () => setTileError(true))
    view.createPane('officialPane').style.zIndex = 390
    view.createPane('riskZones').style.zIndex = 410
    renderer.current = L.svg({ pane: 'riskZones', padding: 0.5 })
    const outline = L.geoJSON(boundary, { interactive: false, style: { color: '#35605a', weight: 1.5, fillOpacity: 0 } }).addTo(view)
    stateBounds.current = outline.getBounds(); view.fitBounds(stateBounds.current, { padding: [20, 20], maxZoom: 7, animate: false })
    view.attributionControl.addAttribution('<a href="https://www.geoboundaries.org/">geoBoundaries</a> / DataMeet / Election Commission of India · <a href="https://creativecommons.org/licenses/by/2.5/in/">CC BY 2.5 IN</a> · Warnings: <a href="https://mausam.imd.gov.in/">IMD</a>')
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
    map.current.invalidateSize({ pan: false })
    if (!point && stateBounds.current) map.current.fitBounds(stateBounds.current, { padding: [20, 20], maxZoom: 7, animate: false })
  }, [fitViewport])
  // Official IMD district warnings (today), shown as issued.
  useEffect(() => {
    if (!map.current || !showOfficial || !districts?.districts?.length) return
    const layer = L.layerGroup()
    for (const d of districts.districts) {
      const today = d.days[0], colour = OFFICIAL_COLOURS[today?.level] || '#8a8f98', mine = d.imd_name === userDistrict, alerting = ['orange', 'red'].includes(today?.level)
      const text = d.status === 'stale' ? `${d.district}: IMD bulletin from ${d.issued_date} is out of date` : `${d.district} · official IMD warning today: ${today?.level ? `${cap(today.level)} (${MEANING[today.level]})` : 'Unavailable'}${today?.warnings?.length ? ' — ' + today.warnings.join(', ') : ''}`
      L.geoJSON({ type: 'Feature', properties: {}, geometry: d.geometry }, { pane: 'officialPane', bubblingMouseEvents: true,
        style: { color: mine ? '#17313c' : colour, weight: mine ? 3 : alerting ? 2 : 0.8, opacity: .9, fillColor: colour, fillOpacity: today?.level === 'green' ? 0.05 : alerting ? 0.2 : 0.13, dashArray: mine ? '6 4' : null },
        onEachFeature: (f, l) => l.bindTooltip(text, { sticky: true }) }).addTo(layer)
    }
    layer.addTo(map.current)
    return () => { if (map.current) map.current.removeLayer(layer) }
  }, [districts, showOfficial, userDistrict])
  useEffect(() => {
    if (!map.current) return
    const layers = L.layerGroup().addTo(map.current)
    if (gps) {
      L.circleMarker([gps.latitude, gps.longitude], { bubblingMouseEvents: false, radius: 7, color: '#fff', weight: 2, fillColor: '#286ba4', fillOpacity: 1 }).bindPopup(popup(`Actual GPS point · ${Number.isFinite(gps.accuracy_m) ? `browser-reported accuracy ±${Math.round(gps.accuracy_m)} m` : 'accuracy unavailable'}. District unconfirmed.`, 'Report flooding here', '/report', () => actions.current.navigate('/report'))).addTo(layers)
      // Very large uncertainty circles obscure the entire state; report their radius in text instead.
      if (gps.accuracy_m > 0 && gps.accuracy_m <= 10000) L.circle([gps.latitude, gps.longitude], { radius: gps.accuracy_m, color: '#286ba4', weight: 1, fillOpacity: .08, interactive: false }).addTo(layers)
    }
    if (point && point.kind !== 'gps') L.circleMarker([point.latitude, point.longitude], { bubblingMouseEvents: false, radius: 7, color: '#fff', weight: 2, fillColor: '#087e7c', fillOpacity: 1 }).bindPopup(popup(`${point.name} · ${point.locality_id ? 'reviewed locality point' : point.kind === 'network' ? 'approximate network estimate; uncertainty unknown' : 'selected point; locality unconfirmed'}.`, 'Report flooding here', '/report', () => actions.current.onReportHere ? actions.current.onReportHere(point) : actions.current.navigate('/report'))).addTo(layers)
    return () => { if (map.current) map.current.removeLayer(layers) }
  }, [point])
  useEffect(() => {
    if (!map.current || !point) return
    map.current.setView([point.latitude, point.longitude], point.kind === 'network' || point.accuracy_m > 10000 ? 8 : point.accuracy_m > 1000 ? 11 : 13, { animate: false })
  }, [point?.latitude, point?.longitude, point?.accuracy_m])
  // Experimental 24 h prediction: soft blurred zones around each ~5.5 km spot.
  useEffect(() => {
    zones.current = {}
    if (!map.current || !area?.cells?.length) return
    const radius = area.cell_size_degrees * 111000 * 0.62, layer = L.layerGroup(), frame = []
    for (const cell of area.cells) {
      const result = cell[kind], level = result.level
      frame.push([cell.latitude, cell.longitude])
      const reasons = result.reasons.length ? `Why: ${result.reasons.join(', ').toLowerCase()}.` : 'No factor adds points.'
      const content = choosePopup([['strong', `${KIND_NAME[kind]} risk: ${LEVEL_NAMES[level]}${result.score === null ? '' : ` (score ${result.score} of ${result.max_score})`}`], ['p', spotLabel(cell)], ['p', spotInputs(cell, kind)], ['p', reasons], ['small', 'Experimental index for the next 24 hours · not an official warning.']],
        'Full assessment here', () => { map.current?.closePopup(); actions.current.onChoose({ name: spotLabel(cell).replace('Your location', 'Grid spot'), latitude: cell.latitude, longitude: cell.longitude }) })
      const zone = ZONE[level]
        ? L.circle([cell.latitude, cell.longitude], { renderer: renderer.current, radius, stroke: false, fillColor: LEVEL_COLORS[level], fillOpacity: showRisk ? ZONE[level] : 0, bubblingMouseEvents: false, interactive: showRisk })
        : L.circle([cell.latitude, cell.longitude], { renderer: renderer.current, radius: radius * 0.9, stroke: false, fillColor: '#ffffff', fillOpacity: 0.001, bubblingMouseEvents: false, interactive: showRisk })
      zone.bindPopup(content); zone.addTo(layer); zones.current[cell.id] = zone
      if (level === 'unavailable' && showRisk) L.circleMarker([cell.latitude, cell.longitude], { radius: 3, color: '#8a8f98', weight: 1, fillOpacity: .6, interactive: false }).addTo(layer)
    }
    layer.addTo(map.current)
    // Frame each new area once; switching Flood/Drainage keeps the user's current view.
    if (fitted.current !== area && frame.length) { fitted.current = area; map.current.fitBounds(L.latLngBounds(frame).pad(0.12), { animate: false }) }
    return () => { if (map.current) map.current.removeLayer(layer) }
  }, [area, kind, showRisk])
  useEffect(() => {
    const zone = focus && zones.current[focus.id]
    if (!zone || !map.current) return
    map.current.setView(zone.getLatLng(), Math.max(map.current.getZoom(), 11), { animate: false }); zone.openPopup()
  }, [focus])
  function statewide() { if (stateBounds.current) map.current?.fitBounds(stateBounds.current, { padding: [20, 20], maxZoom: 7, animate: false }) }
  const hasArea = area?.cells?.length > 0
  return <section className="panel workspace-map home-map-stage" aria-labelledby="home-map-title">
    <div className="home-map-toolbar"><div className="home-map-heading"><h2 id="home-map-title">Karnataka Map</h2><PageLink to="/flood-map" navigate={navigate}>Full map</PageLink></div>
      <div className="map-actions"><button onClick={statewide}>Show Karnataka</button><button onClick={()=>point&&map.current?.setView([point.latitude,point.longitude],12,{animate:false})} disabled={!point}>Show selected point</button></div></div>
    <div className="home-map-frame">
      <div ref={element} className="home-flood-map" role="region" aria-label="Karnataka emergency map" />
      <div className="map-overlay map-layers" role="group" aria-label="Map layers">
        <label><input type="checkbox" checked={showOfficial} onChange={e => setShowOfficial(e.target.checked)} /> Official IMD warnings</label>
        <label><input type="checkbox" checked={showRisk} onChange={e => setShowRisk(e.target.checked)} disabled={!hasArea} /> 24 h prediction</label>
        {hasArea && showRisk && <KindToggle kind={kind} onKind={onKind} label="Map prediction type" />}
      </div>
      <div className="map-overlay map-legend-card" aria-label="Map legend">
        {showOfficial && <p><span className="legend-title">IMD today</span>{['red', 'orange', 'yellow', 'green'].map(l => <span key={l} className="legend-item"><i className="legend-fill" style={{ background: OFFICIAL_COLOURS[l] }} />{cap(l)}</span>)}</p>}
        {hasArea && showRisk && <p><span className="legend-title">{KIND_NAME[kind]} 24 h</span>{['moderate', 'high', 'severe'].map(l => <span key={l} className="legend-item"><i className="legend-zone" style={{ background: LEVEL_COLORS[l] }} />{LEVEL_NAMES[l]}</span>)}<span className="legend-item muted">clear = Low</span></p>}
        <p><span className="legend-item"><i className="legend-dot gps" />GPS point</span><span className="legend-item"><i className="legend-dot locality" />Selected place</span></p>
      </div>
      {tileError && <p className="notice home-tile-notice" role="status">{BASEMAP_NOTICE}</p>}
    </div>
    <p className="home-map-notes"><Popup label="Map sources & limitations" title="Map sources & limitations"><p className="home-map-limitations">District colours are official IMD district warnings for today, shown as issued. Shaded zones are FloodPulse's experimental 24-hour risk index around ~5.5 km spots — not flooded areas, probabilities or official warning zones; unshaded spots are Low. Points are locations, not flooded-area polygons. State outline: simplified 2011 context; border coverage is uncertain.</p></Popup></p>
  </section>
}
