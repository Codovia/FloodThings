import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import OfficialWarnings, { OfficialSummary } from './OfficialWarnings.jsx'
import { validOfficial } from './useRisk.js'

afterEach(cleanup)
// TEST FIXTURE ONLY — shape of /api/official/warnings, invented values.
const days = [['2026-10-16', 'orange', ['Very heavy rain']], ['2026-10-17', 'yellow', ['Heavy rain']], ['2026-10-18', 'green', []],
  ['2026-10-19', null, []], ['2026-10-20', 'green', []]].map(([date, level, warnings]) => ({ date, level, warnings, status: level ? 'available' : 'unavailable' }))
const data = { official: true, label: 'Official warnings as issued — TEST.', generated_at: '2026-10-16T10:00:00Z',
  imd: { status: 'available', district: 'Udupi', issued_date: '2026-10-16', updated_at: '2026-10-16T08:00:00Z', days, source: { url: 'https://mausam.imd.gov.in/' } },
  sachet: { status: 'available', alerts: [{ identifier: 'IN-1_19', event: 'Heavy rain', severity: 'Severe', headline: 'TEST ONLY headline over Udupi', sender: 'TEST-SDMA',
    expires: '2026-10-16T12:00:00+05:30', instruction: 'Follow SDMA guidelines.', names_your_district: true }], checked_messages: 3, unreadable_messages: 0,
    retrieved_at: '2026-10-16T10:00:00Z', source: { url: 'https://sachet.ndma.gov.in/' } } }
const state = d => ({ data: d, loading: false, error: null, refresh: vi.fn() })
const point = { name: 'Fixture', latitude: 13.6, longitude: 74.7, kind: 'gps', accuracy_m: 20 }

it('validates and shows the IMD five-day strip and active SACHET alerts as issued', () => {
  expect(validOfficial(data)).toBe(true); expect(validOfficial({ ...data, official: false })).toBe(false)
  render(<OfficialWarnings official={state(data)} point={point} />)
  const strip = screen.getByRole('list', { name: 'IMD five-day district warnings' })
  expect(strip.textContent).toMatch(/Orange.*Very heavy rain.*Yellow.*Heavy rain.*Green.*No warning.*Unavailable/)
  expect(screen.getByText('Names your district')).toBeTruthy(); expect(screen.getByText('TEST ONLY headline over Udupi')).toBeTruthy()
  render(<OfficialSummary official={state(data)} point={point} />)
  expect(screen.getByText(/Official IMD warning for/).textContent).toMatch(/Udupi.*Orange.*Very heavy rain.*1 active NDMA SACHET alert in Karnataka/)
})

it('never turns a failure or an empty feed into "no warning"', () => {
  render(<OfficialWarnings official={{ data: null, loading: false, error: 'Risk request timed out.', refresh: vi.fn() }} point={point} />)
  expect(screen.getByText(/This does not mean there is no warning/)).toBeTruthy()
  cleanup()
  const quiet = { ...data, sachet: { ...data.sachet, alerts: [] }, imd: { status: 'unavailable', message: 'IMD down — TEST. This does not mean there is no warning.' } }
  render(<OfficialWarnings official={state(quiet)} point={{ ...point, kind: 'network' }} />)
  expect(screen.getByText(/No active SACHET alert for Karnataka right now \(3 recent messages checked\)/)).toBeTruthy()
  expect(screen.getByText(/IMD down — TEST/)).toBeTruthy()
})

it('warns that a network-estimate district may be wrong', () => {
  render(<OfficialWarnings official={state(data)} point={{ ...point, kind: 'network' }} />)
  expect(screen.getByText(/district may be wrong/)).toBeTruthy()
})
