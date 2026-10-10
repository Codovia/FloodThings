import React,{useEffect,useState} from 'react'
import AdminEntranceMap from './AdminEntranceMap.jsx'
import AdminNotifications from './AdminNotifications.jsx'
import './Shelters.css'
const blank=()=>({name:'',address:'',district_id:'',latitude:'',longitude:'',capacity:'',occupancy:'',water:'unknown',toilets:'unknown',accessibility:'',contact:'',publish_contact:false,status:'pending',notes:'',restrictions:'',revision:null,verification:{authorization:false,entrance:false,usability:false,capacity:false,evidence:''}})
const clock=value=>value?new Date(value).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})+' IST':'Not verified'
export default function AdminShelters({embedded=false,onHome=null}){
  const [session,setSession]=useState(null),[checking,setChecking]=useState(true),[error,setError]=useState(null),[notice,setNotice]=useState(null),[busy,setBusy]=useState(false)
  const [rows,setRows]=useState([]),[total,setTotal]=useState(0),[offset,setOffset]=useState(0),[districts,setDistricts]=useState([]),[form,setForm]=useState(blank),[editing,setEditing]=useState(null),[history,setHistory]=useState(null)
  const [adminTab,setAdminTab]=useState('shelters')
  const [username,setUsername]=useState(''),[password,setPassword]=useState('')
  async function request(path,options={},auth=session){
    const response=await fetch(path,{credentials:'same-origin',...options,headers:{...(options.body?{'Content-Type':'application/json'}:{}),...(auth?.csrf_token?{'X-CSRF-Token':auth.csrf_token}:{}),...options.headers}})
    const data=await response.json()
    if(!response.ok){if(response.status===401)setSession(null);throw Error(typeof data.detail==='string'?data.detail:'Invalid shelter request; check all fields and verification confirmations')}
    return data
  }
  useEffect(()=>{
    const controller=new AbortController();let stopped=false
    fetch('/api/admin/session',{credentials:'same-origin',signal:controller.signal}).then(async r=>{const data=await r.json();if(!stopped){if(r.ok)setSession(data);else if(r.status!==401)setError(typeof data.detail==='string'?data.detail:'Administrator service unavailable')}}).catch(e=>{if(!stopped)setError('Administrator service unavailable')}).finally(()=>{if(!stopped)setChecking(false)})
    return()=>{stopped=true;controller.abort()}
  },[])
  async function load(auth=session,start=offset){
    const [directory,list]=await Promise.all([request('/api/locations/districts',{},auth),request('/api/admin/shelters?limit=100&offset='+start,{},auth)])
    if(directory.status!=='available'||!Array.isArray(directory.items)||!Array.isArray(list.shelters))throw Error('Location directory or shelter response unavailable')
    setDistricts(directory.items);setRows(list.shelters);setTotal(list.total)
  }
  useEffect(()=>{if(session)load(session,offset).catch(e=>setError(e.message))},[session,offset])
  function field(key,value){setForm(f=>({...f,[key]:value}))}
  function verify(key,value){setForm(f=>({...f,verification:{...f.verification,[key]:value}}))}
  function edit(row){setEditing(row.id);setHistory(null);setNotice(null);setForm({...blank(),...Object.fromEntries(Object.keys(blank()).filter(k=>k!=='verification').map(k=>[k,row[k]??blank()[k]])),latitude:row.latitude??'',longitude:row.longitude??'',capacity:String(row.capacity),occupancy:String(row.occupancy),verification:{authorization:false,entrance:false,usability:false,capacity:false,evidence:''}})}
  async function operation(fn){setBusy(true);setError(null);try{await fn()}catch(e){setError(e.message)}finally{setBusy(false)}}
  async function login(e){e.preventDefault();await operation(async()=>{try{const data=await request('/api/admin/login',{method:'POST',headers:{'X-FloodPulse-Login':'1'},body:JSON.stringify({username,password})},null);setSession(data);setNotice('Signed in')}finally{setPassword('')}})}
  async function save(e){e.preventDefault();await operation(async()=>{
    const body={...form,latitude:form.latitude===''?null:Number(form.latitude),longitude:form.longitude===''?null:Number(form.longitude),capacity:Number(form.capacity),occupancy:Number(form.occupancy)}
    const row=await request('/api/admin/shelters'+(editing?'/'+editing:''),{method:editing?'PUT':'POST',body:JSON.stringify(body)})
    edit(row);setNotice('Assignment saved. Public availability depends on status, verification expiry and capacity.');await load()
  })}
  const entrance=form.latitude!==''&&form.longitude!==''&&Number.isFinite(Number(form.latitude))&&Number.isFinite(Number(form.longitude))&&Math.abs(Number(form.latitude))<=90&&Math.abs(Number(form.longitude))<=180?[{name:'Unconfirmed entrance selection',latitude:Number(form.latitude),longitude:Number(form.longitude)}]:[]
  const Container=embedded?'div':'main'
  return <Container className="admin-shell"><a href="/" onClick={onHome?e=>{e.preventDefault();onHome()}:undefined}>Return to citizen dashboard</a><h2>Shelter administrator</h2><p>Provisioned project staff only. Prototype; no affiliation with a disaster-management authority. No public registration.</p>
    {checking&&<p role="status">Checking administrator session…</p>}
    {error&&<p role="alert" className="notice error">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {!checking&&!session&&<form className="panel shelter-form" onSubmit={login}><h2>Administrator login</h2><label>Username<input autoComplete="username" required maxLength={64} value={username} onChange={e=>setUsername(e.target.value)} /></label><label>Password<input type="password" autoComplete="current-password" required maxLength={128} value={password} onChange={e=>setPassword(e.target.value)} /></label><button disabled={busy}>Sign in</button></form>}
    {session&&<>
      {session.mode==='demonstration'&&<p role="alert" className="notice error"><strong>DEMONSTRATION ONLY — isolated database. These are not operational shelter assignments.</strong></p>}
      <p>Signed in as {session.user.username}. Session expires after 30 idle minutes or eight hours.</p><button disabled={busy} onClick={()=>operation(async()=>{await request('/api/admin/logout',{method:'POST'});setSession(null);setRows([]);setForm(blank());setEditing(null);setNotice('Signed out')})}>Sign out</button>
      <nav aria-label="Administrator workspace" className="admin-tabs"><button type="button" aria-pressed={adminTab==='shelters'} onClick={()=>setAdminTab('shelters')}>Shelter workspace</button><button type="button" aria-pressed={adminTab==='notifications'} onClick={()=>setAdminTab('notifications')}>Telegram notifications</button></nav>
      <div hidden={adminTab!=='notifications'} className="admin-notifications"><AdminNotifications session={session} request={request} /></div>
      <div className="admin-management" hidden={adminTab!=='shelters'}>
      <section className="panel admin-assignments"><h2>Shelter assignments</h2><button disabled={busy} onClick={()=>operation(()=>load())}>Refresh assignments</button><button disabled={busy} onClick={()=>{setEditing(null);setForm(blank());setHistory(null)}}>Create new shelter</button>
        {!rows.length&&<p>No assignments in this directory.</p>}<p>{rows.length} of {total} assignments shown.</p>
        <ul aria-label="Administrator shelter assignments" className="shelter-list">{rows.map(row=><li key={row.id}><strong>{row.name}</strong><p>{row.district_name} · {row.status} · {row.occupancy}/{row.capacity} occupants · {row.publicly_available?'Publicly available':'Unavailable to public'}</p><p>Verified: {clock(row.verified_at)}. Updated: {clock(row.updated_at)}.</p><button disabled={busy} onClick={()=>edit(row)}>Edit {row.name}</button><button disabled={busy} onClick={()=>operation(async()=>{setHistory(await request('/api/admin/shelters/'+row.id+'/audit'))})}>Audit {row.name}</button></li>)}</ul>
        <button disabled={busy||offset===0} onClick={()=>setOffset(n=>Math.max(0,n-100))}>Previous assignments</button><button disabled={busy||offset+100>=total} onClick={()=>setOffset(n=>n+100)}>Next assignments</button>
        {history&&<div aria-label="Shelter audit history"><h3>Audit history</h3><ul>{history.events.map(event=><li key={event.id}>{clock(event.at)} · {event.action} by {event.admin_id} · {event.before?.status||'new'} → {event.after.status} · occupancy {event.before?.occupancy??'none'} → {event.after.occupancy}; capacity {event.before?.capacity??'none'} → {event.after.capacity}</li>)}</ul></div>}
      </section>
      <AdminEntranceMap entrance={entrance} onSelect={point=>setForm(f=>({...f,latitude:String(point.latitude),longitude:String(point.longitude),verification:{authorization:false,entrance:false,usability:false,capacity:false,evidence:''}}))} />
      <form className="panel shelter-form" onSubmit={save} aria-label="Shelter assignment form"><h2>{editing?'Edit shelter assignment':'Create Pending shelter assignment'}</h2>
        <label>Facility name<input required maxLength={200} value={form.name} onChange={e=>field('name',e.target.value)} /></label>
        <label>Facility address<textarea required maxLength={1000} value={form.address} onChange={e=>field('address',e.target.value)} /></label>
        <label htmlFor="shelter-district">Shelter district</label><select id="shelter-district" required value={form.district_id} onChange={e=>field('district_id',e.target.value)}><option value="">Choose district</option>{districts.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select>
        <p>District association is assigned by the administrator using NIC directory identities; independent current LGD reconciliation is unresolved.</p>
        <label>Entrance latitude<input type="number" step="any" min={-90} max={90} value={form.latitude} onChange={e=>field('latitude',e.target.value)} /></label>
        <label>Entrance longitude<input type="number" step="any" min={-180} max={180} value={form.longitude} onChange={e=>field('longitude',e.target.value)} /></label>
        <p>Enter a verified entrance or choose a point on the map. Placing a marker does not verify a facility. Leave both blank while Pending if unknown.</p>
        <label>Maximum capacity<input required type="number" min={1} max={100000} step={1} value={form.capacity} onChange={e=>field('capacity',e.target.value)} /></label>
        <label>Current occupancy<input required type="number" min={0} max={Number(form.capacity)||100000} step={1} value={form.occupancy} onChange={e=>field('occupancy',e.target.value)} /></label>
        {['water','toilets'].map(key=><div key={key}><label htmlFor={'shelter-'+key}>{key==='water'?'Water availability':'Toilets'}</label><select id={'shelter-'+key} value={form[key]} onChange={e=>field(key,e.target.value)}><option value="unknown">Unknown</option><option value="yes">Yes</option><option value="no">No</option></select></div>)}
        <label>Accessibility information<textarea maxLength={2000} value={form.accessibility} onChange={e=>field('accessibility',e.target.value)} /></label>
        <label>Contact information<input maxLength={200} value={form.contact} onChange={e=>field('contact',e.target.value)} /></label><label><input type="checkbox" checked={form.publish_contact} onChange={e=>field('publish_contact',e.target.checked)} />Approved for public contact disclosure</label>
        <label htmlFor="shelter-status">Shelter status</label><select id="shelter-status" value={form.status} disabled={!editing} onChange={e=>field('status',e.target.value)}><option value="pending">Pending verification</option><option value="open">Open</option><option value="full">Full</option><option value="closed">Closed</option></select>
        <fieldset><legend>Explicit verification — renew all confirmations for each Open/Full save</legend>{[['authorization','Facility is authorized for shelter use'],['entrance','This exact entrance has been independently verified'],['usability','Facility is currently usable'],['capacity','Capacity and current occupancy have been checked']].map(([key,label])=><label key={key}><input type="checkbox" checked={form.verification[key]} onChange={e=>verify(key,e.target.checked)} />{label}</label>)}<label>Verification evidence and method<textarea maxLength={2000} required={['open','full'].includes(form.status)} value={form.verification.evidence} onChange={e=>verify('evidence',e.target.value)} /></label></fieldset>
        <label>Public operational restrictions<textarea maxLength={2000} value={form.restrictions} onChange={e=>field('restrictions',e.target.value)} /></label><label>Internal notes (not public)<textarea maxLength={2000} value={form.notes} onChange={e=>field('notes',e.target.value)} /></label>
        <p>Open requires spare capacity and all four confirmations. Verification expires after 24 hours; recheck actual conditions before renewal. Full, Closed, Pending and expired assignments are excluded from public destinations. Weather/AI predictions never assign shelters.</p>
        <button disabled={busy||!districts.length}>{busy?'Saving…':'Save shelter assignment'}</button>
      </form>
      </div>
    </>}
  </Container>
}
