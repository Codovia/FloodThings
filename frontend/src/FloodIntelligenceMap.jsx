import React, { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { addBasemap, BASEMAP_NOTICE } from './mapBasemap.js'
import 'leaflet/dist/leaflet.css'
import useMapResize from './useMapResize.js'
import useShelterDirectory, { validShelterDirectory } from './useShelterDirectory.js'
import { PageLink } from './AppNavigation.jsx'
import { useRiskGrid, useOfficialDistricts, useRiverForecast, LEVEL_COLORS, LEVEL_NAMES } from './useRisk.js'
import { OFFICIAL_COLOURS } from './OfficialWarnings.jsx'
import './RiskPanel.css'
import ScreenTabs, { useWide } from './ScreenTabs.jsx'
import Popup from './Popup.jsx'

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
   if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:typeof data.message==='string'?data.message:'Map evidence request failed')
   if(active)setState({url,data,error:null,loading:false})
  }).catch(error=>{if(active)setState({url,data:null,error:timedOut?'Map evidence request timed out.':error.message,loading:false})}).finally(()=>clearTimeout(timer))
  return()=>{active=false;clearTimeout(timer);controller.abort()}
 },[url,retry])
 return !url?{data:null,error:null,loading:false}:state.url===url?state:{data:null,error:null,loading:true}
}

function IntelligenceGeography({district,history,shelters,risk,official,rivers,point,popup,onPoint,onFeature,children}){
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
    const text=document.createElement('span');text.textContent=`${monthYear(feature.properties.start_date)} flood · seen by satellite`
    layer.bindTooltip(text);layer.on('click',()=>detail.current(feature.id))
   }}))
  // Checked river points: GloFAS 7-day forecast against each cell's own flood levels.
  if(rivers)for(const r of rivers){
   const marker=L.circleMarker([r.grid.latitude,r.grid.longitude],{radius:9,color:'#0d3b66',weight:3,fillColor:LEVEL_COLORS[r.level],fillOpacity:.95,bubblingMouseEvents:false})
   const text=document.createElement('span');text.textContent=`${r.river} at ${r.place} · river flood forecast, 7 days: ${LEVEL_NAMES[r.level]} — ${Math.round(r.peak.share_above['2_year']*100)}% of forecast runs above the 2-year flood level (${r.peak.date}). Modelled, not observed.`
   marker.bindTooltip(text);add(marker)
  }
  if(shelters&&validShelterDirectory(shelters))for(const shelter of shelters.shelters){
   const marker=L.circleMarker([shelter.latitude,shelter.longitude],{radius:9,color:'#00695c',fillColor:'#18a999',fillOpacity:.9})
   const text=document.createElement('span');text.textContent=`${shelters.mode==='demonstration'?'DEMONSTRATION ONLY — ':''}${shelter.name} · ${shelter.available_capacity} reported spaces · verified ${shelter.verified_at}`;marker.bindPopup(text);add(marker)
  }
  return()=>{if(map.current)for(const layer of layers)map.current.removeLayer(layer)}
 },[history,shelters,risk,official,rivers])
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

function FeatureDetails({data}){
 const p=data.feature.properties
 return <div className="intelligence-detail">
  <dl><dt>District</dt><dd>{p.district}</dd><dt>Place</dt><dd>{p.place_name||'No verified place name for this cell'}</dd><dt>Flood</dt><dd>{dates(p)} (Global Flood Database event {p.event_id})</dd><dt>Satellite views</dt><dd>{p.clear_views} cloud-free satellite observations</dd><dt>Cell size</dt><dd>About {p.processing_grid_m} m</dd><dt>Source</dt><dd><a href={p.source.url}>{p.source.name}</a> · {p.dataset_version}</dd><dt>Licence</dt><dd><a href={p.source.license_url}>{p.source.license}</a> — {p.source.conditions}</dd></dl>
  <p className="notice">Maximum water seen by satellite during this flood — not current flooding. Places without satellite coverage are unknown, not flood-free.</p>
 </div>
}

