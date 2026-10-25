import React, { useEffect, useState } from 'react'

// Place name with PIN code (and the full address on request) for a GPS fix or a spot on the map. The point goes
// through our server to OpenStreetMap's Nominatim once the person has shared their location or tapped the map;
// the server makes the answer no more precise than the location. It is OpenStreetMap's nearest mapped address and
// PIN code, not a verified postal address.
export const addressable = point => (point?.kind === 'gps' || point?.kind === 'map') && Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
const UNAVAILABLE = 'Address lookup is unavailable right now.'
const text = (value, limit) => typeof value === 'string' && value.trim() && value.length <= limit && !/[\x00-\x1f]/.test(value) ? value.trim() : null

export function usePlaceLookup(point) {
  const [state, setState] = useState({ status: 'idle' })
  const [attempt, setAttempt] = useState(0)
  const accuracy = point?.accuracy_m ?? point?.uncertainty_m
  const key = addressable(point) ? `${point.latitude},${point.longitude},${accuracy ?? ''}` : null
  useEffect(() => {
    if (!key) { setState({ status: 'idle' }); return }
    const controller = new AbortController()
    setState({ status: 'loading' })
    fetch('/api/location/address', { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
      body: JSON.stringify({ latitude: point.latitude, longitude: point.longitude, ...(Number.isFinite(accuracy) ? { accuracy_m: accuracy } : {}) }) })
      .then(response => response.json())
      .then(body => {
        if (controller.signal.aborted) return
        const address = text(body?.address, 1000)
        if (body?.status === 'available' && address && ['street', 'area'].includes(body.precision)) setState({ status: 'available', address, precision: body.precision, place: text(body.place, 200) })
        else setState({ status: 'failed', message: text(body?.message, 200) || UNAVAILABLE })
      })
      .catch(() => { if (!controller.signal.aborted) setState({ status: 'failed', message: UNAVAILABLE }) })
    return () => controller.abort()
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
