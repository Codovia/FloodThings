import React,{useEffect,useState} from 'react'
import OfficialHelp from './OfficialHelp.jsx'
import { PageLink } from './AppNavigation.jsx'
import ScreenTabs from './ScreenTabs.jsx'
export default function AlertSubscription({navigate}){
 const [data,setData]=useState(null),[retry,setRetry]=useState(0)
 useEffect(()=>{setData(null);const controller=new AbortController();let active=true;const timer=setTimeout(()=>controller.abort(),10000)
 ;(async()=>{try{const response=await fetch('/api/alerts/subscription',{signal:controller.signal});const body=await response.json();if(!response.ok||!['available','unavailable'].includes(body.status))throw Error();if(body.status==='available'&&(!/^https:\/\/t\.me\/[A-Za-z][A-Za-z0-9_]{4,31}\?start=floodpulse$/.test(body.url)))throw Error();if(active)setData(body)}catch{if(active)setData({status:'unavailable',message:'Telegram subscription setup could not be checked.'})}finally{clearTimeout(timer)}})();return()=>{active=false;controller.abort();clearTimeout(timer)}},[retry])
 // One-screen rule: two sections side by side on laptops, two tabs on phones.
 return <ScreenTabs className="alerts-tabs" label="Alert sections" tabs={[{id:'telegram',label:'Telegram alerts',content:<section className="panel"><h2>Citizen Telegram alerts</h2><p>These are project notices, not an official government warning service. Only reviewed administrator notices are eligible. Citizen reports and experimental model outputs never automatically trigger alerts.</p>{!data?<p role="status">Checking subscription setup…</p>:data.status==='available'?<><h3>Subscribe in Telegram</h3><a className="button-link" href={data.url} target="_blank" rel="noopener noreferrer">Open configured Telegram bot</a><p>In Telegram, send <strong>/start floodpulse</strong> to request project alerts; <strong>/stop</strong> opts out. A project administrator must authorize your destination. No guaranteed delivery or emergency dispatch.</p><p>Subscription commands record consent only; this prototype does not send automatic acknowledgement messages. An attempt already in progress cannot be recalled.</p></>:<><p role="status">{data.message}</p><button onClick={()=>setRetry(n=>n+1)}>Check subscription setup again</button></>}
  <ol className="alert-steps" aria-label="How project alerts work"><li><strong>Subscribe</strong> in Telegram with /start floodpulse.</li><li><strong>An administrator reviews</strong> official warnings and the experimental risk index.</li><li><strong>Only an approved notice</strong> is sent. You can stop any time with /stop.</li></ol>
 </section>},
 {id:'official',label:'Official warnings & help',content:<section className="panel alert-official" aria-labelledby="alert-official-title"><h2 id="alert-official-title">Official warnings you can use now</h2>
  <ul><li><PageLink to="/" navigate={navigate}>Home</PageLink> shows today's IMD district warning and active NDMA SACHET alerts for your place, as issued.</li>
   <li><a href="https://sachet.ndma.gov.in/" target="_blank" rel="noopener noreferrer">NDMA SACHET</a> — the national Common Alerting Protocol portal for official disaster alerts.</li>
   <li><a href="https://mausam.imd.gov.in/responsive/districtWiseWarningGIS.php" target="_blank" rel="noopener noreferrer">IMD district-wise warnings</a> — the India Meteorological Department's 5-day district map.</li></ul>
  <OfficialHelp/>
 </section>}]}/>
}
