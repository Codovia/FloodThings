import OfficialHelp from './OfficialHelp.jsx'
import React,{useEffect,useRef,useState} from 'react'
import {createPortal} from 'react-dom'
import ShelterMap from './ShelterMap.jsx'
import ShelterNavigation from './ShelterNavigation.jsx'
import useShelterDirectory from './useShelterDirectory.js'
export { validShelterDirectory } from './useShelterDirectory.js'
import './Shelters.css'
import './RiskPanel.css'
import ScreenTabs, { useWide, usePaged, Pager } from './ScreenTabs.jsx'
import Popup from './Popup.jsx'
import { preciseLocation } from './preciseLocation.js'
import RouteSteps from './RouteSteps.jsx'
const PER_PAGE=1  // one shelter card per screen (one-screen rule)
const ago=value=>{const m=Math.max(0,Math.round((Date.now()-Date.parse(value))/60000));return m<1?'just now':m<60?`${m} min ago`:`${Math.round(m/60)} h ago`}
const clock=value=>new Intl.DateTimeFormat('en-IN',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Kolkata'}).format(new Date(value))+' IST'
// A device fix within PRECISE is a precise start; up to MAX (the route service's own limit) it is used as an
// approximate start and labelled so. Coarser fixes, network estimates and fixes older than 5 minutes are not used.
export const PRECISE_START_ACCURACY_M = 100
export const MAX_START_ACCURACY_M = 1000
export const approximateStart = point => point?.kind === 'gps' && point.accuracy_m > PRECISE_START_ACCURACY_M
export function usableNavigationOrigin(point, now=Date.now()) {
  if (!point || point.kind === 'network' || !Number.isFinite(point.latitude) || Math.abs(point.latitude)>90 || !Number.isFinite(point.longitude) || Math.abs(point.longitude)>180) return null
  if (point.kind === 'gps' && (!Number.isFinite(point.accuracy_m) || point.accuracy_m>MAX_START_ACCURACY_M || point.accuracy_m<0 || !Number.isFinite(point.gps_timestamp) || point.gps_timestamp>now || now-point.gps_timestamp>300000)) return null
  return point
}
export default function PublicShelters({point=null,active,overview=false,mapTarget=null,districtId='',navigationBounds=null,onLocate=null,nearestRequest=0}) {
  const [open,setOpen]=useState(false),[navigation,setNavigation]=useState(null),[navigationNotice,setNavigationNotice]=useState(null)
  // Routing availability is learned on the first explicit request, adding no background calls.
  const [routing,setRouting]=useState(true),[route,setRoute]=useState(null),[routeBusy,setRouteBusy]=useState(false)
  const [pending,setPending]=useState(null),locateTried=useRef(false)
  // When GPS is refused or imprecise, the start can be clicked on the shelter map instead.
  const [retryTarget,setRetryTarget]=useState(null),[pickingStart,setPickingStart]=useState(null)
  const [navTarget,setNavTarget]=useState(null),[travelMode,setTravelMode]=useState('walking')
  const [selected,setSelected]=useState(null),[locating,setLocating]=useState(false),[locateError,setLocateError]=useState(null)
  const [awaitingPermission,setAwaitingPermission]=useState(false),[locatingAccuracy,setLocatingAccuracy]=useState(null),locateJob=useRef(null),staleRefreshed=useRef(null),pendingRef=useRef(null)
  pendingRef.current=pending
  useEffect(()=>()=>locateJob.current?.abort(),[])
  // One-screen rule: shelters are paged instead of scrolled; on phones the map and help are tabs.
  const wide=useWide(),[tab,setTab]=useState('list')
  const selectedPoint=point
  point=usableNavigationOrigin(point)
  const approx=approximateStart(point)
  // An imprecise GPS fix is still shown as an area (blue circle) so the person can tap the exact start inside it.
  const mapOrigin=point||(selectedPoint?.kind==='gps'&&Number.isFinite(selectedPoint.accuracy_m)?{...selectedPoint,showAccuracy:true}:null)
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
  const paged=usePaged(ordered,PER_PAGE)
  // A pin on the map opens that shelter's card; "Show on map" on a card switches phones to the map.
  function select(id,fromMap=false){setSelected(id);const index=ordered.findIndex(s=>s.id===id);if(fromMap){if(index>=0)paged.setPage(Math.floor(index/(PER_PAGE)));setTab('list')}else setTab('map')}
  const pins=ordered.map((s,i)=>({...s,label:String(i+1),name:`${i+1}. ${s.name} · ${s.available_capacity} places free`,tone:s.available_capacity<Math.max(10,s.capacity*0.15)?'limited':'ok'}))
  const navListed=!!navTarget&&!!data?.shelters.some(s=>s.id===navTarget.id&&s.latitude===navTarget.latitude&&s.longitude===navTarget.longitude)
  const navLink=navTarget&&navigation?.id===navTarget.id&&navigation.key===key&&Date.now()-navigation.at<5000?navigation.url:null
  const navigator_=navTarget&&point?<ShelterNavigation shelter={navTarget} origin={approx?{...point,approximate:true}:point} listed={navListed} demonstration={data?.mode==='demonstration'} mode={travelMode} onMode={setTravelMode} link={navLink} rechecking={current.loading} onRecheck={()=>checkDestination({preventDefault(){}},navTarget)} onClose={()=>setNavTarget(null)}/>:null
  useEffect(()=>{if(navTarget)setTab('map')},[navTarget?.id])
  function startPicking(target=retryTarget||'nearest'){setPickingStart(target);setNavigationNotice(null);setTab('map')}  // the map banner says what to do
  function pickStart(p){
    const target=pickingStart;setPickingStart(null);setRetryTarget(null)
    onLocate?.({name:'Start point chosen on the map',latitude:p.latitude,longitude:p.longitude,kind:'map',uncertainty_m:50})
    if(target==='locate')return  // only the start was refined; the distance line confirms it
    locateTried.current=true;setPending(target);setNavigationNotice('Start point set. Rechecking availability for directions…')
  }
  const pickBanner=pickingStart&&<div className="shelter-pick-banner" role="status"><strong>Click your starting point on the map.</strong> <button type="button" className="secondary" onClick={()=>{setPickingStart(null);setNavigationNotice(null)}}>Cancel</button></div>
  const map=navigator_||<><h2>Verified shelter entrances</h2>{pickBanner}{route&&<div className="route-summary" role="status"><p><strong>{(route.distance_m/1000).toFixed(1)} km · about {Math.round(route.duration_s/60)} min walking to {ordered.find(x=>x.id===route.shelterId)?.name||'the shelter'}</strong> · <Popup label="Turn-by-turn directions" title={`Turn-by-turn directions · ${route.steps.length} steps`}><RouteSteps steps={route.steps}/></Popup></p><p className="notice">{route.label}</p><p className="muted">{route.attribution}</p></div>}<ShelterMap onSelect={pickingStart?pickStart:null} points={pins} route={route?.geometry} origin={mapOrigin} focus={focus} onInspect={p=>select(p.id,true)} navigationBounds={navigationBounds} label="Verified open shelter entrances"/><p className="muted">Numbered pins match the list; the small dark dot is your starting point. Only freshly rechecked Open shelters with free places are marked.</p></>
  // Browsers answer first with a coarse fix and refine it: watch briefly and keep the best one.
  function locate(onFail){
    if(!onLocate)return
    if(!navigator.geolocation||!window.isSecureContext){setLocateError('Location needs a supported browser and a secure connection. Use "Change location" instead.');onFail?.();return}
    locateJob.current?.abort();const job=new AbortController();locateJob.current=job
    setLocating(true);setLocateError(null);setLocatingAccuracy(null);setAwaitingPermission(false)
    // While the browser's permission prompt is open, say so; a "Block" answer ends the attempt at once.
    Promise.resolve(navigator.permissions?.query?.({name:'geolocation'})).then(status=>{
      if(!status||locateJob.current!==job)return
      if(status.state==='prompt')setAwaitingPermission(true)
      status.onchange=()=>{if(locateJob.current!==job)return;setAwaitingPermission(false);if(status.state==='denied')job.abort('denied')}
    },()=>{})
    const asPoint=r=>({name:'Your GPS location',latitude:r.coords.latitude,longitude:r.coords.longitude,accuracy_m:r.coords.accuracy,gps_timestamp:r.timestamp,kind:'gps'})
    // The first usable fix is used at once (shelters list immediately); a better one replaces it when it arrives.
    let used=null
    preciseLocation({signal:job.signal,onProgress:p=>{setAwaitingPermission(false);setLocatingAccuracy(Math.round(p.coords.accuracy));if(!used&&p.coords.accuracy<=MAX_START_ACCURACY_M){used=p.coords.accuracy;onLocate(asPoint(p))}}}).then(r=>{
      if(used===null||r.coords.accuracy<used)onLocate(asPoint(r))
      // Too coarse for directions: show the area on the map and let the person tap the exact start.
      if(r.coords.accuracy>MAX_START_ACCURACY_M&&!pendingRef.current)startPicking('locate')
    },e=>{if(e?.name==='AbortError'&&job.signal.reason!=='denied')return;setLocateError(e?.code===1||job.signal.reason==='denied'?'Location permission denied. Allow location for this site, or use "Change location" to choose your place.':'Location unavailable. Use "Change location", or tap your start on the map.');onFail?.()})
    .finally(()=>{if(locateJob.current===job){locateJob.current=null;setLocating(false);setLocatingAccuracy(null);setAwaitingPermission(false)}})
  }
  // Like Home: when Shelters opens without a usable start, look up the location once (unless access was refused),
  // so nobody has to place their start by hand. A fix older than five minutes is refreshed the same way.
  const autoLocated=useRef(false)
  useEffect(()=>{
    if(!enabled){autoLocated.current=false;return}
    if(autoLocated.current||point||!onLocate||locating)return
    autoLocated.current=true
    let live=true
    Promise.resolve(navigator.permissions?.query?.({name:'geolocation'})).then(state=>{if(live&&state?.state!=='denied')locate()},()=>{if(live)locate()})
    return()=>{live=false}
  },[enabled,point])
  // With an approximate start the origin is left out, so Google Maps starts from the phone's own location.
  const directions=s=>'https://www.google.com/maps/dir/?'+new URLSearchParams({api:'1',destination:`${s.latitude},${s.longitude}`,...(point&&!approx?{origin:`${point.latitude},${point.longitude}`}:{})})
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
      setRoute({...body,shelterId:shelter.id});setNavigationNotice(null);setTab('map')
    }catch{setNavigationNotice('Routing request failed. Use external directions.')}finally{setRouteBusy(false)}
  }
  // Directions need a precise start: ask for location first, then continue automatically.
  function needLocation(target){
    locateTried.current=true;setPending(target);setNavigationNotice('Finding your location for directions… allow location access if your browser asks.')
    locate(()=>{setRetryTarget(target);setPending(null);setNavigationNotice('Select an adequate starting location before requesting directions. Network estimates and stale or imprecise GPS fixes cannot be used.')})
  }
  const handledNearest=useRef(0)  // each Home "nearest shelter" press is handled once
  useEffect(()=>{if(nearestRequest>handledNearest.current&&enabled){handledNearest.current=nearestRequest;locateTried.current=false;setPending('nearest')}},[nearestRequest,enabled])
  useEffect(()=>{
    if(!pending||!enabled)return
    if(!point){
      if(!locateTried.current&&onLocate&&!locating)needLocation(pending)
      else if(locateTried.current&&!locating&&selectedPoint){setRetryTarget(pending);setPending(null);startPicking(pending);setNavigationNotice(`Your location is too uncertain${Number.isFinite(selectedPoint.accuracy_m)?` (±${Math.round(selectedPoint.accuracy_m)} m)`:''} for directions. Tap your exact start on the map (blue circle), or try again outdoors.`)}
      else if(!onLocate){setRetryTarget(pending);setPending(null);setNavigationNotice('Select an adequate starting location before requesting directions.')}
      return
    }
    if(current.loading||!data||data.shelters.some(s=>s.straight_line_km===null))return  // wait for distances from this start point
    const target=pending==='nearest'?ordered[0]:ordered.find(s=>s.id===pending.id)
    setPending(null);setRetryTarget(null);locateTried.current=false
    if(!target){setNavigationNotice(pending==='nearest'?'No verified open shelter with free places is available right now. Call 112 or 080-1070 for help.':'This shelter is no longer listed as available.');return}
    select(target.id);void checkDestination({preventDefault(){}},target)
  },[pending,enabled,point?.latitude,point?.longitude,selectedPoint,locating,current.loading,data])
  async function checkDestination(event,shelter) {
    event.preventDefault();setNavigation(null)
    if(!usableNavigationOrigin(selectedPoint)&&onLocate&&!pending){needLocation(shelter);return}
    if(!usableNavigationOrigin(selectedPoint)){setNavigationNotice('Select an adequate starting location before requesting directions. Network estimates and stale or imprecise GPS fixes cannot be used.');return}
    setNavigationNotice('Rechecking destination availability…')
    const requestedKey=key,latest=await current.refresh()
    if(selectedKey.current!==requestedKey||!usableNavigationOrigin(selectedPoint))return
    const found=latest?.shelters.find(s=>s.id===shelter.id&&s.latitude===shelter.latitude&&s.longitude===shelter.longitude)
    if(!found){setNavigationNotice('This destination could not be revalidated. No directions were opened. Check the current directory.');return}
    setNavigation({id:found.id,key:requestedKey,url:directions(found),at:Date.now()})
    setNavTarget(found)
    // The navigation panel that opens now explains the five-second link and road-safety limits.
    setNavigationNotice(null)
  }
  const limits=<><p>Only manually authorized, entrance-verified, usable Open assignments with reported available capacity are listed{data?.shelters.length?` (${data.shelters.length} of ${data.total} assignments shown; verification expires after ${data.verification_valid_hours} hours)`:''}. This prototype is not affiliated with a disaster-management authority.</p>
    {!point&&<p>No starting location selected. Choose a starting point on the map or an explicitly selected locality before requesting directions.</p>}
    <p className="notice">Approximate straight-line distance is not road distance. Flooding and road closures may make external routes unsafe. Confirm access and availability with local authorities before travel.</p>
    <p>"Get directions" rechecks this shelter's availability first; the directions link then stays active for five seconds.</p>
    {enabled&&<p>Availability: {current.freshness}. Active directories are checked at least every minute; returning to this tab rechecks availability. A network failure removes destinations.</p>}</>
  const listView=<>
    {data?.shelters.length>0&&<>
      <p className="shelter-summary"><strong>{data.shelters.length} open {data.shelters.length===1?'shelter':'shelters'} with free space</strong>{data.retrieved_at&&<> · checked <span className="label-long">{clock(data.retrieved_at)}</span><span className="label-short">{new Date(data.retrieved_at).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour:'numeric',minute:'2-digit'})}</span></>}</p>
      <ol aria-label="Available shelter destinations" className="shelter-list" start={paged.page*(PER_PAGE)+1}>{paged.items.map((s,j)=>{
        const i=paged.page*(PER_PAGE)+j
          const used=Math.min(100,Math.round(100*(s.capacity-s.available_capacity)/Math.max(1,s.capacity)))
          return <li key={s.id} id={'shelter-'+s.id} className={'shelter-card'+(selected===s.id?' selected':'')}>
          <div className="shelter-card-head"><span className="shelter-num" aria-hidden="true">{i+1}</span><h3>{s.name}</h3>{i===0&&point&&s.straight_line_km!==null&&<span className="shelter-nearest">Nearest</span>}</div>
          <p className="shelter-distance">{s.straight_line_km===null?'Straight-line distance unavailable':`${Number(s.straight_line_km).toFixed(1)} km approximate straight-line distance`}</p>
          {wide&&<p className="shelter-address">{s.address} · {s.district_name}</p>}
          <div className="shelter-capacity" data-tone={pins[i].tone}><p><strong>{s.available_capacity} available</strong> of {s.capacity} places · {s.occupancy} reported occupants</p><div className="capacity-bar" role="img" aria-label={`${used}% of places taken`}><span style={{width:used+'%'}}/></div></div>
          {s.restrictions&&<p className="shelter-restrictions">Restrictions: {s.restrictions}</p>}
          {wide?<>          <ul className="shelter-facilities" aria-label="Facilities"><li data-value={s.water}>Water: {s.water}</li><li data-value={s.toilets}>Toilets: {s.toilets}</li><li>Accessibility: {s.accessibility||'Not reported'}</li></ul>
          {s.contact&&<p>Approved contact: {s.contact}</p>}
          <p className="muted">Verified {ago(s.verified_at)} · verification expires {clock(s.verification_expires_at)}</p>
          </>:<p className="shelter-more"><Popup label="Shelter details: address, facilities, contact" title={s.name}><p>{s.address} · {s.district_name}</p>
          <ul className="shelter-facilities" aria-label="Facilities"><li data-value={s.water}>Water: {s.water}</li><li data-value={s.toilets}>Toilets: {s.toilets}</li><li>Accessibility: {s.accessibility||'Not reported'}</li></ul>
          {s.contact&&<p>Approved contact: {s.contact}</p>}
          <p className="muted">Verified {ago(s.verified_at)} · verification expires {clock(s.verification_expires_at)}</p>
          </Popup></p>}
          <div className="shelter-actions">
          {navigation?.id===s.id&&navigation.key===key&&navigation.url===directions(s)&&Date.now()-navigation.at<5000
            ?<a className="button-link" href={navigation.url} onClick={event=>{if(Date.now()-navigation.at>=5000||!usableNavigationOrigin(selectedPoint)){event.preventDefault();setNavigation(null)}else setNavigation(null)}} target="_blank" rel="noopener noreferrer">{data.mode==='demonstration'?'Inspect demonstration directions (not for travel)':'Open external directions to verified entrance'}</a>
            :<button type="button" aria-label="Get directions" onClick={event=>checkDestination(event,s)} disabled={current.loading}><span className="label-long">Get directions</span><span className="label-short">Directions</span></button>}
          {routing&&<button type="button" className="secondary" aria-label={routeBusy?'Planning route…':'Show walking route on map'} onClick={()=>inAppRoute(s)} disabled={routeBusy||current.loading}>{routeBusy?'Planning route…':<><span className="label-long">Show walking route on map</span><span className="label-short">Walking route</span></>}</button>}
          <button type="button" className="secondary" aria-label="Show on map" onClick={()=>select(s.id)} aria-pressed={selected===s.id}><span className="label-long">Show on map</span><span className="label-short">On map</span></button>
          </div>

        </li>})}</ol>
      <Pager paged={paged} label="More shelters"/>
      <p className="shelter-safety">Capacity is not a reservation. Directions are not verified flood-safe; confirm access before travel.{wide&&<> <Popup label="Limitations" title="Availability and navigation limitations">{limits}</Popup></>}</p>
    </>}
  </>
  const mapView=navigator_||<>{pickBanner}{route&&<div className="route-summary" role="status"><p><strong>{(route.distance_m/1000).toFixed(1)} km · about {Math.round(route.duration_s/60)} min walking to {ordered.find(x=>x.id===route.shelterId)?.name||'the shelter'}</strong> · <Popup label="Turn-by-turn directions" title={`Turn-by-turn directions · ${route.steps.length} steps`}><RouteSteps steps={route.steps}/></Popup></p><p className="notice">{route.label}</p><p className="muted">{route.attribution}</p></div>}<ShelterMap onSelect={pickingStart?pickStart:null} points={pins} route={route?.geometry} origin={mapOrigin} focus={focus} onInspect={p=>select(p.id,true)} navigationBounds={navigationBounds} label="Verified open shelter entrances"/></>
  // Phones: while the Map tab is open, the list header steps aside so the map and directions fit.
  // Why the current location cannot start directions, and how to fix it.
  const roughness=selectedPoint?.kind==='network'?'Your location is only an approximate city estimate.':selectedPoint?.kind==='gps'&&!(selectedPoint.accuracy_m<=MAX_START_ACCURACY_M)?`Your device located you only to ±${Math.round(selectedPoint.accuracy_m)} m; directions need ±${MAX_START_ACCURACY_M} m or better. Laptops often cannot do better.`:'Your GPS fix is older than five minutes; update your location for directions.'
  return <section className={(overview?"panel shelters-overview":"panel shelters-panel")+(!wide&&tab==='map'?' map-focus':'')} aria-labelledby="public-shelters-title">
    <div className="panel-heading"><div><p className="eyebrow">VERIFIED BY ADMINISTRATORS</p><h2 id="public-shelters-title">Open shelters near you</h2></div><button className="secondary" onClick={()=>enabled?current.refresh():setOpen(true)} disabled={current.loading}>{current.loading?'Loading shelters…':enabled?'Refresh shelters':'Find open shelters'}</button></div>
    <div className="shelter-origin">{point?<p>{`Distances from ${point.name}${point.kind==='gps'?` (GPS ±${Math.round(point.accuracy_m)} m${approx?', approximate':''})`:''}.`}</p>:<p>{awaitingPermission?'Allow location access in your browser\'s prompt (next to the address bar) to list the nearest shelters.':'Set your location to list the nearest shelters first.'}</p>}
      {onLocate&&<button type="button" onClick={()=>locate()} disabled={locating}>{locating?(awaitingPermission?'Allow location…':locatingAccuracy!==null?`±${locatingAccuracy} m, improving…`:'Finding you…'):point?'Update my location':'Use my location'}</button>}</div>
    {locateError&&!point&&<p role="status" className="notice">{locateError}</p>}
    {selectedPoint && !point && !locating && <p role="status" className="notice">{roughness}{!pickingStart&&onLocate&&<> <button type="button" className="link-button" onClick={()=>startPicking('locate')}>Tap my start on the map</button></>}</p>}
    <div aria-live="polite" aria-busy={current.loading} className="shelter-status">
      {current.loading&&<p role="status">Checking shelter directory…</p>}
      {current.error&&<p role="alert">{current.error}. No substitute destinations are shown.</p>}
      {navigationNotice&&<p role="status" className="shelter-navigation-notice">{navigationNotice}</p>}
      {retryTarget&&!pickingStart&&onLocate&&<button type="button" className="shelter-pick-start" onClick={()=>startPicking()}>Choose my start on the map</button>}
      {data?.mode==='demonstration'&&<p role="alert" className="notice error"><strong>DEMONSTRATION ONLY — isolated test assignments, not actual emergency shelters. Do not travel to these points.</strong></p>}
      {data&&!data.shelters.length&&<p role="status" className="shelter-empty">No currently verified open shelters are available in this directory.</p>}
    </div>
    {/* Laptop: list here, map in the right-hand panel. Phone: Shelters | Map | Help tabs. */}
    <ScreenTabs className="shelter-tabs" label="Shelter sections" active={tab} onActive={setTab} tabs={[
      {id:'list',label:'Shelters',content:<>{listView}{wide&&<OfficialHelp prominent={!!data&&!data.shelters.length}/>}{wide&&!(data?.shelters.length>0)&&<p className="shelter-limits"><Popup label="Limitations" title="Availability and navigation limitations">{limits}</Popup></p>}</>},
      !mapTarget&&{id:'map',label:'Map',content:enabled?<div className="shelter-inline-map">{mapView}</div>:null},
      !wide&&{id:'help',label:'Help',content:<><OfficialHelp prominent={!!data&&!data.shelters.length}/><p className="shelter-limits"><Popup label="Availability and navigation limitations" title="Availability and navigation limitations">{limits}</Popup></p></>},
    ]}/>
    {mapTarget&&enabled&&createPortal(map,mapTarget)}
  </section>
}
