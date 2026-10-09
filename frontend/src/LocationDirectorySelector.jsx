import React, { useEffect, useState } from 'react'
import './LocationDirectorySelector.css'

// Abort on replacement/unmount; late directory responses cannot replace a newer query.
function useDirectory(url, retry) {
  const [state, setState] = useState({ data: null, error: null, loading: false })
  useEffect(() => {
    if (!url) { setState({ data: null, error: null, loading: false }); return }
    const controller = new AbortController()
    let active = true, timedOut = false
    setState({ data: null, error: null, loading: true })
    const timer = setTimeout(() => { timedOut = true; controller.abort() }, 10000)
    ;(async () => {
      try {
        const response = await fetch(url, { signal: controller.signal })
        const data = await response.json()
        if (!response.ok) throw new Error(data.detail || 'Location directory unavailable.')
        if (data.status !== 'available' || !Array.isArray(data.items) || !Number.isInteger(data.total)) throw new Error('Location directory response is invalid.')
        if (active) setState({ data, error: null, loading: false })
      } catch (error) {
        if (active) setState({ data: null, error: timedOut ? 'Location search timed out. Retry or use coordinates.' : error.message, loading: false })
      } finally { clearTimeout(timer) }
    })()
    return () => { active = false; clearTimeout(timer); controller.abort() }
  }, [url, retry])
  return state
}

function useDebounced(value) {
  const [settled, setSettled] = useState(value)
  useEffect(() => { const timer = setTimeout(() => setSettled(value.trim()), 250); return () => clearTimeout(timer) }, [value])
  return settled
}

function canChoose(row) {
  const point = row.coordinates
  return row.selectable === true && row.coordinate_status === 'verified_osm_place_point' && row.coordinate_source?.license === 'ODbL 1.0'
    && point && Number.isFinite(point.latitude) && Number.isFinite(point.longitude) && Math.abs(point.latitude) <= 90 && Math.abs(point.longitude) <= 180
}