export default function FloodIntelligenceMap({point,onPoint,navigate,selectedDistrictId,onDistrictChange,selectedFeatureId,onFeatureChange}){
 const [districtId,setDistrictId]=useState(''),[eventId,setEventId]=useState(''),[featureId,setFeatureId]=useState(null),[retry,setRetry]=useState(0)
 const [checked,setChecked]=useState(point||null)
 useEffect(()=>{setChecked(point||null)},[point?.latitude,point?.longitude])
 useEffect(()=>{if(selectedDistrictId!==undefined){setDistrictId(selectedDistrictId);setFeatureId(null)}},[selectedDistrictId])
 useEffect(()=>{if(selectedFeatureId!==undefined)setFeatureId(selectedFeatureId)},[selectedFeatureId])
 function chooseFeature(id){setFeatureId(id);onFeatureChange?.(id)}
 const wide=useWide(),[tab,setTab]=useState(()=>wide?'place':'map')
 function check(next){setChecked(next);onPoint?.(next);setTab('place')}
 const [layers,setLayers]=useState({official:true,risk:true,rivers:true,history:true,shelters:false})
 const riskGrid=useRiskGrid(layers.risk),officialDistricts=useOfficialDistricts(true),riverForecast=useRiverForecast(layers.rivers)
 const directory=useEvidence('/api/flood-map/districts',retry)
 const query=new URLSearchParams(districtId?{district_id:districtId}:{})
 const historicalQuery=new URLSearchParams(query);if(eventId)historicalQuery.set('event_id',eventId)
 const history=useEvidence(layers.history?'/api/flood-map/historical?'+historicalQuery:null,retry)
 const shelters=useShelterDirectory(null,layers.shelters)
 const details=useEvidence(featureId?'/api/flood-map/features/'+encodeURIComponent(featureId):null,retry)
 const district=directory.data?.items.find(d=>d.id===districtId)||null
 const shownShelters=shelters.data&&validShelterDirectory(shelters.data)?{...shelters.data,shelters:shelters.data.shelters.filter(s=>!districtId||s.district_id===districtId)}:null
 function toggle(key){setLayers(current=>({...current,[key]:!current[key]}));if(key==='history')chooseFeature(null)}
 function chooseDistrict(id){setDistrictId(id);onDistrictChange?.(id,directory.data?.items.find(d=>d.id===id)||null);chooseFeature(null)}
 const failures=[directory,history,shelters,details].filter(s=>s.error)
 const loading=[directory,history,shelters,details].some(s=>s.loading)
 const safeHistory=history.data?.status==='available'&&history.data.geojson?.type==='FeatureCollection'?history.data:null
 const warned=officialDistricts.data?['red','orange','yellow'].map(l=>[l,officialDistricts.data.districts.filter(d=>d.status!=='stale'&&d.days[0]?.level===l).map(d=>d.district).sort()]).filter(([,names])=>names.length):[]
 const riskCounts=riskGrid.data?['severe','high','moderate'].map(l=>[l,riskGrid.data.cells.filter(c=>c.level===l).length]).filter(([,n])=>n):[]
 const place=placeCheck(checked,{official:officialDistricts.data,risk:layers.risk?riskGrid.data:null,history:safeHistory})
 const today=place?.imd&&place.imd.status!=='stale'?place.imd.days[0]:null
 const popup=place?[place.imd?`${place.imd.district} district`:'Outside Karnataka districts',`Official IMD warning today: ${today?levelName(today.level):'unavailable'}`,place.cell?`Rain risk next 24 h: ${LEVEL_NAMES[place.cell.level]||'Unavailable'} (experimental)`:null].filter(Boolean):null
 const mapStage=<div className="intelligence-map-stage">
  <IntelligenceGeography district={district} history={safeHistory} shelters={shownShelters} risk={layers.risk&&riskGrid.data?.cells?riskGrid.data:null} official={layers.official?officialDistricts.data:null} rivers={layers.rivers&&riverForecast.data?riverForecast.data.points:null} point={checked} popup={popup} onPoint={check} onFeature={chooseFeature}>
   {wide?<>
   <fieldset className="intelligence-layers"><legend>Show on map</legend>
    <p className="layer-group">Today</p>{[['official','Official IMD warnings'],['risk','Rain risk, next 24 h'],['rivers','River flood forecast, 7 days']].map(([key,label])=><label key={key}><input type="checkbox" checked={layers[key]} onChange={()=>toggle(key)}/>{label}</label>)}
    <p className="layer-group">Background</p>{[['history','Past floods (satellite)'],['shelters','Verified shelters']].map(([key,label])=><label key={key}><input type="checkbox" checked={layers[key]} onChange={()=>toggle(key)}/>{label}</label>)}
   </fieldset>
   <div className="intelligence-legend" aria-label="Map legend">
    {layers.official&&<div className="risk-legend" aria-label="Official IMD warning legend"><strong>IMD today</strong>{['red','orange','yellow','green'].map(l=><span key={l} style={{'--swatch':OFFICIAL_COLOURS[l]}}>{levelName(l)}</span>)}</div>}
    {layers.risk&&<div className="risk-legend zones" aria-label="Rain risk legend"><strong>Rain risk 24 h</strong>{['moderate','high','severe','unavailable'].map(l=><span key={l} style={{'--swatch':LEVEL_COLORS[l]}}>{LEVEL_NAMES[l]}</span>)}<span className="muted">clear = Low</span></div>}
    {layers.rivers&&<div className="risk-legend rivers" aria-label="River flood forecast legend"><strong>Rivers 7 days</strong>{['low','moderate','high','severe'].map(l=><span key={l} style={{'--swatch':LEVEL_COLORS[l]}}>{LEVEL_NAMES[l]}</span>)}</div>}
    <div className="risk-legend other">{layers.history&&<span className="legend-water">Past flood</span>}{layers.shelters&&<span className="legend-shelter">Verified shelter</span>}<span className="legend-point">Your checked place</span></div>
   </div>
   </>:<div className="intelligence-layers-toggle"><Popup label="Layers & legend" buttonClassName="secondary" title="Map layers and legend">
   <fieldset className="intelligence-layers"><legend>Show on map</legend>
    <p className="layer-group">Today</p>{[['official','Official IMD warnings'],['risk','Rain risk, next 24 h'],['rivers','River flood forecast, 7 days']].map(([key,label])=><label key={key}><input type="checkbox" checked={layers[key]} onChange={()=>toggle(key)}/>{label}</label>)}
    <p className="layer-group">Background</p>{[['history','Past floods (satellite)'],['shelters','Verified shelters']].map(([key,label])=><label key={key}><input type="checkbox" checked={layers[key]} onChange={()=>toggle(key)}/>{label}</label>)}
   </fieldset>
   <div className="intelligence-legend" aria-label="Map legend">
    {layers.official&&<div className="risk-legend" aria-label="Official IMD warning legend"><strong>IMD today</strong>{['red','orange','yellow','green'].map(l=><span key={l} style={{'--swatch':OFFICIAL_COLOURS[l]}}>{levelName(l)}</span>)}</div>}
    {layers.risk&&<div className="risk-legend zones" aria-label="Rain risk legend"><strong>Rain risk 24 h</strong>{['moderate','high','severe','unavailable'].map(l=><span key={l} style={{'--swatch':LEVEL_COLORS[l]}}>{LEVEL_NAMES[l]}</span>)}<span className="muted">clear = Low</span></div>}
    {layers.rivers&&<div className="risk-legend rivers" aria-label="River flood forecast legend"><strong>Rivers 7 days</strong>{['low','moderate','high','severe'].map(l=><span key={l} style={{'--swatch':LEVEL_COLORS[l]}}>{LEVEL_NAMES[l]}</span>)}</div>}
    <div className="risk-legend other">{layers.history&&<span className="legend-water">Past flood</span>}{layers.shelters&&<span className="legend-shelter">Verified shelter</span>}<span className="legend-point">Your checked place</span></div>
   </div>
   </Popup></div>}
  </IntelligenceGeography>
 </div>
 const tabs=[!wide&&{id:'map',label:'Map',content:mapStage},
  {id:'place',label:'Place',content:place?<section className="intelligence-card place-check" aria-labelledby="place-check-title">
     <div className="place-check-head"><h3 id="place-check-title">{place.imd?`Checked place · ${place.imd.district}`:'Checked place'}</h3><button className="link-button" onClick={()=>setChecked(null)}>Clear</button></div>
     <p className="muted">{checked.latitude.toFixed(4)}°N, {checked.longitude.toFixed(4)}°E{!place.imd&&officialDistricts.data?' · outside Karnataka district boundaries':''}</p>
     <dl className="place-rows">
      <div><dt>Official IMD warning today</dt><dd>{today?<><span className="official-chip" data-level={today.level} style={{background:OFFICIAL_COLOURS[today.level]}}>{levelName(today.level)}</span> {today.warnings?.length?today.warnings.join(', '):'No warning (Green)'}</>:place.imd?.status==='stale'?'IMD bulletin is out of date — check IMD directly.':officialDistricts.error?'Could not be checked. This does not mean there is no warning.':officialDistricts.data?'Not available for this point.':'Checking…'}</dd></div>
      <div><dt>Rain risk, next 24 h <small>experimental</small></dt><dd>{!layers.risk?'Turn on "Rain risk, next 24 h" to see it.':place.cell?<><span className="risk-chip" style={{'--swatch':LEVEL_COLORS[place.cell.level]}}>{LEVEL_NAMES[place.cell.level]||'Unavailable'}</span> {place.cell.rain_24h_mm??'–'} mm rain forecast</>:riskGrid.data?'Outside the statewide grid.':'Checking…'}</dd></div>
      <div><dt>Past floods mapped within 5 km</dt><dd>{!layers.history?'Turn on "Past floods" to see them.':place.near===null?'Checking…':place.near?`${place.near} mapped flood cells nearby — this area has flooded before.`:'None mapped. Satellite records cover only parts of Udupi; this does not mean it is safe.'}</dd></div>
     </dl>
     <div className="place-actions"><PageLink to="/" navigate={navigate} className="button-link">Full check on Home</PageLink><PageLink to="/shelters" navigate={navigate} className="button-link secondary">Shelters near here</PageLink></div>
    </section>:<div className="intelligence-card place-prompt"><h3>Check a place</h3><p>Tap or click anywhere on the map. You will see the official IMD warning for that district, the experimental rain risk for the next 24 hours, and whether floods were mapped nearby before.</p></div>},
  {id:'today',label:'Today',content:<>
   <h3 className="intelligence-glance-title">{district?.name||'Today across Karnataka'}</h3>
   <div className="intelligence-card official-district-status"><p><strong>Official IMD warnings today:</strong> {officialDistricts.loading&&!officialDistricts.data?'loading':officialDistricts.error?`unavailable (${officialDistricts.error}). This does not mean there is no warning`:officialDistricts.data?['red','orange','yellow','green'].map(l=>[l,officialDistricts.data.districts.filter(d=>d.days[0]?.level===l).length]).filter(([,n])=>n).map(([l,n])=>`${n} ${levelName(l)}`).join(' · ')||'no current district bulletins':'unavailable'}.</p>
    {warned.length>0&&<ul className="warned-districts" aria-label="Districts under an IMD warning today">{warned.map(([l,names])=><li key={l} style={{'--swatch':OFFICIAL_COLOURS[l]}}><span className="warned-level">{levelName(l)}</span> {names.join(', ')}</li>)}</ul>}
    <p className="muted">As issued by the India Meteorological Department (<a href="https://mausam.imd.gov.in/responsive/districtWiseWarningGIS.php">source</a>). Red = take action, Orange = be prepared, Yellow = be updated.</p></div>
   {layers.risk&&<div className="intelligence-card risk-grid-status"><p><strong>Rain risk, next 24 h:</strong> {riskGrid.loading&&!riskGrid.data?'loading statewide grid':riskGrid.error?riskGrid.error:riskGrid.data?(riskCounts.length?`${riskGrid.data.cells.filter(c=>['high','severe'].includes(c.level)).length} of ${riskGrid.data.cells.length} areas High or Severe`:`all ${riskGrid.data.cells.length} areas Low or unavailable`)+` · checked ${new Date(riskGrid.data.retrieved_at).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour:'numeric',minute:'2-digit'})} IST`:'unavailable'}.</p>
    {riskCounts.length>0&&<p className="risk-count-chips">{riskCounts.map(([l,n])=><span key={l} className="risk-chip" style={{'--swatch':LEVEL_COLORS[l]}}>{n} {LEVEL_NAMES[l]}</span>)}</p>}
    <p className="muted">Experimental rule-based index from forecast rain only (~28 km areas) — not a flood probability or an official warning.</p></div>}
  </>},
  {id:'rivers',label:'Rivers',content:<section className="intelligence-card river-forecast" aria-labelledby="river-forecast-title">
   <h3 id="river-forecast-title">River flood forecast · next 7 days <span className="source-tag experimental">Experimental</span></h3>
   {!layers.rivers?<p className="muted">River forecast hidden. Turn on "River flood forecast" in the map layers.</p>
    :riverForecast.loading&&!riverForecast.data?<p role="status">Loading the river forecast…</p>
    :riverForecast.error||!riverForecast.data?<p role="status">River forecast unavailable{riverForecast.error?` (${riverForecast.error})`:''}. This does not mean rivers are normal; check CWC and KSNDMC.</p>
    :<ul className="river-list" aria-label="River flood forecast, next 7 days">{riverForecast.data.points.map(r=><li key={r.id} data-level={r.level}>
      <span className="risk-chip" style={{'--swatch':LEVEL_COLORS[r.level]}}>{LEVEL_NAMES[r.level]}</span>
      <strong>{r.river}</strong> at {r.place} <span className="muted">({r.district})</span>
      <small>{Math.round(r.peak.share_above['2_year']*100)}% of runs above the 2-year flood level · {Math.round(r.peak.share_above['5_year']*100)}% above 5-year</small></li>)}</ul>}
   <p className="muted">Modelled river flow from Copernicus GloFAS (50 forecast runs) at {riverForecast.data?.points.length||6} river points checked against OpenStreetMap and past floods. Not observed water levels or an official warning; dam releases are only approximated.</p>
   <p className="muted"><Popup label="How the river forecast was checked" title="How the river forecast works">
    <p>Each point is the GloFAS model cell on a named river near a town. A point was kept only if OpenStreetMap shows that river within 3 km and the model's largest past flows (1997–2021) fall within 3 days of a documented flood, such as the Krishna and Ghataprabha floods of August 2019 and the Kabini flood of August 2018.</p>
    <p>Flood levels (2-, 5- and 10-year) come from each cell's own 25 yearly maxima, as GloFAS does. "High" means most of the 50 forecast runs exceed the 2-year level; "Severe", the 5-year level; "Moderate", at least 1 in 5 runs above the 2-year level. These cut-offs are the project's choice.</p>
    <p>Not shown: Bhima at Afzalpur and Kaveri at Srirangapatna did not pass the past-flood check, so they are not forecast here. Source: Copernicus GloFAS v4 via Open-Meteo (CC BY 4.0); river lines © OpenStreetMap contributors.</p>
   </Popup></p>
  </section>},
  {id:'floods',label:<><span className="label-long">Past floods</span><span className="label-short">Floods</span></>,ariaLabel:'Past floods',content:<>
   {layers.history&&<section className="intelligence-card past-floods" aria-labelledby="past-floods-title"><h3 id="past-floods-title">Past floods</h3>
    <p className="historical-notice">{safeHistory?(safeHistory.total===0?'No past floods are mapped for this district. This does not mean it never floods.':`${safeHistory.total} mapped flood cells from ${safeHistory.coverage.historical_events} recorded floods in ${[...new Set(safeHistory.geojson.features.map(f=>f.properties.district).filter(Boolean))].join(', ')||'mapped districts'}.`):history.error?'Past floods could not be loaded.':'Loading past floods…'}</p>
    <p className="muted">Maximum water seen by satellite during each flood — not current flooding, flooded roads or evacuation advice.</p>
    <label>Recorded flood<select aria-label="Recorded flood" value={eventId} onChange={e=>{setEventId(e.target.value);chooseFeature(null)}}><option value="">All recorded floods</option>{(safeHistory?.events||[]).map(e=><option key={e.event_id} value={e.event_id}>{eventName(e)}</option>)}</select></label>
   </section>}
   {!layers.history&&<p className="muted">Past floods hidden.</p>}
   {district&&!district.navigation_bounds&&<p className="notice">Map bounds are unavailable for {district.name}, so the map keeps its current view; the information here is still filtered to {district.name}.</p>}
   {layers.shelters&&shownShelters&&<p>{shownShelters.mode==='demonstration'?'DEMONSTRATION ONLY — not actual destinations. ':''}{shownShelters.shelters.length?'Only currently verified Open entrances with spare capacity are shown.':'No currently verified open shelters are available in this directory.'} Directions are not verified flood-safe.</p>}
   {layers.shelters&&<p className="muted">Shelter availability: {shelters.freshness}, rechecked every minute.</p>}
   {layers.shelters&&shelters.data&&!shownShelters&&<p role="alert">Shelter availability could not be verified. No substitute destinations are shown.</p>}
  </>},
  {id:'sources',label:'Sources',content:<div className="intelligence-events">{layers.history&&(safeHistory?.events||[]).map(e=><p key={e.event_id}>GFD {e.event_id} ({eventName(e)}): {e.qualified_pixel_count} satellite cells.</p>)}{layers.history&&<p>Satellite flood maps exist for two Udupi floods (2005 and 2009). Each red cell is part of one of those floods, not a separate flood. Tap a cell on the map for its details.</p>}
   <p>{hazardNotice} Past floods and terrain are not relabelled as flood-prone zones.</p>
   <p>{directory.data?.total??'Unavailable'} districts. A checked place is matched to a district using IMD's district boundaries.</p>
<p className="muted intelligence-attribution">Satellite evidence: <a href="https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1">Global Flood Database V1</a> · Tellman et al. (2021) · <a href="https://creativecommons.org/licenses/by-nc/4.0/">CC BY-NC 4.0</a>, attribution and non-commercial use required. Modern Udupi outline: geoBoundaries v6 · CC BY 4.0, not a verified historical boundary.</p>
  </div>}]
 return <section className="intelligence-workspace" aria-labelledby="intelligence-title">
  <h2 id="intelligence-title" className="visually-hidden">Karnataka Flood Intelligence</h2>
  <div className="panel intelligence-toolbar">
   <p className="intelligence-howto"><strong>Tap any place on the map</strong> to check its official warning, rain risk and past floods.</p>
   <label htmlFor="intelligence-district">Go to district</label><select id="intelligence-district" value={districtId} disabled={!directory.data} onChange={e=>chooseDistrict(e.target.value)}><option value="">All of Karnataka</option>{directory.data?.items.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select>
   {districtId&&<button className="secondary" onClick={()=>chooseDistrict('')}>Show all Karnataka</button>}
  </div>
  {/* Laptop: map left, information tabs right. Phone: the map is one of the tabs. Nothing scrolls. */}
  <div className="intelligence-layout">{wide&&mapStage}<aside className="intelligence-sidebar" aria-label="Map evidence and limitations"><div aria-live="polite" aria-busy={loading} className="intelligence-coverage">
   {/* Loading and errors stay visible whichever tab is open. */}
   {loading&&<p role="status">Loading map information…</p>}
   {!!failures.length&&<p role="alert" className="notice error">{failures.map(s=>s.error).join(' · ')} No substitute geometry is shown. <button onClick={()=>{setRetry(n=>n+1);if(layers.shelters)shelters.refresh()}}>Retry map evidence</button></p>}
   <ScreenTabs mode="always" label="Map information" active={tab} onActive={setTab} tabs={tabs}/>
  </div></aside></div>
  <Popup open={!!details.data?.feature} onClose={()=>chooseFeature(null)} title="Flood evidence details">{details.data?.feature&&<FeatureDetails data={details.data}/>}</Popup>
 </section>
}
