import React, { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { addBasemap, BASEMAP_NOTICE } from './mapBasemap.js'
import 'leaflet/dist/leaflet.css'
import useMapResize from './useMapResize.js'
import DrainageResearchLayers from './DrainageResearchLayers.jsx'
import useShelterDirectory, { validShelterDirectory } from './useShelterDirectory.js'
import { PageLink } from './AppNavigation.jsx'
import { useRiskGrid, useOfficialDistricts, LEVEL_COLORS, LEVEL_NAMES } from './useRisk.js'
import { OFFICIAL_COLOURS } from './OfficialWarnings.jsx'
import './RiskPanel.css'

const mechanismNames={riverine:'Riverine flooding',pluvial_urban_waterlogging:'Pluvial or urban waterlogging',flash:'Flash flooding',coastal:'Coastal flooding',unknown:'Unknown'}
const EMPTY={type:'FeatureCollection',features:[]}
const hazardNotice='No verified potential flood-prone zone dataset is available, so no flood-prone zones are shown.'
const KARNATAKA_BOUNDS=[[11.55,74.0],[18.48,78.6]]
// Room for the floating action buttons (top), layer box (right) and legend (bottom) so zoomed evidence stays clickable.
const CLEAR_OVERLAYS={paddingTopLeft:[24,60],paddingBottomRight:[280,110]}
const levelName=l=>l?l[0].toUpperCase()+l.slice(1):'Unavailable'
const monthYear=d=>new Date(d+'T00:00:00Z').toLocaleDateString('en-IN',{month:'long',year:'numeric',timeZone:'UTC'})
const eventName=e=>`${monthYear(e.start_date)} flood (${e.start_date} – ${e.end_date_inclusive})`
// Ray casting on GeoJSON rings ([lon,lat]); holes are subtracted.
function inRing(lon,lat,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const [xi,yi]=ring[i],[xj,yj]=ring[j];if((yi>lat)!==(yj>lat)&&lon<(xj-xi)*(lat-yi)/(yj-yi)+xi)inside=!inside}return inside}
export function inGeometry(lon,lat,g){const polys=g?.type==='Polygon'?[g.coordinates]:g?.type==='MultiPolygon'?g.coordinates:[];return polys.some(([outer,...holes])=>outer&&inRing(lon,lat,outer)&&!holes.some(h=>inRing(lon,lat,h)))}
const km=(a,b,c,d)=>{const r=Math.PI/180,x=(d-b)*r*Math.cos((a+c)/2*r),y=(c-a)*r;return 6371*Math.hypot(x,y)}
const firstVertex=g=>g?.type==='Polygon'?g.coordinates[0]?.[0]:g?.type==='MultiPolygon'?g.coordinates[0]?.[0]?.[0]:null
// Answers "what about this place?" only from data already on the page; every part says when it is unavailable.
export function placeCheck(point,{official,risk,history}){
 if(!point)return null
 const imd=official?.districts?.find(d=>inGeometry(point.longitude,point.latitude,d.geometry))||null
 const half=(risk?.cell_size_degrees||0)/2
 const cell=risk?.cells?.find(c=>Math.abs(c.latitude-point.latitude)<=half&&Math.abs(c.longitude-point.longitude)<=half)||null
 const near=history?.geojson?.features?.filter(f=>{const v=firstVertex(f.geometry);return v&&km(point.latitude,point.longitude,v[1],v[0])<=5}).length??null
 return {imd,cell,near}
}
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

