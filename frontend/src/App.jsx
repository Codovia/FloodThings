import { useState, useEffect } from 'react';

/**
 * FloodPulse — Phase 2.1 Foundation
 *
 * Minimal application shell that fetches real backend health status.
 * No flood features, maps, or predictions — those belong to later phases.
 */

const API_BASE = '/api';

function StatusIndicator({ label, status, detail }) {
  const statusClass =
    status === 'ok' ? 'status-ok' :
    status === 'loading' ? 'status-loading' :
    'status-error';

  return (
    <div className="status-row">
      <span className="status-label">{label}</span>
      <span className={`status-badge ${statusClass}`}>
        {status === 'loading' ? '…' : status}
      </span>
      {detail && <span className="status-detail">{detail}</span>}
    </div>
  );
}

function App() {
  const [health, setHealth] = useState({ status: 'loading' });
  const [dbHealth, setDbHealth] = useState({ status: 'loading' });
  const [gisHealth, setGisHealth] = useState({ status: 'loading' });

  useEffect(() => {
    async function fetchHealth(endpoint, setter) {
      try {
        const response = await fetch(`${API_BASE}${endpoint}`);
        if (!response.ok) {
          setter({ status: 'error', detail: `HTTP ${response.status}` });
          return;
        }
        const data = await response.json();
        setter(data);
      } catch (err) {
        setter({ status: 'unreachable', detail: err.message });
      }
    }

    fetchHealth('/health', setHealth);
    fetchHealth('/health/database', setDbHealth);
    fetchHealth('/health/postgis', setGisHealth);
  }, []);

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">FloodPulse</h1>
        <p className="app-subtitle">
          Karnataka AI Flood Intelligence &amp; Early-Warning System
        </p>
        <p className="app-region">Karnataka, India</p>
      </header>

      <main className="app-main">
        <section className="status-section" id="system-health">
          <h2>System Health</h2>
          <div className="status-grid">
            <StatusIndicator label="API" status={health.status} />
            <StatusIndicator label="Database" status={dbHealth.status} detail={dbHealth.detail} />
            <StatusIndicator
              label="PostGIS"
              status={gisHealth.status}
              detail={gisHealth.postgis_version || gisHealth.detail}
            />
          </div>
        </section>

        <section className="status-section" id="phase-info">
          <h2>Current Phase</h2>
          <p className="status-note">
            Phase 2.1 — Project Foundation. Data sources, predictions, and
            emergency response features will be added in subsequent development
            phases.
          </p>
          <p className="status-note" style={{ marginTop: '0.5rem', fontSize: '0.8125rem' }}>
            This is a decision-support system. It does not replace official
            government flood warnings.
          </p>
        </section>
      </main>

      <footer className="app-footer">
        <p>FloodPulse &mdash; Phase 2.1 Foundation</p>
      </footer>
    </div>
  );
}

export default App;
