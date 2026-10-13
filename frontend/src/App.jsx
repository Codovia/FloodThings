import React, { useEffect, useRef, useState } from 'react'
import useWeatherSession from './useWeatherSession.js'
import { AppHeader, PageLink, usePage } from './AppNavigation.jsx'
import WeatherPanel from './WeatherPanel.jsx'
import RainfallOutlook from './RainfallOutlook.jsx'
import PublicShelters from './PublicShelters.jsx'
import FloodIntelligenceMap from './FloodIntelligenceMap.jsx'
import WeatherLocationSelector, { DEFAULT_POINT, WeatherPointMap } from './WeatherLocationSelector.jsx'
import AdminShelters from './AdminShelters.jsx'
import HomeEmergencyDashboard from './HomeEmergencyDashboard.jsx'
import useHomeGeolocation, {MAX_WEATHER_ACCURACY_M} from './useHomeGeolocation.js'

const pageInfo={
 '/': ['KARNATAKA · ENVIRONMENT & RESPONSE','FloodPulse','Emergency overview · verified evidence and response resources.'],
 '/weather': ['POINT WEATHER · EXPERIMENTAL AI','Weather & AI','Real forecasts for your selected point, with an experimental heavy-rainfall outlook.'],
 '/flood-map': ['GIS · HISTORICAL EVIDENCE','Flood Map','Explore reviewed satellite flood extents and bounded drainage research layers. These are historical records, not live flooding.'],
 '/shelters': ['MANUALLY VERIFIED DESTINATIONS','Emergency Shelters','Find administrator-verified open shelters and directions to their verified entrances.'],
 '/admin': ['AUTHORIZED PROJECT STAFF','Administration','Manage verified shelter assignments and explicitly approved Telegram notifications.'],
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
 const homeGpsUnusable=selectedPoint?.kind==='gps'&&(!Number.isFinite(selectedPoint.accuracy_m)||selectedPoint.accuracy_m>MAX_WEATHER_ACCURACY_M)
 const homePoint=homeGpsUnusable?null:selectedPoint
 const session=useWeatherSession(selectedPoint,path==='/weather'||(path==='/'&&!!homePoint))
 const manualRevision=useRef(0)
 const homeLocation=useHomeGeolocation(path==='/',manualRevision,!!selectedPoint||!!districtId,next=>setSelectedPoint(next))
 const point=selectedPoint || DEFAULT_POINT
 const publicPage=path !== '/admin' && !!pageInfo[path]
 const selectorPage=publicPage&&path!=='/flood-map'
 const sheltersPage=path==='/shelters'
 const info=pageInfo[path]
 function chooseDistrict(next){manualRevision.current++;homeLocation.cancel();setDistrictId(next?.id||'');setDistrict(next||null);setEvidenceFeature(null)}
 function filterDistrict(id,record){manualRevision.current++;homeLocation.cancel();setDistrictId(id);setDistrict(record||null);setEvidenceFeature(null)}
 function choosePoint(next){manualRevision.current++;homeLocation.cancel();if(next.district_id)setDistrictId(next.district_id);if(next.latitude===point.latitude&&next.longitude===point.longitude&&weatherPage)session.refresh(next);setSelectedPoint({...next})}
 return <>
  <AppHeader path={path} navigate={navigate} />
  <main id="page-content" className={'app-content page-'+(path==='/'?'home':path.slice(1))}>
   <section className="page-intro"><div><p className="eyebrow">{info?.[0] || 'PAGE NOT FOUND'}</p><h1 ref={heading} tabIndex={-1}>{info?.[1] || 'This page is unavailable'}</h1><p>{info?.[2] || 'Choose a page from the navigation to continue.'}</p></div></section>
   {path==='/'&&<HomeEmergencyDashboard point={homePoint} district={district} districtId={districtId} session={session} location={homeGpsUnusable?{...homeLocation,status:'coarse',gps:null,message:'Approximate location — select your town. This GPS accuracy cannot support local Home weather or river focus.'}:homeLocation} choosePoint={choosePoint} chooseDistrict={chooseDistrict} navigate={navigate}/> }
   {publicPage&&path!=='/'&&<div className="wireframe-workspace">
    <div hidden={!selectorPage} className="workspace-information" aria-label="Selected district and services">
     <WeatherLocationSelector point={point} onSelect={choosePoint} compact externalMap active={selectorPage} selectedDistrictId={districtId} onDistrict={chooseDistrict}/>
     {districtId&&<p className="district-context" role="status">District filter: <strong>{district?.name||districtId.replace(/^nic:|\.nic\.in$/g,'')}</strong>. Weather remains point-specific. {!district?.navigation_bounds&&'Public district navigation bounds are unavailable; no bounds or representative point are invented.'}</p>}
     <div hidden={!weatherPage} className="weather-sections">
      <WeatherPanel point={point} selectedPoint={selectedPoint} session={session} overview={false}/>
      <RainfallOutlook point={point} weather={session.data} freshness={session.freshness} overview={false} active={weatherPage}/>
     </div>
     <div hidden={!sheltersPage} className="shelter-sections"><PublicShelters point={point} active={sheltersPage} overview={false} mapTarget={path==='/shelters'?shelterMapTarget:null} districtId={districtId} navigationBounds={district?.navigation_bounds}/></div>
    </div>
    {path==='/weather'&&<section className="panel workspace-map" aria-labelledby="context-map-title"><div className="panel-heading"><div><p className="eyebrow">GEOGRAPHIC CONTEXT</p><h2 id="context-map-title">{district?.name||'Selected-point context'}</h2></div>{path==='/weather'&&<button onClick={()=>setContextVisible(v=>!v)} aria-expanded={contextVisible}>{contextVisible?'Hide geographic context':'Show geographic context'}</button>}</div>{contextVisible&&<WeatherPointMap point={point} onSelect={choosePoint} navigationBounds={district?.navigation_bounds} historical={null}/>}<p className="map-legend">Selected point: {point.name}.  District filtering and point weather remain separate.</p></section>}
    {path==='/shelters'&&<section className="panel workspace-map shelter-map-stage" ref={setShelterMapTarget} aria-label="Shelter geographic context"/>}
    {path==='/flood-map'&&<FloodIntelligenceMap point={point} onPoint={choosePoint} navigate={navigate} selectedDistrictId={districtId} onDistrictChange={filterDistrict} selectedFeatureId={evidenceFeature} onFeatureChange={setEvidenceFeature}/>}
   </div>}
   {path==='/admin'&&<AdminShelters embedded onHome={()=>navigate('/')}/>}
   {!info&&<PageLink to="/" navigate={navigate} className="button-link">Return Home</PageLink>}
  </main>
  <footer className="app-footer"><div><strong>FloodPulse</strong><p>Environmental information and verified response resources.</p></div><div><p>Weather by <a href="https://open-meteo.com/">Open-Meteo</a> · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>.</p><p>Validated flood prediction is unavailable. Experimental rainfall inference is not a flood probability or an emergency warning.</p></div></footer>
 </>
}