function IntelligenceGeography({district,history,drainage,shelters,risk,official,point,popup,onPoint,onFeature,children}){
 const element=useRef(null),map=useRef(null),select=useRef(onPoint),detail=useRef(onFeature),zoneRenderer=useRef(null)
 const [tileError,setTileError]=useState(false)
 const districtRef=useRef(district)
 select.current=onPoint;detail.current=onFeature;districtRef.current=district
 useEffect(()=>{
  const view=L.map(element.current,{scrollWheelZoom:false,zoomControl:false,zoomSnap:0.25}).setView([15.1,76.1],6);map.current=view
  L.control?.zoom?.({position:'bottomright'}).addTo(view)
  addBasemap(L, view, () => setTileError(true))
  // Prediction zones are blurred in their own pane so the statewide grid reads as soft areas, not squares.
  const pane=view.createPane?.('riskZones');if(pane)pane.style.zIndex=350  // below overlays, so evidence polygons stay clickable
  zoneRenderer.current=L.svg?.({pane:'riskZones',padding:0.5})
  view.on('click',e=>select.current?.({name:'Selected map point',latitude:e.latlng.lat,longitude:((e.latlng.lng+180)%360+360)%360-180}))
  // Fit Karnataka again once the flex layout has given the map its final height.
  const settle=setTimeout(()=>{if(map.current===view&&!districtRef.current){view.invalidateSize?.();view.fitBounds(KARNATAKA_BOUNDS,{padding:[8,8],animate:false})}},200)
  return()=>{clearTimeout(settle);view.remove();map.current=null}
 },[])
 useMapResize(map)
 useEffect(()=>{
  if(!map.current)return
  if(!district)map.current.fitBounds(KARNATAKA_BOUNDS,{padding:[8,8],animate:false})
  else if(district.navigation_bounds)map.current.fitBounds(district.navigation_bounds,{padding:[20,20],animate:false})
 },[district])
 useEffect(()=>{
  if(!map.current)return
  const layers=[]
  const add=layer=>{layer.addTo(map.current);layers.push(layer)}
  if(risk?.cells){const radius=risk.cell_size_degrees*111000*0.62,ZONE={moderate:.34,high:.5,severe:.6}
   for(const cell of risk.cells){
    // Moderate+ are shaded soft zones; Low stays clear (but clickable); unavailable shows a grey dot.
    if(cell.level==='unavailable')add(L.circleMarker([cell.latitude,cell.longitude],{radius:2.5,color:'#8a8f98',weight:1,fillOpacity:.6,interactive:false}))
    const box=L.circle([cell.latitude,cell.longitude],{renderer:zoneRenderer.current||undefined,radius,stroke:false,fillColor:LEVEL_COLORS[cell.level]||LEVEL_COLORS.unavailable,fillOpacity:ZONE[cell.level]||0.001,bubblingMouseEvents:false})
    const text=document.createElement('span');text.textContent=`Rain risk ${LEVEL_NAMES[cell.level]||'Unavailable'} · next 24 h ${cell.rain_24h_mm??'–'} mm · past 5 days ${cell.rain_5d_mm??'–'} mm · peak ${cell.peak_mmh??'–'} mm/h`
    box.bindTooltip(text);box.on('click',e=>select.current?.({name:'Selected map point',latitude:e.latlng.lat,longitude:((e.latlng.lng+180)%360+360)%360-180}));add(box)
   }}
  if(official?.districts)for(const d of official.districts){
   const today=d.days[0],colour=OFFICIAL_COLOURS[today?.level]||'#8a8f98'
   const text=document.createElement('span');text.textContent=d.status==='stale'?`${d.district}: IMD bulletin from ${d.issued_date} is out of date`:`${d.district} · official IMD warning today: ${today?.level?today.level[0].toUpperCase()+today.level.slice(1):'Unavailable'}${today?.warnings?.length?' — '+today.warnings.join(', '):''}`
   add(L.geoJSON({type:'Feature',properties:{},geometry:d.geometry},{interactive:true,bubblingMouseEvents:true,style:{color:colour,weight:today?.level==='green'?1:3,opacity:.95,fillColor:colour,fillOpacity:today?.level==='green'?0.04:0.16},onEachFeature:(f,layer)=>layer.bindTooltip(text,{sticky:true})}))
  }
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
 },[history,drainage,shelters,risk,official])
 useEffect(()=>{
  if(!map.current||!point)return
  const marker=L.circleMarker([point.latitude,point.longitude],{radius:7,color:'#fff',weight:2,fillColor:'#344b68',fillOpacity:1}).addTo(map.current)
  let bubble=null
  if(popup&&L.popup){const text=document.createElement('div');text.className='place-popup';for(const line of popup){const row=document.createElement('div');row.textContent=line;text.appendChild(row)};bubble=L.popup({autoPan:true,closeButton:true,offset:[0,-4]}).setLatLng([point.latitude,point.longitude]).setContent(text).openOn(map.current)}
  return()=>{if(map.current){map.current.removeLayer(marker);if(bubble)map.current.closePopup?.(bubble)}}
 },[point,popup])
 function zoomWater(){if(history?.geojson?.features?.length){const bounds=L.geoJSON(history.geojson).getBounds();map.current?.fitBounds(bounds,{...CLEAR_OVERLAYS,maxZoom:14,animate:false})}}
 return <>
  <div className="intelligence-canvas">
  {history?.geojson?.features?.length>0&&<div className="map-actions intelligence-map-actions"><button onClick={zoomWater}>Zoom to past floods</button></div>}
  <div ref={element} className="historical-map intelligence-map" role="region" aria-label="Historical satellite floodwater and Karnataka evidence map"/>
  {children}
  </div>
  {tileError&&<p className="notice">{BASEMAP_NOTICE}</p>}
 </>
}

