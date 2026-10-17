import React, { useEffect, useRef, useState } from 'react'

// In-app GPS camera: a live photo plus the device's own GPS fix and time, captured together.
// The uploaded image stays clean (no text in the pixels, better for later analysis); the
// location stamp is shown on screen and can be saved locally as a separate stamped copy.
const MAX_BYTES = 5 * 1024 * 1024, MAX_PIXELS = 10_000_000
const clock = ms => new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'medium' }).format(new Date(ms)) + ' IST'
const metres = (a, b) => { const r = Math.PI / 180; return 6371000 * Math.hypot((b.longitude - a.longitude) * r * Math.cos((a.latitude + b.latitude) / 2 * r), (b.latitude - a.latitude) * r) }

// BigDataCloud's free client API is only for the device's own current location — which this is.
// The label is shown to the person and is not sent to FloodPulse.
export async function placeLabel(fix, signal) {
  const params = new URLSearchParams({ latitude: fix.latitude, longitude: fix.longitude, localityLanguage: 'en' })
  const response = await fetch('https://api.bigdatacloud.net/data/reverse-geocode-client?' + params, { signal, credentials: 'omit', referrerPolicy: 'no-referrer' })
  if (!response.ok) throw Error('Place lookup unavailable')
  const body = await response.json()
  const admin = Array.isArray(body.localityInfo?.administrative) ? body.localityInfo.administrative : []
  const district = admin.find(a => /district/i.test(a.description || '') && typeof a.name === 'string')?.name
  const parts = [body.locality, body.city, district, body.principalSubdivision].filter(p => typeof p === 'string' && p.trim() && p.length < 120 && !/[\x00-\x1f]/.test(p))
  const unique = parts.filter((p, i) => parts.findIndex(q => q.toLowerCase() === p.toLowerCase()) === i)
  if (!unique.length) throw Error('No place name')
  return unique.join(', ') + (typeof body.postcode === 'string' && /^\d{6}$/.test(body.postcode) ? ' ' + body.postcode : '')
}

function stampLines(fix, place, at) {
  return [place || 'Place name unavailable', `${fix.latitude.toFixed(6)}°N, ${fix.longitude.toFixed(6)}°E · GPS ±${Math.round(fix.accuracy_m)} m`, clock(at), 'FloodPulse citizen report photo']
}

