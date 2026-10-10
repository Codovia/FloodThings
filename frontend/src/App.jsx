import React, { useEffect, useState } from 'react'
import useWeatherSession from './useWeatherSession.js'
import { AppHeader, PageLink, usePage } from './AppNavigation.jsx'
import WeatherPanel from './WeatherPanel.jsx'
import RainfallOutlook from './RainfallOutlook.jsx'
import PublicShelters from './PublicShelters.jsx'
import FloodIntelligenceMap from './FloodIntelligenceMap.jsx'
import WeatherLocationSelector, { DEFAULT_POINT } from './WeatherLocationSelector.jsx'
import AdminShelters from './AdminShelters.jsx'

const pageInfo={
 '/': ['KARNATAKA · ENVIRONMENT & RESPONSE','FloodPulse','Monitor real weather, explore historical flood information, access experimental AI rainfall outlooks and discover administrator-verified emergency shelters.'],
 '/weather': ['POINT WEATHER · EXPERIMENTAL AI','Weather & AI','Real forecasts for your selected point, with an experimental heavy-rainfall outlook.'],
 '/flood-map': ['GIS · HISTORICAL EVIDENCE','Flood Map','Explore reviewed satellite flood extents and bounded drainage research layers. These are historical records, not live flooding.'],
 '/shelters': ['MANUALLY VERIFIED DESTINATIONS','Emergency Shelters','Find administrator-verified open shelters and directions to their verified entrances.'],
 '/admin': ['AUTHORIZED PROJECT STAFF','Administration','Manage verified shelter assignments and explicitly approved Telegram notifications.'],
}
export default function App() {
 const {path,navigate,heading}=usePage()
 const [selectedPoint,setSelectedPoint]=useState(null)
 const [weatherEnabled,setWeatherEnabled]=useState(path!=='/admin')
 useEffect(()=>{if(path!=='/admin')setWeatherEnabled(true)},[path])
 const session=useWeatherSession(selectedPoint, weatherEnabled)
 const point=selectedPoint || DEFAULT_POINT
 const publicPage=path !== '/admin' && !!pageInfo[path]
 const weatherPage=path==='/' || path==='/weather'
 const sheltersPage=path==='/' || path==='/shelters'
 const info=pageInfo[path]
 function choosePoint(next){if(next.latitude===point.latitude && next.longitude===point.longitude) session.refresh(next);setSelectedPoint({...next})}
 return <>
  <AppHeader path={path} navigate={navigate} />
  <main id="page-content" className={'app-content page-'+(path==='/'?'home':path.slice(1))}>
   <section className={'page-intro '+(path==='/'?'home-hero':'')}>
    <div><p className="eyebrow">{info?.[0] || 'PAGE NOT FOUND'}</p><h1 ref={heading} tabIndex={-1}>{info?.[1] || 'This page is unavailable'}</h1>
    {path==='/' && <p className="hero-subtitle">AI Flood Intelligence & Emergency Response</p>}
    <p>{info?.[2] || 'Choose a page from the navigation to continue.'}</p>
    {path==='/' && <div className="hero-actions"><PageLink to="/weather" navigate={navigate} className="button-link">Explore weather & AI</PageLink><PageLink to="/shelters" navigate={navigate} className="button-link secondary">Find verified shelters</PageLink></div>}
    </div>{path==='/' && <div className="hero-art" aria-hidden="true"><svg viewBox="0 0 240 170"><circle cx="170" cy="48" r="27"/><path d="M40 88c-4-28 35-45 54-25 9-42 66-37 69 0 33-6 43 47 10 49H61c-22 0-30-13-21-24Z"/><path d="m80 125-8 16m44-16-8 16m44-16-8 16"/></svg><span>Real data. Clear context.</span></div>}
   </section>
   {path==='/' && <nav className="overview-links" aria-label="Explore FloodPulse"><PageLink to="/weather" navigate={navigate}><strong>Weather & AI</strong><span>Seven-day point forecasts and experimental rainfall inference</span></PageLink><PageLink to="/flood-map" navigate={navigate}><strong>Historical flood maps</strong><span>Reviewed satellite evidence and source-labelled GIS layers</span></PageLink><PageLink to="/shelters" navigate={navigate}><strong>Verified shelters</strong><span>Manually approved availability, capacity and entrance directions</span></PageLink></nav>}
   {/* Shared public session stays mounted across routes: one location and freshness lifecycle. */}
   <div className="dashboard-content">
   <div className="location-side">
   <div hidden={!publicPage || path==='/flood-map'} className="location-context">
    <WeatherLocationSelector point={point} onSelect={choosePoint} compact overview={path==='/'} />
    {!weatherPage && <p className="selection-summary">Selected point: <strong>{point.name}</strong> · {point.latitude}°, {point.longitude}°. Point selection does not imply a district-wide condition.</p>}
   </div>
   <div hidden={!sheltersPage} className="shelter-sections"><PublicShelters point={point} active={path==='/' || path==='/shelters'} overview={path==='/'} /></div>
   </div>
   <div hidden={!weatherPage} className="weather-sections">
    <WeatherPanel point={point} selectedPoint={selectedPoint} session={session} overview={path==='/'} />
    <RainfallOutlook point={point} weather={session.data} freshness={session.freshness} overview={path==='/'} />
   </div>
   {path==='/flood-map' && <FloodIntelligenceMap point={point} onPoint={choosePoint} navigate={navigate} />}
   </div>
   {path==='/admin' && <AdminShelters embedded onHome={()=>navigate('/')} />}
   {!info && <PageLink to="/" navigate={navigate} className="button-link">Return Home</PageLink>}
  </main>
  <footer className="app-footer"><div><strong>FloodPulse</strong><p>Environmental information and verified response resources.</p></div><div><p>Weather by <a href="https://open-meteo.com/">Open-Meteo</a> · <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>.</p><p>Validated flood prediction is unavailable. Experimental rainfall inference is not a flood probability or an emergency warning.</p></div></footer>
 </>
}
