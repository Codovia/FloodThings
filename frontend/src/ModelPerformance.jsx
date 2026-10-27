import React, { useEffect, useState } from 'react'
import { PageLink } from './AppNavigation.jsx'
import ScreenTabs from './ScreenTabs.jsx'
import './HowItWorks.css'
import './ModelPerformance.css'

// Research view of FloodPulse's two trained models. Every number comes from /api/models/performance, which reads
// the recorded held-out test results from the model artifacts; nothing here is computed from live data or invented.
const pct = v => `${Math.round(v * 100)}%`
const f2 = v => v.toFixed(2)
const SERIES = [['model', 'AI model'], ['rain_rule', 'Simple rain rule']]

function Stat({ value, label, note }) {
  return <div className="mp-stat"><strong>{value}</strong><span>{label}</span>{note && <small>{note}</small>}</div>
}

// Grouped bars: F1 on the 2016–2021 test years, AI model vs the best single 3-day rain rule, per river.
export function F1Chart({ rivers }) {
  const [hover, setHover] = useState(null)
  const row = 34, left = 112, right = 44, width = 520, top = 8, height = top + rivers.length * row + 22
  const x = v => left + v * (width - left - right)
  const bar = (v, y) => { const w = Math.max(x(v) - left, 0), h = 11, r = Math.min(4, w); return `M${left} ${y}h${w - r}a${r} ${r} 0 0 1 ${r} ${r}v${h - 2 * r}a${r} ${r} 0 0 1 -${r} ${r}h-${w - r}z` }
  return <figure className="mp-chart">
    <figcaption><span className="mp-legend">{SERIES.map(([k, name]) => <span key={k} className={`mp-key mp-${k}`}>{name}</span>)}</span> F1 score on test years 2016–2021 (higher is better)</figcaption>
    <div className="mp-chart-box">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="F1 score per river: AI model compared with the simple rain rule. The table tab lists the same numbers.">
        {[0, .25, .5, .75, 1].map(t => <g key={t}><line x1={x(t)} x2={x(t)} y1={top - 4} y2={height - 20} className="mp-grid" /><text x={x(t)} y={height - 6} className="mp-tick" textAnchor="middle">{t}</text></g>)}
        {rivers.map((r, i) => { const y = top + i * row
          return <g key={r.id} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <rect x="0" y={y - 3} width={width} height={row - 2} className="mp-hit" />
            <text x={left - 8} y={y + 10} textAnchor="end" className="mp-label">{r.river}</text>
            <text x={left - 8} y={y + 22} textAnchor="end" className="mp-sub">{r.served ? r.place : 'rule kept'}</text>
            <path d={bar(r.model.f1, y)} className="mp-bar mp-model" />
            <path d={bar(r.rain_rule.f1, y + 13)} className="mp-bar mp-rain_rule" />
            <text x={x(r.model.f1) + 4} y={y + 9} className="mp-value">{f2(r.model.f1)}</text>
            <text x={x(r.rain_rule.f1) + 4} y={y + 22} className="mp-value">{f2(r.rain_rule.f1)}</text>
          </g> })}
      </svg>
      {hover !== null && <div className="mp-tooltip" style={{ top: `${((top + hover * row + row) / height) * 100}%` }} role="status">
        <strong>{rivers[hover].river} at {rivers[hover].place}</strong>
        {SERIES.map(([k, name]) => <span key={k}><i className={`mp-dot mp-${k}`} />{name}: F1 {f2(rivers[hover][k].f1)} · precision {pct(rivers[hover][k].precision)} · recall {pct(rivers[hover][k].recall)}</span>)}
      </div>}
    </div>
  </figure>
}

