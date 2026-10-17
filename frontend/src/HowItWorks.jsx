import React from 'react'
import { PageLink } from './AppNavigation.jsx'
import { LEVEL_COLORS } from './useRisk.js'
import './HowItWorks.css'

// Explains the prediction pipeline, the trained models and the evidence behind each choice.
// Every figure here comes from the project's recorded experiments (see docs and git tag archive/research-2026-10-16).
const PIPELINE = [
  ['Live data', 'Forecast rain, river flow, ground height (Open-Meteo); official warnings (IMD, NDMA SACHET); approved citizen reports'],
  ['Prediction', 'Flood and drainage risk index for the next 24 hours, plus the trained AI rainfall model where it is validated'],
  ['Map and app', 'Risk for any point in Karnataka, nearby risky spots, statewide map, shelters and safe routes'],
  ['Early warning', 'Suggested alert drafts → an administrator checks and approves → Telegram'],
]
const FACTORS = [
  ['Forecast rain, next 24 h', 'IMD rain categories: heavy 64.5 mm, very heavy 115.6 mm, extremely heavy 204.5 mm', 'Flood and drainage'],
  ['Peak hourly rain', 'Short bursts overwhelm drains even when the daily total is modest', 'Drainage'],
  ['Rain in the past 5 days', 'Wet ground cannot absorb more water, so runoff rises', 'Flood and drainage'],
  ['River flow forecast', 'GloFAS forecast compared with the river\'s 2-, 5- and 20-year flood levels', 'Flood'],
  ['Ground height', 'Low-lying land floods first (Copernicus GLO-90 elevation)', 'Flood'],
  ['Past floods', 'Satellite-mapped floods from the Global Flood Database', 'Flood'],
  ['Approved citizen reports', 'Recent reports of blocked drains or flooding, checked by an administrator', 'Drainage'],
]
const BENCHMARK = [
  ['Rule: more rain in the last 3 days = more risk', 0.83, '8.3%', true],
  ['Logistic Regression', 0.81, '10.0%'],
  ['LightGBM (unconstrained)', 0.79, '0.0%'],
  ['LightGBM (monotonic)', 0.78, '3.3%'],
  ['Random Forest', 0.74, '0.8%'],
  ['PU Bagging', 0.73, '0.8%'],
]

