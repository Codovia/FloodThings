import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ImdCard, SachetCard } from './OfficialWarnings.jsx'
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

it('validates and highlights today, then the following IMD days, and active SACHET alerts as issued', () => {
  expect(validOfficial(data)).toBe(true); expect(validOfficial({ ...data, official: false })).toBe(false)
  const { container } = render(<><ImdCard official={state(data)} point={point} /><SachetCard official={state(data)} /></>)
  expect(container.querySelector('.imd-card').dataset.level).toBe('orange')
  expect(screen.getByRole('heading', { name: 'Official IMD warning · Udupi' })).toBeTruthy()
  expect(container.querySelector('.imd-today').textContent).toMatch(/Orange.*Today · Be prepared.*Very heavy rain/)
  expect(screen.getByRole('list', { name: 'IMD district warnings, next days' }).textContent).toMatch(/Yellow.*Green.*Unavailable.*Green/)
  expect(screen.getByText('Your district')).toBeTruthy(); expect(screen.getByText('TEST ONLY headline over Udupi')).toBeTruthy()
  expect(container.querySelector('.sachet-card').dataset.active).toBe('true')
})

it('never turns a failure or an empty feed into "no warning"', () => {
  render(<ImdCard official={{ data: null, loading: false, error: 'Risk request timed out.', refresh: vi.fn() }} point={point} />)
  expect(screen.getByText(/This does not mean there is no warning/)).toBeTruthy()
  cleanup()
  const quiet = { ...data, sachet: { ...data.sachet, alerts: [] }, imd: { status: 'unavailable', message: 'IMD down — TEST. This does not mean there is no warning.' } }
  render(<><ImdCard official={state(quiet)} point={point} /><SachetCard official={state(quiet)} /></>)
  expect(screen.getByText(/No active alert right now/).textContent).toContain('3 recent messages checked')
  expect(screen.getByText(/IMD down — TEST/)).toBeTruthy()
})

it('warns that a network-estimate district may be wrong, and asks for a place without one', () => {
  const { rerender } = render(<ImdCard official={state(data)} point={{ ...point, kind: 'network' }} />)
  expect(screen.getByText('Approximate network location — the district may be wrong.')).toBeTruthy()
  rerender(<ImdCard official={state({ ...data, imd: { status: 'not_requested', message: 'x' } })} point={null} />)
  expect(screen.getByText(/Choose your place to see its official IMD district warning/)).toBeTruthy()
})

it('shows the IMD 3-hour nowcast in IMD wording, a quiet nowcast plainly, and never an expired one as current', () => {
  const nowcast = { status: 'available', district: 'Udupi', issued_at: '2026-10-16T08:45:00+05:30', valid_until: '2026-10-16T11:45:00+05:30',
    categories: ['Light rain (under 5 mm/h)', 'Lightning possible (under 30%)'], other: 'TEST ONLY other warning', message: null }
  const { container, rerender } = render(<ImdCard official={state({ ...data, nowcast })} point={point} />)
  const line = container.querySelector('.imd-nowcast')
  expect(line.dataset.active).toBe('true')
  expect(line.textContent).toMatch(/Next 3 hours.*Light rain \(under 5 mm\/h\) · Lightning possible \(under 30%\) · TEST ONLY other warning.*IMD nowcast · 8:45 am IST/)
  rerender(<ImdCard official={state({ ...data, nowcast: { ...nowcast, categories: [], other: null } })} point={point} />)
  expect(container.querySelector('.imd-nowcast').textContent).toMatch(/Next 3 hours.*No significant weather/)
  rerender(<ImdCard official={state({ ...data, nowcast: { status: 'expired', district: 'Udupi', issued_at: '2026-10-16T05:00:00+05:30', message: 'No current IMD nowcast for this district (the latest is older than three hours).' } })} point={point} />)
  expect(container.querySelector('.imd-nowcast').dataset.active).toBe('false')
  expect(container.querySelector('.imd-nowcast').textContent).toMatch(/older than three hours/); expect(container.textContent).not.toMatch(/No significant weather/)
})
