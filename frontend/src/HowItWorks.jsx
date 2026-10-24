import React from 'react'
import { PageLink } from './AppNavigation.jsx'
import { LEVEL_COLORS } from './useRisk.js'
import './HowItWorks.css'
import ScreenTabs from './ScreenTabs.jsx'

// Explains the risk index, the river flood forecast and which machine-learning models failed or work.
const PIPELINE = [
  ['Live data', 'Forecast rain, river flow, ground height (Open-Meteo); official warnings (IMD, NDMA SACHET); approved citizen reports'],
  ['Prediction', 'Flood and drainage risk index for the next 24 hours; 7-day river flood forecast (Copernicus GloFAS) for six checked rivers'],
  ['Map and app', 'Risk for any point in Karnataka, nearby risky spots, statewide map, verified shelters and routes to them (not certified flood-safe)'],
  ['Early warning', 'Suggested alert drafts → an administrator checks and approves → Telegram'],
]
const FACTORS = [
  ['Forecast rain, next 24 h', 'IMD rain categories: heavy 64.5 mm, very heavy 115.6 mm, extremely heavy 204.5 mm', 'Flood and drainage'],
  ['Peak hourly rain', 'Short bursts overwhelm drains even when the daily total is modest', 'Drainage'],
  ['Rain in the past 5 days', 'Wet ground cannot absorb more water, so runoff rises', 'Flood and drainage'],
  ['River flow forecast', 'GloFAS forecast vs the 2- and 5-year flood levels of the nearest ~5 km model cell (river not verified)', 'Flood'],
  ['Ground height', 'Low-lying land floods first (Copernicus GLO-90 elevation)', 'Flood'],
  ['Past floods', 'Satellite-mapped floods from the Global Flood Database (two Udupi floods, 2005 and 2009)', 'Flood'],
  ['Approved citizen reports', 'Recent reports of blocked drains or flooding, checked by an administrator', 'Drainage'],
]
export default function HowItWorks({ navigate }) {
  // One-screen rule: each section is a tab, so nothing scrolls during a presentation.
  return <div className="how">
    <ScreenTabs mode="always" label="How FloodPulse works" tabs={[
      { id: 'pipeline', label: 'Overview', content: <>
    <section className="panel how-intro" aria-labelledby="how-pipeline">
      <h2 id="how-pipeline">From live data to an early warning</h2>
      <ol className="how-pipeline">{PIPELINE.map(([title, text]) => <li key={title}><strong>{title}</strong><span>{text}</span></li>)}</ol>
      <p className="muted">Works for any point in Karnataka. Official warnings are shown exactly as issued; FloodPulse's own prediction is always labelled experimental and is never presented as a flood probability.</p>
    </section>
      </> },
      { id: 'index', label: 'Risk index', content: <>
    <section className="panel" aria-labelledby="how-index">
      <h2 id="how-index">How the flood and drainage risk is calculated</h2>
      <p>Each factor below adds points when it passes a threshold: IMD's official rain categories where they exist, otherwise project-chosen thresholds that are stated in the panel. The total gives a level, and the <strong>"Why?"</strong> panel on Home shows every factor's value for your place.</p>
      <div className="how-levels" aria-label="Risk levels">{['low', 'moderate', 'high', 'severe'].map(l => <span key={l} style={{ '--swatch': LEVEL_COLORS[l] }}>{l[0].toUpperCase() + l.slice(1)}</span>)}</div>
      <div className="how-table"><table>
        <thead><tr><th>Factor</th><th>Why it matters</th><th>Affects</th></tr></thead>
        <tbody>{FACTORS.map(([f, why, risk]) => <tr key={f}><td><strong>{f}</strong></td><td>{why}</td><td>{risk}</td></tr>)}</tbody>
      </table></div>
      <p className="muted">Flood risk is about rivers and low land. Drainage risk is about water that cannot drain away in towns.</p>
      <p className="muted">Separately, the Flood Map's <strong>Rivers</strong> tab compares the 50-run GloFAS river forecast with each river's own 2-, 5- and 10-year flood levels at six points (Krishna, Ghataprabha, Kabini, Netravati, Tungabhadra, Kali). Each point was kept only because its model cell lies on that river in OpenStreetMap and its largest past flows match documented floods.</p>
    </section>
      </> },
      { id: 'ml', label: 'AI models', content: <>
    <section className="panel" aria-labelledby="how-ml">
      <h2 id="how-ml">Machine learning: what failed and what works</h2>
      <h3>Failed: predicting district "flood days" from flood reports</h3>
      <p>The India Flood Inventory has no confirmed "no flood" days, and reporting grew about 24 times (0.39% of days in 1969–94, 9.31% in 2011–23), so the labels partly measure reporting. Those models did not beat a simple rainfall rule, so the risk index above stays rule-based.</p>
      <h3>Works: the AI river flood model</h3>
      <p>A model trained by FloodPulse predicts whether a river will rise above its 2-year flood level within 3 days, from rain over its upstream catchment (e.g. near Mahabaleshwar for the Krishna — in August 2019 Kudachi had 196 mm while the upstream catchment had 1,513 mm). Trained on 1997–2015, tested on 2016–2021: it beat a simple rain rule on 5 of 6 rivers and flagged all 5 documented floods in those years 1–4 days ahead. It learned from GloFAS river flow, because measured Karnataka gauge data are not available, so it cannot be more accurate than GloFAS. See Flood Map → Rivers.</p>
    </section>
      </> },
      { id: 'next', label: 'Next steps', content: <>
    <section className="panel" aria-labelledby="how-next">
      <h2 id="how-next">Building a true flood AI model</h2>
      <ol className="how-steps">
        <li><strong>Collect verified evidence:</strong> citizens report flooding with the in-app GPS camera (photo, location and time recorded together).</li>
        <li><strong>Check it:</strong> administrators approve or reject each report with a reason.</li>
        <li><strong>Label it:</strong> approved reports (only with the reporter's separate consent to training) plus satellite flood maps give confirmed flood places and dates.</li>
        <li><strong>Train and test:</strong> on held-out places and dates; deploy only if it beats the current index.</li>
      </ol>
      <p><PageLink to="/report" navigate={navigate}>Report flooding</PageLink> · <PageLink to="/flood-map" navigate={navigate}>See the risk map</PageLink></p>
    </section>
      </> },
      { id: 'sources', label: 'Sources', content: <>
    <section className="panel" aria-labelledby="how-sources">
      <h2 id="how-sources">Data sources</h2>
      <ul className="how-sources">
        <li><a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Open-Meteo</a>: forecast weather, GloFAS river flow, elevation (CC BY 4.0)</li>
        <li><a href="https://mausam.imd.gov.in/responsive/districtWiseWarningGIS.php" target="_blank" rel="noopener noreferrer">India Meteorological Department</a>: district warnings</li>
        <li><a href="https://sachet.ndma.gov.in/" target="_blank" rel="noopener noreferrer">NDMA SACHET</a>: official disaster alerts</li>
        <li><a href="https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1" target="_blank" rel="noopener noreferrer">Global Flood Database</a>: satellite-mapped past floods (CC BY-NC 4.0)</li>
        <li>India Flood Inventory and ERA5 reanalysis: data for the machine-learning test</li>
        <li><a href="https://openrouteservice.org/" target="_blank" rel="noopener noreferrer">openrouteservice</a> and <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>: routes and maps</li>
      </ul>
    </section>
      </> }
    ]} />
  </div>
}
