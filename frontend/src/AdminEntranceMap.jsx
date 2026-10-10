import React,{useEffect,useRef,useState} from 'react'
import ShelterMap from './ShelterMap.jsx'
import LocationDirectorySelector from './LocationDirectorySelector.jsx'
import {adminMapSettings,buildingSearchURL,validatedSearchResults} from './adminMapProvider.js'
const settings=adminMapSettings()
export default function AdminEntranceMap({entrance,onSelect,selectedDistrictId,onDistrict=()=>{},navigationBounds=null}) {
 const [mode,setMode]=useState('street'),[reference,setReference]=useState(null),[query,setQuery]=useState(''),[results,setResults]=useState([]),[error,setError]=useState(null),[loading,setLoading]=useState(false)
 const controller=useRef(null),busy=useRef(false),mounted=useRef(true)
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;controller.current?.abort()}},[])
 function changeQuery(value){controller.current?.abort();controller.current=null;setLoading(false);setQuery(value);setResults([]);setError(null)}
 async function search(e){
  e.preventDefault();if(busy.current||!settings.enabled)return
  const abort=new AbortController();controller.current=abort;busy.current=true;setLoading(true);setError(null);setResults([])
  const timer=setTimeout(()=>abort.abort(),10000)
  try{
   const response=await fetch(buildingSearchURL(query,settings),{signal:abort.signal,credentials:'omit',referrerPolicy:'origin'})
   if(!response.ok)throw Error('Provider unavailable')
   const rows=validatedSearchResults(await response.json());if(mounted.current&&controller.current===abort&&!abort.signal.aborted)setResults(rows)
  }catch{if(mounted.current&&controller.current===abort)setError('Building search unavailable or timed out. Use the verified place directory or inspect the street map. No substitute result was generated.')}
  finally{clearTimeout(timer);busy.current=false;if(mounted.current&&controller.current===abort)setLoading(false)}
 }
 return <section className="panel admin-entrance-panel" aria-labelledby="entrance-map-title">
  <h3 id="entrance-map-title">Inspect facility & select entrance</h3>
  <div className="admin-map-controls"><LocationDirectorySelector collapseOnChoose onChoose={setReference} selectedDistrictId={selectedDistrictId} onDistrict={onDistrict} />
  <div><label htmlFor="admin-map-mode">Map mode</label><select id="admin-map-mode" value={mode} onChange={e=>setMode(e.target.value)}><option value="street">Street map</option><option value="satellite" disabled={!settings.enabled}>Satellite imagery</option><option value="hybrid" disabled={!settings.enabled}>Satellite Hybrid</option></select></div></div>
  {!settings.enabled&&<p role="status" className="notice">Satellite, Hybrid and building search require an authorized MapTiler configuration. Street map and verified place search remain available.</p>}
  <div className="admin-inspection-options"><details open={settings.enabled} className="building-search-options"><summary>Provider building-reference search</summary><form onSubmit={search} className="building-search"><label htmlFor="building-name">Search place or building name</label><input id="building-name" type="search" value={query} maxLength={120} onChange={e=>changeQuery(e.target.value)} disabled={!settings.enabled}/><button disabled={!settings.enabled||loading||query.trim().length<3}>{loading?'Searching…':'Search building references'}</button></form></details>
  <details className="inspection-limitations"><summary>Manual entrance verification and imagery limitations</summary><p className="notice">Inspect provider labels and mapped building outlines where available, then click the actual entrance and confirm its coordinates. Imagery does not verify authorization, occupancy, structural safety, road access, water, toilets or electricity. Confirm facility name/address and actual conditions manually.</p></details>
  </div>
  {error&&<p role="alert">{error}</p>}
  <div aria-live="polite">{!loading&&results.length>0&&<ul aria-label="Building reference results">{results.map((r,i)=><li key={r.id+':'+i}><button type="button" onClick={()=>setReference(r)}>{r.name} — inspect reference point</button></li>)}</ul>}{settings.enabled&&!loading&&results.length===0&&query&&<p>No building reference selected. Search is explicit and bounded; not all buildings are named or mapped.</p>}</div>
  <ShelterMap inspection points={entrance} origin={reference} navigationBounds={navigationBounds} mode={mode} providerSettings={settings} label="Administrator entrance selection map" onSelect={onSelect}/>
  {reference&&<p>Navigation reference: {reference.name}. This point is not a verified entrance and does not fill the shelter fields.</p>}
 </section>
}
