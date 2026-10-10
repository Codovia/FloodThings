import React, { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { addBasemap, BASEMAP_NOTICE } from './mapBasemap.js'
import 'leaflet/dist/leaflet.css'
import useMapResize from './useMapResize.js'
import DrainageResearchLayers from './DrainageResearchLayers.jsx'
import useShelterDirectory, { validShelterDirectory } from './useShelterDirectory.js'
import { PageLink } from './AppNavigation.jsx'

const mechanismNames={riverine:'Riverine flooding',pluvial_urban_waterlogging:'Pluvial or urban waterlogging',flash:'Flash flooding',coastal:'Coastal flooding',unknown:'Unknown'}
const EMPTY={type:'FeatureCollection',features:[]}
const hazardNotice='No verified potential flood-prone zone dataset is available for this district.'
const dates=p=>`${p.start_date} – ${p.end_date_inclusive} (UTC source dates)`

function useEvidence(url, retry=0){
 const [state,setState]=useState({url:null,data:null,error:null,loading:false})
 useEffect(()=>{
  if(!url)return
  const controller=new AbortController();let active=true,timedOut=false
  setState({url,data:null,error:null,loading:true})
  const timer=setTimeout(()=>{timedOut=true;controller.abort()},15000)
  fetch(url,{signal:controller.signal}).then(async response=>{
   const data=await response.json()
   if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Map evidence request failed')
   if(active)setState({url,data,error:null,loading:false})
  }).catch(error=>{if(active)setState({url,data:null,error:timedOut?'Map evidence request timed out.':error.message,loading:false})}).finally(()=>clearTimeout(timer))
  return()=>{active=false;clearTimeout(timer);controller.abort()}
 },[url,retry])
 return !url?{data:null,error:null,loading:false}:state.url===url?state:{data:null,error:null,loading:true}
}

function IntelligenceGeography({district,history,drainage,shelters,point,onPoint,onFeature}){
 const element=useRef(null),map=useRef(null),select=useRef(onPoint),detail=useRef(onFeature)
 const [tileError,setTileError]=useState(false)
 select.current=onPoint;detail.current=onFeature
 useEffect(()=>{
  const view=L.map(element.current,{scrollWheelZoom:false}).setView([15.1,76.1],6);map.current=view
  addBasemap(L, view, () => setTileError(true))
  view.on('click',e=>select.current?.({name:'Selected map point',latitude:e.latlng.lat,longitude:((e.latlng.lng+180)%360+360)%360-180}))
  return()=>{view.remove();map.current=null}
 },[])
 useMapResize(map)
 useEffect(()=>{
  if(!map.current)return
  if(!district)map.current.setView([15.1,76.1],6,{animate:false})
  else if(district.navigation_bounds)map.current.fitBounds(district.navigation_bounds,{padding:[20,20],animate:false})
 },[district])
 useEffect(()=>{
  if(!map.current)return
  const layers=[]
  const add=layer=>{layer.addTo(map.current);layers.push(layer)}
  if(history?.boundary)add(L.geoJSON(history.boundary,{style:{color:'#50736e',weight:2,fillOpacity:0.025}}))
  if(history?.geojson)add(L.geoJSON(history.geojson,{bubblingMouseEvents:false,
   style:{color:'#9c3627',weight:1.5,fillColor:'#dc6047',fillOpacity:.75},
   onEachFeature:(feature,layer)=>{
    const text=document.createElement('span');text.textContent=`Event ${feature.properties.event_id} · historical mapped cell · clear_views: ${feature.properties.clear_views}`
    layer.bindTooltip(text);layer.on('click',()=>detail.current(feature.id))
   }}))
  if(drainage?.status==='available'){
   add(L.geoJSON(drainage.study_area,{style:{color:'#0076a8',weight:2,dashArray:'6 4',fillOpacity:0}}))
   add(L.geoJSON(drainage.mapped_drains||EMPTY,{style:{color:'#0076a8',weight:4},onEachFeature:(f,layer)=>{const text=document.createElement('span');text.textContent=`OSM ${f.properties.waterway} ${f.properties.osm_id} · Mapped drainage feature — overflow risk not established.`;layer.bindPopup(text)}}))
  }
  if(shelters&&validShelterDirectory(shelters))for(const shelter of shelters.shelters){
   const marker=L.circleMarker([shelter.latitude,shelter.longitude],{radius:9,color:'#00695c',fillColor:'#18a999',fillOpacity:.9})
   const text=document.createElement('span');text.textContent=`${shelters.mode==='demonstration'?'DEMONSTRATION ONLY — ':''}${shelter.name} · ${shelter.available_capacity} reported spaces · verified ${shelter.verified_at}`;marker.bindPopup(text);add(marker)
  }
  return()=>{if(map.current)for(const layer of layers)map.current.removeLayer(layer)}
 },[history,drainage,shelters])
 useEffect(()=>{
  if(!map.current||!point)return
  const marker=L.circleMarker([point.latitude,point.longitude],{radius:5,color:'#344b68',fillOpacity:.6}).addTo(map.current)
  return()=>{if(map.current)map.current.removeLayer(marker)}
 },[point])
 function zoomWater(){if(history?.geojson?.features?.length){const bounds=L.geoJSON(history.geojson).getBounds();map.current?.fitBounds(bounds,{padding:[30,30],maxZoom:14})}}
 return <>
  <div className="map-actions"><button onClick={()=>district?.navigation_bounds?map.current?.fitBounds(district.navigation_bounds):map.current?.setView([15.1,76.1],6)} disabled={!!district&&!district.navigation_bounds}>Show district</button><button onClick={zoomWater} disabled={!history?.geojson?.features?.length}>Zoom to mapped water</button></div>
  <div ref={element} className="historical-map intelligence-map" role="region" aria-label="Historical satellite floodwater and Karnataka evidence map"/>
  {tileError&&<p className="notice">{BASEMAP_NOTICE}</p>}
 </>
}

function FeatureDetails({data,onClose,navigate}){
 const feature=data.feature,p=feature.properties
 return <section className="panel intelligence-detail" aria-labelledby="feature-details-title">
  <div className="panel-heading"><h2 id="feature-details-title">Flood evidence details</h2><button onClick={onClose}>Close details</button></div>
  <dl><dt>District</dt><dd>{p.district}</dd><dt>Place</dt><dd>{p.place_name||'No verified settlement name for this raster cell'}</dd><dt>Evidence category</dt><dd>Historical observed floodwater polygon</dd><dt>Event</dt><dd>GFD {p.event_id} · {dates(p)}</dd><dt>Possible mechanism</dt><dd>{p.mechanism.mechanisms?.map(m=>mechanismNames[m]||'Unknown').join(', ')||'Unknown'} — {p.mechanism.method}</dd><dt>Observation quality</dt><dd>{p.observation_quality}; {p.clear_views} clear-view observations</dd><dt>Geometry meaning</dt><dd>{p.geometry_meaning} · {p.processing_grid_m} m processing grid</dd><dt>Drainage coverage</dt><dd>Limited, separately reviewed Udupi study; no cell-specific association established</dd><dt>Overflow assessment</dt><dd>Not validated</dd><dt>Environmental information</dt><dd><PageLink to="/weather" navigate={navigate}>Open selected-point Weather & AI</PageLink>. This cell is not automatically a supported AI locality.</dd><dt>Source / version</dt><dd><a href={p.source.url}>{p.source.name}</a> · {p.dataset_version}</dd><dt>Source image</dt><dd>{p.image_id}</dd><dt>Licence</dt><dd><a href={p.source.license_url}>{p.source.license}</a> — {p.source.conditions}</dd><dt>Extraction retrieved</dt><dd>{p.retrieved_at}</dd><dt>Source geometry SHA-256</dt><dd>{p.source_geometry_sha256}</dd><dt>Stable feature ID</dt><dd>{feature.id}</dd></dl>
  <p className="notice">{p.limitations} Missing observations are unknown, not non-flood. Current LGD reconciliation remains unresolved.</p>
 </section>
}

export default function FloodIntelligenceMap({point,onPoint,navigate,selectedDistrictId,onDistrictChange}){
 const [districtId,setDistrictId]=useState(''),[eventId,setEventId]=useState(''),[featureId,setFeatureId]=useState(null),[retry,setRetry]=useState(0)
 useEffect(()=>{if(selectedDistrictId!==undefined){setDistrictId(selectedDistrictId);setFeatureId(null)}},[selectedDistrictId])
 const [layers,setLayers]=useState({history:true,hazards:false,drainage:false,shelters:false})
 const directory=useEvidence('/api/flood-map/districts',retry)
 const query=new URLSearchParams(districtId?{district_id:districtId}:{})
 const historicalQuery=new URLSearchParams(query);if(eventId)historicalQuery.set('event_id',eventId)
 const history=useEvidence(layers.history?'/api/flood-map/historical?'+historicalQuery:null,retry)
 const hazard=useEvidence(layers.hazards?'/api/flood-map/hazards?'+query:null,retry)
 const drainage=useEvidence(layers.drainage?'/api/flood-map/drainage?'+query:null,retry)
 const shelters=useShelterDirectory(null,layers.shelters)
 const details=useEvidence(featureId?'/api/flood-map/features/'+encodeURIComponent(featureId):null,retry)
 const district=directory.data?.items.find(d=>d.id===districtId)||null
 const shownShelters=shelters.data&&validShelterDirectory(shelters.data)?{...shelters.data,shelters:shelters.data.shelters.filter(s=>!districtId||s.district_id===districtId)}:null
 function toggle(key){setLayers(current=>({...current,[key]:!current[key]}));if(key==='history')setFeatureId(null)}
 const failures=[directory,history,hazard,drainage,shelters,details].filter(s=>s.error)
 const loading=[directory,history,hazard,drainage,shelters,details].some(s=>s.loading)
 const safeHistory=history.data?.status==='available'&&history.data.geojson?.type==='FeatureCollection'?history.data:null
 return <section className="intelligence-workspace" aria-labelledby="intelligence-title">
  <h2 id="intelligence-title">Karnataka Flood Intelligence</h2>
  <div className="panel intelligence-toolbar">
   <label htmlFor="intelligence-district">Flood Map district</label><select id="intelligence-district" value={districtId} disabled={!directory.data} onChange={e=>{setDistrictId(e.target.value);onDistrictChange?.(e.target.value);setFeatureId(null)}}><option value="">Karnataka — statewide evidence</option>{directory.data?.items.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select>
   <button onClick={()=>{setDistrictId('');onDistrictChange?.('');setFeatureId(null)}}>Return to statewide view</button>
   <fieldset><legend>Evidence layers</legend>{[['history','Historical Flood Locations'],['hazards','Potential Flood-Prone Zones'],['drainage','Drainage / waterways'],['shelters','Verified shelters']].map(([key,label])=><label key={key}><input type="checkbox" checked={layers[key]} onChange={()=>toggle(key)}/>{label}</label>)}</fieldset>
   {layers.history&&<label>Recorded event<select aria-label="Recorded event" value={eventId} onChange={e=>{setEventId(e.target.value);setFeatureId(null)}}><option value="">All reviewed public spatial events</option>{(safeHistory?.events||[]).map(e=><option key={e.event_id} value={e.event_id}>Event {e.event_id} · {e.start_date} – {e.end_date_inclusive}</option>)}</select></label>}
  </div>
  <div className="intelligence-layout"><div className="intelligence-map-stage">  <IntelligenceGeography district={district} history={safeHistory} drainage={drainage.data} shelters={shownShelters} point={point} onPoint={onPoint} onFeature={setFeatureId}/>
  <p className="map-legend"><span className="water-swatch"/>Historical water polygons · dashed blue outline: bounded drainage study · teal circles: verified shelter entrances · small slate circle: selected weather point. No hazard polygons are registered.</p>
</div><aside className="intelligence-sidebar" aria-label="Map evidence and limitations" tabIndex={0}>  <p className="historical-notice">Historical event-window maximum satellite observations. This is not current flooding, predicted risk, flooded roads or evacuation advice. No validated district flood-risk classes are available.</p>  <div aria-live="polite" aria-busy={loading} className="intelligence-coverage">
   {loading&&<p role="status">Loading selected map evidence…</p>}
   {!!failures.length&&<p role="alert" className="notice error">{failures.map(s=>s.error).join(' · ')} No substitute geometry is shown. <button onClick={()=>{setRetry(n=>n+1);if(layers.shelters)shelters.refresh()}}>Retry map evidence</button></p>}
   <p><strong>{district?.name||'Karnataka statewide view'}</strong> · {directory.data?.total??'Unavailable'} district names; current LGD reconciliation unresolved. Statewide selection does not imply statewide hazard coverage.</p>
   {district&&!district.navigation_bounds&&<p className="notice">Verified public navigation bounds are unavailable for {district.name}; evidence filtering works, and the map retains its previous view.</p>}
   {district?.navigation_source&&<p className="muted">Navigation source: {district.navigation_source.id} · {district.navigation_source.license}. Bounds are context, not current official boundary certification.</p>}
   {safeHistory&&<p>{safeHistory.total} eligible historical cells across {safeHistory.coverage.historical_events} events{safeHistory.total===0?' — no reviewed public historical geometry for this district; not evidence of no flooding.':'. Raster cells are not independent flood events.'}</p>}
   {!layers.history&&<p>Historical layer hidden.</p>}
   {layers.hazards&&<p className="notice">{hazard.data?.message||hazardNotice} Historical events and terrain are not reclassified as potential hazards.</p>}
   {layers.shelters&&shownShelters&&<p>{shownShelters.mode==='demonstration'?'DEMONSTRATION ONLY — not actual destinations. ':''}{shownShelters.shelters.length?'Only currently verified Open entrances with spare capacity are shown.':'No currently verified open shelters are available in this directory.'} Directions are not verified flood-safe.</p>}
   {layers.shelters&&<p>Directory availability: {shelters.freshness}. Rechecked every minute in an active tab and when returning to the tab; network failures remove shelter markers.</p>}
   {layers.shelters&&shelters.data&&!shownShelters&&<p role="alert">Shelter availability could not be verified. No substitute destinations are shown.</p>}
  </div>
  <p className="muted">Click a historical polygon or choose a cell below for details. Clicking the background selects a weather point; it does not establish district identity or flood risk. <PageLink to="/weather" navigate={navigate}>View selected-point weather</PageLink>.</p>
  {safeHistory?.geojson?.features?.length>0&&<div className="intelligence-cell-selector"><label htmlFor="evidence-cell">Historical evidence cell (keyboard alternative)</label><select id="evidence-cell" value={featureId||''} onChange={e=>setFeatureId(e.target.value||null)}><option value="">Choose an observed cell</option>{safeHistory.geojson.features.map(f=><option key={f.id} value={f.id}>Udupi · GFD {f.properties.event_id} · row {f.properties.grid_row}, column {f.properties.grid_col}</option>)}</select></div>}
  {details.data?.feature&&<FeatureDetails data={details.data} navigate={navigate} onClose={()=>setFeatureId(null)}/>}
  {layers.history&&<details className="intelligence-events"><summary>Event sources and observation limitations</summary>{(safeHistory?.events||[]).map(e=><p key={e.event_id}>GFD {e.event_id}: {e.qualified_pixel_count} qualifying cells · Source image: {e.image_id}</p>)}<p>Two public Udupi event products. Other reviewed GFD positives, observed-zero comparisons and insufficient-observation scopes retain their research statuses; no unreviewed geometry or flood-negative labels are published.</p></details>}
  <p className="muted">Satellite evidence: <a href="https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1">Global Flood Database V1</a> · Tellman et al. (2021) · <a href="https://creativecommons.org/licenses/by-nc/4.0/">CC BY-NC 4.0</a>, attribution and non-commercial use required. Modern Udupi outline: geoBoundaries v6 · CC BY 4.0, not a verified historical boundary. SOI geometry remains local.</p>
  {layers.drainage&&<section className="panel"><h2>Drainage context</h2><p>Mapped drainage feature — overflow risk not established.</p>{drainage.data?.status==='available'?<><p>{drainage.data.coverage_notice}</p><p>OSM snapshot: {drainage.data.osm.osm_base_timestamp}; retrieved {drainage.data.osm.retrieved_at}. {drainage.data.osm.feature_count} mapped drain/ditch ways. Capacity, condition, blockage and flow direction are unknown.</p><DrainageResearchLayers/></>:<p>{drainage.data?.message||'Drainage context is not available yet.'} Absence of mapped data does not establish absence of drainage.</p>}</section>}</aside></div>
 </section>
}