export default function GpsCamera({ onCapture, onClose }) {
  const video = useRef(null), stream = useRef(null), watch = useRef(null), lookup = useRef({ at: 0, fix: null, controller: null })
  const [fix, setFix] = useState(null), [place, setPlace] = useState(null), [error, setError] = useState(null), [gpsError, setGpsError] = useState(null)
  const [shot, setShot] = useState(null), [now, setNow] = useState(Date.now()), [ready, setReady] = useState(false)

  useEffect(() => {
    let stopped = false
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) { setError('The in-app camera needs a secure (https) connection and a supported browser. Use "Take photo" instead.'); return }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false })
      .then(media => { if (stopped) { media.getTracks().forEach(t => t.stop()); return } stream.current = media; if (video.current) { video.current.srcObject = media; video.current.play?.().catch(() => {}) } })
      .catch(() => { if (!stopped) setError('Camera permission was denied or no camera is available. Allow the camera, or use "Take photo" instead.') })
    if (navigator.geolocation?.watchPosition) {
      watch.current = navigator.geolocation.watchPosition(p => {
        const c = p.coords
        if (!Number.isFinite(c.latitude) || !Number.isFinite(c.longitude) || !Number.isFinite(c.accuracy) || c.accuracy < 0) return
        if (!stopped) { setGpsError(null); setFix({ latitude: c.latitude, longitude: c.longitude, accuracy_m: c.accuracy, at: p.timestamp }) }
      }, () => { if (!stopped) setGpsError('Location is blocked or unavailable. Allow location so the photo records where it was taken.') }, { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 })
    } else setGpsError('This browser cannot provide location.')
    const tick = setInterval(() => setNow(Date.now()), 1000)
    return () => {
      stopped = true; clearInterval(tick)
      stream.current?.getTracks().forEach(t => t.stop()); stream.current = null
      if (watch.current !== null) navigator.geolocation?.clearWatch?.(watch.current)
      lookup.current.controller?.abort()
    }
  }, [])

  // Refresh the place label when the fix moves more than 50 m, at most every 10 seconds.
  useEffect(() => {
    if (!fix) return
    const last = lookup.current
    if (last.fix && metres(last.fix, fix) < 50) return
    if (Date.now() - last.at < 10000 && last.fix) return
    last.controller?.abort(); const controller = new AbortController()
    lookup.current = { at: Date.now(), fix, controller }
    placeLabel(fix, controller.signal).then(setPlace).catch(() => {})
  }, [fix])

  const age = fix ? Math.max(0, Math.round((now - fix.at) / 1000)) : null
  const gpsOk = fix && fix.accuracy_m <= 100 && age <= 60

  async function capture() {
    const v = video.current
    if (!v || !fix || !v.videoWidth) return
    let w = v.videoWidth, h = v.videoHeight
    const scale = Math.min(1, Math.sqrt(MAX_PIXELS / (w * h))); w = Math.round(w * scale); h = Math.round(h * scale)
    const canvas = document.createElement('canvas'); canvas.width = w; canvas.height = h
    canvas.getContext('2d').drawImage(v, 0, 0, w, h)
    const at = Date.now(), taken = { ...fix }
    let quality = 0.9, blob = null
    while (quality >= 0.5) { blob = await new Promise(r => canvas.toBlob(r, 'image/jpeg', quality)); if (blob && blob.size <= MAX_BYTES) break; quality -= 0.1 }
    if (!blob || blob.size > MAX_BYTES) { setError('The photo is too large. Try again.'); return }
    const base64 = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = reject; reader.readAsDataURL(blob) })
    setShot({ base64, url: URL.createObjectURL(blob), at, fix: taken, place, width: w, height: h })
  }
  function retake() { if (shot?.url) URL.revokeObjectURL(shot.url); setShot(null) }
  function useShot() {
    onCapture({ name: `gps-photo-${new Date(shot.at).toISOString().replace(/[:.]/g, '-')}.jpg`, mime: 'image/jpeg', base64: shot.base64, preview: shot.url,
      capture: { source: 'IN_APP_GPS_CAMERA', captured_at: new Date(shot.at).toISOString() }, place: shot.place,
      fix: { latitude: shot.fix.latitude, longitude: shot.fix.longitude, accuracy_m: shot.fix.accuracy_m, gps_at: new Date(shot.fix.at).toISOString() }, stamp: stampLines(shot.fix, shot.place, shot.at) })
  }
  // A stamped copy for the person's own records; it is downloaded locally, never uploaded.
  async function saveStamped() {
    const img = new Image(); img.src = shot.url; await img.decode()
    const canvas = document.createElement('canvas'); canvas.width = img.width; canvas.height = img.height
    const ctx = canvas.getContext('2d'); ctx.drawImage(img, 0, 0)
    const lines = stampLines(shot.fix, shot.place, shot.at), size = Math.max(16, Math.round(img.width / 45)), pad = size * 0.6
    const band = lines.length * size * 1.35 + pad * 2
    ctx.fillStyle = 'rgba(0,0,0,0.6)'; ctx.fillRect(0, img.height - band, img.width, band)
    ctx.fillStyle = '#fff'; ctx.font = `600 ${size}px sans-serif`; ctx.textBaseline = 'top'
    lines.forEach((line, i) => ctx.fillText(line, pad, img.height - band + pad + i * size * 1.35, img.width - pad * 2))
    const link = document.createElement('a'); link.download = `floodpulse-gps-photo-${shot.at}.jpg`; link.href = canvas.toDataURL('image/jpeg', 0.9); link.click()
  }

  const lines = fix ? stampLines(fix, place, now) : null
  return <div className="gps-camera" role="dialog" aria-modal="true" aria-label="GPS camera">
    <div className="gps-camera-view">
      {shot ? <img src={shot.url} alt="Captured flood photo preview" /> : <video ref={video} playsInline muted autoPlay onLoadedMetadata={() => setReady(true)} aria-label="Live camera view" />}
      <div className="gps-camera-stamp" aria-live="polite">
        {shot ? stampLines(shot.fix, shot.place, shot.at).map(l => <div key={l}>{l}</div>) : lines ? lines.slice(0, 3).map(l => <div key={l}>{l}</div>) : <div>{gpsError || 'Waiting for GPS…'}</div>}
      </div>
      <span className={'gps-camera-badge ' + (gpsOk ? 'ok' : fix ? 'weak' : 'none')}>{fix ? `GPS ±${Math.round(fix.accuracy_m)} m${age > 5 ? ` · ${age}s ago` : ''}` : 'No GPS yet'}</span>
    </div>
    {error && <p role="alert" className="gps-camera-error">{error}</p>}
    {!error && !shot && fix && !gpsOk && <p className="gps-camera-hint">GPS is weak (±{Math.round(fix.accuracy_m)} m). Wait a few seconds outdoors for a better fix; the reviewer will see the accuracy.</p>}
    <div className="gps-camera-actions">
      {shot ? <>
        <button type="button" onClick={useShot}>Use this photo</button>
        <button type="button" className="secondary" onClick={retake}>Retake</button>
        <button type="button" className="secondary" onClick={saveStamped}>Save stamped copy</button>
      </> : <>
        <button type="button" className="gps-camera-shutter" onClick={capture} disabled={!ready || !fix || !!error} aria-label={fix ? 'Take GPS photo' : 'Take GPS photo (waiting for GPS)'}>{fix ? 'Take GPS photo' : 'Waiting for GPS…'}</button>
      </>}
      <button type="button" className="secondary" onClick={() => { retake(); onClose() }}>Close camera</button>
    </div>
    <p className="gps-camera-note">Place name: BigDataCloud (shown only to you). The uploaded photo has no text added; its location, time and accuracy are stored as report details.</p>
  </div>
}
