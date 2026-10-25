import React, { useEffect, useState } from 'react'

// Place name with PIN code (and the full address on request) for a GPS fix or a spot on the map. The point goes
// through our server to OpenStreetMap's Nominatim once the person has shared their location or tapped the map;
// the server makes the answer no more precise than the location. It is OpenStreetMap's nearest mapped address and
// PIN code, not a verified postal address.
export const addressable = point => (point?.kind === 'gps' || point?.kind === 'map') && Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
const UNAVAILABLE = 'Address lookup is unavailable right now.'
const text = (value, limit) => typeof value === 'string' && value.trim() && value.length <= limit && !/[\x00-\x1f]/.test(value) ? value.trim() : null

// One request per point, shared by every page that shows it (Home, the location bar, Shelters…). Answers live in
// memory for this visit only; failures are forgotten so "Try again" asks again.
const answers = new Map()
export function forgetPlaces() { answers.clear() }
function lookupOnce(key, point, accuracy) {
  if (!answers.has(key)) {
    const job = fetch('/api/location/address', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ latitude: point.latitude, longitude: point.longitude, ...(Number.isFinite(accuracy) ? { accuracy_m: accuracy } : {}) }) })
      .then(response => response.json())
      .then(body => {
        const address = text(body?.address, 1000)
        return body?.status === 'available' && address && ['street', 'area'].includes(body.precision)
          ? { status: 'available', address, precision: body.precision, place: text(body.place, 200) }
          : { status: 'failed', message: text(body?.message, 200) || UNAVAILABLE }
      }, () => ({ status: 'failed', message: UNAVAILABLE }))
    answers.set(key, job)
    job.then(answer => { if (answer.status !== 'available') answers.delete(key) })
    if (answers.size > 50) answers.delete(answers.keys().next().value)
  }
  return answers.get(key)
}

export function usePlaceLookup(point) {
  const [state, setState] = useState({ status: 'idle' })
  const [attempt, setAttempt] = useState(0)
  const accuracy = point?.accuracy_m ?? point?.uncertainty_m
  const key = addressable(point) ? `${point.latitude},${point.longitude},${accuracy ?? ''}` : null
  useEffect(() => {
    if (!key) { setState({ status: 'idle' }); return }
    let current = true
    setState({ status: 'loading' })
    lookupOnce(key, point, accuracy).then(answer => { if (current) setState(answer) })
    return () => { current = false }
  }, [key, attempt]) // the key holds the point's values
  return { ...state, retry: () => setAttempt(n => n + 1) }
}

export default function AddressLine({ lookup, className = '' }) {
  const [open, setOpen] = useState(false)
  const status = lookup?.status
  useEffect(() => { if (status === 'loading') setOpen(false) }, [status])
  if (status !== 'available' && status !== 'failed') return null
  const classes = `address-line ${className}`.trim()
  if (!open) return <p className={classes}><button type="button" className="link-button" onClick={() => setOpen(true)} title="Nearest mapped address from OpenStreetMap, for the point rounded to about 11 m. Nothing is stored.">Show address</button></p>
  if (status === 'failed') return <p className={classes} role="status">{lookup.message} <button type="button" className="link-button" onClick={lookup.retry}>Try again</button></p>
  return <p className={classes} role="status"><span className="address-text">{lookup.precision === 'area' ? 'Area' : 'Near'}: {lookup.address}</span>{' '}
    <small>· nearest mapped address and PIN, not verified · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap</a></small></p>
}