function Matrix({ title, m }) {
  return <div className="mp-matrix" role="group" aria-label={title}>
    <h4>{title}</h4>
    <table>
      <thead><tr><th scope="col"></th><th scope="col">Flood level reached</th><th scope="col">Not reached</th></tr></thead>
      <tbody>
        <tr><th scope="row">Warned</th><td className="mp-good">{m.tp}<small>hits</small></td><td className="mp-bad">{m.fp}<small>false alarms</small></td></tr>
        <tr><th scope="row">Not warned</th><td className="mp-bad">{m.fn}<small>missed</small></td><td>{m.tn}<small>correct quiet</small></td></tr>
      </tbody>
    </table>
    <p>Precision {pct(m.precision)} · Recall {pct(m.recall)} · F1 {f2(m.f1)}</p>
  </div>
}

export default function ModelPerformance({ navigate }) {
  const [state, setState] = useState({ status: 'loading', data: null })
  const [river, setRiver] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/models/performance', { signal: controller.signal }).then(r => r.ok ? r.json() : Promise.reject(Error()))
      .then(data => setState({ status: 'ready', data }), () => { if (!controller.signal.aborted) setState({ status: 'error', data: null }) })
    return () => controller.abort()
  }, [])
  if (state.status !== 'ready') return <section className="panel"><p role={state.status === 'error' ? 'alert' : 'status'}>{state.status === 'error' ? 'Model results are unavailable right now. Nothing is shown instead of them.' : 'Loading the recorded test results…'}</p></section>
  const { river_flood: rf, rainfall: rain } = state.data, s = rf.summary, chosen = rf.rivers[river]
  const floods = rf.rivers.flatMap(r => r.documented_floods.map(f => ({ ...f, river: r.river, place: r.place }))).sort((a, b) => a.date.localeCompare(b.date))
  return <div className="how model-performance">
    <ScreenTabs mode="always" label="Model performance" tabs={[
      { id: 'summary', label: 'Summary', content: <section className="panel" aria-labelledby="mp-summary">
        <h2 id="mp-summary">AI river flood model: results on years it never saw</h2>
        <p>The model predicts whether a river will rise above its 2-year flood level within 3 days, from rain over its upstream catchment. It was trained on {rf.train_years[0]}–{rf.train_years[1]} and tested on {rf.test_years[0]}–{rf.test_years[1]}, which were never used for fitting or for choosing thresholds.</p>
        <div className="mp-stats">
          <Stat value={`${s.beat_rain_rule} of ${s.rivers}`} label="rivers where the AI model beat a simple rain rule (F1)" note="The rule is kept where it did not" />
          <Stat value={`${s.documented_floods_flagged} of ${s.documented_floods}`} label="documented floods in the test years flagged 1–4 days ahead" />
          <Stat value={`${rain.model.tp} of ${rain.model.tp + rain.model.fn}`} label={`heavy-rain days caught by the rainfall model in ${rain.testing.first_cutoff.slice(0, 4)} (recall ${pct(rain.model.recall)})`} note={`Precision ${pct(rain.model.precision)}: it warns often`} />
        </div>
        <div className="mp-timeline" aria-label={`Training years ${rf.train_years.join('–')}, test years ${rf.test_years.join('–')}`}>
          <span className="mp-train">Training {rf.train_years.join('–')}</span><span className="mp-test">Test {rf.test_years.join('–')}</span>
        </div>
        <p className="muted">Experimental research results, not an official warning. Accuracy is measured against GloFAS modelled river flow, because measured Karnataka gauge data are not available.</p>
      </section> },
      { id: 'rivers', label: 'River model', content: <section className="panel" aria-labelledby="mp-rivers">
        <h2 id="mp-rivers">AI model vs a simple rain rule, per river</h2>
        <F1Chart rivers={rf.rivers} />
        <p className="muted">F1 combines precision (of the days it warned, how many the river did rise) and recall (of the days the river rose, how many it warned). The rain rule is the best single "3-day catchment rain above X mm" threshold, chosen on the training years.</p>
      </section> },
      { id: 'table', label: 'Table', content: <section className="panel" aria-labelledby="mp-table">
        <h2 id="mp-table">Test results, {rf.test_years.join('–')}</h2>
        <div className="how-table"><table>
          <thead><tr><th>River (place)</th><th>Flood days</th><th>AI model P / R / F1</th><th>Rain rule P / R / F1</th><th>Used live</th></tr></thead>
          <tbody>{rf.rivers.map(r => <tr key={r.id}><td><strong>{r.river}</strong> ({r.place})</td><td className="num">{r.test.positives} of {r.test.days}</td>
            {SERIES.map(([k]) => <td key={k} className="num">{pct(r[k].precision)} / {pct(r[k].recall)} / {f2(r[k].f1)}</td>)}<td>{r.served ? 'AI model' : 'Rain rule'}</td></tr>)}</tbody>
        </table></div>
      </section> },
      { id: 'matrix', label: 'Confusion matrix', content: <section className="panel" aria-labelledby="mp-matrix">
        <h2 id="mp-matrix">What the warnings got right and wrong (test days)</h2>
        <div className="mp-river-picker" role="group" aria-label="Choose a river">{rf.rivers.map((r, i) => <button key={r.id} type="button" aria-pressed={i === river} onClick={() => setRiver(i)}>{r.river}</button>)}</div>
        <div className="mp-matrices"><Matrix title={`AI model · ${chosen.river} at ${chosen.place}`} m={chosen.model} /><Matrix title={`Rain rule (3-day rain ≥ ${chosen.rain_rule_3d_mm} mm)`} m={chosen.rain_rule} /></div>
        <p className="muted">One cell is a day in {rf.test_years.join('–')}. "Correct quiet" days are test days minus the other three cells.</p>
      </section> },
      { id: 'floods', label: 'Real floods', content: <section className="panel" aria-labelledby="mp-floods">
        <h2 id="mp-floods">Documented floods in the test years</h2>
        <div className="how-table"><table>
          <thead><tr><th>Date</th><th>River (place)</th><th>AI model warned 1–4 days before</th><th>Rain rule warned</th></tr></thead>
          <tbody>{floods.map(f => <tr key={f.date + f.river}><td className="num">{f.date}</td><td>{f.river} ({f.place})</td><td>{f.model_flagged ? 'Yes' : 'No'}</td><td>{f.rule_flagged ? 'Yes' : 'No'}</td></tr>)}</tbody>
        </table></div>
        <p className="muted">These are the documented floods that fall in the test years at the six river points; Tungabhadra (Hampi) had none.</p>
      </section> },
      { id: 'rainfall', label: 'Rainfall model', content: <section className="panel" aria-labelledby="mp-rain">
        <h2 id="mp-rain">AI heavy-rainfall model ({rain.version})</h2>
        <p>Predicts whether the next 24 hours will bring at least {rain.target.threshold_mm} mm (IMD "heavy" rain) at {rain.locations.join(' and ')}. Trained on {rain.training.samples} six-hourly cases from {rain.training.first_cutoff.slice(0, 4)}–{rain.training.last_cutoff.slice(0, 4)}, tested on {rain.testing.samples} from {rain.testing.first_cutoff.slice(0, 4)}.</p>
        <div className="mp-matrices"><Matrix title="AI rainfall model" m={rain.model} /><Matrix title='Baseline: always "no heavy rain"' m={rain.baseline} /></div>
      </section> },
      { id: 'method', label: 'Method & limits', content: <section className="panel" aria-labelledby="mp-method">
        <h2 id="mp-method">Method and limitations</h2>
        <dl className="how-card">
          <div><dt>River target</dt><dd>{rf.target}</dd></div>
          <div><dt>River inputs</dt><dd>Catchment rain over 1, 3, 5, 10 and 30 days, the wettest cell's 3-day rain, and season. No river flow is used as an input.</dd></div>
          <div><dt>Rain target</dt><dd>{rain.target.definition}</dd></div>
        </dl>
        <ul className="how-steps">{[...rf.limitations, ...rain.limitations].map(t => <li key={t}>{t}</li>)}</ul>
        <p><PageLink to="/how-it-works" navigate={navigate}>How FloodPulse predicts</PageLink> · <PageLink to="/flood-map" navigate={navigate}>River forecasts on the Flood Map</PageLink></p>
      </section> },
    ]} />
  </div>
}
