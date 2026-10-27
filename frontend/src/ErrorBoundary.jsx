import React from 'react'

const errorId = () => Array.from(crypto.getRandomValues(new Uint8Array(6)), b => b.toString(16).padStart(2, '0')).join('')
let reported = 0
// Sends only the page path and a short message (see backend/app/client_errors.py); at most three per page load.
export function reportError(error) {
  const id = errorId()
  if (error?.name === 'AbortError') return id  // a request the app cancelled on purpose
  if (reported++ < 3) {
    const message = String(error?.message || error || 'unknown').slice(0, 300) || 'unknown'
    fetch('/api/client-errors', { method: 'POST', headers: { 'Content-Type': 'application/json' }, keepalive: true,
      body: JSON.stringify({ error_id: id, page: window.location.pathname.replace(/[^A-Za-z0-9/_-]/g, '').slice(0, 81) || '/', message }) }).catch(() => {})
  }
  return id
}

// A crash anywhere in the app shows a way forward instead of a blank page.
export default class ErrorBoundary extends React.Component {
  state = { id: null }
  static getDerivedStateFromError() { return { id: 'pending' } }
  componentDidCatch(error) { this.setState({ id: reportError(error) }) }
  render() {
    if (!this.state.id) return this.props.children
    return <main className="app-content crash-screen" role="alert">
      <section className="panel">
        <h1>Something went wrong on this page</h1>
        <p>FloodPulse hit an unexpected problem. Reloading usually fixes it. Official warnings stay available from IMD and NDMA SACHET; in an emergency call <a href="tel:112">112</a>.</p>
        <p><button type="button" onClick={() => window.location.reload()}>Reload the page</button> <a className="button-link" href="/">Go to Home</a></p>
        {this.state.id !== 'pending' && <p className="muted">Error ID: {this.state.id} (quote it if you report the problem).</p>}
      </section>
    </main>
  }
}
