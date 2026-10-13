import React,{useEffect,useRef,useState} from 'react'
import ShelterMap from './ShelterMap.jsx'
import './Reports.css'
const newKey=()=>Array.from(crypto.getRandomValues(new Uint8Array(32)),n=>n.toString(16).padStart(2,'0')).join('')
const utcLocal=()=>{const date=new Date();return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16)}
export default function CitizenReport(){
 const [gps,setGps]=useState(null),[locating,setLocating]=useState(false),[message,setMessage]=useState(null),[error,setError]=useState(null),[busy,setBusy]=useState(false),[receipt,setReceipt]=useState(null)
 const [description,setDescription]=useState(''),[type,setType]=useState('waterlogging'),[observed,setObserved]=useState(utcLocal),[consent,setConsent]=useState(false),[rights,setRights]=useState(false),[metadata,setMetadata]=useState(false),[photo,setPhoto]=useState(null),[review,setReview]=useState(false)
 const [manual,setManual]=useState(false),[manualRadius,setManualRadius]=useState(''),[manualCoordinates,setManualCoordinates]=useState({latitude:'',longitude:''})
 const job=useRef(null),pending=useRef(null),mounted=useRef(true),gallery=useRef(null),camera=useRef(null)
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;clearTimeout(job.current);job.current=null;pending.current?.abort()}},[])
 function change(fn){if(busy||receipt)return;fn();setReview(false);submission.current=null}
 const submission=useRef(null)
 function location(){
  if(!navigator.geolocation||!window.isSecureContext){setError('GPS requires a supported browser and secure connection. No network estimate will be submitted.');return}
  setManual(false);setGps(null);setError(null);setLocating(true);setReview(false);submission.current=null
  const token=setTimeout(()=>{if(job.current!==token)return;job.current=null;setLocating(false);setError('GPS timed out. Try again outdoors or submit later.')},10000);job.current=token
  navigator.geolocation.getCurrentPosition(result=>{
   if(!mounted.current||job.current!==token)return;clearTimeout(token);job.current=null;setLocating(false)
   const c=result.coords
   if(!Number.isFinite(c.latitude)||Math.abs(c.latitude)>90||!Number.isFinite(c.longitude)||Math.abs(c.longitude)>180||!Number.isFinite(c.accuracy)||c.accuracy<0||!Number.isFinite(result.timestamp)||Date.now()-result.timestamp>60000||result.timestamp>Date.now()+1000){setError('GPS result invalid; try again.');return}
   setGps({latitude:c.latitude,longitude:c.longitude,accuracy_m:c.accuracy,position_source:'BROWSER_GPS',gps_at:new Date(result.timestamp).toISOString()});setMessage(`GPS acquired · uncertainty ±${Math.round(c.accuracy)} m. ${c.accuracy>100?'Coarse location will be flagged for the moderator.':''}`)
  },()=>{if(!mounted.current||job.current!==token)return;clearTimeout(token);job.current=null;setLocating(false);setError('GPS unavailable or permission denied. No location was guessed.')},{enableHighAccuracy:true,timeout:10000,maximumAge:0})
 }
 function enableManual(){
  if(busy||receipt)return
  clearTimeout(job.current);job.current=null;setLocating(false);setManual(true);setGps(null);setReview(false);setError(null);submission.current=null
  setMessage('Select the incident point on the map or enter coordinates. Provide your estimated uncertainty; this is a user-selected location, not a GPS fix.')
 }
 function selectManual(point){
  if(!manual||busy||receipt)return
  if(!Number.isFinite(point.latitude)||Math.abs(point.latitude)>90||!Number.isFinite(point.longitude)||Math.abs(point.longitude)>180){setError('Enter valid latitude and longitude.');return}
  change(()=>{setGps({...point,accuracy_m:Number(manualRadius)||null,position_source:'USER_SELECTED_MAP',gps_at:null,location_selected_at:new Date().toISOString()});setManualCoordinates({latitude:String(point.latitude),longitude:String(point.longitude)});setError(null)})
 }
 async function selectPhoto(event){
  const file=event.target.files?.[0];event.target.value='';if(!file)return
  if(!['image/jpeg','image/png'].includes(file.type)||file.size>5*1024*1024){setError('Choose one JPEG/PNG photo up to 5 MiB.');return}
  const reader=new FileReader();reader.onload=()=>{if(mounted.current)change(()=>{setPhoto({name:file.name,mime:file.type,base64:String(reader.result).split(',')[1]});setError(null)})};reader.onerror=()=>{if(mounted.current)setError('Photo could not be read.')};reader.readAsDataURL(file)
 }
 const position=manual&&gps?{...gps,accuracy_m:Number(manualRadius)}:gps
 const canReview=!!position&&Number.isFinite(position.accuracy_m)&&position.accuracy_m>=0&&(!manual||(manualRadius!==''&&position.accuracy_m>=1&&position.accuracy_m<=10000000))&&description.trim().length>=10&&consent&&(!photo||rights)&&Number.isFinite(Date.parse(observed))&&!locating
 async function submit(event){
  event.preventDefault();if(!canReview||busy||!review)return
  if(Date.now()-Date.parse(position.gps_at||position.location_selected_at)>600000){setError('Location evidence is older than ten minutes. Select a fresh point or acquire GPS and review again.');setReview(false);return}
  if(!submission.current)submission.current={request_id:crypto.randomUUID(),withdrawal_secret:newKey(),event_type:type,description:description.trim(),observed_at:new Date(observed).toISOString(),...position,consent,image_rights:rights,metadata_consent:metadata,...(photo?{photo_base64:photo.base64,photo_mime:photo.mime}:{})}
  setBusy(true);setError(null);const controller=new AbortController();pending.current=controller;const timeout=setTimeout(()=>controller.abort(),15000)
  try{const response=await fetch('/api/reports',{method:'POST',headers:{'Content-Type':'application/json','X-FloodPulse-Report':'1'},body:JSON.stringify(submission.current),signal:controller.signal});const body=await response.json();if(!mounted.current)return;if(!response.ok)throw Error(body.detail||'Report not recorded')
   setReceipt(body);submission.current={withdrawal_secret:submission.current.withdrawal_secret};setPhoto(null);setMessage(body.message)
  }catch(e){if(mounted.current)setError(e.name==='AbortError'?'Submission timed out; it may have completed. Retry unchanged to use the same submission token.':e.message)}finally{clearTimeout(timeout);if(mounted.current)setBusy(false)}
 }
 async function withdraw(){
  if(busy||!receipt||!submission.current)return;setBusy(true);setError(null)
  const controller=new AbortController();pending.current=controller;const timeout=setTimeout(()=>controller.abort(),15000)
  try{const response=await fetch(`/api/reports/${receipt.id}/withdraw`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({withdrawal_secret:submission.current.withdrawal_secret}),signal:controller.signal});const body=await response.json();if(!response.ok)throw Error(body.detail||'Withdrawal failed');if(mounted.current){setReceipt({...receipt,...body});setGps(null);setDescription('');submission.current=null;setMessage('Private photo and location removed. Status audit remains.')}}catch(e){if(mounted.current)setError(e.name==='AbortError'?'Withdrawal timed out; retry to check its result.':e.message)}finally{clearTimeout(timeout);if(mounted.current)setBusy(false)}
 }
 return <div className="report-workspace"><section className="panel report-form"><h2>Report local flooding or blocked drainage</h2><p>This is private citizen evidence for project administrators. It does not request emergency dispatch or create an official warning. Avoid faces, vehicle plates, private addresses and contact details.</p>
 {error&&<p role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
 {receipt?<>{receipt.demonstration&&<p role="alert">DEMONSTRATION ONLY — isolated test report, not an actual incident.</p>}<h3>Report {receipt.id}</h3><p>{receipt.source} · {receipt.state}. Receipt: {new Date(receipt.received_at).toLocaleString('en-IN')}.</p><p>Keep this page open to withdraw your private evidence. Reloading clears the withdrawal key; contact the project administrator if it is lost.</p>{receipt.state!=='WITHDRAWN'&&<button disabled={busy} onClick={withdraw}>Withdraw private evidence</button>}</>:<form onSubmit={submit}>
 <fieldset disabled={busy}><legend>Incident details</legend><label>Event type<select value={type} onChange={e=>change(()=>setType(e.target.value))}><option value="flooding">Flooding</option><option value="waterlogging">Waterlogging</option><option value="drainage_blockage">Drainage blockage</option><option value="other">Other</option></select></label>
 <label>What did you see?<textarea minLength={10} maxLength={2000} required value={description} onChange={e=>change(()=>setDescription(e.target.value))}/></label>
 <label>When did you observe it? (your device's local time)<input required type="datetime-local" value={observed} onChange={e=>change(()=>setObserved(e.target.value))}/></label>
 <button type="button" disabled={locating} onClick={location}>{locating?'Acquiring GPS…':'Use GPS for this report'}</button><button type="button" onClick={enableManual}>Select location manually</button>{manual&&<fieldset><legend>Manual incident location</legend><p>Click the map or enter the location you observed. The radius below is your estimate, not measured GPS accuracy.</p><label>Incident latitude<input type="number" step="any" min={-90} max={90} value={manualCoordinates.latitude} onChange={e=>change(()=>{setManualCoordinates(v=>({...v,latitude:e.target.value}));setGps(null)})}/></label><label>Incident longitude<input type="number" step="any" min={-180} max={180} value={manualCoordinates.longitude} onChange={e=>change(()=>{setManualCoordinates(v=>({...v,longitude:e.target.value}));setGps(null)})}/></label><label>Estimated uncertainty radius (m)<input type="number" min={1} max={10000000} value={manualRadius} onChange={e=>change(()=>setManualRadius(e.target.value))}/></label><button type="button" disabled={manualCoordinates.latitude===''||manualCoordinates.longitude===''} onClick={()=>selectManual({latitude:Number(manualCoordinates.latitude),longitude:Number(manualCoordinates.longitude)})}>Place manual incident point</button></fieldset>}{gps&&<p>Submitted point: {gps.latitude.toFixed(5)}, {gps.longitude.toFixed(5)} · {manual?`user-estimated uncertainty ${manualRadius||'not supplied'} m`:`GPS accuracy ±${Math.round(gps.accuracy_m)} m`}. This is your reported position, not verified flood extent.</p>}
 <input hidden ref={gallery} type="file" accept="image/jpeg,image/png" onChange={selectPhoto}/><input hidden ref={camera} type="file" accept="image/jpeg,image/png" capture="environment" onChange={selectPhoto}/>
 <div className="report-actions"><button type="button" onClick={()=>gallery.current.click()}>Choose photo</button><button type="button" onClick={()=>camera.current.click()}>Take photo</button>{photo&&<button type="button" onClick={()=>change(()=>setPhoto(null))}>Remove photo</button>}</div>{photo&&<p>Selected: {photo.name}. Optional; JPEG/PNG up to 5 MiB, ten megapixels. Camera/gallery opens only after your action.</p>}
 {photo&&<><label><input type="checkbox" checked={rights} onChange={e=>change(()=>setRights(e.target.checked))}/>I own or have permission to upload this photo for private review.</label><label><input type="checkbox" checked={metadata} onChange={e=>change(()=>setMetadata(e.target.checked))}/>Allow private extraction of embedded capture time/GPS if present and retention of the original photo for seven days.</label></>}
 <label><input type="checkbox" checked={consent} onChange={e=>change(()=>setConsent(e.target.checked))}/>I consent to private admin review of this description and location for 30 days, and an optional sanitized photo for seven days. No public publication or model training is authorized; status/reviewer/reason audits are retained. I can withdraw while this page remains open.</label>
 {review?<div className="report-review"><h3>Review before submission</h3><p>{type.replaceAll('_',' ')} · {new Date(observed).toLocaleString()} · {manual?'User-selected point; estimated uncertainty':'GPS accuracy'} {Math.round(position.accuracy_m)} m.</p><p>{description}</p><p>{photo?'One private photo. Only actual decoded metadata is extracted.':'No photo attached.'} This remains USER_REPORTED until moderation.</p><button type="submit">Submit for private review</button><button type="button" onClick={()=>setReview(false)}>Edit report</button></div>:<button type="button" disabled={!canReview} onClick={()=>setReview(true)}>Review report</button>}
 </fieldset></form>}
 </section><section className="panel"><h2>Your reported location</h2><ShelterMap points={gps?[{...gps,name:manual?'USER_SELECTED_MAP · estimated uncertainty':'USER_REPORTED GPS · ±'+Math.round(gps.accuracy_m)+' m'}]:[]} onSelect={manual?selectManual:null} label="Citizen report location map"/><p>Map position is private report evidence. Manual selections record their source and user-estimated uncertainty separately from browser GPS. No flooded area, precise town identity or road closure is inferred. Photo analysis currently extracts genuine format/dimensions and consented EXIF only; a vision model is unavailable.</p></section></div>
}
