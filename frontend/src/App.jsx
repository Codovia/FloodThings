import React, { useEffect, useState } from 'react'
import useWeatherSession from './useWeatherSession.js'
import { AppHeader, PageLink, usePage } from './AppNavigation.jsx'
import WeatherPanel from './WeatherPanel.jsx'
import RainfallOutlook from './RainfallOutlook.jsx'
import PublicShelters from './PublicShelters.jsx'
import FloodIntelligenceMap from './FloodIntelligenceMap.jsx'
import WeatherLocationSelector, { DEFAULT_POINT, WeatherPointMap } from './WeatherLocationSelector.jsx'
import AdminShelters from './AdminShelters.jsx'

const pageInfo={
 '/': ['KARNATAKA · ENVIRONMENT & RESPONSE','FloodPulse','Emergency overview · verified evidence and response resources.'],
 '/weather': ['POINT WEATHER · EXPERIMENTAL AI','Weather & AI','Real forecasts for your selected point, with an experimental heavy-rainfall outlook.'],
 '/flood-map': ['GIS · HISTORICAL EVIDENCE','Flood Map','Explore reviewed satellite flood extents and bounded drainage research layers. These are historical records, not live flooding.'],
 '/shelters': ['MANUALLY VERIFIED DESTINATIONS','Emergency Shelters','Find administrator-verified open shelters and directions to their verified entrances.'],
 '/admin': ['AUTHORIZED PROJECT STAFF','Administration','Manage verified shelter assignments and explicitly approved Telegram notifications.'],
}

function useOverviewEvidence(active,districtId) {
 const [view,setView]=useState({key:null,data:null,error:null})
 const key=districtId||'statewide'
 useEffect(()=>{
  if(!active)return
  const controller=new AbortController();let stopped=false
  setView({key,data:null,error:null})
  const timer=setTimeout(()=>controller.abort(),15000)
  fetch('/api/flood-map/historical'+(districtId?'?district_id='+encodeURIComponent(districtId):''),{signal:controller.signal}).then(async response=>{
   const data=await response.json()
   if(!response.ok||data.status!=='available'||data.geojson?.type!=='FeatureCollection'||!Array.isArray(data.geojson.features)||!Number.isInteger(data.total))throw Error('Historical evidence unavailable')
   if(!stopped&&!controller.signal.aborted)setView({key,data,error:null})
  }).catch(()=>{if(!stopped)setView({key,data:null,error:'Historical evidence could not be checked. No substitute geometry is shown.'})}).finally(()=>clearTimeout(timer))
  return()=>{stopped=true;clearTimeout(timer);controller.abort()}
 },[active,key])
 return view.key===key?view:{data:null,error:null}
}

