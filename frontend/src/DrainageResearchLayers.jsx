import React, { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import useMapResize from './useMapResize.js'

const DEM = 'COPERNICUS/DEM/GLO30_2024_1'
const LAND = 'ESA/WorldCover/v200'
const names = { elevation: 'Surface elevation', slope: 'Surface slope', land_cover: 'Land cover (2021)', drains: 'Mapped drains and ditches' }

function ResearchMap({ data, selected, onFailure }) {
  const element = useRef(null)
  const map = useRef(null)
  const overlays = useRef({})
  useMapResize(map)
  useEffect(() => {
    const instance = L.map(element.current, { scrollWheelZoom: false })
    map.current = instance
    const base = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
    }).addTo(instance)
    base.on('tileerror', () => onFailure('Basemap tiles unavailable. Local research layers remain available.'))
    const boundary = L.geoJSON(data.study_area, { style: { color: '#405f69', weight: 2, fillOpacity: 0 } }).addTo(instance)
    instance.fitBounds(boundary.getBounds(), { padding: [15, 15] })
    for (const [key, item] of Object.entries(data.layers)) {
      if (item.status === 'unavailable') continue
      const overlay = L.imageOverlay(item.url, item.preview_bounds, { opacity: 0.85, alt: names[key],
        attribution: key === 'land_cover' ? 'ESA WorldCover 2021 · CC BY 4.0' : 'Copernicus WorldDEM-30',
      })
      overlay.on('error', () => onFailure(`${names[key]} image unavailable. This layer cannot be interpreted.`))
      overlays.current[key] = overlay
    }
    overlays.current.drains = L.geoJSON(data.mapped_drains, { style: { color: '#0076a8', weight: 4 },
      onEachFeature: (feature, layer) => {
        // Text nodes avoid rendering untrusted OSM tags as HTML.
        const text = document.createElement('span')
        text.textContent = `OSM way ${feature.properties.osm_id} · ${feature.properties.waterway} · capacity unknown`
        layer.bindPopup(text)
      },
    })
    return () => { instance.remove(); map.current = null; overlays.current = {} }
  }, [data, onFailure])

  useEffect(() => {
    if (!map.current) return
    for (const [key, overlay] of Object.entries(overlays.current)) {
      if (selected[key]) overlay.addTo(map.current)
      else map.current.removeLayer(overlay)
    }
  }, [data, selected])
  return <div className="research-map" ref={element} role="region" aria-label="Udupi drainage research geography" />
}

function Legend({ layer, name }) {
  const legend = layer.legend
  return <div className="research-legend">
    <strong>{name}</strong>
    {Array.isArray(legend) ? <div className="class-legend">{legend.map(item => <span key={item.value}>
      <i style={{ background: item.color }} />{item.label} ({item.value})
    </span>)}</div> : <>
      {legend.min == null ? <p>Values unavailable</p> : <div className="scale-legend">
        <span>{legend.min.toFixed(2)} {layer.units}</span>
        <i style={{ background: `linear-gradient(to right, ${legend.colors.join(',')})` }} />
        <span>{legend.max.toFixed(2)} {layer.units}</span>
      </div>}
    </>}
    <small>{layer.resolution_m} m processing grid · {layer.valid_pixels.toLocaleString()} / {layer.total_pixels.toLocaleString()} valid pixels. Transparent pixels are unknown.</small>
  </div>
}

