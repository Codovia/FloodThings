import React from 'react'

// Official public numbers, verified 17 Oct 2026: 112 is India's Emergency Response Support System
// (police, fire, ambulance, disasters; live in Karnataka since 2019); 080-1070 is the toll-free
// Karnataka State Emergency Operation Centre (Revenue Department, Disaster Management).
export const EMERGENCY_CONTACTS = [
  { number: '112', tel: '112', label: 'Emergency — police, fire, ambulance, disasters' },
  { number: '080-1070', tel: '0801070', label: 'Karnataka State Emergency Operation Centre (toll-free, 24×7)' },
]

export default function OfficialHelp({ prominent = false }) {
  return <section className={'official-help' + (prominent ? ' prominent' : '')} aria-labelledby="official-help-title">
    <h3 id="official-help-title">In danger now? Call official help</h3>
    <ul>{EMERGENCY_CONTACTS.map(c => <li key={c.number}><a href={`tel:${c.tel}`}>{c.number}</a> <span>{c.label}</span></li>)}</ul>
    <p className="muted">Follow evacuation orders from your district administration. FloodPulse does not dispatch help.</p>
  </section>
}
