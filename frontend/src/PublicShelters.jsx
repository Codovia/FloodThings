import React,{useEffect,useRef,useState} from 'react'
import {createPortal} from 'react-dom'
import ShelterMap from './ShelterMap.jsx'
import useShelterDirectory from './useShelterDirectory.js'
export { validShelterDirectory } from './useShelterDirectory.js'
import './Shelters.css'
const clock=value=>new Intl.DateTimeFormat('en-IN',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Kolkata'}).format(new Date(value))+' IST'
export default function PublicShelters({point=null,active,overview=false,mapTarget=null,districtId='',navigationBounds=null}) {
  const [open,setOpen]=useState(false),[navigation,setNavigation]=useState(null),[navigationNotice,setNavigationNotice]=useState(null)
  const key=point?`${point.latitude}:${point.longitude}`:'no-origin'
  const enabled=active===undefined?open:active
  const selectedKey=useRef(key);selectedKey.current=key
  useEffect(()=>{selectedKey.current=enabled?key:null;setNavigation(null);setNavigationNotice(null);return()=>{selectedKey.current=null}},[key,enabled])
  useEffect(()=>{if(!navigation)return;const timer=setTimeout(()=>setNavigation(null),5000);return()=>clearTimeout(timer)},[navigation])
  const current=useShelterDirectory(point,enabled),source=current.data
  const data=source?{...source,shelters:source.shelters.filter(s=>!districtId||s.district_id===districtId)}:null
  const map=<><h2>Verified shelter entrances</h2><ShelterMap points={data?.shelters||[]} origin={point} navigationBounds={navigationBounds} label="Verified open shelter entrances"/><p className="muted">Only freshly revalidated Open destinations with spare capacity are marked. The selected-point marker is an origin, not a shelter. No markers are invented for missing records.</p></>
  const directions=s=>'https://www.google.com/maps/dir/?'+new URLSearchParams({api:'1',destination:`${s.latitude},${s.longitude}`,...(point?{origin:`${point.latitude},${point.longitude}`}:{})})
  async function checkDestination(event,shelter) {
    event.preventDefault();setNavigation(null);setNavigationNotice('Rechecking destination availability…')
    const requestedKey=key,latest=await current.refresh()
    if(selectedKey.current!==requestedKey)return
    const found=latest?.shelters.find(s=>s.id===shelter.id&&s.latitude===shelter.latitude&&s.longitude===shelter.longitude)
    if(!found){setNavigationNotice('This destination could not be revalidated. No directions were opened. Check the current directory.');return}
    setNavigation({id:found.id,key:requestedKey,url:directions(found),at:Date.now()})
    setNavigationNotice('Availability rechecked. Select directions again within five seconds to open external navigation. Reported conditions and road access may still change.')
  }
  return <section className={overview?"panel shelters-overview":"panel"} aria-labelledby="public-shelters-title">
    <div className="panel-heading"><div><p className="eyebrow">ADMINISTRATOR-REPORTED AVAILABILITY</p><h2 id="public-shelters-title">Emergency shelter directory</h2></div><button onClick={()=>enabled?current.refresh():setOpen(true)} disabled={current.loading}>{current.loading?'Loading shelters…':enabled?'Refresh shelters':'Find open shelters'}</button></div>
    {data&&!data.shelters.length&&<p role="status" className="shelter-empty">No currently verified open shelters are available in this directory.</p>}
    <p className="muted">Reported capacity is not a reservation. External directions are not verified flood-safe; confirm availability and road access before travel.</p>
    <details className="shelter-usage"><summary>Availability and safe navigation limitations</summary><p>Only manually authorized, entrance-verified, usable Open assignments with reported available capacity are listed. This prototype is not affiliated with a disaster-management authority.</p>
    {point?<p>Distances from selected point: {point.name}.</p>:<p>No starting location selected. Directions can ask you to enter an origin.</p>}
    <p className="notice">Approximate straight-line distance is not road distance. Flooding and road closures may make external routes unsafe. Confirm access and availability with local authorities before travel.</p>
    </details>
    {mapTarget&&enabled&&createPortal(map,mapTarget)}
    <div aria-live="polite" aria-busy={current.loading}>
      {enabled&&<p role="status">Availability: {current.freshness}. Active directories are checked at least every minute; returning to this tab rechecks availability. A network failure removes destinations.</p>}
      {navigationNotice&&<p role="status">{navigationNotice}</p>}
      {current.loading&&<p role="status">Checking shelter directory…</p>}
      {current.error&&<p role="alert">{current.error}. No substitute destinations are shown.</p>}
      {data?.mode==='demonstration'&&<p role="alert" className="notice error"><strong>DEMONSTRATION ONLY — isolated test assignments, not actual emergency shelters. Do not travel to these points.</strong></p>}
      {data?.retrieved_at&&<p className="muted">Directory checked {clock(data.retrieved_at)}. Reported conditions may change; refresh and confirm access before travel.</p>}
      {data?.shelters.length>0&&<>
        <p>{data.shelters.length} of {data.total} available assignments shown. Capacity is reported, not a reservation. Verification expires after {data.verification_valid_hours} hours.</p>
        {!mapTarget&&!overview&&<ShelterMap points={data.shelters} origin={point} label="Verified open shelter entrances" />}
        <ul aria-label="Available shelter destinations" className="shelter-list">{data.shelters.map(s=><li key={s.id}>
          <h3>{s.name}</h3><p>{s.address} · {s.district_name}</p><p>{s.available_capacity} available / {s.capacity} maximum; {s.occupancy} reported occupants.</p>
          <p>Water: {s.water}. Toilets: {s.toilets}. Accessibility: {s.accessibility||'Not reported'}.</p>
          <p>{s.straight_line_km===null?'Straight-line distance unavailable':`${s.straight_line_km} km approximate straight-line distance`}</p>
          <p>Verified {clock(s.verified_at)} · updated {clock(s.updated_at)} · verification expires {clock(s.verification_expires_at)}</p>
          {s.restrictions&&<p>Restrictions: {s.restrictions}</p>}{s.contact&&<p>Approved contact: {s.contact}</p>}
          {navigation?.id===s.id&&navigation.key===key&&navigation.url===directions(s)&&Date.now()-navigation.at<5000
            ?<a href={navigation.url} onClick={event=>{if(Date.now()-navigation.at>=5000){event.preventDefault();setNavigation(null)}else setNavigation(null)}} target="_blank" rel="noopener noreferrer">{data.mode==='demonstration'?'Inspect demonstration directions (not for travel)':'Open external directions to verified entrance'}</a>
            :<button type="button" onClick={event=>checkDestination(event,s)} disabled={current.loading}>Recheck availability for directions</button>}
        </li>)}</ul>
      </>}
    </div>
  </section>
}