function OpenResearch() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [mapFailure, setMapFailure] = useState(null)
  const [selected, setSelected] = useState({ elevation: true, slope: false, land_cover: false, drains: false })
  useEffect(() => {
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), 15000)
    let active = true
    ;(async () => {
      try {
        const response = await fetch('/api/drainage-research', { signal: controller.signal })
        const body = await response.json()
        if (!response.ok || body.status !== 'available') throw new Error(body.message || 'Research dataset unavailable')
        if (body.dataset_version !== 'udupi_drainage_gis_v1' || body.study_area?.properties?.official_municipal_boundary !== false ||
            body.layers?.elevation?.source_id !== DEM || body.layers?.land_cover?.source_id !== LAND) throw new Error('Research source identities are inconsistent')
        if (active) {
          setData(body)
          setSelected(current => ({ ...current, elevation: body.layers.elevation.status !== 'unavailable' }))
        }
      } catch (err) {
        if (active) setError(err.name === 'AbortError' ? 'Research request timed out.' : err.message)
      } finally { clearTimeout(timeout) }
    })()
    return () => { active = false; controller.abort(); clearTimeout(timeout) }
  }, [])

  const toggle = key => setSelected(current => {
    const next = { ...current, [key]: !current[key] }
    // Raster overlays have different meanings: show one at a time so colours remain interpretable.
    if (key !== 'drains' && next[key]) for (const other of ['elevation', 'slope', 'land_cover']) if (other !== key) next[other] = false
    return next
  })
  return <div aria-live="polite">
    {!data && !error && <p className="notice">Loading local GIS research layers…</p>}
    {error && <p className="notice error" role="alert">Research layers unavailable. {error} Missing data remain unknown.</p>}
    {data && <>
      <p className="muted">3 km × 3 km study window around Udupi OSM city point {data.study_area.properties.anchor_osm_node_id}. This is not an official municipal boundary.</p>
      <p className="muted">Layer extraction completed {data.finished_at} · EPSG:32643 research rasters; Web Mercator map previews.</p>
      <fieldset className="research-controls"><legend>Select layers</legend>
        {Object.entries(names).map(([key, name]) => {
          const unavailable = key === 'drains' ? data.osm.feature_count === 0 : data.layers[key].status === 'unavailable'
          return <label key={key}><input type="checkbox" checked={selected[key]} disabled={unavailable} onChange={() => toggle(key)} /> {name}{unavailable ? ' — unavailable' : ''}</label>
        })}
      </fieldset>
      <p className="muted">Select one raster at a time to keep its colours readable. Mapped lines can overlay any raster.</p>
      {mapFailure && <p className="notice error" role="alert">{mapFailure}</p>}
      <ResearchMap data={data} selected={selected} onFailure={setMapFailure} />
      {Object.entries(data.layers).map(([key, layer]) => selected[key] && <Legend key={key} layer={layer} name={names[key]} />)}
      {selected.drains && <p className="map-legend"><i className="drain-swatch" />OSM drain / ditch ways; geometry only, capacity and condition unknown.</p>}
      <p className="notice">{data.osm.feature_count ? `${data.osm.drain_count} mapped drain ways and ${data.osm.ditch_count} mapped ditch ways; ${data.osm.clipped_length_m.toFixed(1)} m of clipped mapped lines.` : 'No drain or ditch ways were returned for this study window. Mapped-drain coverage is unavailable; this does not mean there are no drains.'} OSM snapshot: {data.osm.osm_base_timestamp}; retrieved {data.osm.retrieved_at}.</p>
      <p className="muted">Elevation is a digital surface model, including buildings and vegetation, with a composite acquisition period of 2010–2020. Slope uses Horn’s 3 × 3 method on the 30 m grid and requires nine valid neighbouring heights. Neither layer verifies drainage infrastructure or hydrological flow paths.</p>
      <p className="muted">WorldCover is a 2021 classification at 10 m native resolution, reprojected with nearest-neighbour sampling. Local class accuracy is unverified. DSM, land cover and OSM dates differ.</p>
      <p className="muted">DEM quality: {data.dem_quality.EDM['1.0'] || 0} pixels marked unedited; {data.height_error_m.missing_pixels} pixels without a height-error estimate. Edited heights and missing error estimates limit small-scale interpretation.</p>
      <details className="research-provenance"><summary>Sources, retrieval times and licence conditions</summary>
        {Object.entries(data.sources).map(([id, source]) => <div key={id}>
          <p><a href={source.url}>{id}</a> · <a href={source.license_url}>{source.license}</a></p>
          {id !== DEM && <p>{source.attribution}</p>}
        </div>)}
        {Object.entries(data.layers).map(([key, layer]) => <p key={key}>{names[key]} retrieved {layer.retrieved_at}; missing pixels: {layer.missing_pixels}.</p>)}
      </details>
      <p className="muted">{data.sources[DEM].attribution}. {data.sources[DEM].liability_notice}.</p>
      <p className="muted">© ESA WorldCover project 2021 · CC BY 4.0. © OpenStreetMap contributors · ODbL 1.0. Copernicus attribution and liability notice above apply to the terrain layers.</p>
    </>}
  </div>
}

export default function DrainageResearchLayers() {
  const [open, setOpen] = useState(false)
  return <section className="panel research-panel" aria-labelledby="research-title">
    <div className="panel-heading"><div><p className="eyebrow">UDUPI · GIS FOUNDATION</p><h2 id="research-title">Drainage Research Layers</h2></div>
      <button aria-expanded={open} onClick={() => setOpen(current => !current)}>{open ? 'Hide research layers' : 'Show research layers'}</button>
    </div>
    <p>Surface elevation, slope, 2021 land cover and available mapped drains. These research layers do not establish drainage risk or live waterlogging.</p>
    {open && <OpenResearch />}
  </section>
}