export default function HowItWorks({ navigate }) {
  return <div className="how">
    <section className="panel how-intro" aria-labelledby="how-pipeline">
      <h2 id="how-pipeline">From live data to an early warning</h2>
      <ol className="how-pipeline">{PIPELINE.map(([title, text]) => <li key={title}><strong>{title}</strong><span>{text}</span></li>)}</ol>
      <p className="muted">Works for any point in Karnataka. Official warnings are shown exactly as issued; FloodPulse's own prediction is always labelled experimental and is never presented as a flood probability.</p>
    </section>

    <section className="panel" aria-labelledby="how-index">
      <h2 id="how-index">How the flood and drainage risk is calculated</h2>
      <p>Each factor below adds points according to a published threshold. The total gives a level, and the <strong>"Why?"</strong> panel on Home shows every factor's value for your place.</p>
      <div className="how-levels" aria-label="Risk levels">{['low', 'moderate', 'high', 'severe'].map(l => <span key={l} style={{ '--swatch': LEVEL_COLORS[l] }}>{l[0].toUpperCase() + l.slice(1)}</span>)}</div>
      <div className="how-table"><table>
        <thead><tr><th>Factor</th><th>Why it matters</th><th>Affects</th></tr></thead>
        <tbody>{FACTORS.map(([f, why, risk]) => <tr key={f}><td><strong>{f}</strong></td><td>{why}</td><td>{risk}</td></tr>)}</tbody>
      </table></div>
      <p className="muted">Flood risk is about rivers and low land. Drainage risk is about water that cannot drain away in towns.</p>
    </section>

    <section className="panel" aria-labelledby="how-ml">
      <h2 id="how-ml">The machine-learning experiment</h2>
      <p>We trained six methods to predict flood days for all <strong>31 districts</strong>, using <strong>434,744 district-days</strong> of weather (1969–1994 and 2011–2023) and flood records from the India Flood Inventory. Each was trained on earlier years and tested on unseen years (2022–2023).</p>
      <div className="how-table"><table>
        <thead><tr><th>Method</th><th>ROC-AUC</th><th aria-label="Ranking score bar"></th><th>Floods caught</th></tr></thead>
        <tbody>{BENCHMARK.map(([name, auc, caught, best]) => <tr key={name} className={best ? 'best' : ''}>
          <td>{best ? <strong>{name}</strong> : name}</td><td className="num">{auc.toFixed(2)}</td>
          <td className="bar-cell"><span className="how-bar"><i style={{ width: `${(auc - 0.5) / 0.5 * 100}%` }} /></span></td><td className="num">{caught}</td></tr>)}</tbody>
      </table></div>
      <p className="muted">ROC-AUC measures how well a method ranks real flood days above other days: 1.0 is perfect, 0.5 is guessing. Bars start at 0.5.</p>
      <h3>Result: no ML model beat the simple rainfall rule</h3>
      <ul>
        <li><strong>No confirmed "no flood" days exist.</strong> The flood inventory lists reported floods; a day without a report is unknown, not dry.</li>
        <li><strong>Reporting grew about 24 times</strong> (0.39% of days in 1969–94, 9.31% in 2011–23), so the labels partly measure reporting, not flooding.</li>
        <li><strong>No historical river-gauge data</strong> is available to train on.</li>
      </ul>
      <p>So FloodPulse uses the explainable index above for flood and drainage risk, and uses machine learning where the training labels are reliable.</p>
    </section>

    <section className="panel" aria-labelledby="how-rain">
      <h2 id="how-rain">The AI rainfall model in use</h2>
      <dl className="how-card">
        <div><dt>Predicts</dt><dd>Whether rain will reach 64.5 mm (IMD "heavy rain") in the next 24 hours</dd></div>
        <div><dt>Method</dt><dd>Logistic regression (scikit-learn), 8 weather features: rain over 24 and 72 hours, peak hourly rain, humidity, pressure, temperature, season</dd></div>
        <div><dt>Training data</dt><dd>8,768 daily examples from the two locations; tested on later, unseen data</dd></div>
        <div><dt>Results</dt><dd>Caught 88 of 96 heavy-rain days (recall 0.92). About 1 in 7 alerts was a real heavy-rain day (precision 0.145), so it is a "watch out" signal, not a forecast.</dd></div>
        <div><dt>Where</dt><dd>Kundapur and Mangaluru, the two points whose data was verified</dd></div>
      </dl>
      <p><PageLink to="/weather" navigate={navigate}>Open the weather page</PageLink> and choose Kundapur or Mangaluru to run it.</p>
    </section>

    <section className="panel" aria-labelledby="how-next">
      <h2 id="how-next">Building a true flood AI model</h2>
      <ol className="how-steps">
        <li><strong>Collect verified evidence:</strong> citizens report flooding with the in-app GPS camera (photo, location and time recorded together).</li>
        <li><strong>Check it:</strong> administrators approve or reject each report with a reason.</li>
        <li><strong>Label it:</strong> approved reports plus satellite flood maps give confirmed flood places and dates.</li>
        <li><strong>Train and test:</strong> on held-out places and dates; deploy only if it beats the current index.</li>
      </ol>
      <p><PageLink to="/report" navigate={navigate}>Report flooding</PageLink> · <PageLink to="/flood-map" navigate={navigate}>See the risk map</PageLink></p>
    </section>

    <section className="panel" aria-labelledby="how-sources">
      <h2 id="how-sources">Data sources</h2>
      <ul className="how-sources">
        <li><a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Open-Meteo</a>: forecast weather, GloFAS river flow, elevation (CC BY 4.0)</li>
        <li><a href="https://mausam.imd.gov.in/responsive/districtWiseWarningGIS.php" target="_blank" rel="noopener noreferrer">India Meteorological Department</a>: district warnings</li>
        <li><a href="https://sachet.ndma.gov.in/" target="_blank" rel="noopener noreferrer">NDMA SACHET</a>: official disaster alerts</li>
        <li><a href="https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1" target="_blank" rel="noopener noreferrer">Global Flood Database</a>: satellite-mapped past floods (CC BY-NC 4.0)</li>
        <li>India Flood Inventory and ERA5 reanalysis: historical training data</li>
        <li><a href="https://openrouteservice.org/" target="_blank" rel="noopener noreferrer">openrouteservice</a> and <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>: routes and maps</li>
      </ul>
    </section>
  </div>
}
