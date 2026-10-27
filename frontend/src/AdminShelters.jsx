import React,{useEffect,useMemo,useRef,useState} from 'react'
import AdminLogin, { loginErrorMessage } from './AdminLogin.jsx'
import AdminEntranceMap from './AdminEntranceMap.jsx'
import AdminNotifications from './AdminNotifications.jsx'
import AdminReports from './AdminReports.jsx'
import useAdminRequests from './useAdminRequests.js'
import './Shelters.css'
const blank=()=>({name:'',address:'',district_id:'',latitude:'',longitude:'',capacity:'',occupancy:'',water:'unknown',toilets:'unknown',accessibility:'',contact:'',publish_contact:false,status:'pending',notes:'',restrictions:'',revision:null,verification:{authorization:false,entrance:false,usability:false,capacity:false,evidence:''}})
const clock=value=>value?new Date(value).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})+' IST':'Not verified'
const HOUR=3600e3
const span=ms=>{const m=Math.round(Math.abs(ms)/60000);return m<60?`${m} min`:m<48*60?`${Math.round(m/60)} h`:`${Math.round(m/1440)} days`}
// Explains public visibility from the server's own fields; the server alone decides publicly_available.
export function shelterState(row,now=Date.now()){
  // The server sends verification_expires_at; fall back to its 24-hour rule if a row lacks it.
  const expires=Date.parse(row.verification_expires_at)||(row.verified_at?Date.parse(row.verified_at)+24*HOUR:NaN)
  if(row.publicly_available){const left=expires-now;return Number.isFinite(left)&&left<3*HOUR?{tone:'warn',label:'Visible to public',detail:`Verification expires in ${span(left)} — re-verify soon`,attention:true}:{tone:'ok',label:'Visible to public',detail:Number.isFinite(left)?`Verification expires in ${span(left)}`:'Visible',attention:false}}
  if(row.status==='pending')return{tone:'muted',label:'Hidden: pending verification',detail:'Verify and set Open to publish',attention:true}
  if(row.status==='full')return{tone:'muted',label:'Hidden: full',detail:'Set Open with free places to publish again',attention:false}
  if(row.status==='closed')return{tone:'muted',label:'Hidden: closed',detail:'Not offered to the public',attention:false}
  if(row.status==='open'&&(!row.verified_at||(Number.isFinite(expires)&&expires<=now)))return{tone:'bad',label:'Hidden: verification expired',detail:row.verified_at?`Expired ${span(now-expires)} ago — re-verify to publish again`:'Never verified — verify to publish',attention:true}
  return{tone:'bad',label:'Hidden from public',detail:'Check status, verification and capacity',attention:true}
}
const STATUS_NAMES={pending:'Pending',open:'Open',full:'Full',closed:'Closed'}
const materialFields=new Set(['name','address','district_id','latitude','longitude','capacity','occupancy','water','toilets','accessibility','restrictions'])
export default function AdminShelters({embedded=false,onHome=null}){
  const [session,setSession]=useState(null),[checking,setChecking]=useState(true),[error,setError]=useState(null),[notice,setNotice]=useState(null),[busy,setBusy]=useState(false)
  const [rows,setRows]=useState([]),[total,setTotal]=useState(0),[offset,setOffset]=useState(0),[districts,setDistricts]=useState([]),[form,setForm]=useState(blank),[editing,setEditing]=useState(null),[history,setHistory]=useState(null)
  const [adminTab,setAdminTab]=useState('shelters')
  const [workspaceDistrict,setWorkspaceDistrict]=useState(''),[view,setView]=useState('all')
  const formRef=useRef(null),formHeading=useRef(null)
  const [lookup,setLookup]=useState(null),lookupSequence=useRef(0),latestForm=useRef(null)
  const busyRef=useRef(false),loadSequence=useRef(0),operationSequence=useRef(0)
  function clearPrivate(){loadSequence.current++;setSession(null);setRows([]);setTotal(0);setDistricts([]);setForm(blank());setEditing(null);setHistory(null);setOffset(0);setWorkspaceDistrict('');setNotice(null);setAdminTab('shelters')}
  const requests=useAdminRequests(clearPrivate)
  async function request(path,options={},auth=session){
    return requests.request(path,{credentials:'same-origin',...options,headers:{...(options.body?{'Content-Type':'application/json'}:{}),...(auth?.csrf_token?{'X-CSRF-Token':auth.csrf_token}:{}),...options.headers}})
  }
  useEffect(()=>{
    const controller=new AbortController();let stopped=false
    request('/api/admin/session',{signal:controller.signal},null).then(data=>{if(!stopped)setSession(data)}).catch(e=>{if(!stopped&&e.status!==401&&e.name!=='AbortError')setError(e.message)}).finally(()=>{if(!stopped)setChecking(false)})
    return()=>{stopped=true;controller.abort()}
  },[])
  async function load(auth=session,start=offset){
    const generation=requests.generation(),sequence=++loadSequence.current
    const [directory,list]=await Promise.all([request('/api/locations/districts',{},auth),request('/api/admin/shelters?limit=100&offset='+start,{},auth)])
    if(!requests.current(generation)||sequence!==loadSequence.current)return
    if(directory.status!=='available'||!Array.isArray(directory.items)||!Array.isArray(list.shelters))throw Error('Location directory or shelter response unavailable')
    setDistricts(directory.items);setRows(list.shelters);setTotal(list.total)
  }
  useEffect(()=>{const generation=requests.generation();if(session)load(session,offset).catch(e=>{if(requests.current(generation)&&e.name!=='AbortError')setError(e.message)})},[session,offset])
  function field(key,value){setForm(f=>({...f,[key]:value,...(materialFields.has(key)&&f[key]!==value?{verification:blank().verification}:{})}))}
  latestForm.current=form
  // Map click: suggest district, facility name and address for this entrance (administrator confirms).
  async function lookupPlace(point){
    const sequence=++lookupSequence.current
    setLookup({status:'loading'})
    try{
      const data=await request('/api/admin/place?'+new URLSearchParams({latitude:point.latitude.toFixed(6),longitude:point.longitude.toFixed(6)}))
      if(sequence!==lookupSequence.current)return
      if(data.status!=='available'){setLookup({status:'outside',message:data.message});return}
      const aliases=(data.district?.aliases||[]).map(a=>a.toLowerCase())
      const district=districts.find(d=>aliases.includes(d.name.toLowerCase()))
      const current=latestForm.current,notes=[]
      if(district&&current.district_id&&current.district_id!==district.id)notes.push(`District changed to ${district.name} to match the map point.`)
      if(district)field('district_id',district.id)
      if(data.name?.value&&!current.name.trim())field('name',data.name.value)
      if(data.address?.value&&!current.address.trim())field('address',data.address.value)
      setLookup({status:'done',data,district,notes})
    }catch(e){if(sequence===lookupSequence.current&&e.name!=='AbortError')setLookup({status:'error',message:e.message})}
  }
  function verify(key,value){setForm(f=>({...f,verification:{...f.verification,[key]:value}}))}
  function open(row,section){edit(row);requestAnimationFrame(()=>{(section==='verify'?document.getElementById('shelter-verification'):formRef.current)?.scrollIntoView?.({block:'start',behavior:'smooth'});formHeading.current?.focus({preventScroll:true})})}
  function edit(row){setLookup(null);lookupSequence.current++;setEditing(row.id);setHistory(null);setNotice(null);setForm({...blank(),...Object.fromEntries(Object.keys(blank()).filter(k=>k!=='verification').map(k=>[k,row[k]??blank()[k]])),latitude:row.latitude??'',longitude:row.longitude??'',capacity:String(row.capacity),occupancy:String(row.occupancy),verification:{authorization:false,entrance:false,usability:false,capacity:false,evidence:''}})}
  async function operation(fn){if(busyRef.current)return;const sequence=++operationSequence.current;busyRef.current=true;setBusy(true);setError(null);try{await fn()}catch(e){if(requests.mounted()&&sequence===operationSequence.current&&e.name!=='AbortError')setError(e.message)}finally{if(sequence===operationSequence.current){busyRef.current=false;if(requests.mounted())setBusy(false)}}}
  function signOut(){const auth=session;requests.cancel();busyRef.current=false;clearPrivate();void operation(async()=>{await request('/api/admin/logout',{method:'POST'},auth);requests.cancel();setNotice('Signed out')})}
  // The sign-in form clears the password after every attempt; failures get a specific, credential-free message.
  async function login(username,password){await operation(async()=>{let data;try{data=await request('/api/admin/login',{method:'POST',headers:{'X-FloodPulse-Login':'1'},body:JSON.stringify({username,password})},null)}catch(e){throw e.name==='AbortError'?e:Error(loginErrorMessage(e))}setSession(data);setNotice('Signed in')})}
  async function save(e){e.preventDefault();await operation(async()=>{
    const body={...form,latitude:form.latitude===''?null:Number(form.latitude),longitude:form.longitude===''?null:Number(form.longitude),capacity:Number(form.capacity),occupancy:Number(form.occupancy)}
    const row=await request('/api/admin/shelters'+(editing?'/'+editing:''),{method:editing?'PUT':'POST',body:JSON.stringify(body)})
    edit(row);setNotice('Assignment saved. Public availability depends on status, verification expiry and capacity.');await load()
  })}
  const entrance=useMemo(()=>form.latitude!==''&&form.longitude!==''&&Number.isFinite(Number(form.latitude))&&Number.isFinite(Number(form.longitude))&&Math.abs(Number(form.latitude))<=90&&Math.abs(Number(form.longitude))<=180?[{name:'Unconfirmed entrance selection',latitude:Number(form.latitude),longitude:Number(form.longitude)}]:[],[form.latitude,form.longitude])
  const now=Date.now()
  const states=new Map(rows.map(row=>[row.id,shelterState(row,now)]))
  const counts={visible:rows.filter(r=>r.publicly_available).length,attention:rows.filter(r=>states.get(r.id).attention).length,full:rows.filter(r=>r.status==='full').length,closed:rows.filter(r=>r.status==='closed').length}
  const shownRows=rows.filter(row=>(!workspaceDistrict||row.district_id===workspaceDistrict)&&(view==='all'||(view==='attention'?states.get(row.id).attention:view==='public'?row.publicly_available:row.status===view)))
  const workspace=districts.find(row=>row.id===workspaceDistrict)
  const Container=embedded?'div':'main'
  return <Container className="admin-shell"><div className="admin-identity-bar"><div className="admin-identity-title"><h2>Administrator workspace</h2><a href="/" onClick={onHome?e=>{e.preventDefault();onHome()}:undefined}>Return to citizen dashboard</a></div>{session&&<div><span>Signed in as {session.user.username}</span> <button onClick={signOut}>Sign out</button></div>}</div><p className="admin-access-note">Provisioned project staff only. Prototype; no affiliation with a disaster-management authority. No public registration. {session&&'Session expires after 30 idle minutes or eight hours.'}</p>
    {checking&&<p role="status">Checking administrator session…</p>}
    {error&&<p role="alert" className="notice error">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {!checking&&!session&&<AdminLogin busy={busy} onSignIn={login}/>}
    {session&&<>
      {session.mode==='demonstration'&&<p role="alert" className="notice error"><strong>DEMONSTRATION ONLY — isolated database. These are not operational shelter assignments.</strong></p>}
      <nav aria-label="Administrator workspace" className="admin-tabs"><button type="button" aria-pressed={adminTab==='shelters'} onClick={()=>setAdminTab('shelters')}>Shelter workspace</button>{counts.attention>0&&<button type="button" className="admin-tab-badge" onClick={()=>{setAdminTab('shelters');setView('attention')}}>{counts.attention} {counts.attention===1?'shelter needs':'shelters need'} attention</button>}<button type="button" aria-pressed={adminTab==='notifications'} onClick={()=>setAdminTab('notifications')}>Telegram notifications</button><button type="button" aria-pressed={adminTab==='reports'} onClick={()=>setAdminTab('reports')}>Citizen reports</button></nav>
      {adminTab==='reports'&&<AdminReports request={request} active/>}
      <div hidden={adminTab!=='notifications'} className="admin-notifications"><AdminNotifications session={session} request={request} /></div>
      <div className="admin-management" hidden={adminTab!=='shelters'}>
      <div className="admin-information">
      <section className="panel admin-assignments"><div className="admin-section-head"><h2>Shelter assignments</h2><div className="admin-head-actions"><button className="secondary" disabled={busy} onClick={()=>operation(()=>load())}>Refresh assignments</button><button disabled={busy} onClick={()=>{setEditing(null);setForm(blank());setHistory(null);requestAnimationFrame(()=>formRef.current?.scrollIntoView?.({block:'start',behavior:'smooth'}))}}>Create new shelter</button></div></div>
        <div className="admin-counts" aria-label="Shelter overview"><span className="admin-count ok"><strong>{counts.visible}</strong> visible to public</span><span className={'admin-count '+(counts.attention?'bad':'ok')}><strong>{counts.attention}</strong> need attention</span><span className="admin-count muted"><strong>{counts.full}</strong> full</span><span className="admin-count muted"><strong>{counts.closed}</strong> closed</span></div>
        <div className="admin-filters"><div><label htmlFor="admin-view-filter">Show</label><select id="admin-view-filter" value={view} onChange={e=>setView(e.target.value)}><option value="all">All shelters</option><option value="attention">Needs attention</option><option value="public">Visible to public</option><option value="pending">Pending</option><option value="open">Open</option><option value="full">Full</option><option value="closed">Closed</option></select></div>
        <div><label htmlFor="admin-district-filter">Assignment district filter</label><select id="admin-district-filter" value={workspaceDistrict} onChange={e=>setWorkspaceDistrict(e.target.value)}><option value="">All districts</option>{districts.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></div></div>
        {!rows.length&&<p>No assignments in this directory. Use "Create new shelter" to add the first one.</p>}<p className="muted">{shownRows.length} shown · {rows.length} of {total} assignments loaded.</p>
        {workspaceDistrict&&<p role="status" className="muted">{shownRows.length} {workspace?.name} assignments on this page. Filtering applies to the loaded page; use pagination to inspect other assignments. {!workspace?.navigation_bounds&&'Public navigation bounds unavailable.'}</p>}
        <ul aria-label="Administrator shelter assignments" className="shelter-list admin-shelter-list">{shownRows.map(row=>{const st=states.get(row.id),used=Math.min(100,Math.round(100*row.occupancy/Math.max(1,row.capacity)));return <li key={row.id} className={'admin-shelter-card'+(editing===row.id?' selected':'')} data-tone={st.tone}>
          <div className="admin-shelter-head"><strong>{row.name}</strong><span className={'admin-status '+row.status}>{STATUS_NAMES[row.status]||row.status}</span></div>
          <p className="admin-visibility" data-tone={st.tone}><strong>{row.publicly_available?'Publicly available':'Unavailable to public'}</strong> · {st.label.replace(/^Visible to public$/,'shown on the Shelters page').replace(/^Hidden: /,'')}. {st.detail}.</p>
          <p className="muted">{row.district_name} · {row.occupancy}/{row.capacity} occupants · {row.capacity-row.occupancy} free</p>
          <div className="capacity-bar" role="img" aria-label={`${used}% occupied`}><span style={{width:used+'%'}}/></div>
          <p className="muted">Verified: {clock(row.verified_at)}. Updated: {clock(row.updated_at)}.</p>
          <div className="admin-card-actions">{st.attention&&row.status!=='closed'&&<button type="button" disabled={busy} onClick={()=>open(row,'verify')}>Re-verify</button>}<button type="button" className="secondary" disabled={busy} aria-label={'Edit '+row.name} onClick={()=>open(row)}>Edit</button><button type="button" className="secondary" disabled={busy} aria-label={'Audit '+row.name} onClick={()=>operation(async()=>{setHistory(await request('/api/admin/shelters/'+row.id+'/audit'))})}>History</button></div></li>})}</ul>
        {total>100&&<div className="admin-pager"><button className="secondary" disabled={busy||offset===0} onClick={()=>setOffset(n=>Math.max(0,n-100))}>Previous assignments</button><button className="secondary" disabled={busy||offset+100>=total} onClick={()=>setOffset(n=>n+100)}>Next assignments</button></div>}
        {history&&<div aria-label="Shelter audit history" className="admin-history"><h3>Audit history</h3><button type="button" className="link-button" onClick={()=>setHistory(null)}>Close history</button><ul>{history.events.map(event=><li key={event.id}>{clock(event.at)} · {event.action} by {event.admin_id} · {event.before?.status||'new'} → {event.after.status} · occupancy {event.before?.occupancy??'none'} → {event.after.occupancy}; capacity {event.before?.capacity??'none'} → {event.after.capacity}</li>)}</ul></div>}
      </section>
      <form ref={formRef} className="panel shelter-form" onSubmit={save} aria-label="Shelter assignment form"><div className="admin-section-head"><h2 ref={formHeading} tabIndex={-1}>{editing?`Edit: ${form.name||"shelter assignment"}`:'Create Pending shelter assignment'}</h2>{editing&&<button type="button" className="secondary" disabled={busy} onClick={()=>{setEditing(null);setForm(blank());setHistory(null)}}>Stop editing</button>}</div>
        {!editing&&<p className="admin-form-hint">New shelters are saved as Pending. After you verify the facility, edit it and set Open.</p>}
        <fieldset className="form-section"><legend>1. Facility identity and entrance</legend><label>Facility name<input required maxLength={200} value={form.name} onChange={e=>field('name',e.target.value)} /></label>
        <label>Facility address<textarea required maxLength={1000} value={form.address} onChange={e=>field('address',e.target.value)} /></label>
        <label htmlFor="shelter-district">Shelter district</label><select id="shelter-district" required value={form.district_id} onChange={e=>field('district_id',e.target.value)}><option value="">Choose district</option>{districts.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select>
        <p>District association is assigned by the administrator using NIC directory identities; independent current LGD reconciliation is unresolved.</p>
        <label>Entrance latitude<input type="number" step="any" min={-90} max={90} value={form.latitude} onChange={e=>field('latitude',e.target.value)} /></label>
        <label>Entrance longitude<input type="number" step="any" min={-180} max={180} value={form.longitude} onChange={e=>field('longitude',e.target.value)} /></label>
        <p className={'admin-entrance-status'+(entrance.length?' set':'')} role="status">{entrance.length?`Entrance pin set at ${Number(form.latitude).toFixed(5)}, ${Number(form.longitude).toFixed(5)} — shown on the map.`:'No entrance pin yet — click the exact entrance on the map, or type its coordinates.'}</p>
        {lookup&&<div className="admin-place-lookup" role="status" aria-live="polite">
          {lookup.status==='loading'&&<p>Looking up the place name, address and district for this point…</p>}
          {lookup.status==='outside'&&<p className="notice">{lookup.message}</p>}
          {lookup.status==='error'&&<p className="notice">Place lookup failed ({lookup.message}). Type the name, address and district manually.</p>}
          {lookup.status==='done'&&<>
            <p><strong>From the map point:</strong> {lookup.district?`District ${lookup.district.name}`:'District not found — choose it manually'}{lookup.data.name?` · ${lookup.data.name.value}`:lookup.data.nearby?` · nearest named place: ${lookup.data.nearby.value} (${lookup.data.nearby.distance_m} m away — is this the facility?)`:''}{lookup.data.address?` · ${lookup.data.address.value}`:''}</p>
            {lookup.notes.map(n=><p key={n} className="admin-place-note">{n}</p>)}
            <div className="admin-card-actions">
              {lookup.data.name&&form.name!==lookup.data.name.value&&<button type="button" className="secondary" onClick={()=>field('name',lookup.data.name.value)}>Use this name</button>}
              {!lookup.data.name&&lookup.data.nearby&&form.name!==lookup.data.nearby.value&&<button type="button" className="secondary" onClick={()=>field('name',lookup.data.nearby.value)}>Use “{lookup.data.nearby.value}” ({lookup.data.nearby.distance_m} m away)</button>}
              {lookup.data.address&&form.address!==lookup.data.address.value&&<button type="button" className="secondary" onClick={()=>field('address',lookup.data.address.value)}>Use this address</button>}
            </div>
            {lookup.data.messages.map(m=><p key={m} className="muted">{m}</p>)}
            <p className="muted">Suggestions only — check them on site. District: {lookup.district?lookup.data.district.source:'—'}. Name and address: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a>, ODbL 1.0, via Nominatim.</p>
          </>}
        </div>}
        <p className="muted">Placing a marker does not verify a facility. Leave both blank while Pending if unknown.</p>
        </fieldset><fieldset className="form-section"><legend>2. Capacity, facilities and contact</legend><label>Maximum capacity<input required type="number" min={1} max={100000} step={1} value={form.capacity} onChange={e=>field('capacity',e.target.value)} /></label>
        <label>Current occupancy<input required type="number" min={0} max={Number(form.capacity)||100000} step={1} value={form.occupancy} onChange={e=>field('occupancy',e.target.value)} /></label>
        {['water','toilets'].map(key=><div key={key}><label htmlFor={'shelter-'+key}>{key==='water'?'Water availability':'Toilets'}</label><select id={'shelter-'+key} value={form[key]} onChange={e=>field(key,e.target.value)}><option value="unknown">Unknown</option><option value="yes">Yes</option><option value="no">No</option></select></div>)}
        <label>Accessibility information<textarea maxLength={2000} value={form.accessibility} onChange={e=>field('accessibility',e.target.value)} /></label>
        <label>Contact information<input maxLength={200} value={form.contact} onChange={e=>field('contact',e.target.value)} /></label><label><input type="checkbox" checked={form.publish_contact} onChange={e=>field('publish_contact',e.target.checked)} />Approved for public contact disclosure</label>
        </fieldset><fieldset className="form-section"><legend>3. Availability and independent verification</legend><label htmlFor="shelter-status">Shelter status</label><select id="shelter-status" value={form.status} disabled={!editing} onChange={e=>field('status',e.target.value)}><option value="pending">Pending verification</option><option value="open">Open</option><option value="full">Full</option><option value="closed">Closed</option></select>
        <fieldset id="shelter-verification"><legend>Explicit verification — renew all confirmations for each Open/Full save</legend>{[['authorization','Facility is authorized for shelter use'],['entrance','This exact entrance has been independently verified'],['usability','Facility is currently usable'],['capacity','Capacity and current occupancy have been checked']].map(([key,label])=><label key={key}><input type="checkbox" checked={form.verification[key]} onChange={e=>verify(key,e.target.checked)} />{label}</label>)}<label>Verification evidence and method<textarea maxLength={2000} required={['open','full'].includes(form.status)} value={form.verification.evidence} onChange={e=>verify('evidence',e.target.value)} /></label></fieldset>
        <p>Changing facility identity, entrance, district, capacity, occupancy or usability details clears earlier confirmations and evidence. Review the latest values before confirming again.</p>
        </fieldset><fieldset className="form-section"><legend>4. Restrictions and internal notes</legend><label>Public operational restrictions<textarea maxLength={2000} value={form.restrictions} onChange={e=>field('restrictions',e.target.value)} /></label><label>Internal notes (not public)<textarea maxLength={2000} value={form.notes} onChange={e=>field('notes',e.target.value)} /></label>
        <p>Open requires spare capacity and all four confirmations. Verification expires after 24 hours; recheck actual conditions before renewal. Full, Closed, Pending and expired assignments are excluded from public destinations. Weather/AI predictions never assign shelters.</p></fieldset>
        <button disabled={busy||!districts.length}>{busy?'Saving…':'Save shelter assignment'}</button>
      </form>
      </div>
      <AdminEntranceMap entrance={entrance} selectedDistrictId={workspaceDistrict} onDistrict={row=>setWorkspaceDistrict(row?.id||'')} navigationBounds={workspace?.navigation_bounds} onSelect={point=>{setForm(f=>({...f,latitude:point.latitude.toFixed(6),longitude:point.longitude.toFixed(6),verification:{authorization:false,entrance:false,usability:false,capacity:false,evidence:''}}));void lookupPlace(point)}} />
      </div>
    </>}
  </Container>
}
