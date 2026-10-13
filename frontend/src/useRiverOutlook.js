import {useEffect,useRef,useState} from 'react'
import {retrievalTime} from './useWeatherSession.js'
export const NEARBY_UNAVAILABLE='Nearby flood possibility cannot currently be assessed reliably. Check official local warnings.'
export function usableRiver(body,point,now){
 const retrieved=retrievalTime(body?.retrieved_at,now),expires=Date.parse(body?.fresh_until)
 const grid=body?.grid_location,expected=body?.reach?.expected_grid
 const verifiedGrid=['latitude','longitude'].every(k=>Number.isFinite(grid?.[k])&&Number.isFinite(expected?.[k])&&Math.abs(grid[k]-expected[k])<=.0001)&&Math.abs(grid?.latitude)<=90&&Math.abs(grid?.longitude)<=180
 return !!point&&['available','partial'].includes(body?.status)&&body.source?.data_kind==='external_modelled_river_forecast'&&body.requested_model==='forecast_v4'&&body.reach?.verified_grid===true&&verifiedGrid&&body.units==='m³/s'&&body.timezone==='GMT'&&retrieved!==null&&now-retrieved<3600000&&Number.isFinite(expires)&&expires>now&&body.viewing_point?.latitude===point.latitude&&body.viewing_point?.longitude===point.longitude&&(body.viewing_point?.accuracy_m||0)===(point.accuracy_m||0)&&Array.isArray(body.forecast)&&body.forecast.length===7&&body.forecast.every((d,i)=>d&&/^\d{4}-\d{2}-\d{2}$/.test(d.date)&&(i===0||Date.parse(d.date)-Date.parse(body.forecast[i-1].date)===86400000)&&['river_discharge','river_discharge_mean','river_discharge_p25','river_discharge_p75'].every(k=>d[k]==null||(Number.isFinite(d[k])&&d[k]>=0)))
}
export default function useRiverOutlook(point){
 const key=point?`${point.latitude}:${point.longitude}:${point.accuracy_m||0}`:null
 const [revision,setRevision]=useState(0),[view,setView]=useState({key:null,data:null,error:null,loading:false,now:Date.now()})
 const cache=useRef(null)
 useEffect(()=>{
  if(!point)return
  let stopped=false;const controller=new AbortController(),cached=cache.current?.key===key?cache.current.data:null
  if(revision===0&&cached){setView({key,data:cached,error:null,loading:false,now:Date.now()});return}
  setView({key,data:null,error:null,loading:true,now:Date.now()})
  const timer=setTimeout(()=>controller.abort(),15000)
  ;(async()=>{
   try{
    const response=await fetch('/api/river-outlook',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({latitude:point.latitude,longitude:point.longitude,accuracy_m:point.accuracy_m||0}),signal:controller.signal})
    const body=await response.json()
    if(!response.ok||!['available','partial','unsupported','unavailable'].includes(body?.status))throw Error('River outlook response is unavailable.')
    if(['available','partial'].includes(body.status)&&!usableRiver(body,point,Date.now()))throw Error('River forecast freshness or geographic association could not be verified.')
    if(!stopped&&!controller.signal.aborted){cache.current={key,data:body};setView({key,data:body,error:null,loading:false,now:Date.now()})}
   }catch{if(!stopped)setView({key,data:null,error:controller.signal.aborted?'River outlook request timed out.':'River outlook could not be checked.',loading:false,now:Date.now()})}
   finally{clearTimeout(timer)}
  })()
  return()=>{stopped=true;controller.abort();clearTimeout(timer)}
 },[key,revision])
 useEffect(()=>{if(!view.data?.fresh_until)return;const timer=setTimeout(()=>setView(v=>({...v,now:Date.now()})),Math.max(0,Date.parse(view.data.fresh_until)-Date.now()));return()=>clearTimeout(timer)},[view.data])
 return {...(view.key===key?view:{data:null,error:null,loading:!!point,now:Date.now()}),refresh:()=>setRevision(n=>n+1)}
}