function FeatureDetails({data,onClose,navigate}){
 const feature=data.feature,p=feature.properties
 return <section className="panel intelligence-detail" aria-labelledby="feature-details-title">
  <div className="panel-heading"><h2 id="feature-details-title">Flood evidence details</h2><button onClick={onClose}>Close details</button></div>
  <dl><dt>District</dt><dd>{p.district}</dd><dt>Place</dt><dd>{p.place_name||'No verified settlement name for this raster cell'}</dd><dt>Evidence category</dt><dd>Historical observed floodwater polygon</dd><dt>Event</dt><dd>GFD {p.event_id} · {dates(p)}</dd><dt>Possible mechanism</dt><dd>{p.mechanism.mechanisms?.map(m=>mechanismNames[m]||'Unknown').join(', ')||'Unknown'} — {p.mechanism.method}</dd><dt>Observation quality</dt><dd>{p.observation_quality}; {p.clear_views} clear-view observations</dd><dt>Geometry meaning</dt><dd>{p.geometry_meaning} · {p.processing_grid_m} m processing grid</dd><dt>Drainage coverage</dt><dd>Limited, separately reviewed Udupi study; no cell-specific association established</dd><dt>Overflow assessment</dt><dd>Not validated</dd><dt>Environmental information</dt><dd><PageLink to="/weather" navigate={navigate}>Open selected-point weather details</PageLink>. This cell is not automatically a supported AI locality.</dd><dt>Source / version</dt><dd><a href={p.source.url}>{p.source.name}</a> · {p.dataset_version}</dd><dt>Source image</dt><dd>{p.image_id}</dd><dt>Licence</dt><dd><a href={p.source.license_url}>{p.source.license}</a> — {p.source.conditions}</dd><dt>Extraction retrieved</dt><dd>{p.retrieved_at}</dd><dt>Source geometry SHA-256</dt><dd>{p.source_geometry_sha256}</dd><dt>Stable feature ID</dt><dd>{feature.id}</dd></dl>
  <p className="notice">{p.limitations} Missing observations are unknown, not non-flood. Current LGD reconciliation remains unresolved.</p>
 </section>
}

