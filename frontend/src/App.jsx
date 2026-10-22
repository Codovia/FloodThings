import React, { useEffect, useRef, useState } from 'react'
import useWeatherSession from './useWeatherSession.js'
import { AppHeader, PageLink, usePage } from './AppNavigation.jsx'
import WeatherPanel from './WeatherPanel.jsx'
import PublicShelters from './PublicShelters.jsx'
import FloodIntelligenceMap from './FloodIntelligenceMap.jsx'
import WeatherLocationSelector, { DEFAULT_POINT, WeatherPointMap } from './WeatherLocationSelector.jsx'
import AdminShelters from './AdminShelters.jsx'
import CitizenReport from './CitizenReport.jsx'
import AlertSubscription from './AlertSubscription.jsx'
import HomeEmergencyDashboard from './HomeEmergencyDashboard.jsx'
import HowItWorks from './HowItWorks.jsx'
import { useWide } from './ScreenTabs.jsx'
import useFitGuard from './useFitGuard.js'
import useHomeGeolocation, {MAX_WEATHER_ACCURACY_M} from './useHomeGeolocation.js'

const pageInfo={
 '/': ['KARNATAKA · ENVIRONMENT & RESPONSE','FloodPulse','Emergency overview · verified evidence and response resources.'],
 '/weather': ['POINT WEATHER','Weather details','Seven-day forecast, rainfall chart and source details for your selected point.'],
 '/flood-map': ['OFFICIAL WARNINGS · LIVE RISK · HISTORY','Flood Map','Official IMD district warnings, an experimental statewide rain-risk grid, and historical satellite flood extents.'],
 '/shelters': ['MANUALLY VERIFIED DESTINATIONS','Emergency Shelters','Find administrator-verified open shelters and directions to their verified entrances.'],
 '/alerts': ['ADMIN-REVIEWED NOTICES','Citizen alerts','Telegram opt-in and opt-out for project notices.'],
 '/report': ['CITIZEN EVIDENCE · PRIVATE REVIEW','Report an incident','Tell us what you see. Your location is found automatically; photos are optional.'],
 '/how-it-works': ['PREDICTION · EVIDENCE','How FloodPulse predicts','How the flood and drainage risk is calculated, and why it is a rule-based index rather than a trained flood model.'],
 '/admin': ['AUTHORIZED PROJECT STAFF','Administration','Review citizen evidence, manage shelters and control project notifications.'],
}

