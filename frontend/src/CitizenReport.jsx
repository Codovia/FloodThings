import React,{useEffect,useRef,useState} from 'react'
import ShelterMap from './ShelterMap.jsx'
import GpsCamera, { placeLabel } from './GpsCamera.jsx'
import { preparePhoto, toBase64 } from './reportPhoto.js'
import ScreenTabs, { useWide } from './ScreenTabs.jsx'
import Popup from './Popup.jsx'
import { PageLink } from './AppNavigation.jsx'
import './Reports.css'
const newKey=()=>Array.from(crypto.getRandomValues(new Uint8Array(32)),n=>n.toString(16).padStart(2,'0')).join('')
const utcLocal=(ms=Date.now())=>new Date(ms-new Date(ms).getTimezoneOffset()*60000).toISOString().slice(0,16)
const EVENT_NAMES={flooding:'Flooding',waterlogging:'Waterlogging',drainage_blockage:'Drainage blockage',other:'Other'}
// Optional observation details, sent as a fixed first line of the description so they can be parsed later.
export const DEPTHS={ankle:'ankle-deep (up to about 15 cm)',knee:'knee-deep (about 50 cm)',waist:'waist-deep (about 1 m)',above_waist:'above the waist (over 1 m)'}
export const ROADS={passable:'passable by people and vehicles',large_vehicles_only:'only large vehicles can pass',impassable:'not passable'}
export function detailLine(depth,road){const parts=[depth&&`Water depth: ${DEPTHS[depth]}`,road&&`Road: ${ROADS[road]}`].filter(Boolean);return parts.length?`[${parts.join(' | ')}]`:''}
const RADII=[[10,'Exact spot (±10 m)'],[50,'Same street (±50 m)'],[250,'Nearby (±250 m)']]
const istTime=v=>new Date(v).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'})+' IST'
export default function CitizenReport({navigate=null,suggestedSpot=null,onSpotUsed=null}={}){
 const [gps,setGps]=useState(null),[locating,setLocating]=useState(false),[message,setMessage]=useState(null),[error,setError]=useState(null),[busy,setBusy]=useState(false),[receipt,setReceipt]=useState(null)
 const [description,setDescription]=useState(''),[type,setType]=useState(''),[observed,setObserved]=useState(utcLocal),[consent,setConsent]=useState(false),[rights,setRights]=useState(false),[metadata,setMetadata]=useState(false),[photo,setPhoto]=useState(null),[review,setReview]=useState(false)
 const [cameraOpen,setCameraOpen]=useState(false),[preparing,setPreparing]=useState(false),[depth,setDepth]=useState(''),[road,setRoad]=useState(''),[near,setNear]=useState(null)
 const narrow=!useWide()
 const [step,setStep]=useState('where')
 function goStep(id){setStep(id)}
 const [manual,setManual]=useState(false),[manualRadius,setManualRadius]=useState(''),[manualCoordinates,setManualCoordinates]=useState({latitude:'',longitude:''})
 const [locNote,setLocNote]=useState(null)
 const reviewHeading=useRef(null),receiptHeading=useRef(null),errorSummary=useRef(null)
 useEffect(()=>{if(review)reviewHeading.current?.focus()},[review])
 useEffect(()=>{if(receipt)receiptHeading.current?.focus()},[receipt])
 useEffect(()=>{if(error)errorSummary.current?.focus()},[error])
 const job=useRef(null),pending=useRef(null),mounted=useRef(true),gallery=useRef(null)
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;clearTimeout(job.current);job.current=null;pending.current?.abort()}},[])
 function change(fn){if(busy||receipt)return;fn();setReview(false);submission.current=null}
 const submission=useRef(null)
 // Automatic on opening the page (the browser asks permission first); manual retries use the button.
 // Nothing leaves the device until the citizen reviews and submits.
 function location(auto=false){
  const fail=text=>auto?setLocNote(text):setError(text)
  if(!navigator.geolocation||!window.isSecureContext){fail('GPS requires a supported browser and secure connection. Choose the spot on the map instead. No network estimate will be submitted.');return}
  setManual(false);setGps(null);setError(null);setLocNote(null);setLocating(true);setReview(false);submission.current=null
  const token=setTimeout(()=>{if(job.current!==token)return;job.current=null;setLocating(false);fail('GPS timed out. Try again outdoors, or choose the spot on the map.')},10000);job.current=token
  navigator.geolocation.getCurrentPosition(result=>{
   if(!mounted.current||job.current!==token)return;clearTimeout(token);job.current=null;setLocating(false)
   const c=result.coords
   if(!Number.isFinite(c.latitude)||Math.abs(c.latitude)>90||!Number.isFinite(c.longitude)||Math.abs(c.longitude)>180||!Number.isFinite(c.accuracy)||c.accuracy<0||!Number.isFinite(result.timestamp)||Date.now()-result.timestamp>60000||result.timestamp>Date.now()+1000){fail('Your device gave an old or invalid location, so it was not used. Press "Use my current location" to try again, or choose the spot on the map.');return}
   setGps({latitude:c.latitude,longitude:c.longitude,accuracy_m:c.accuracy,position_source:'BROWSER_GPS',gps_at:new Date(result.timestamp).toISOString()});setNear(null);placeLabel({latitude:c.latitude,longitude:c.longitude}).then(label=>{if(mounted.current)setNear(label)}).catch(()=>{})
  },()=>{if(!mounted.current||job.current!==token)return;clearTimeout(token);job.current=null;setLocating(false);fail('Location is off or was not allowed. No location was guessed — allow location and press "Use my current location", or choose the spot on the map.')},{enableHighAccuracy:true,timeout:10000,maximumAge:0})
 }
 // A spot handed over from Home's map ("Report flooding here") is a user-chosen spot, never a GPS fix.
 function applySpot(spot){setManual(true);setNear(null);setGps({latitude:spot.latitude,longitude:spot.longitude,accuracy_m:null,position_source:'USER_SELECTED_MAP',gps_at:null,location_selected_at:new Date().toISOString()});setManualCoordinates({latitude:spot.latitude.toFixed(6),longitude:spot.longitude.toFixed(6)});setMessage(`Spot taken from the Home map (${spot.name}). Choose how sure you are of the spot, or use your current location instead.`)}
 useEffect(()=>{if(suggestedSpot){applySpot(suggestedSpot);onSpotUsed?.()}else location(true)},[])
 function enableManual(){
  if(busy||receipt)return
  clearTimeout(job.current);job.current=null;setLocating(false);setManual(true);setGps(null);setNear(null);setReview(false);setError(null);submission.current=null
  setLocNote(null);setMessage('Tap the map where the problem is, then choose how sure you are of the spot. This is recorded as a spot you chose, not a GPS fix.')
 }
 function selectManual(point){
  if(!manual||busy||receipt)return
  if(!Number.isFinite(point.latitude)||Math.abs(point.latitude)>90||!Number.isFinite(point.longitude)||Math.abs(point.longitude)>180){setError('Enter valid latitude and longitude.');return}
  change(()=>{setGps({...point,accuracy_m:Number(manualRadius)||null,position_source:'USER_SELECTED_MAP',gps_at:null,location_selected_at:new Date().toISOString()});setManualCoordinates({latitude:point.latitude.toFixed(6),longitude:point.longitude.toFixed(6)});setError(null)})
 }
 async function selectPhoto(event){
  const file=event.target.files?.[0];event.target.value='';if(!file)return
  if(busy||receipt)return;setPreparing(true)
  try{const ready=await preparePhoto(file);const base64=await toBase64(ready.blob);if(!mounted.current)return
   change(()=>{setPhoto({name:file.name,mime:ready.mime,base64,resized:ready.resized});if(ready.resized)setMetadata(false);setError(null)})
  }catch(e){if(mounted.current)setError(e.message)}finally{if(mounted.current)setPreparing(false)}
 }
 // GPS camera: the photo, its own GPS fix and the capture time are recorded together.
 function acceptGpsPhoto(shot){
  if(busy||receipt)return
  clearTimeout(job.current);job.current=null;setLocating(false);setCameraOpen(false)
  const local=new Date(Date.parse(shot.capture.captured_at)-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16)
  change(()=>{setMetadata(false);setPhoto({name:shot.name,mime:shot.mime,base64:shot.base64,capture:shot.capture,fix:shot.fix,preview:shot.preview,place:shot.place});setManual(false);setNear(shot.place||null);setGps({latitude:shot.fix.latitude,longitude:shot.fix.longitude,accuracy_m:shot.fix.accuracy_m,position_source:'BROWSER_GPS',gps_at:shot.fix.gps_at});setObserved(local);setError(null)})
  setMessage(`GPS photo recorded · location ±${Math.round(shot.fix.accuracy_m)} m and time filled in.${shot.fix.accuracy_m>100?' Coarse location will be flagged for the moderator.':''}`)
 }
 const position=manual&&gps?{...gps,accuracy_m:Number(manualRadius)}:gps
 const canReview=!!type&&!preparing&&!!position&&Number.isFinite(position.accuracy_m)&&position.accuracy_m>=0&&(!manual||(manualRadius!==''&&position.accuracy_m>=1&&position.accuracy_m<=10000000))&&description.trim().length>=10&&consent&&(!photo||rights)&&Number.isFinite(Date.parse(observed))&&!locating
 async function submit(event){
  event.preventDefault();if(!canReview||busy||!review)return
  if(Date.now()-Date.parse(position.gps_at||position.location_selected_at)>600000){setError('Location evidence is older than ten minutes. Select a fresh point or acquire GPS and review again.');setReview(false);return}
  if(!submission.current)submission.current={request_id:crypto.randomUUID(),withdrawal_secret:newKey(),event_type:type,description:[detailLine(depth,road),description.trim()].filter(Boolean).join(' '),observed_at:new Date(observed).toISOString(),...position,consent,image_rights:rights,metadata_consent:metadata&&!!photo&&!photo.resized&&!photo.capture,...(photo?{photo_base64:photo.base64,photo_mime:photo.mime}:{}),...(photo?.capture&&!manual&&position?.position_source==='BROWSER_GPS'&&position.gps_at===photo.fix?.gps_at?{capture:photo.capture}:{})}
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
 function newReport(){if(busy)return;setReceipt(null);setReview(false);setType('');setDescription('');setDepth('');setRoad('');setPhoto(null);setRights(false);setMetadata(false);setConsent(false);setGps(null);setNear(null);setManual(false);setManualRadius('');setManualCoordinates({latitude:'',longitude:''});setObserved(utcLocal());setError(null);setMessage(null);submission.current=null;setStep('where');location(true)}
 const mapBlock=<div className="report-map-block"><p className="report-map-hint" aria-live="polite">{gps?(manual?'Spot selected. Tap again to move it.':'This is where you are now. The circle shows GPS accuracy.'):manual?'Tap the map where the problem is.':locating?'Finding your location…':'Use your current location, or choose the spot on the map.'}</p><ShelterMap points={gps?[{...gps,showAccuracy:!manual,name:manual?`Spot you chose (±${manualRadius||'?'} m)`:`You are here (±${Math.round(gps.accuracy_m)} m)`}]:[]} onSelect={manual?selectManual:null} pointZoom={17} label="Citizen report location map"/></div>
 return <div className="report-workspace"><section className="panel report-form"><h2>Report local flooding or blocked drainage</h2><p>Your report goes privately to project administrators. It does not call for help or create a public warning.</p>
 <p className="report-emergency"><strong>In danger now?</strong> Call <a href="tel:112">112</a> or the Karnataka emergency centre <a href="tel:0801070">080-1070</a>. This form does not send help.</p>
 {cameraOpen&&<GpsCamera onCapture={acceptGpsPhoto} onClose={()=>setCameraOpen(false)}/>}
 {error&&<p role="alert" className="notice error" ref={errorSummary} tabIndex={-1}>{error}</p>}{message&&<p role="status">{message}</p>}
 {receipt?<>{receipt.demonstration&&<p role="alert">DEMONSTRATION ONLY — isolated test report, not an actual incident.</p>}<h2 className="confirmation-title">{receipt.state==='WITHDRAWN'?'Evidence withdrawn':'Report received for private review'}</h2><h3 ref={receiptHeading} tabIndex={-1}>Report {receipt.id}</h3><p className="report-status">Status: <strong>{receipt.state==='WITHDRAWN'?'Withdrawn':'Received — waiting for review by a project administrator'}</strong></p><p className="muted">{receipt.source} · {receipt.state}. Receipt: {new Date(receipt.received_at).toLocaleString('en-IN')}.</p><h3>What happens next</h3><p>{receipt.state==='WITHDRAWN'?'Private photo and location have been removed. The status and reviewer audit remain; this page does not provide a recoverable withdrawal key.':'Project administrators can review this evidence. Submission does not confirm an incident or guarantee a response. No emergency dispatch, public warning or training label is created.'}</p>{receipt.state!=='WITHDRAWN'&&<><p>Keep this page open to withdraw your private evidence. Reloading clears the withdrawal key; contact the project administrator if it is lost.</p><button disabled={busy} className="secondary" onClick={withdraw}>Withdraw private evidence</button></>}<div className="report-next"><button type="button" disabled={busy} onClick={newReport}>Report another incident</button>{navigate&&<p className="report-after"><PageLink to="/shelters" navigate={navigate}>Find a shelter</PageLink> · <PageLink to="/" navigate={navigate}>Back to Home</PageLink></p>}<p className="muted">Starting a new report removes the option to withdraw this one from this page.</p></div></>:<form onSubmit={submit}>
 <fieldset disabled={busy} className="report-fields"><legend className="visually-hidden">Your incident report</legend>
 {/* One-screen rule: the form is four steps instead of one long page. All checks are unchanged. */}
 <ScreenTabs mode="always" className="report-steps" label="Report steps" active={step} onActive={goStep} tabs={[
  {id:'where',label:'1 Location',content:<><fieldset className="report-location"><legend className="step-legend">1. Your location</legend><p className="report-location-status" role="status" aria-live="polite">{locating?'Finding your location…':gps?(manual?<><strong>Spot you chose on the map</strong>{manualRadius?` · within about ${manualRadius} m`:' · now choose how sure you are'}</>:<><strong>{near?`You are near ${near}`:'Your location was found'}</strong> · GPS accuracy ±{Math.round(gps.accuracy_m)} m{gps.accuracy_m>100?' (coarse — the reviewer will see this)':''}</>):locNote||'Your location is not set yet.'}</p>
 <p className="muted">Problem somewhere else? Choose the spot on the map. Nothing is sent until you submit.{gps&&!manual&&' Town name from BigDataCloud.'}</p>
 <div className="report-actions"><button type="button" disabled={locating} className={gps&&!manual?'secondary':''} onClick={()=>location()}>{locating?'Finding your location…':gps&&!manual?'Update my location':'Use my current location'}</button><button type="button" className={manual?'':'secondary'} onClick={enableManual}>Choose the spot on the map</button></div>{manual&&<fieldset className="report-manual"><legend>Manual incident location</legend><div className="report-chips" role="group" aria-label="How sure are you of the spot?">{RADII.map(([m,label])=><button type="button" key={m} className={'chip'+(Number(manualRadius)===m?' active':'')} aria-pressed={Number(manualRadius)===m} onClick={()=>change(()=>setManualRadius(String(m)))}>{label}</button>)}</div><p className="report-manual-more"><Popup label="Enter coordinates or a custom radius" title="Manual incident location">{close=><><p>Enter the location you observed. The radius is your estimate, not measured GPS accuracy.</p><label>Incident latitude<input type="number" step="any" min={-90} max={90} value={manualCoordinates.latitude} onChange={e=>change(()=>{setManualCoordinates(v=>({...v,latitude:e.target.value}));setGps(null)})}/></label><label>Incident longitude<input type="number" step="any" min={-180} max={180} value={manualCoordinates.longitude} onChange={e=>change(()=>{setManualCoordinates(v=>({...v,longitude:e.target.value}));setGps(null)})}/></label><label>Estimated uncertainty radius (m)<input type="number" min={1} max={10000000} value={manualRadius} onChange={e=>change(()=>setManualRadius(e.target.value))}/></label><button type="button" disabled={manualCoordinates.latitude===''||manualCoordinates.longitude===''} onClick={()=>{selectManual({latitude:Number(manualCoordinates.latitude),longitude:Number(manualCoordinates.longitude)});close()}}>Place manual incident point</button></>}</Popup></p></fieldset>}
 {narrow&&mapBlock}
</fieldset>
 <div className={'gps-photo-card'+(photo?.capture?' done':'')}><div><h3>{photo?.capture?'GPS photo recorded':'Fastest: take a GPS photo'}</h3>
  {photo?.capture?<p>{photo.place?photo.place+' · ':''}±{Math.round(photo.fix.accuracy_m)} m · {new Date(photo.capture.captured_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})} IST</p>:<p>Opens the camera here and records the photo, its exact location and the time together.</p>}</div>
  {photo?.capture&&photo.preview&&<img src={photo.preview} alt="Your GPS photo" className="gps-photo-thumb"/>}
  <button type="button" onClick={()=>setCameraOpen(true)}>{photo?.capture?'Retake GPS photo':'Open GPS camera'}</button></div>
 <div className="report-step-nav"><span/><button type="button" onClick={()=>goStep('details')}>Next: details ›</button></div></>},
  {id:'details',label:'2 Details',content:<><fieldset><legend className="step-legend">2. Describe the incident</legend><fieldset className="report-types"><legend>What is the problem?</legend>{Object.entries(EVENT_NAMES).map(([k,v])=><label key={k} className={'report-type'+(type===k?' active':'')}><input type="radio" name="event-type" value={k} checked={type===k} onChange={()=>change(()=>setType(k))}/>{v}</label>)}</fieldset>
 <label>What did you see?<textarea minLength={10} maxLength={1900} placeholder="For example: Water across the main road near the bus stand, rising since 6 pm." required value={description} onChange={e=>change(()=>setDescription(e.target.value))}/></label>
 <label>When did you observe it? (your device's local time)<input required type="datetime-local" value={observed} onChange={e=>change(()=>setObserved(e.target.value))}/></label>
 <div className="report-chips" role="group" aria-label="Quick time">{[[0,'Just now'],[15,'15 min ago'],[60,'1 hour ago'],[180,'3 hours ago']].map(([m,label])=><button type="button" key={m} className="chip" onClick={()=>change(()=>setObserved(utcLocal(Date.now()-m*60000)))}>{label}</button>)}</div>
 {['flooding','waterlogging','other'].includes(type)&&<div className="report-details">
  <label>How deep was the water? (optional)<select value={depth} onChange={e=>change(()=>setDepth(e.target.value))}><option value="">Not sure</option>{Object.entries(DEPTHS).map(([k,v])=><option key={k} value={k}>{v[0].toUpperCase()+v.slice(1)}</option>)}</select></label>
  <label>Could the road be used? (optional)<select value={road} onChange={e=>change(()=>setRoad(e.target.value))}><option value="">Not sure / no road</option>{Object.entries(ROADS).map(([k,v])=><option key={k} value={k}>{v[0].toUpperCase()+v.slice(1)}</option>)}</select></label>
 </div>}
  </fieldset>
 <div className="report-step-nav"><button type="button" className="secondary" onClick={()=>goStep('where')}>‹ Back</button><button type="button" onClick={()=>goStep('photo')}>Next: photo & consent ›</button></div></>},
  {id:'photo',label:'3 Photo',content:<><fieldset><legend className="step-legend">3. Photo (optional)</legend><p>Add a photo from your gallery, or use the GPS camera in step 1. Avoid faces, number plates and private details. Large photos are made smaller on your device before sending.</p><input hidden ref={gallery} type="file" accept="image/jpeg,image/png" onChange={selectPhoto}/>
 <div className="report-actions"><button type="button" className="secondary" disabled={preparing} onClick={()=>gallery.current.click()}>{preparing?'Preparing photo…':'Choose from gallery'}</button>{photo&&<button type="button" onClick={()=>change(()=>setPhoto(null))}>Remove photo</button>}</div>{photo&&<img className="report-photo-preview" src={photo.preview||`data:${photo.mime};base64,${photo.base64}`} alt="Selected photo preview"/>}{photo&&!photo.capture&&<p>Selected: {photo.name}.{photo.resized&&' It was made smaller to fit the 10-megapixel limit, so its own embedded time and location could not be kept.'}</p>}
 {photo&&<><label><input type="checkbox" checked={rights} onChange={e=>change(()=>setRights(e.target.checked))}/>I own or have permission to upload this photo for private review.</label>{!photo.resized&&!photo.capture&&<label><input type="checkbox" checked={metadata} onChange={e=>change(()=>setMetadata(e.target.checked))}/>Allow private extraction of embedded capture time/GPS if present and retention of the original photo for seven days.</label>}</>}
 
 
 </fieldset>
 
 <div className="report-step-nav"><button type="button" className="secondary" onClick={()=>goStep('details')}>‹ Back</button><button type="button" onClick={()=>goStep('review')}>Next: consent & review ›</button></div></>},
  {id:'review',label:'4 Review',content:review?<div className="report-review"><h3 ref={reviewHeading} tabIndex={-1}>4. Review before submission</h3><p><strong>{EVENT_NAMES[type]}</strong> · {istTime(observed)} · {manual?'User-selected point; estimated uncertainty':'GPS accuracy'} {Math.round(position.accuracy_m)} m.</p>{detailLine(depth,road)&&<p>{detailLine(depth,road)}</p>}<p>{description}</p>{!manual&&near&&<p>Near {near}.</p>}<p>Incident point: {position.latitude.toFixed(5)}, {position.longitude.toFixed(5)}. Confirm this is where you observed the incident.</p>{photo&&<img className="report-photo-preview small" src={photo.preview||`data:${photo.mime};base64,${photo.base64}`} alt="Photo to be submitted"/>}<p>{photo?'One private photo. Only actual decoded metadata is extracted.':'No photo attached.'} This remains USER_REPORTED until moderation.</p><button type="submit">Submit for private review</button><button type="button" onClick={()=>setReview(false)}>Edit report</button></div>:<><fieldset className="report-consent"><legend className="step-legend">4. Consent and review</legend><label><input type="checkbox" checked={consent} onChange={e=>change(()=>setConsent(e.target.checked))}/>I consent to private admin review of this report (description and location kept for 30 days; photo for seven days).</label>
 <p className="report-consent-terms"><Popup label="Privacy terms" title="Privacy terms"><p>Only project administrators review your description, location and optional sanitized photo. They are not published and not used to train any model. A record of the report's status, reviewer and reason is kept. You can withdraw your report while this page stays open.</p></Popup></p></fieldset>
 <p id="report-readiness" role="status" className="form-readiness">{canReview?'Ready to review. Nothing is sent until you submit.':'Before review: '+[!type&&'choose what the problem is',description.trim().length<10&&'describe what you saw (at least 10 characters)',!position&&'set your location',manual&&(!manualRadius||!Number.isFinite(Number(manualRadius))||Number(manualRadius)<1||Number(manualRadius)>10000000)&&'provide a valid uncertainty radius',!Number.isFinite(Date.parse(observed))&&'enter a valid observation time',locating&&'wait for your location or choose the spot on the map',preparing&&'wait for the photo to be prepared',!consent&&'confirm private review consent',photo&&!rights&&'confirm photo upload permission'].filter(Boolean).join('; ')+'.'}</p>
 <div className="report-step-nav"><button type="button" className="secondary" onClick={()=>goStep('photo')}>‹ Back</button><button type="button" disabled={!canReview} aria-describedby="report-readiness" onClick={()=>{if(!manual&&position?.gps_at&&!photo?.capture&&Date.now()-Date.parse(position.gps_at)>540000){location();setMessage('Your location was more than 9 minutes old, so it is being updated. Check it, then press Review report again.');return}setReview(true);setStep('review')}}>Review report</button></div></>},
 ]}/>
</fieldset></form>}
 </section>{!narrow&&<section className="panel" id="report-location-map"><h2>Your reported location</h2>{mapBlock}<p className="muted">Only project administrators see this location. It shows where you reported the incident; it does not confirm flooding or road closures.</p></section>}</div>
}