export default function FloodIntelligenceMap({point,onPoint,navigate,selectedDistrictId,onDistrictChange,selectedFeatureId,onFeatureChange}){
 const [districtId,setDistrictId]=useState(''),[eventId,setEventId]=useState(''),[featureId,setFeatureId]=useState(null),[retry,setRetry]=useState(0)
 const [checked,setChecked]=useState(point||null)
 useEffect(()=>{setChecked(point||null)},[point?.latitude,point?.longitude])
 useEffect(()=>{if(selectedDistrictId!==undefined){setDistrictId(selectedDistrictId);setFeatureId(null)}},[selectedDistrictId])
 useEffect(()=>{if(selectedFeatureId!==undefined)setFeatureId(selectedFeatureId)},[selectedFeatureId])
 function chooseFeature(id){setFeatureId(id);onFeatureChange?.(id)}
 function check(next){setChecked(next);onPoint?.(next)}
 const [layers,setLayers]=useState({official:true,risk:true,history:true,drainage:false,shelters:false})
 const riskGrid=useRiskGrid(layers.risk),officialDistricts=useOfficialDistricts(true)
 const directory=useEvidence('/api/flood-map/districts',retry)
 const query=new URLSearchParams(districtId?{district_id:districtId}:{})
 const historicalQuery=new URLSearchParams(query);if(eventId)historicalQuery.set('event_id',eventId)
 const history=useEvidence(layers.history?'/api/flood-map/historical?'+historicalQuery:null,retry)
 const drainage=useEvidence(layers.drainage?'/api/flood-map/drainage?'+query:null,retry)
 const shelters=useShelterDirectory(null,layers.shelters)
 const details=useEvidence(featureId?'/api/flood-map/features/'+encodeURIComponent(featureId):null,retry)
 const district=directory.data?.items.find(d=>d.id===districtId)||null
 const shownShelters=shelters.data&&validShelterDirectory(shelters.data)?{...shelters.data,shelters:shelters.data.shelters.filter(s=>!districtId||s.district_id===districtId)}:null
 function toggle(key){setLayers(current=>({...current,[key]:!current[key]}));if(key==='history')chooseFeature(null)}
 function chooseDistrict(id){setDistrictId(id);onDistrictChange?.(id,directory.data?.items.find(d=>d.id===id)||null);chooseFeature(null)}
 const failures=[directory,history,drainage,shelters,details].filter(s=>s.error)
 const loading=[directory,history,drainage,shelters,details].some(s=>s.loading)
 const safeHistory=history.data?.status==='available'&&history.data.geojson?.type==='FeatureCollection'?history.data:null
 const warned=officialDistricts.data?['red','orange','yellow'].map(l=>[l,officialDistricts.data.districts.filter(d=>d.status!=='stale'&&d.days[0]?.level===l).map(d=>d.district).sort()]).filter(([,names])=>names.length):[]
 const riskCounts=riskGrid.data?['severe','high','moderate'].map(l=>[l,riskGrid.data.cells.filter(c=>c.level===l).length]).filter(([,n])=>n):[]
 const place=placeCheck(checked,{official:officialDistricts.data,risk:layers.risk?riskGrid.data:null,history:safeHistory})
 const today=place?.imd&&place.imd.status!=='stale'?place.imd.days[0]:null
 const popup=place?[place.imd?`${place.imd.district} district`:'Outside Karnataka districts',`Official IMD warning today: ${today?levelName(today.level):'unavailable'}`,place.cell?`Rain risk next 24 h: ${LEVEL_NAMES[place.cell.level]||'Unavailable'} (experimental)`:null].filter(Boolean):null
 return <section className="intelligence-workspace" aria-labelledby="intelligence-title">
  <h2 id="intelligence-title" className="visually-hidden">Karnataka Flood Intelligence</h2>
  <div className="panel intelligence-toolbar">
   <p className="intelligence-howto"><strong>Tap any place on the map</strong> to check its official warning, rain risk and past floods.</p>
   <label htmlFor="intelligence-district">Go to district</label><select id="intelligence-district" value={districtId} disabled={!directory.data} onChange={e=>chooseDistrict(e.target.value)}><option value="">All of Karnataka</option>{directory.data?.items.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select>
   {districtId&&<button className="secondary" onClick={()=>chooseDistrict('')}>Show all Karnataka</button>}
  </div>
  <div className="intelligence-layout"><div className="intelligence-map-stage">
  <IntelligenceGeography district={district} history={safeHistory} drainage={drainage.data} shelters={shownShelters} risk={layers.risk&&riskGrid.data?.cells?riskGrid.data:null} official={layers.official?officialDistricts.data:null} point={checked} popup={popup} onPoint={check} onFeature={chooseFeature}>
   <fieldset className="intelligence-layers"><legend>Show on map</legend>
    <p className="layer-group">Today</p>{[['official','Official IMD warnings'],['risk','Rain risk, next 24 h']].map(([key,label])=><label key={key}><input type="checkbox" checked={layers[key]} onChange={()=>toggle(key)}/>{label}</label>)}
    <p className="layer-group">Background</p>{[['history','Past floods (satellite)'],['drainage','Drains (Udupi study)'],['shelters','Verified shelters']].map(([key,label])=><label key={key}><input type="checkbox" checked={layers[key]} onChange={()=>toggle(key)}/>{label}</label>)}
   </fieldset>
   <div className="intelligence-legend" aria-label="Map legend">
    {layers.official&&<div className="risk-legend" aria-label="Official IMD warning legend"><strong>IMD today</strong>{['red','orange','yellow','green'].map(l=><span key={l} style={{'--swatch':OFFICIAL_COLOURS[l]}}>{levelName(l)}</span>)}</div>}
    {layers.risk&&<div className="risk-legend zones" aria-label="Rain risk legend"><strong>Rain risk 24 h</strong>{['moderate','high','severe','unavailable'].map(l=><span key={l} style={{'--swatch':LEVEL_COLORS[l]}}>{LEVEL_NAMES[l]}</span>)}<span className="muted">clear = Low</span></div>}
    <div className="risk-legend other">{layers.history&&<span className="legend-water">Past flood</span>}{layers.drainage&&<span className="legend-drain">Drainage study</span>}{layers.shelters&&<span className="legend-shelter">Verified shelter</span>}<span className="legend-point">Your checked place</span></div>
   </div>
  </IntelligenceGeography>
</div><aside className="intelligence-sidebar" aria-label="Map evidence and limitations" tabIndex={0}>  <div aria-live="polite" aria-busy={loading} className="intelligence-coverage">
   {place?<section className="intelligence-card place-check" aria-labelledby="place-check-title">
     <div className="place-check-head"><h3 id="place-check-title">{place.imd?`Checked place · ${place.imd.district}`:'Checked place'}</h3><button className="link-button" onClick={()=>setChecked(null)}>Clear</button></div>
     <p className="muted">{checked.latitude.toFixed(4)}°N, {checked.longitude.toFixed(4)}°E{!place.imd&&officialDistricts.data?' · outside Karnataka district boundaries':''}</p>
     <dl className="place-rows">
      <div><dt>Official IMD warning today</dt><dd>{today?<><span className="official-chip" data-level={today.level} style={{background:OFFICIAL_COLOURS[today.level]}}>{levelName(today.level)}</span> {today.warnings?.length?today.warnings.join(', '):'No warning (Green)'}</>:place.imd?.status==='stale'?'IMD bulletin is out of date — check IMD directly.':officialDistricts.error?'Could not be checked. This does not mean there is no warning.':officialDistricts.data?'Not available for this point.':'Checking…'}</dd></div>
      <div><dt>Rain risk, next 24 h <small>experimental</small></dt><dd>{!layers.risk?'Turn on "Rain risk, next 24 h" to see it.':place.cell?<><span className="risk-chip" style={{'--swatch':LEVEL_COLORS[place.cell.level]}}>{LEVEL_NAMES[place.cell.level]||'Unavailable'}</span> {place.cell.rain_24h_mm??'–'} mm rain forecast</>:riskGrid.data?'Outside the statewide grid.':'Checking…'}</dd></div>
      <div><dt>Past floods mapped within 5 km</dt><dd>{!layers.history?'Turn on "Past floods" to see them.':place.near===null?'Checking…':place.near?`${place.near} mapped flood cells nearby — this area has flooded before.`:'None mapped. Satellite records cover only parts of Udupi; this does not mean it is safe.'}</dd></div>
     </dl>
     <div className="place-actions"><PageLink to="/" navigate={navigate} className="button-link">Full check on Home</PageLink><PageLink to="/shelters" navigate={navigate} className="button-link secondary">Shelters near here</PageLink></div>
    </section>:<div className="intelligence-card place-prompt"><h3>Check a place</h3><p>Tap or click anywhere on the map. You will see the official IMD warning for that district, the experimental rain risk for the next 24 hours, and whether floods were mapped nearby before.</p></div>}
   <h3 className="intelligence-glance-title">{district?.name||'Today across Karnataka'}</h3>
   {loading&&<p role="status">Loading map information…</p>}
   {!!failures.length&&<p role="alert" className="notice error">{failures.map(s=>s.error).join(' · ')} No substitute geometry is shown. <button onClick={()=>{setRetry(n=>n+1);if(layers.shelters)shelters.refresh()}}>Retry map evidence</button></p>}
   <div className="intelligence-card official-district-status"><p><strong>Official IMD warnings today:</strong> {officialDistricts.loading&&!officialDistricts.data?'loading':officialDistricts.error?`unavailable (${officialDistricts.error}). This does not mean there is no warning`:officialDistricts.data?['red','orange','yellow','green'].map(l=>[l,officialDistricts.data.districts.filter(d=>d.days[0]?.level===l).length]).filter(([,n])=>n).map(([l,n])=>`${n} ${levelName(l)}`).join(' · ')||'no current district bulletins':'unavailable'}.</p>
    {warned.length>0&&<ul className="warned-districts" aria-label="Districts under an IMD warning today">{warned.map(([l,names])=><li key={l} style={{'--swatch':OFFICIAL_COLOURS[l]}}><span className="warned-level">{levelName(l)}</span> {names.join(', ')}</li>)}</ul>}
    <p className="muted">As issued by the India Meteorological Department (<a href="https://mausam.imd.gov.in/responsive/districtWiseWarningGIS.php">source</a>). Red = take action, Orange = be prepared, Yellow = be updated.</p></div>
   {layers.risk&&<div className="intelligence-card risk-grid-status"><p><strong>Rain risk, next 24 h:</strong> {riskGrid.loading&&!riskGrid.data?'loading statewide grid':riskGrid.error?riskGrid.error:riskGrid.data?(riskCounts.length?`${riskGrid.data.cells.filter(c=>['high','severe'].includes(c.level)).length} of ${riskGrid.data.cells.length} areas High or Severe`:`all ${riskGrid.data.cells.length} areas Low or unavailable`)+` · checked ${new Date(riskGrid.data.retrieved_at).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour:'numeric',minute:'2-digit'})} IST`:'unavailable'}.</p>
    {riskCounts.length>0&&<p className="risk-count-chips">{riskCounts.map(([l,n])=><span key={l} className="risk-chip" style={{'--swatch':LEVEL_COLORS[l]}}>{n} {LEVEL_NAMES[l]}</span>)}</p>}
    <p className="muted">Experimental rule-based index from forecast rain only (~28 km areas) — not a flood probability or an official warning.</p></div>}
   {layers.history&&<section className="intelligence-card past-floods" aria-labelledby="past-floods-title"><h3 id="past-floods-title">Past floods</h3>
    <p className="historical-notice">{safeHistory?(safeHistory.total===0?'No past floods are mapped for this district. This does not mean it never floods.':`${safeHistory.total} mapped flood cells from ${safeHistory.coverage.historical_events} recorded floods in ${[...new Set(safeHistory.geojson.features.map(f=>f.properties.district).filter(Boolean))].join(', ')||'mapped districts'}.`):history.error?'Past floods could not be loaded.':'Loading past floods…'}</p>
    <p className="muted">Maximum water seen by satellite during each flood — not current flooding, flooded roads or evacuation advice.</p>
    <label>Recorded flood<select aria-label="Recorded flood" value={eventId} onChange={e=>{setEventId(e.target.value);chooseFeature(null)}}><option value="">All recorded floods</option>{(safeHistory?.events||[]).map(e=><option key={e.event_id} value={e.event_id}>{eventName(e)}</option>)}</select></label>
    {safeHistory?.geojson?.features?.length>0&&<div className="intelligence-cell-selector"><label htmlFor="evidence-cell">Mapped flood cell</label><select id="evidence-cell" value={featureId||''} onChange={e=>chooseFeature(e.target.value||null)}><option value="">Choose a mapped cell for details</option>{safeHistory.geojson.features.map(f=><option key={f.id} value={f.id}>{f.properties.district||'Udupi'} · {monthYear(f.properties.start_date)} flood · row {f.properties.grid_row}, column {f.properties.grid_col}</option>)}</select></div>}
   </section>}
   {!layers.history&&<p className="muted">Past floods hidden.</p>}
   {district&&!district.navigation_bounds&&<p className="notice">Map bounds are unavailable for {district.name}, so the map keeps its current view; the information here is still filtered to {district.name}.</p>}
   {layers.shelters&&shownShelters&&<p>{shownShelters.mode==='demonstration'?'DEMONSTRATION ONLY — not actual destinations. ':''}{shownShelters.shelters.length?'Only currently verified Open entrances with spare capacity are shown.':'No currently verified open shelters are available in this directory.'} Directions are not verified flood-safe.</p>}
   {layers.shelters&&<p className="muted">Shelter availability: {shelters.freshness}, rechecked every minute.</p>}
   {layers.shelters&&shelters.data&&!shownShelters&&<p role="alert">Shelter availability could not be verified. No substitute destinations are shown.</p>}
  </div>
  {details.data?.feature&&<FeatureDetails data={details.data} navigate={navigate} onClose={()=>chooseFeature(null)}/>}
  <details className="intelligence-events"><summary>Sources and limitations</summary>{layers.history&&(safeHistory?.events||[]).map(e=><p key={e.event_id}>GFD {e.event_id} ({eventName(e)}): {e.qualified_pixel_count} qualifying cells · Source image: {e.image_id}</p>)}{layers.history&&<p>Two public Udupi event products. Raster cells are not independent flood events. Other reviewed GFD positives, observed-zero comparisons and insufficient-observation scopes retain their research statuses; no unreviewed geometry or flood-negative labels are published.</p>}
   <p>{hazardNotice} Past floods and terrain are not relabelled as flood-prone zones.</p>
   <p>{directory.data?.total??'Unavailable'} district names; current LGD reconciliation unresolved. A checked place uses IMD's district polygons; it does not establish an administrative identity.</p>
   {district?.navigation_source&&<p>Navigation source: {district.navigation_source.id} · {district.navigation_source.license}. Bounds are context, not current official boundary certification.</p>}</details>
  <p className="muted intelligence-attribution">Satellite evidence: <a href="https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1">Global Flood Database V1</a> · Tellman et al. (2021) · <a href="https://creativecommons.org/licenses/by-nc/4.0/">CC BY-NC 4.0</a>, attribution and non-commercial use required. Modern Udupi outline: geoBoundaries v6 · CC BY 4.0, not a verified historical boundary. SOI geometry remains local.</p>
  {layers.drainage&&<section className="panel"><h2>Drainage context</h2><p>Mapped drainage feature — overflow risk not established.</p>{drainage.data?.status==='available'?<><p>{drainage.data.coverage_notice}</p><p>OSM snapshot: {drainage.data.osm.osm_base_timestamp}; retrieved {drainage.data.osm.retrieved_at}. {drainage.data.osm.feature_count} mapped drain/ditch ways. Capacity, condition, blockage and flow direction are unknown.</p><DrainageResearchLayers/></>:<p>{drainage.data?.message||'Drainage context is not available yet.'} Absence of mapped data does not establish absence of drainage.</p>}</section>}</aside></div>
 </section>
}
