import React from 'react'
import { PageLink } from './AppNavigation.jsx'
import { LEVEL_COLORS } from './useRisk.js'
import './HowItWorks.css'
import ScreenTabs from './ScreenTabs.jsx'

// Explains the risk index and why it is rule-based rather than a trained flood model.
const PIPELINE = [
  ['Live data', 'Forecast rain, river flow, ground height (Open-Meteo); official warnings (IMD, NDMA SACHET); approved citizen reports'],
  ['Prediction', 'Flood and drainage risk index for the next 24 hours'],
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
    </section>
      </> },
      { id: 'ml', label: 'Why not ML', content: <>
    <section className="panel" aria-labelledby="how-ml">
      <h2 id="how-ml">The machine-learning experiment</h2>
      <p>Before building the index, we tested whether machine learning could predict flood days for Karnataka's districts from historical weather and the India Flood Inventory's flood records.</p>
      <h3>Result: the models did not beat a simple rainfall rule, and the records cannot support a trained flood model</h3>
      <ul>
        <li><strong>No confirmed "no flood" days exist.</strong> The flood inventory lists reported floods; a day without a report is unknown, not dry.</li>
        <li><strong>Reporting grew about 24 times</strong> (0.39% of days in 1969–94, 9.31% in 2011–23), so the labels partly measure reporting, not flooding.</li>
        <li><strong>No historical river-gauge data</strong> is available to train on.</li>
      </ul>
      <p>So FloodPulse uses the explainable index above instead of a trained flood model, and labels it experimental.</p>
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
