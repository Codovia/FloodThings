import React,{useEffect,useRef,useState} from 'react'
import OfficialHelp from './OfficialHelp.jsx'
import { PageLink } from './AppNavigation.jsx'
import ScreenTabs from './ScreenTabs.jsx'
// A district's link is only accepted when it points at the configured bot with a floodpulse_<district> start code.
const districtEntry=(base,d)=>d&&typeof d.name==='string'&&typeof d.command==='string'&&typeof d.url==='string'&&d.url.startsWith(base+'_')&&/^https:\/\/t\.me\/[A-Za-z][A-Za-z0-9_]{4,31}\?start=floodpulse_[a-z0-9_]{1,50}$/.test(d.url)&&/^\/start floodpulse [a-z0-9 ]{1,50}$/.test(d.command)&&(d.also===undefined||Array.isArray(d.also)&&d.also.every(a=>typeof a==='string'&&a.length<=40))
export default function AlertSubscription({navigate}){
 const [data,setData]=useState(null),[retry,setRetry]=useState(0),[district,setDistrict]=useState('')
 useEffect(()=>{setData(null);const controller=new AbortController();let active=true;const timer=setTimeout(()=>controller.abort(),10000)
 ;(async()=>{try{const response=await fetch('/api/alerts/subscription',{signal:controller.signal});const body=await response.json();if(!response.ok||!['available','unavailable'].includes(body.status))throw Error();if(body.status==='available'&&(!/^https:\/\/t\.me\/[A-Za-z][A-Za-z0-9_]{4,31}\?start=floodpulse$/.test(body.url)))throw Error();if(body.status==='available')body.districts=(Array.isArray(body.districts)?body.districts:[]).filter(d=>districtEntry(body.url,d));if(active)setData(body)}catch{if(active)setData({status:'unavailable',message:'Telegram subscription setup could not be checked.'})}finally{clearTimeout(timer)}})();return()=>{active=false;controller.abort();clearTimeout(timer)}},[retry])
 // One-screen rule: two sections side by side on laptops, two tabs on phones.
 return <ScreenTabs className="alerts-tabs" label="Alert sections" tabs={[{id:'telegram',label:'Telegram alerts',content:<section className="panel"><h2>Citizen Telegram alerts</h2><p>These are project notices, not an official government warning service. Only reviewed administrator notices are eligible. Citizen reports and experimental model outputs never automatically trigger alerts.</p>{!data?<p role="status">Checking subscription setup…</p>:data.status==='available'?<><h3>Alerts for your district</h3>{data.districts.length?<DistrictLink districts={data.districts} district={district} setDistrict={setDistrict}/>:<p role="status">The district list is unavailable right now; open the bot below and it will list the districts.</p>}{!district&&<p>Or <a href={data.url} target="_blank" rel="noopener noreferrer">Open configured Telegram bot</a> and send <strong>/start floodpulse</strong>: it replies with buttons for every district.</p>}<p>The bot confirms your subscription once. <strong>/mydistricts</strong> lists your districts, <strong>/stop udupi</strong> stops one district, and <strong>/stop</strong> stops all alerts and deletes your chat ID, which FloodPulse stores only to deliver these alerts. No guaranteed delivery or emergency dispatch. An attempt already in progress cannot be recalled.</p></>:<><p role="status">{data.message}</p><button onClick={()=>setRetry(n=>n+1)}>Check subscription setup again</button></>}
  <ol className="alert-steps" aria-label="How project alerts work"><li><strong>Subscribe</strong> to your district in Telegram, for example /start floodpulse udupi.</li><li><strong>An administrator reviews</strong> official warnings and the experimental risk index.</li><li><strong>Only an approved notice</strong> is sent. You can stop any time with /stop.</li></ol>
 </section>},
 {id:'official',label:'Official warnings & help',content:<section className="panel alert-official" aria-labelledby="alert-official-title"><h2 id="alert-official-title">Official warnings you can use now</h2>
  <ul><li><PageLink to="/" navigate={navigate}>Home</PageLink> shows today's IMD district warning and active NDMA SACHET alerts for your place, as issued.</li>
   <li><a href="https://sachet.ndma.gov.in/" target="_blank" rel="noopener noreferrer">NDMA SACHET</a> — the national Common Alerting Protocol portal for official disaster alerts.</li>
   <li><a href="https://mausam.imd.gov.in/responsive/districtWiseWarningGIS.php" target="_blank" rel="noopener noreferrer">IMD district-wise warnings</a> — the India Meteorological Department's 5-day district map.</li></ul>
  <OfficialHelp/>
 </section>}]}/>
}
// Finds a district from what people type: current names, former names (Mangalore, Belgaum…) and misspellings.
const fold=value=>value.toLowerCase().replace(/[^a-z0-9]/g,'')
function closeness(a,b){
 if(!a||!b)return 0
 let previous=[...Array(b.length+1).keys()]
 for(let i=1;i<=a.length;i++){const row=[i];for(let j=1;j<=b.length;j++)row[j]=Math.min(previous[j]+1,row[j-1]+1,previous[j-1]+(a[i-1]===b[j-1]?0:1));previous=row}
 return 1-previous[b.length]/Math.max(a.length,b.length)
}
export function findDistricts(districts,typed,limit=4){
 const q=fold(typed.replace(/district$/i,''))
 if(q.length<2)return []
 const scored=districts.map(d=>{
  const names=[d.name,...(Array.isArray(d.also)?d.also:[])].map(n=>({n,f:fold(n)}))
  const hit=names.find(x=>x.f===q)||names.find(x=>x.f.startsWith(q))||names.find(x=>x.f.includes(q))
  if(hit)return {d,score:hit.f===q?3:hit.f.startsWith(q)?2:1.5,via:hit.n===d.name?null:hit.n}
  const close=names.map(x=>({...x,s:closeness(q,x.f)})).sort((a,b)=>b.s-a.s)[0]
  return {d,score:close.s,via:close.n===d.name?null:close.n,close:true}
 }).filter(x=>x.score>=0.7).sort((a,b)=>b.score-a.score||a.d.name.localeCompare(b.d.name))
 const best=scored[0]?.score||0
 // Misspellings: only names nearly as close as the best one, so "mangalor" does not also offer Bengaluru.
 return scored.filter(x=>!x.close||x.score>=best-0.1).slice(0,limit)
}
function DistrictLink({districts,district,setDistrict}){
 const [typed,setTyped]=useState(''),[copied,setCopied]=useState(null),command=useRef(null)
 const chosen=districts.find(d=>d.name===district),found=findDistricts(districts,typed)
 function choose(name){setDistrict(name);setTyped('');setCopied(null)}
 function copy(){
  const done=()=>setCopied('Copied — paste it into the FloodPulse bot chat.')
  const select=()=>{const range=document.createRange();range.selectNodeContents(command.current);const sel=window.getSelection();sel.removeAllRanges();sel.addRange(range);setCopied('Selected — copy it with your phone or keyboard.')}
  if(navigator.clipboard?.writeText)navigator.clipboard.writeText(chosen.command).then(done,select);else select()
 }
 return <div className="district-subscribe">
  <label htmlFor="alert-district-search">Find your district</label>
  <input id="alert-district-search" type="search" autoComplete="off" placeholder="e.g. Udupi, Mangalore, Belgaum" value={typed} onChange={e=>setTyped(e.target.value)} aria-describedby="alert-district-hint"/>
  <p id="alert-district-hint" className="muted">Old names and small spelling mistakes are fine.</p>
  {typed.trim().length>=2&&(found.length?<ul className="district-matches" aria-label="Matching districts">{found.map(({d,via,close})=><li key={d.name}><button type="button" onClick={()=>choose(d.name)}>{close?'Did you mean ':''}{d.name}{via?` (${via})`:''}{close?'?':''}</button></li>)}</ul>
   :<p role="status">No Karnataka district matches "{typed.trim()}". Check the spelling, or choose from the list below.</p>)}
  <label htmlFor="alert-district">Or choose from the list</label>
  <select id="alert-district" value={district} onChange={e=>choose(e.target.value)}><option value="">Choose your district</option>{districts.map(d=><option key={d.name} value={d.name}>{d.name}</option>)}</select>
  {chosen&&<div className="district-command" aria-label={`How to get ${chosen.name} alerts`}>
   <p><a className="button-link" href={chosen.url} target="_blank" rel="noopener noreferrer">Get {chosen.name} alerts in Telegram</a></p>
   <p className="muted">Opens the bot; press <strong>Start</strong> and you are subscribed. Or send this exact command to the bot:</p>
   <p className="command-row"><code ref={command}>{chosen.command}</code><button type="button" className="secondary" onClick={copy}>Copy command</button></p>
   {copied&&<p role="status">{copied}</p>}
  </div>}
 </div>
}
