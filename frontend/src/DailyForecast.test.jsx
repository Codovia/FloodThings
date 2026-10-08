import React from 'react'
import { afterEach, expect, it } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import DailyForecast from './DailyForecast.jsx'

const days = () => Array.from({ length: 7 }, (_, i) => ({ date: `2026-10-${String(8 + i).padStart(2, '0')}`,
  weather_code: [0, 2, 3, 61, 63, 95, 97][i], temperature_min_c: 20 + i, temperature_max_c: 30 + i, precipitation_mm: i }))
afterEach(cleanup)

it('displays all seven actual dates in order, supported conditions and explicit units', () => {
  render(<DailyForecast days={days()} />)
  const rows = within(screen.getByRole('list', { name: 'Daily weather forecasts' })).getAllByRole('article')
  expect(rows).toHaveLength(7)
  expect(rows.map(row => row.querySelector('time').dateTime)).toEqual(days().map(day => day.date))
  expect(within(rows[0]).getByText('Clear sky')).toBeTruthy()
  expect(within(rows[0]).getByText('0 mm')).toBeTruthy()
  expect(within(rows[0]).getByText('20 °C')).toBeTruthy()
  expect(within(rows[6]).getByText('Heavy thunderstorm')).toBeTruthy()
  expect(screen.getByText(/calendar days beginning on 2026-10-08/)).toBeTruthy()
  expect(screen.getByText(/not a seven-day flood prediction/)).toBeTruthy()
  expect(screen.queryByRole('status')).toBeNull()
})

it('short coverage displays only returned dates and reports the missing dates without filler cards', () => {
  render(<DailyForecast days={days().slice(0, 3)} coverage={{ valid_days: 3, missing_dates: ['2026-10-11', '2026-10-12', '2026-10-13', '2026-10-14'] }} />)
  expect(screen.getAllByRole('article')).toHaveLength(3)
  expect(screen.getByRole('status').textContent).toContain('3 of 7')
  expect(screen.getByText(/Dates without forecast data:/).textContent).toContain('2026-10-14')
  expect(document.querySelector('time[datetime="2026-10-14"]')).toBeNull()
})

it('empty coverage has an explicit daily-forecast unavailable state', () => {
  render(<DailyForecast days={[]} coverage={{ valid_days: 0, missing_dates: [] }} />)
  expect(screen.getByText(/Daily forecast unavailable/)).toBeTruthy()
  expect(screen.getByRole('status').textContent).toContain('0 of 7')
  expect(screen.queryByRole('list')).toBeNull()
})

it('missing optional fields do not become clear weather, zero precipitation or zero temperature', () => {
  const row = { ...days()[0], weather_code: null, precipitation_mm: null, temperature_min_c: null }
  render(<DailyForecast days={[row]} />)
  expect(screen.getAllByText('Unavailable')).toHaveLength(3)
  expect(screen.queryByText('Clear sky')).toBeNull()
  expect(screen.queryByText('0 mm')).toBeNull()
  expect(screen.queryByText('0 °C')).toBeNull()
})

it('unknown provider codes retain a diagnostic instead of guessing a condition', () => {
  render(<DailyForecast days={[{ ...days()[0], weather_code: 4 }]} />)
  expect(screen.getByText('Unrecognized weather code (4)')).toBeTruthy()
})

it('a wholly unavailable supplied row is not counted as a day with data', () => {
  render(<DailyForecast days={[{ date: '2026-10-08', weather_code: null, temperature_min_c: null, temperature_max_c: null, precipitation_mm: null }]} />)
  expect(screen.getByRole('status').textContent).toContain('0 of 7')
  expect(screen.getAllByText('Unavailable')).toHaveLength(4)
})