export default function App() {
 const {path,navigate,heading}=usePage()
 const wide=useWide()  // phones show page maps inside tabs (one-screen rule)
 useFitGuard(path)
 const [deploymentMode,setDeploymentMode]=useState(null)
 useEffect(()=>{const controller=new AbortController();void(async()=>{try{const response=await fetch('/api/environment',{signal:controller.signal});const body=await response.json();if(response.ok&&['live','demonstration'].includes(body.mode)&&!controller.signal.aborted)setDeploymentMode(body.mode)}catch{/* Mode failure never invents operational readiness. */}})();return()=>controller.abort()},[])
 // Three separate identities: district evidence filter, weather point, map cell.
 // A district without a verified point never changes weather coordinates.
 const [selectedPoint,setSelectedPoint]=useState(null)
 const [districtId,setDistrictId]=useState(''),[district,setDistrict]=useState(null)
 const [evidenceFeature,setEvidenceFeature]=useState(null)
 const [shelterMapTarget,setShelterMapTarget]=useState(null)
 const [nearestRequest,setNearestRequest]=useState(0)
 // A spot handed from Home's map to Report ("Report flooding here"); used once.
 const [reportSpot,setReportSpot]=useState(null)
 const [contextVisible,setContextVisible]=useState(true)
 const weatherPage=path==='/' || path==='/weather'
 const homeGpsUnusable=selectedPoint?.kind==='gps'&&(!Number.isFinite(selectedPoint.accuracy_m)||selectedPoint.accuracy_m>MAX_WEATHER_ACCURACY_M)
 const homePoint=homeGpsUnusable?null:selectedPoint
 const session=useWeatherSession(selectedPoint,path==='/weather'||(path==='/'&&!!homePoint))
 const manualRevision=useRef(0)
 const homeLocation=useHomeGeolocation(path==='/',manualRevision,!!selectedPoint||!!districtId,next=>setSelectedPoint(next))
 const point=selectedPoint || DEFAULT_POINT
 const publicPage=path !== '/admin' && !!pageInfo[path]
 const selectorPage=publicPage&&path!=='/flood-map'&&path!=='/report'&&path!=='/alerts'&&path!=='/how-it-works'
 const sheltersPage=path==='/shelters'
 const info=pageInfo[path]
 function chooseDistrict(next){manualRevision.current++;homeLocation.cancel();setDistrictId(next?.id||'');setDistrict(next||null);setEvidenceFeature(null)}
 function filterDistrict(id,record){manualRevision.current++;homeLocation.cancel();setDistrictId(id);setDistrict(record||null);setEvidenceFeature(null)}
 function choosePoint(next){manualRevision.current++;homeLocation.cancel();if(next.district_id)setDistrictId(next.district_id);if(next.latitude===point.latitude&&next.longitude===point.longitude&&weatherPage)session.refresh(next);setSelectedPoint({...next})}
 return <>
  <AppHeader path={path} navigate={navigate} mode={deploymentMode} />
  <main id="page-content" className={'app-content page-'+(path==='/'?'home':path.slice(1))}>
   <section className={'page-intro'+(['/','/flood-map','/admin'].includes(path)?' visually-hidden':'')}><div><p className="eyebrow">{info?.[0] || 'PAGE NOT FOUND'}</p><h1 ref={heading} tabIndex={-1}>{info?.[1] || 'This page is unavailable'}</h1><p>{info?.[2] || 'Choose a page from the navigation to continue.'}</p></div></section>
   {path==='/'&&<HomeEmergencyDashboard point={homePoint} district={district} districtId={districtId} session={session} location={homeGpsUnusable?{...homeLocation,status:'coarse',gps:null,message:'Approximate location — select your town. This GPS accuracy cannot support local Home weather or river focus.'}:homeLocation} choosePoint={choosePoint} chooseDistrict={chooseDistrict} navigate={navigate} onNearestShelter={()=>{setNearestRequest(n=>n+1);navigate('/shelters')}} onReportHere={spot=>{setReportSpot({name:spot.name,latitude:spot.latitude,longitude:spot.longitude});navigate('/report')}}/> }
   {publicPage&&path!=='/'&&path!=='/report'&&path!=='/alerts'&&<div className="wireframe-workspace">
    <div hidden={!selectorPage} className="workspace-information" aria-label="Selected district and services">
     <WeatherLocationSelector point={point} chosen={!!selectedPoint||weatherPage} onSelect={choosePoint} compact externalMap active={selectorPage} selectedDistrictId={districtId} onDistrict={chooseDistrict}/>
     {districtId&&<p className="district-context" role="status">District filter: <strong>{district?.name||districtId.replace(/^nic:|\.nic\.in$/g,'')}</strong>.</p>}
     <div hidden={!weatherPage} className="weather-sections">
      <WeatherPanel point={point} selectedPoint={selectedPoint} session={session} overview={false} active={weatherPage}/>
     </div>
     <div hidden={!sheltersPage} className="shelter-sections"><PublicShelters point={selectedPoint} onLocate={choosePoint} nearestRequest={nearestRequest} active={sheltersPage} overview={false} mapTarget={path==='/shelters'&&wide?shelterMapTarget:null} districtId={districtId} navigationBounds={district?.navigation_bounds}/></div>
    </div>
    {path==='/weather'&&<section className="panel workspace-map" aria-labelledby="context-map-title"><div className="panel-heading"><div><p className="eyebrow">GEOGRAPHIC CONTEXT</p><h2 id="context-map-title">{district?.name||'Selected-point context'}</h2></div>{path==='/weather'&&<button onClick={()=>setContextVisible(v=>!v)} aria-expanded={contextVisible}>{contextVisible?'Hide geographic context':'Show geographic context'}</button>}</div>{contextVisible&&<WeatherPointMap point={point} onSelect={choosePoint} navigationBounds={district?.navigation_bounds} historical={null}/>}<p className="map-legend weather-map-caption">Selected point: {point.name}.</p></section>}
    {path==='/shelters'&&wide&&<section className="panel workspace-map shelter-map-stage" ref={setShelterMapTarget} aria-label="Shelter geographic context"/>}
    {path==='/flood-map'&&<FloodIntelligenceMap point={selectedPoint} onPoint={choosePoint} navigate={navigate} selectedDistrictId={districtId} onDistrictChange={filterDistrict} selectedFeatureId={evidenceFeature} onFeatureChange={setEvidenceFeature}/>}
   </div>}
   {path==='/alerts'&&<AlertSubscription navigate={navigate}/>}
   {path==='/how-it-works'&&<HowItWorks navigate={navigate}/>}
   {path==='/report'&&<CitizenReport navigate={navigate} suggestedSpot={reportSpot} onSpotUsed={()=>setReportSpot(null)}/>}
   {path==='/admin'&&<AdminShelters embedded onHome={()=>navigate('/')}/>}
   {!info&&<nav className="not-found" aria-label="Suggested pages"><PageLink to="/" navigate={navigate} className="button-link">Return Home</PageLink><PageLink to="/flood-map" navigate={navigate}>Flood Map</PageLink><PageLink to="/shelters" navigate={navigate}>Shelters</PageLink><PageLink to="/report" navigate={navigate}>Report an incident</PageLink></nav>}
  </main>
  <footer className="app-footer"><p><strong>FloodPulse</strong> · <span className="footer-long">Weather, river and elevation data: </span><span className="footer-short">Data: </span><a href="https://open-meteo.com/">Open-Meteo</a> (<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>) · <span className="footer-long">Risk levels are experimental, not an official warning. Follow IMD, KSNDMC and district advice.</span><span className="footer-short">Experimental, not an official warning.</span></p></footer>
 </>
}
