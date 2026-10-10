import React,{useEffect,useState} from 'react'
import ShelterMap from './ShelterMap.jsx'
import './Shelters.css'
const clock=value=>new Intl.DateTimeFormat('en-IN',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Kolkata'}).format(new Date(value))+' IST'
export function validShelterDirectory(data){return ['live','demonstration'].includes(data?.mode)&&Array.isArray(data.shelters)&&data.shelters.every(s=>s.status==='open'&&s.available_capacity>0&&Number.isFinite(s.latitude)&&Math.abs(s.latitude)<=90&&Number.isFinite(s.longitude)&&Math.abs(s.longitude)<=180&&Number.isFinite(Date.parse(s.verified_at))&&Date.parse(s.verification_expires_at)>Date.now()&&s.demonstration===(data.mode==='demonstration'))}
export default function PublicShelters({point=null,active=false}) {
  const [open,setOpen]=useState(false),[refresh,setRefresh]=useState(0),[view,setView]=useState({key:null,data:null,error:null,loading:false})
  const key=point?`${point.latitude}:${point.longitude}`:'no-origin'
  useEffect(()=>{if(active)setOpen(true)},[active])
  useEffect(()=>{
    if(!open)return
    const controller=new AbortController();let stopped=false
    const timer=setTimeout(()=>controller.abort(),15000)
    setView({key,data:null,error:null,loading:true})
    ;(async()=>{
      try{
        const params=point?'?'+new URLSearchParams({latitude:point.latitude,longitude:point.longitude}):''
        const response=await fetch('/api/shelters'+params,{signal:controller.signal}),data=await response.json()
        if(!response.ok||data.status!=='available')throw Error(typeof data.detail==='string'?data.detail:'Shelter directory unavailable')
        if(!validShelterDirectory(data))
          throw Error('Shelter availability could not be verified')
        if(!stopped)setView({key,data,error:null,loading:false})
      }catch(error){if(!stopped)setView({key,data:null,error:error.name==='AbortError'?'Shelter directory request timed out. Please retry.':error.message,loading:false})}
      finally{clearTimeout(timer)}
    })()
    return()=>{stopped=true;clearTimeout(timer);controller.abort()}
  },[key,open,refresh])
  const current=view.key===key?view:{data:null,error:null,loading:open},data=current.data
  useEffect(()=>{
    if(!data?.shelters.length)return
    const expiry=Math.min(...data.shelters.map(s=>Date.parse(s.verification_expires_at)))
    const timer=setTimeout(()=>setRefresh(n=>n+1),Math.max(0,expiry-Date.now()+25))
    return()=>clearTimeout(timer)
  },[data])
  return <section className="panel" aria-labelledby="public-shelters-title">
    <div className="panel-heading"><div><p className="eyebrow">ADMINISTRATOR-REPORTED AVAILABILITY</p><h2 id="public-shelters-title">Emergency shelter directory</h2></div><button onClick={()=>open?setRefresh(n=>n+1):setOpen(true)} disabled={current.loading}>{current.loading?'Loading shelters…':open?'Refresh shelters':'Find open shelters'}</button></div>
    <p>Only manually authorized, entrance-verified, usable Open assignments with reported available capacity are listed. This prototype is not affiliated with a disaster-management authority.</p>
    {point?<p>Distances from selected point: {point.name}.</p>:<p>No starting location selected. Directions can ask you to enter an origin.</p>}
    <p className="notice">Approximate straight-line distance is not road distance. External directions are not verified flood-safe: flooding and road closures may make routes unsafe. Confirm access and availability with local authorities before travel.</p>
    <div aria-live="polite" aria-busy={current.loading}>
      {current.loading&&<p role="status">Checking shelter directory…</p>}
      {current.error&&<p role="alert">{current.error}. No substitute destinations are shown.</p>}
      {data?.mode==='demonstration'&&<p role="alert" className="notice error"><strong>DEMONSTRATION ONLY — isolated test assignments, not actual emergency shelters. Do not travel to these points.</strong></p>}
      {data&&!data.shelters.length&&<p role="status" className="shelter-empty">No currently verified open shelters are available in this directory.</p>}
      {data?.retrieved_at&&<p className="muted">Directory checked {clock(data.retrieved_at)}. Reported conditions may change; refresh and confirm access before travel.</p>}
      {data?.shelters.length>0&&<>
        <p>{data.shelters.length} of {data.total} available assignments shown. Capacity is reported, not a reservation. Verification expires after {data.verification_valid_hours} hours.</p>
        <ShelterMap points={data.shelters} origin={point} label="Verified open shelter entrances" />
        <ul aria-label="Available shelter destinations" className="shelter-list">{data.shelters.map(s=><li key={s.id}>
          <h3>{s.name}</h3><p>{s.address} · {s.district_name}</p><p>{s.available_capacity} available / {s.capacity} maximum; {s.occupancy} reported occupants.</p>
          <p>Water: {s.water}. Toilets: {s.toilets}. Accessibility: {s.accessibility||'Not reported'}.</p>
          <p>{s.straight_line_km===null?'Straight-line distance unavailable':`${s.straight_line_km} km approximate straight-line distance`}</p>
          <p>Verified {clock(s.verified_at)} · updated {clock(s.updated_at)} · verification expires {clock(s.verification_expires_at)}</p>
          {s.restrictions&&<p>Restrictions: {s.restrictions}</p>}{s.contact&&<p>Approved contact: {s.contact}</p>}
          <a href={'https://www.google.com/maps/dir/?'+new URLSearchParams({api:'1',destination:`${s.latitude},${s.longitude}`,...(point?{origin:`${point.latitude},${point.longitude}`}:{})})} target="_blank" rel="noopener noreferrer">{data.mode==='demonstration'?'Inspect demonstration directions (not for travel)':'Open external directions to verified entrance'}</a>
        </li>)}</ul>
      </>}
    </div>
  </section>
}
