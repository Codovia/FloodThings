import React, { useEffect, useState } from 'react'

const keyOf = point => `${point.latitude}:${point.longitude}`
const time = value => new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'}).format(new Date(value))+' IST'

export default function RainfallOutlook({ point, weather, freshness }) {
  const [open,setOpen] = useState(false)
  const [attempt,setAttempt] = useState(0)
  const key=keyOf(point)
  const [view,setView] = useState({key:null,data:null,error:null,loading:false})
  const receipt=weather?.retrieved_at || null
  useEffect(()=>{
    if (!open || !receipt) return
    const controller=new AbortController();let stopped=false
    const timer=setTimeout(()=>controller.abort(),15000)
    setView({key,data:null,error:null,loading:true})
    ;(async()=>{
      try {
        const response=await fetch('/api/ai/rainfall-outlook?'+new URLSearchParams({latitude:point.latitude,longitude:point.longitude}),{signal:controller.signal})
        const data=await response.json()
        if (!response.ok || data.status!=='available') throw Error(data.message || 'AI rainfall outlook is unavailable.')
        if (data.location?.latitude!==point.latitude || data.location?.longitude!==point.longitude || data.experimental!==true ||
            !['heavy_rainfall_predicted','below_heavy_threshold_predicted'].includes(data.prediction) || data.probability!==null ||
            data.model_version!=='rainfall_logistic_v1' || !/^[a-f0-9]{64}$/.test(data.model_sha256) ||
            !Number.isFinite(Date.parse(data.feature_valid_through_utc)) || Date.parse(data.feature_valid_through_utc)>Date.parse(data.retrieved_at) ||
            !data.provider_grid || !Number.isFinite(data.provider_grid.latitude) || Math.abs(data.provider_grid.latitude)>90 ||
            !Number.isFinite(data.provider_grid.longitude) || Math.abs(data.provider_grid.longitude)>180 || !data.retrieved_at || !Number.isFinite(Date.parse(data.retrieved_at)) ||
            !data.horizon || data.horizon.hours!==24 || !Number.isFinite(Date.parse(data.horizon.start_utc)) ||
            Date.parse(data.horizon.end_utc)-Date.parse(data.horizon.start_utc)!==24*60*60*1000 || data.target?.threshold_mm!==64.5)
          throw Error('AI response does not match the selected location or validated target.')
        if (!stopped && !controller.signal.aborted) setView({key,data,error:null,loading:false})
      } catch (error) {
        if (!stopped) setView({key,data:null,error:error.name==='AbortError'?'AI hourly request timed out. Try again.':error.message,loading:false})
      } finally { clearTimeout(timer) }
    })()
    return ()=>{stopped=true;clearTimeout(timer);controller.abort()}
  },[key,receipt,open,attempt])
  const current=view.key===key?view:{data:null,error:null,loading:open&&!!receipt}
  return <section className="panel" aria-labelledby="rainfall-outlook-title">
    <div className="panel-heading"><div><p className="eyebrow">EXPERIMENTAL MACHINE LEARNING</p><h2 id="rainfall-outlook-title">AI Rainfall Outlook</h2></div>
      <button type="button" onClick={()=>open?setAttempt(n=>n+1):setOpen(true)} disabled={current.loading}>{current.loading?'Running rainfall model…':open?'Retry rainfall outlook':'Run experimental rainfall model'}</button></div>
    <p>{point.name} · next 24 complete hours beginning at the next full UTC hour.</p>
    <p className="notice">Experimental rainfall model, not flood probability or an official warning. Supports only the verified Kundapur and Mangaluru points. Flood prediction remains unavailable.</p>
    {!open && <p className="muted">Run the saved trained Logistic Regression model using a separate bounded past-hourly Open-Meteo request. No seven-day forecast request is duplicated.</p>}
    {open && !receipt && <p role="status">Usable weather retrieval is required before running the rainfall model.</p>}
    <div aria-live="polite" aria-busy={current.loading}>
      {current.loading && <p role="status">Fetching past-hourly model inputs and running the trained model…</p>}
      {current.error && <p className="notice error" role="alert" aria-label="AI rainfall outlook error">{current.error} No replacement prediction is shown.</p>}
      {current.data && <>
        <p><strong>{current.data.prediction_text}</strong></p>
        <p>Window: {time(current.data.horizon.start_utc)} to {time(current.data.horizon.end_utc)}</p>
        <p className="muted">Model {current.data.model_version} · retrieved {time(current.data.retrieved_at)}</p>
        <p className="muted">Past inputs valid through {time(current.data.feature_valid_through_utc)} · hourly provider grid {current.data.provider_grid.latitude}°, {current.data.provider_grid.longitude}°.</p>
        <p className="notice">ERA5 reanalysis-trained grid-scale proxy; live inputs are weather model output. Training/live parity requires validation. No calibrated probability is displayed. Below the threshold does not mean dry or safe.</p>
        {freshness!=='fresh' && <p className="notice error">Weather is stale or refreshing; this is a previously retrieved rainfall outlook with the window shown above.</p>}
        <p className="muted">Rainfall amount threshold: <a href={current.data.target.definition_url}>IMD heavy-rainfall definition</a>. The rolling UTC window differs from the IMD reporting day.</p>
      </>}
    </div>
    <p className="muted">Inputs: <a href="https://open-meteo.com/">Open-Meteo hourly rainfall inputs</a> · CC BY 4.0. Historical test metrics do not establish live forecast skill or station accuracy.</p>
  </section>
}
