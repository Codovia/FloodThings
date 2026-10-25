import React, { useEffect, useRef, useState } from 'react'

// Street address for a GPS fix or a spot on the map. The point goes to OpenStreetMap's Nominatim through
// our server, so it is looked up only when the person taps the button. The server makes it no more precise
// than the location; it is OpenStreetMap's nearest mapped address, not a verified postal address.
export const addressable = point => (point?.kind === 'gps' || point?.kind === 'map') && Number.isFinite(point.latitude) && Number.isFinite(point.longitude)

export default function AddressLine({ point, className = '' }) {
  const [state, setState] = useState({ status: 'idle' })
  const job = useRef(null)
  const key = addressable(point) ? `${point.latitude},${point.longitude},${point.accuracy_m ?? point.uncertainty_m ?? ''}` : null
  useEffect(() => {
    setState({ status: 'idle' })
    return () => { job.current?.abort(); job.current = null }
  }, [key])
  if (!key) return null

  async function look() {
    job.current?.abort()
    const controller = new AbortController(); job.current = controller
    const accuracy = point.accuracy_m ?? point.uncertainty_m
    setState({ status: 'loading' })
    try {
      const response = await fetch('/api/location/address', { method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ latitude: point.latitude, longitude: point.longitude, ...(Number.isFinite(accuracy) ? { accuracy_m: accuracy } : {}) }) })
      const body = await response.json()
      if (job.current !== controller) return
      job.current = null
      if (body?.status === 'available' && typeof body.address === 'string' && body.address.trim() && body.address.length <= 1000 && ['street', 'area'].includes(body.precision)) setState({ status: 'available', address: body.address.trim(), precision: body.precision })
      else setState({ status: 'failed', message: typeof body?.message === 'string' && body.message.length <= 200 ? body.message : 'Address lookup is unavailable right now.' })
    } catch (error) {
      if (error?.name === 'AbortError' || job.current !== controller) return
      job.current = null
      setState({ status: 'failed', message: 'Address lookup is unavailable right now.' })
    }
  }

  const classes = `address-line ${className}`.trim()
  if (state.status === 'idle') return <p className={classes}><button type="button" className="link-button" onClick={look} title="Sends this point, rounded to about 11 m, through FloodPulse to OpenStreetMap's address service. Nothing is stored.">Show address</button></p>
  if (state.status === 'loading') return <p className={classes} role="status">Looking up the address…</p>
  if (state.status === 'failed') return <p className={classes} role="status">{state.message} <button type="button" className="link-button" onClick={look}>Try again</button></p>
  return <p className={classes} role="status"><span className="address-text">{state.precision === 'area' ? 'Area' : 'Near'}: {state.address}</span>{' '}
    <small>· nearest mapped address, not verified · <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap</a></small></p>
}
