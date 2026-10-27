import React,{useEffect,useState} from 'react'
import OfficialHelp from './OfficialHelp.jsx'
import { PageLink } from './AppNavigation.jsx'
import ScreenTabs from './ScreenTabs.jsx'
// A district's link is only accepted when it points at the configured bot with a floodpulse_<district> start code.
const districtEntry=(base,d)=>d&&typeof d.name==='string'&&typeof d.command==='string'&&typeof d.url==='string'&&d.url.startsWith(base+'_')&&/^https:\/\/t\.me\/[A-Za-z][A-Za-z0-9_]{4,31}\?start=floodpulse_[a-z0-9_]{1,50}$/.test(d.url)&&/^\/start floodpulse [a-z0-9 ]{1,50}$/.test(d.command)
export default function AlertSubscription({navigate}){
 const [data,setData]=useState(null),[retry,setRetry]=useState(0),[district,setDistrict]=useState('')
 useEffect(()=>{setData(null);const controller=new AbortController();let active=true;const timer=setTimeout(()=>controller.abort(),10000)
 ;(async()=>{try{const response=await fetch('/api/alerts/subscription',{signal:controller.signal});const body=await response.json();if(!response.ok||!['available','unavailable'].includes(body.status))throw Error();if(body.status==='available'&&(!/^https:\/\/t\.me\/[A-Za-z][A-Za-z0-9_]{4,31}\?start=floodpulse$/.test(body.url)))throw Error();if(body.status==='available')body.districts=(Array.isArray(body.districts)?body.districts:[]).filter(d=>districtEntry(body.url,d));if(active)setData(body)}catch{if(active)setData({status:'unavailable',message:'Telegram subscription setup could not be checked.'})}finally{clearTimeout(timer)}})();return()=>{active=false;controller.abort();clearTimeout(timer)}},[retry])
 // One-screen rule: two sections side by side on laptops, two tabs on phones.
 return <ScreenTabs className="alerts-tabs" label="Alert sections" tabs={[{id:'telegram',label:'Telegram alerts',content:<section className="panel"><h2>Citizen Telegram alerts</h2><p>These are project notices, not an official government warning service. Only reviewed administrator notices are eligible. Citizen reports and experimental model outputs never automatically trigger alerts.</p>{!data?<p role="status">Checking subscription setup…</p>:data.status==='available'?<><h3>Alerts for your district</h3>{data.districts.length?<DistrictLink districts={data.districts} district={district} setDistrict={setDistrict}/>:<p role="status">The district list is unavailable right now; open the bot below and it will list the districts.</p>}<p>Or <a href={data.url} target="_blank" rel="noopener noreferrer">Open configured Telegram bot</a> and send <strong>/start floodpulse</strong>: it replies with the districts you can choose.</p><p>The bot confirms your subscription once. <strong>/mydistricts</strong> lists your districts, <strong>/stop udupi</strong> stops one district, and <strong>/stop</strong> stops all alerts and deletes your chat ID, which FloodPulse stores only to deliver these alerts. No guaranteed delivery or emergency dispatch. An attempt already in progress cannot be recalled.</p></>:<><p role="status">{data.message}</p><button onClick={()=>setRetry(n=>n+1)}>Check subscription setup again</button></>}
  <ol className="alert-steps" aria-label="How project alerts work"><li><strong>Subscribe</strong> to your district in Telegram, for example /start floodpulse udupi.</li><li><strong>An administrator reviews</strong> official warnings and the experimental risk index.</li><li><strong>Only an approved notice</strong> is sent. You can stop any time with /stop.</li></ol>
 </section>},
 {id:'official',label:'Official warnings & help',content:<section className="panel alert-official" aria-labelledby="alert-official-title"><h2 id="alert-official-title">Official warnings you can use now</h2>
  <ul><li><PageLink to="/" navigate={navigate}>Home</PageLink> shows today's IMD district warning and active NDMA SACHET alerts for your place, as issued.</li>
   <li><a href="https://sachet.ndma.gov.in/" target="_blank" rel="noopener noreferrer">NDMA SACHET</a> — the national Common Alerting Protocol portal for official disaster alerts.</li>
   <li><a href="https://mausam.imd.gov.in/responsive/districtWiseWarningGIS.php" target="_blank" rel="noopener noreferrer">IMD district-wise warnings</a> — the India Meteorological Department's 5-day district map.</li></ul>
  <OfficialHelp/>
 </section>}]}/>
}
function DistrictLink({districts,district,setDistrict}){
 const chosen=districts.find(d=>d.name===district)
 return <div className="district-subscribe"><label htmlFor="alert-district">Your district</label><select id="alert-district" value={district} onChange={e=>setDistrict(e.target.value)}><option value="">Choose your district</option>{districts.map(d=><option key={d.name} value={d.name}>{d.name}</option>)}</select>
  {chosen&&<p><a className="button-link" href={chosen.url} target="_blank" rel="noopener noreferrer">Get {chosen.name} alerts in Telegram</a> or send <strong>{chosen.command}</strong> to the bot.</p>}</div>
}