export default function LocationDirectorySelector({ onChoose, onDistrict }) {
  const [open, setOpen] = useState(false)
  const [districtId, setDistrictId] = useState('')
  const [query, setQuery] = useState('')
  const [localQuery, setLocalQuery] = useState('')
  const [retry, setRetry] = useState(0)
  const q = useDebounced(query), localQ = useDebounced(localQuery)
  const districts = useDirectory(open ? '/api/locations/districts' : null, retry)
  const search = useDirectory(open && q ? `/api/locations/search?q=${encodeURIComponent(q)}&limit=20` : null, retry)
  const localities = useDirectory(open && districtId ? `/api/locations/localities?district_id=${encodeURIComponent(districtId)}&q=${encodeURIComponent(localQ)}` : null, retry)
  const district = districts.data?.items.find(r => r.id === districtId)

  function chooseDistrict(row) {
    setDistrictId(row?.id || ''); setLocalQuery(''); setQuery('')
    onDistrict(row || null)
  }
  function chooseLocality(row) {
    // Defence in depth: name-only, restricted or unverified records are never points.
    if (!canChoose(row)) return
    const parent = districts.data?.items.find(d => d.id === row.district_id)
    if (!parent) return
    setDistrictId(parent.id); setQuery(''); setLocalQuery('')
    onChoose({ name: `${row.name}, ${parent.name}`, latitude: row.coordinates.latitude, longitude: row.coordinates.longitude,
      locality_id: row.id, district_id: parent.id, district_name: parent.name, coordinate_source_url: row.coordinate_source.url,
      association_source_url: row.association_source_url })
  }
  function localityButton(row, scope = 'district') {
    const parent = districts.data?.items.find(d => d.id === row.district_id)
    const usable = canChoose(row)
    const descriptionId = `unavailable-${scope}-${row.id}`
    const label = `${row.name} — ${parent?.name || row.district_id} · ${usable ? `Mapped locality point (${row.coordinates.latitude}°, ${row.coordinates.longitude}°)` : 'Coordinates unavailable'}`
    return <><button type="button" disabled={!usable} aria-label={label} aria-describedby={!usable && row.unavailable_reason ? descriptionId : undefined}
      onClick={() => chooseLocality(row)}>{row.name} — {parent?.name || row.district_id} · {usable ? 'Mapped locality point' : 'Coordinates unavailable'}</button>
      {!usable && row.unavailable_reason && <span id={descriptionId} className="muted"> {row.unavailable_reason}</span>}</>
  }
  const error = districts.error || search.error || localities.error
  const loading = districts.loading || search.loading || localities.loading
  return <div className="location-directory">
    <button type="button" aria-expanded={open} aria-controls="location-directory-content" onClick={() => setOpen(v => !v)}>{open ? 'Close place search' : 'Search districts and localities'}</button>
    {open && <div id="location-directory-content">
      <h3>Find a Karnataka place</h3>
      <p className="muted">{districts.data?.coverage ? `${districts.data.coverage.district_names} NIC-listed district names; ${districts.data.coverage.selectable_localities} selectable mapped localities across ${districts.data.coverage.districts_with_selectable_localities} districts; ${districts.data.coverage.name_only_localities} name-only records.` : 'Coverage is limited to reviewed place records.'} Current LGD identities remain unresolved. Unreviewed coordinates are never substituted. {districts.data?.dataset_version && `Directory: ${districts.data.dataset_version}.`}</p>
      <label htmlFor="place-search">Search districts or localities</label>
      <input id="place-search" type="search" maxLength={100} value={query} onChange={e => setQuery(e.target.value)} placeholder="For example: Udupi or Karkala" />
      {q && search.data && <>
        <p role="status" aria-label="Place search results">{search.data.total ? `${search.data.total} matching places; showing ${search.data.items.length}.` : 'No matching places in the verified directory. Try another name or enter coordinates.'}</p>
        <ul aria-label="Place search results">{search.data.items.map(row => <li key={row.id}>{row.kind === 'district'
          ? <button type="button" onClick={() => chooseDistrict(row)}>{row.name} — District · filter localities</button> : localityButton(row, 'search')}</li>)}</ul>
      </>}
      <label htmlFor="district-choice">Karnataka district</label>
      <select id="district-choice" value={districtId} disabled={!districts.data} onChange={e => chooseDistrict(districts.data?.items.find(d => d.id === e.target.value))}>
        <option value="">Select a district</option>
        {districts.data?.items.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}
      </select>
      {district && <>
        <p className="notice">{district.name}: district selection filters localities; it does not request district-wide weather. {district.navigation_bounds ? 'Map navigation uses the public geoBoundaries district extent.' : 'Verified public navigation geometry and a representative point are unavailable.'}</p>
        <label htmlFor="locality-search">Search localities in {district.name}</label>
        <input id="locality-search" type="search" maxLength={100} value={localQuery} onChange={e => setLocalQuery(e.target.value)} />
        {localities.data && <>
          <p role="status" aria-label="District locality results">{localities.data.total ? `${localities.data.total} locality records; showing ${localities.data.items.length}.` : 'No verified localities match this district and search. Coverage is incomplete; use coordinates, map or GPS.'}</p>
          <ul aria-label="District localities">{localities.data.items.map(row => <li key={row.id}>{localityButton(row)}</li>)}</ul>
        </>}
      </>}
      <p role="status" aria-label="Location directory status" aria-live="polite" aria-busy={loading}>{loading ? 'Loading location directory…' : 'Location search ready.'}</p>
      {error && <div role="alert" aria-label="Location directory error"><p>{error}</p><button type="button" onClick={() => setRetry(v => v + 1)}>Retry location search</button></div>}
      <p className="muted">Names: <a href="https://igod.gov.in/sg/KA/E042/organizations">NIC government directory</a>. {district && <>Locality association: <a href={district.source_website}>{district.name} District Administration</a>. </>}Place coordinates: <a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors · ODbL 1.0</a>. Navigation: <a href="https://www.geoboundaries.org/api/current/gbOpen/IND/ADM2/">geoBoundaries / Pathways Data Pvt. Ltd. / lgdirectory.gov.in · ODbL 1.0</a>; existing Udupi CGAZ extent: CC BY 4.0. Points are mapped settlements, not municipal boundaries, gauges or shelters.</p>
    </div>}
  </div>
}