export default function App() {
 const {path,navigate,heading}=usePage()
 // Three separate identities: district evidence filter, weather point, map cell.
 // A district without a verified point never changes weather coordinates.
 const [selectedPoint,setSelectedPoint]=useState(null)
 const [districtId,setDistrictId]=useState(''),[district,setDistrict]=useState(null)
 const [evidenceFeature,setEvidenceFeature]=useState(null)
 const [shelterMapTarget,setShelterMapTarget]=useState(null)
 const [contextVisible,setContextVisible]=useState(true)
 const weatherPage=path==='/' || path==='/weather'
 const session=useWeatherSession(selectedPoint,weatherPage)
 const point=selectedPoint || DEFAULT_POINT
 const publicPage=path !== '/admin' && !!pageInfo[path]
 const selectorPage=publicPage&&path!=='/flood-map'
 const sheltersPage=path==='/' || path==='/shelters'
 const overview=useOverviewEvidence(path==='/',districtId)
 const info=pageInfo[path]
 function chooseDistrict(next){setDistrictId(next?.id||'');setDistrict(next||null);setEvidenceFeature(null)}
 function filterDistrict(id,record){setDistrictId(id);setDistrict(record||null);setEvidenceFeature(null)}
 function choosePoint(next){if(next.district_id)setDistrictId(next.district_id);if(next.latitude===point.latitude&&next.longitude===point.longitude&&weatherPage)session.refresh(next);setSelectedPoint({...next})}
 return <>
  <AppHeader path={path} navigate={navigate} />
  <main id="page-content" className={'app-content page-'+(path==='/'?'home':path.slice(1))}>
   <section className="page-intro"><div><p className="eyebrow">{info?.[0] || 'PAGE NOT FOUND'}</p><h1 ref={heading} tabIndex={-1}>{info?.[1] || 'This page is unavailable'}</h1><p>{info?.[2] || 'Choose a page from the navigation to continue.'}</p></div></section>
   {publicPage&&<div className="wireframe-workspace">
    <div hidden={!selectorPage} className="workspace-information" aria-label="Selected district and services">
     <WeatherLocationSelector point={point} onSelect={choosePoint} compact externalMap active={selectorPage} selectedDistrictId={districtId} onDistrict={chooseDistrict}/>
     {districtId&&<p className="district-context" role="status">District filter: <strong>{district?.name||districtId.replace(/^nic:|\.nic\.in$/g,'')}</strong>. Weather remains point-specific. {!district?.navigation_bounds&&'Public district navigation bounds are unavailable; no bounds or representative point are invented.'}</p>}
     {path==='/'&&<section className="panel emergency-overview" aria-labelledby="emergency-overview-title"><p className="eyebrow">DISTRICT & EMERGENCY EVIDENCE</p><h2 id="emergency-overview-title">Emergency overview</h2><div className="overview-status-grid"><article><h3>Official warning feed</h3><p>Not connected</p><small>This does not establish that no emergency exists. Follow official local advice.</small></article><article><h3>Historical flood evidence</h3><p>{overview.data?`${overview.data.total} reviewed historical cells`:'Coverage unavailable'}</p><small>Historical observations, not active flooding or independent event counts.</small></article><article><h3>Published hazard zones</h3><p>No verified polygons</p><small>No danger levels or district risk percentages are assigned.</small></article></div>{overview.error&&<p role="status">{overview.error}</p>}<PageLink to="/flood-map" navigate={navigate}>Inspect sources and historical evidence</PageLink></section>}
     <div hidden={!weatherPage} className="weather-sections">
      <WeatherPanel point={point} selectedPoint={selectedPoint} session={session} overview={path==='/'}/>
      <RainfallOutlook point={point} weather={session.data} freshness={session.freshness} overview={path==='/'} active={weatherPage}/>
     </div>
     <div hidden={!sheltersPage} className="shelter-sections"><PublicShelters point={point} active={sheltersPage} overview={path==='/'} mapTarget={path==='/shelters'?shelterMapTarget:null} districtId={districtId} navigationBounds={district?.navigation_bounds}/></div>
    </div>
    {(path==='/'||path==='/weather')&&<section className="panel workspace-map" aria-labelledby="context-map-title"><div className="panel-heading"><div><p className="eyebrow">GEOGRAPHIC CONTEXT</p><h2 id="context-map-title">{path==='/'?'Karnataka overview':district?.name||'Selected-point context'}</h2></div>{path==='/weather'&&<button onClick={()=>setContextVisible(v=>!v)} aria-expanded={contextVisible}>{contextVisible?'Hide geographic context':'Show geographic context'}</button>}</div>{(path==='/'||contextVisible)&&<WeatherPointMap point={point} onSelect={choosePoint} navigationBounds={district?.navigation_bounds} historical={path==='/'?overview.data:null}/>}<p className="map-legend">Selected point: {point.name}. {path==='/'&&'Rust polygons show historical observed floodwater, not current warnings or potential hazard.'} District filtering and point weather remain separate.</p></section>}
    {path==='/shelters'&&<section className="panel workspace-map shelter-map-stage" ref={setShelterMapTarget} aria-label="Shelter geographic context"/>}
    {path==='/flood-map'&&<FloodIntelligenceMap point={point} onPoint={choosePoint} navigate={navigate} selectedDistrictId={districtId} onDistrictChange={filterDistrict} selectedFeatureId={evidenceFeature} onFeatureChange={setEvidenceFeature}/>}
   </div>}
   {path==='/admin'&&<AdminShelters embedded onHome={()=>navigate('/')}/>}
   {!info&&<PageLink to="/" navigate={navigate} className="button-link">Return Home</PageLink>}
  </main>
  <footer className="app-footer"><div><strong>FloodPulse</strong><p>Environmental information and verified response resources.</p></div><div><p>Weather by <a href="https://open-meteo.com/">Open-Meteo</a> · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>.</p><p>Validated flood prediction is unavailable. Experimental rainfall inference is not a flood probability or an emergency warning.</p></div></footer>
 </>
}
