import React, { useEffect, useRef, useState } from 'react'

const stamp = value => value ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) + ' IST' : 'Not recorded'
const resultText = row => ({
  draft: 'Preview only — not sent.',
  sending: 'Attempt started; outcome not recorded. Inspect Telegram and history before composing another notice.',
  accepted: 'Telegram accepted the message. Recipient reading is not confirmed.',
  rejected: 'Telegram rejected the message. It has not been automatically retried.',
  delivery_unknown: 'Delivery is uncertain. Inspect Telegram before composing another notice; do not assume it failed.',
}[row.status] || 'Outcome unavailable')

export default function AdminNotifications({ session, request }) {
  const [options, setOptions] = useState(null), [history, setHistory] = useState(null), [offset, setOffset] = useState(0)
  const [destination, setDestination] = useState(''), [kind, setKind] = useState('informational'), [message, setMessage] = useState(''), [shelter, setShelter] = useState('')
  const [preview, setPreview] = useState(null), [approved, setApproved] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(null)
  const busyRef = useRef(false), requestId = useRef(null), stopped = useRef(false), controllers = useRef(new Set())

  async function call(path, settings = {}, timeout = 15000) {
    const controller = new AbortController(); controllers.current.add(controller)
    const timer = setTimeout(() => controller.abort(), timeout)
    try { return await request(path, { ...settings, signal: controller.signal }, session) }
    catch (e) { throw Error(e.name === 'AbortError' ? 'Request timed out. A send may still have occurred; inspect notification history. No automatic retry.' : e.message) }
    finally { clearTimeout(timer); controllers.current.delete(controller) }
  }

  async function load(start = offset) {
    const [config, rows] = await Promise.all([call('/api/admin/notifications/options'), call('/api/admin/notifications?limit=50&offset=' + start)])
    if (typeof config.configured !== 'boolean' || !Array.isArray(config.destinations) || !Array.isArray(config.shelters) || !Array.isArray(rows.notifications)) throw Error('Notification service response unavailable')
    if (!stopped.current) { setOptions(config); setHistory(rows) }
  }

  useEffect(() => {
    stopped.current = false
    load(offset).catch(e => { if (!stopped.current) setError(e.message) })
    return () => { stopped.current = true; for (const controller of controllers.current) controller.abort() }
  }, [session, offset])

  function change(setter, value) { setter(value); setPreview(null); setApproved(false); requestId.current = null; setError(null) }
  async function operation(action) {
    if (busyRef.current) return
    busyRef.current = true; setBusy(true); setError(null)
    try { await action() } catch (e) { if (!stopped.current) setError(e.message) }
    finally { busyRef.current = false; if (!stopped.current) setBusy(false) }
  }
  async function review(e) {
    e.preventDefault()
    await operation(async () => {
      requestId.current ||= crypto.randomUUID()
      const row = await call('/api/admin/notifications', { method: 'POST', body: JSON.stringify({ request_id: requestId.current, destination_id: destination, kind, message, shelter_id: shelter || null }) })
      if (!stopped.current) { setPreview(row); setApproved(false); await load() }
    })
  }
  async function send() {
    if (!approved || preview?.status !== 'draft') return
    await operation(async () => {
      // A lost HTTP response does not prove the external delivery failed.
      setPreview({ ...preview, status: 'sending' }); setApproved(false)
      const row = await call('/api/admin/notifications/' + preview.id + '/send', { method: 'POST', body: JSON.stringify({ approve: true, content_sha256: preview.content_sha256 }) }, 30000)
      if (!stopped.current) { setPreview(row); setApproved(false); await load() }
    })
  }
  function reset() { setMessage(''); setShelter(''); setPreview(null); setApproved(false); requestId.current = null; setError(null) }
  const enabled = options?.configured && options.destinations.length > 0
  return <section className="panel" aria-labelledby="admin-notifications-title">
    <h2 id="admin-notifications-title">Alerts — administrator-controlled Telegram notices</h2>
    <p>Every notice requires your review and explicit approval. Experimental rainfall outputs never trigger notifications. This prototype is not an official disaster-management service.</p>
    {session.mode === 'demonstration' && <p className="notice error">DEMONSTRATION ONLY. Only explicitly configured private test destinations are permitted. Simulated test results do not verify real Telegram delivery.</p>}
    {!options && !error && <p role="status">Loading notification configuration…</p>}
    {options && !enabled && <p role="status">{options.reason || 'No authorized destination is available for this environment'}. No messages will be sent.</p>}
    {error && <p role="alert">{error}</p>}
    <form className="shelter-form" aria-label="Telegram notification composer" onSubmit={review}>
      <label htmlFor="notice-destination">Telegram destination</label><select id="notice-destination" required disabled={busy || !enabled} value={destination} onChange={e => change(setDestination, e.target.value)}><option value="">Choose authorized destination</option>{options?.destinations.map(d => <option key={d.id} value={d.id}>{d.label}{d.test_only ? ' — private test only' : ''}</option>)}</select>
      <label htmlFor="notice-kind">Notification type</label><select id="notice-kind" disabled={busy || !enabled} value={kind} onChange={e => change(setKind, e.target.value)}><option value="informational">Informational</option><option value="emergency">Emergency — independently verified by administrator</option></select>
      <label>Notification message<textarea required maxLength={3500} disabled={busy || !enabled} value={message} onChange={e => change(setMessage, e.target.value)} /></label>
      <label htmlFor="notice-shelter">Include currently verified Open shelter</label><select id="notice-shelter" disabled={busy || !enabled} value={shelter} onChange={e => change(setShelter, e.target.value)}><option value="">No shelter information</option>{options?.shelters.map(s => <option key={s.id} value={s.id}>{s.name} — {s.district_name}</option>)}</select>
      <p>Use this selector for shelter details; the database snapshot is checked again before sending. Independently verify all factual claims. Do not invent flood probabilities, shelter availability or evacuation instructions from experimental ML.</p>
      <button disabled={busy || !enabled}>{busy ? 'Working…' : 'Review exact notification'}</button>
    </form>
    {preview && <div aria-label="Notification preview">
      <h3>Exact message preview — {preview.destination_label}</h3>
      <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', font: 'inherit' }}>{preview.text}</pre>
      <p role="status">{resultText(preview)}</p>
      {preview.status === 'draft' && <>
        <label><input type="checkbox" checked={approved} disabled={busy} onChange={e => setApproved(e.target.checked)} /> I reviewed this exact message and destination, verified its factual claims, and am authorized to send it.</label>
        <button disabled={busy || !approved || !enabled} onClick={send}>{busy ? 'Sending…' : 'Approve and send once through Telegram'}</button>
      </>}
      <button disabled={busy} onClick={reset}>Compose a new notice</button>
    </div>}
    <h3>Notification history</h3><button disabled={busy} onClick={() => operation(() => load())}>Refresh notification history</button>
    {history && !history.notifications.length && <p>No notification attempts or previews recorded.</p>}
    {history && <><p>{history.notifications.length} of {history.total} records shown.</p><ul aria-label="Notification history" className="shelter-list">{history.notifications.map(row => <li key={row.id}>
      <strong>{row.kind} — {row.destination_label}</strong><p>{resultText(row)}</p>
      <p>Created: {stamp(row.created_at)}. Approved: {stamp(row.confirmed_at)}. Attempt: {stamp(row.attempted_at)}. Result: {stamp(row.completed_at)}.</p>
      <p>Administrator: {row.created_by}. Result code: {row.result_code || 'None'}{row.telegram_error_code ? ' · Telegram code ' + row.telegram_error_code : ''}.</p>
      <details><summary>View recorded message</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', font: 'inherit' }}>{row.text}</pre></details>
    </li>)}</ul><button disabled={busy || offset === 0} onClick={() => setOffset(n => Math.max(0, n - 50))}>Previous notifications</button><button disabled={busy || offset + 50 >= history.total} onClick={() => setOffset(n => n + 50)}>Next notifications</button></>}
  </section>
}
