import React from 'react'
import { usePaged, Pager } from './ScreenTabs.jsx'

// Turn-by-turn steps, eight at a time, so the list never scrolls (one-screen rule).
const PER_PAGE = 8
export default function RouteSteps({ steps }) {
  const paged = usePaged(steps, PER_PAGE)
  return <>
    <ol className="route-steps" start={paged.page * PER_PAGE + 1}>{paged.items.map((step, i) => <li key={paged.page * PER_PAGE + i}>{step.instruction} ({step.distance_m} m)</li>)}</ol>
    <Pager paged={paged} label="More directions" />
  </>
}
