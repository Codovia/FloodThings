import React from 'react'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import WeatherStrip from './WeatherStrip.jsx'

// TEST FIXTURES ONLY — invented forecast values; no provider calls.
const NOW = Date.parse('2026-10-08T06:00:00Z')   // 11:30 IST on 8 Oct
const days = Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-${String(8 + i).padStart(2, '0')}`, weather_code: i === 2 ? 95 : 61,
  precipitation_mm: i === 1 ? null : i * 3, temperature_min_c: 21.6, temperature_max_c: 29.4 }))
const data = { retrieved_at: '2026-10-08T05:50:00Z', forecast: days, forecast_coverage: { valid_days: 7, missing_dates: [], start_date: '2026-10-08' },
  grid_location: { latitude: 13.35, longitude: 74.75 } }
const session = (over = {}) => ({ data, loading: false, error: null, freshness: 'fresh', now: NOW, retryAt: null, paused: false, offline: false, refresh: vi.fn(), ...over })
const POINT = { name: 'TEST Place', kind: 'gps', latitude: 13.34, longitude: 74.74 }
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

const phone = () => vi.stubGlobal('matchMedia', query => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} }))

it('shows all seven days on laptops, with temperature range and rain, keeping a missing value unavailable', () => {
  render(<WeatherStrip point={POINT} session={session()} />)
  expect(screen.getByRole('status', { name: 'Weather data freshness' }).textContent).toMatch(/^Fresh · retrieved/)
  const list = screen.getByRole('list', { name: 'Daily weather forecasts' })
  expect(list.children).toHaveLength(7)
  const today = within(list).getByRole('article', { name: 'Weather forecast for 2026-10-08' })
  expect(today.textContent).toContain('Today'); expect(today.textContent).toContain('29°'); expect(today.textContent).toContain('22°'); expect(today.textContent).toContain('0 mm')
  expect(within(list).getByRole('article', { name: 'Weather forecast for 2026-10-09' }).textContent).toContain('Unavailable')
  expect(within(list).getByRole('article', { name: 'Weather forecast for 2026-10-10' }).textContent).toContain('Thunderstorm')
  expect(screen.queryByRole('navigation', { name: 'More forecast days' })).toBeNull()
})

it('pages four days at a time on phones', () => {
  phone(); render(<WeatherStrip point={POINT} session={session()} />)
  expect(screen.getByRole('list', { name: 'Daily weather forecasts' }).children).toHaveLength(4)
  fireEvent.click(screen.getByRole('button', { name: 'Next ›' }))
  expect(screen.getByRole('list', { name: 'Daily weather forecasts' }).children).toHaveLength(3)
})

it('never fills missing days and says so', () => {
  const short = { ...data, forecast: days.slice(0, 3), forecast_coverage: { valid_days: 3, missing_dates: ['2026-10-11', '2026-10-12'] } }
  render(<WeatherStrip point={POINT} session={session({ data: short })} />)
  expect(screen.getByText(/Incomplete forecast coverage: 3 of 7 days have data. Missing days have not been filled./).textContent).toContain('2026-10-11, 2026-10-12')
  expect(screen.getByRole('list', { name: 'Daily weather forecasts' }).children).toHaveLength(3)
  cleanup(); render(<WeatherStrip point={POINT} session={session({ data: { ...data, forecast: [], forecast_coverage: { valid_days: 0, missing_dates: [] } } })} />)
  expect(screen.getByText(/Daily forecast unavailable/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Rain chart' })).toBeNull()
})

it('says when data is being refreshed or is stale, and refreshes on request', () => {
  const s = session({ loading: true, freshness: 'refreshing', data: { ...data, retrieved_at: '2026-10-07T20:00:00Z' } })
  const { rerender } = render(<WeatherStrip point={POINT} session={s} />)
  const status = screen.getByRole('status', { name: 'Weather data freshness' })
  expect(status.textContent).toContain('Refreshing weather'); expect(status.textContent).toContain('Showing previously retrieved information')
  expect(status.textContent).toContain('Displayed information is stale')
  const button = screen.getByRole('button', { name: 'Refresh weather' }); expect(button.disabled).toBe(true); expect(button.textContent).toBe('Loading…')
  const fresh = session(); rerender(<WeatherStrip point={POINT} session={fresh} />)
  fireEvent.click(screen.getByRole('button', { name: 'Refresh weather' })); expect(fresh.refresh).toHaveBeenCalledTimes(1)
  rerender(<WeatherStrip point={POINT} session={session({ freshness: 'stale', paused: true })} />)
  expect(screen.getByRole('status', { name: 'Weather data freshness' }).textContent).toMatch(/Stale — previously retrieved information.*Automatic retries paused/)
})

it('details name the sources and the point, with locality provenance links; the rain chart opens in a popup', () => {
  const locality = { name: 'TEST Town, Udupi', latitude: 13.2, longitude: 74.5, locality_id: 'osm:node:1', coordinate_source_url: 'https://www.openstreetmap.org/node/1',
    association_source_url: 'https://udupi.nic.in/en/municipal-administration/', district_name: 'Udupi' }
  render(<WeatherStrip point={locality} session={session()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Details' }))
  const dialog = screen.getByRole('dialog', { name: 'Weather details & sources' })
  expect(dialog.textContent).toContain('Requested point: 13.2° latitude, 74.5° longitude')
  expect(within(dialog).getByRole('link', { name: 'Udupi district association' }).getAttribute('href')).toBe('https://udupi.nic.in/en/municipal-administration/')
  expect(dialog.textContent).toContain('13.35°, 74.75°'); expect(dialog.textContent).toContain('not a seven-day flood prediction')
  fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }))
  fireEvent.click(screen.getByRole('button', { name: 'Rain chart' }))
  expect(screen.getByRole('list', { name: 'Forecast daily precipitation chart' })).toBeTruthy()
})
