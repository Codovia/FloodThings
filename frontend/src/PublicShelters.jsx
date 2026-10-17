import OfficialHelp from './OfficialHelp.jsx'
import React,{useEffect,useRef,useState} from 'react'
import {createPortal} from 'react-dom'
import ShelterMap from './ShelterMap.jsx'
import useShelterDirectory from './useShelterDirectory.js'
export { validShelterDirectory } from './useShelterDirectory.js'
import './Shelters.css'
import './RiskPanel.css'
const ago=value=>{const m=Math.max(0,Math.round((Date.now()-Date.parse(value))/60000));return m<1?'just now':m<60?`${m} min ago`:`${Math.round(m/60)} h ago`}
const clock=value=>new Intl.DateTimeFormat('en-IN',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Kolkata'}).format(new Date(value))+' IST'
export function usableNavigationOrigin(point, now=Date.now()) {
  if (!point || point.kind === 'network' || !Number.isFinite(point.latitude) || Math.abs(point.latitude)>90 || !Number.isFinite(point.longitude) || Math.abs(point.longitude)>180) return null
  if (point.kind === 'gps' && (!Number.isFinite(point.accuracy_m) || point.accuracy_m>100 || point.accuracy_m<0 || !Number.isFinite(point.gps_timestamp) || point.gps_timestamp>now || now-point.gps_timestamp>300000)) return null
  return point
}
export default function PublicShelters({point=null,active,overview=false,mapTarget=null,districtId='',navigationBounds=null,onLocate=null}) {
  const [open,setOpen]=useState(false),[navigation,setNavigation]=useState(null),[navigationNotice,setNavigationNotice]=useState(null)
  // Routing availability is learned on the first explicit request, adding no background calls.
  const [routing,setRouting]=useState(true),[route,setRoute]=useState(null),[routeBusy,setRouteBusy]=useState(false)
  const [selected,setSelected]=useState(null),[locating,setLocating]=useState(false),[locateError,setLocateError]=useState(null)
  const selectedPoint=point
  point=usableNavigationOrigin(point)
  const key=point?`${point.latitude}:${point.longitude}`:'no-origin'
  const enabled=active===undefined?open:active
  const selectedKey=useRef(key);selectedKey.current=key
  useEffect(()=>{selectedKey.current=enabled?key:null;setNavigation(null);setNavigationNotice(null);setRoute(null);return()=>{selectedKey.current=null}},[key,enabled])
  useEffect(()=>{if(!navigation)return;const timer=setTimeout(()=>setNavigation(null),5000);return()=>clearTimeout(timer)},[navigation])
  const current=useShelterDirectory(point,enabled),source=current.data
  const data=source?{...source,shelters:source.shelters.filter(s=>!districtId||s.district_id===districtId)}:null
  // Nearest first; shelters without a distance keep their directory order at the end.
  const ordered=data?data.shelters.map((s,i)=>[s,i]).sort(([a,i],[b,j])=>(a.straight_line_km??Infinity)-(b.straight_line_km??Infinity)||i-j).map(([s])=>s):[]
  const focus=ordered.find(s=>s.id===selected)||null
  function select(id,scroll=false){setSelected(id);if(scroll)document.getElementById('shelter-'+id)?.scrollIntoView?.({block:'nearest',behavior:'smooth'})}
  const pins=ordered.map((s,i)=>({...s,label:String(i+1),name:`${i+1}. ${s.name} · ${s.available_capacity} places free`,tone:s.available_capacity<Math.max(10,s.capacity*0.15)?'limited':'ok'}))
  const map=<><h2>Verified shelter entrances</h2><ShelterMap points={pins} route={route?.geometry} origin={point} focus={focus} onInspect={p=>select(p.id,true)} navigationBounds={navigationBounds} label="Verified open shelter entrances"/><p className="muted">Numbered pins match the list. Only freshly revalidated Open destinations with spare capacity are marked; the small dark dot is your starting point, not a shelter. No markers are invented for missing records.</p></>
  function locate(){
    if(!onLocate)return
    if(!navigator.geolocation||!window.isSecureContext){setLocateError('Location needs a supported browser and a secure connection. Use "Change location" instead.');return}
    setLocating(true);setLocateError(null)
    navigator.geolocation.getCurrentPosition(r=>{setLocating(false);onLocate({name:'Your GPS location',latitude:r.coords.latitude,longitude:r.coords.longitude,accuracy_m:r.coords.accuracy,gps_timestamp:r.timestamp,kind:'gps'})},
      ()=>{setLocating(false);setLocateError('Location unavailable or permission denied. Use "Change location" to choose your place.')},{enableHighAccuracy:true,timeout:10000,maximumAge:0})
  }
  const directions=s=>'https://www.google.com/maps/dir/?'+new URLSearchParams({api:'1',destination:`${s.latitude},${s.longitude}`,...(point?{origin:`${point.latitude},${point.longitude}`}:{})})
  async function inAppRoute(shelter,profile='foot-walking'){
    if(!usableNavigationOrigin(selectedPoint)){setNavigationNotice('Select an adequate starting location before requesting a route.');return}
    setRouteBusy(true);setRoute(null);setNavigationNotice('Planning a route that avoids approved flood reports…')
    const requestedKey=key
    try{
      const response=await fetch('/api/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({shelter_id:shelter.id,profile,origin:{latitude:point.latitude,longitude:point.longitude,accuracy_m:point.kind==='gps'?point.accuracy_m:(point.uncertainty_m||250)}})})
      const body=await response.json()
      if(selectedKey.current!==requestedKey)return
      if(body.status==='not_configured')setRouting(false)
      if(!response.ok||body.status!=='available'){setNavigationNotice((typeof body.detail==='string'?body.detail:body.message)||'Route unavailable. Use external directions.');return}
      setRoute({...body,shelterId:shelter.id});setNavigationNotice(null)
    }catch{setNavigationNotice('Routing request failed. Use external directions.')}finally{setRouteBusy(false)}
  }
  async function checkDestination(event,shelter) {
    event.preventDefault();setNavigation(null)
    if(!usableNavigationOrigin(selectedPoint)){setNavigationNotice('Select an adequate starting location before requesting directions. Network estimates and stale or imprecise GPS fixes cannot be used.');return}
    setNavigationNotice('Rechecking destination availability…')
    const requestedKey=key,latest=await current.refresh()
    if(selectedKey.current!==requestedKey||!usableNavigationOrigin(selectedPoint))return
    const found=latest?.shelters.find(s=>s.id===shelter.id&&s.latitude===shelter.latitude&&s.longitude===shelter.longitude)
    if(!found){setNavigationNotice('This destination could not be revalidated. No directions were opened. Check the current directory.');return}
    setNavigation({id:found.id,key:requestedKey,url:directions(found),at:Date.now()})
    setNavigationNotice('Availability rechecked. Select directions again within five seconds to open external navigation. Reported conditions and road access may still change.')
  }
  return <section className={overview?"panel shelters-overview":"panel shelters-panel"} aria-labelledby="public-shelters-title">
    <div className="panel-heading"><div><p className="eyebrow">VERIFIED BY ADMINISTRATORS</p><h2 id="public-shelters-title">Open shelters near you</h2></div><button className="secondary" onClick={()=>enabled?current.refresh():setOpen(true)} disabled={current.loading}>{current.loading?'Loading shelters…':enabled?'Refresh shelters':'Find open shelters'}</button></div>
    <div className="shelter-origin">{point?<p>{`Distances from ${point.name}${point.kind==='gps'?` (GPS ±${Math.round(point.accuracy_m)} m)`:''}.`}</p>:<p>Set your location to list the nearest shelters first.</p>}
      {onLocate&&<button type="button" onClick={locate} disabled={locating}>{locating?'Finding you…':point?'Update my location':'Use my location'}</button>}</div>
    {locateError&&<p role="status" className="notice">{locateError}</p>}
    {selectedPoint && !point && <p role="status" className="notice">Your location is too uncertain or its GPS fix is stale for directions. Use my location again outdoors, or choose your place with "Change location".</p>}
    <div aria-live="polite" aria-busy={current.loading}>
      {current.loading&&<p role="status">Checking shelter directory…</p>}
      {current.error&&<p role="alert">{current.error}. No substitute destinations are shown.</p>}
      {navigationNotice&&<p role="status" className="shelter-navigation-notice">{navigationNotice}</p>}
      {data?.mode==='demonstration'&&<p role="alert" className="notice error"><strong>DEMONSTRATION ONLY — isolated test assignments, not actual emergency shelters. Do not travel to these points.</strong></p>}
      {data&&!data.shelters.length&&<p role="status" className="shelter-empty">No currently verified open shelters are available in this directory.</p>}
      {data?.shelters.length>0&&<>
        <p className="shelter-summary"><strong>{data.shelters.length} open {data.shelters.length===1?'shelter':'shelters'} with free space</strong>{data.retrieved_at&&<> · checked {clock(data.retrieved_at)}</>}</p>
        {!mapTarget&&!overview&&<ShelterMap points={pins} origin={point} focus={focus} onInspect={p=>select(p.id,true)} label="Verified open shelter entrances" />}
        <ol aria-label="Available shelter destinations" className="shelter-list">{ordered.map((s,i)=>{
          const used=Math.min(100,Math.round(100*(s.capacity-s.available_capacity)/Math.max(1,s.capacity)))
          return <li key={s.id} id={'shelter-'+s.id} className={'shelter-card'+(selected===s.id?' selected':'')}>
          <div className="shelter-card-head"><span className="shelter-num" aria-hidden="true">{i+1}</span><h3>{s.name}</h3>{i===0&&point&&s.straight_line_km!==null&&<span className="shelter-nearest">Nearest</span>}</div>
          <p className="shelter-distance">{s.straight_line_km===null?'Straight-line distance unavailable':`${s.straight_line_km} km approximate straight-line distance`}</p>
          <p className="shelter-address">{s.address} · {s.district_name}</p>
          <div className="shelter-capacity" data-tone={pins[i].tone}><p><strong>{s.available_capacity} available</strong> of {s.capacity} places · {s.occupancy} reported occupants</p><div className="capacity-bar" role="img" aria-label={`${used}% of places taken`}><span style={{width:used+'%'}}/></div></div>
          <ul className="shelter-facilities" aria-label="Facilities"><li data-value={s.water}>Water: {s.water}</li><li data-value={s.toilets}>Toilets: {s.toilets}</li><li>Accessibility: {s.accessibility||'Not reported'}</li></ul>
          {s.restrictions&&<p className="shelter-restrictions">Restrictions: {s.restrictions}</p>}{s.contact&&<p>Approved contact: {s.contact}</p>}
          <p className="muted">Verified {ago(s.verified_at)} · verification expires {clock(s.verification_expires_at)}</p>
          <div className="shelter-actions">
          {navigation?.id===s.id&&navigation.key===key&&navigation.url===directions(s)&&Date.now()-navigation.at<5000
            ?<a className="button-link" href={navigation.url} onClick={event=>{if(Date.now()-navigation.at>=5000||!usableNavigationOrigin(selectedPoint)){event.preventDefault();setNavigation(null)}else setNavigation(null)}} target="_blank" rel="noopener noreferrer">{data.mode==='demonstration'?'Inspect demonstration directions (not for travel)':'Open external directions to verified entrance'}</a>
            :<button type="button" onClick={event=>checkDestination(event,s)} disabled={current.loading}>Get directions</button>}
          {routing&&<button type="button" className="secondary" onClick={()=>inAppRoute(s)} disabled={routeBusy||current.loading}>{routeBusy?'Planning route…':'Show walking route on map'}</button>}
          <button type="button" className="secondary" onClick={()=>select(s.id)} aria-pressed={selected===s.id}>Show on map</button>
          </div>
          {route?.shelterId===s.id&&<div className="route-summary" role="status"><p><strong>{(route.distance_m/1000).toFixed(1)} km · about {Math.round(route.duration_s/60)} min walking</strong></p><p className="notice">{route.label}</p>
            <details><summary>Turn-by-turn directions</summary><ol className="route-steps">{route.steps.map((step,i)=><li key={i}>{step.instruction} ({step.distance_m} m)</li>)}</ol></details><p className="muted">{route.attribution}</p></div>}
        </li>})}</ol>
        <p className="shelter-safety">Reported capacity is not a reservation. External directions are not verified flood-safe; confirm availability and road access before travel.</p>
      </>}
    </div>
    <OfficialHelp prominent={!!data&&!data.shelters.length}/>
    {mapTarget&&enabled&&createPortal(map,mapTarget)}
    <details className="shelter-usage"><summary>Availability and safe navigation limitations</summary><p>Only manually authorized, entrance-verified, usable Open assignments with reported available capacity are listed{data?.shelters.length?` (${data.shelters.length} of ${data.total} assignments shown; verification expires after ${data.verification_valid_hours} hours)`:''}. This prototype is not affiliated with a disaster-management authority.</p>
    {!point&&<p>No starting location selected. Choose a starting point on the map or an explicitly selected locality before requesting directions.</p>}
    <p className="notice">Approximate straight-line distance is not road distance. Flooding and road closures may make external routes unsafe. Confirm access and availability with local authorities before travel.</p>
    <p>"Get directions" rechecks this shelter's availability first; the directions link then stays active for five seconds.</p>
    {enabled&&<p>Availability: {current.freshness}. Active directories are checked at least every minute; returning to this tab rechecks availability. A network failure removes destinations.</p>}
    </details>
  </section>
}
