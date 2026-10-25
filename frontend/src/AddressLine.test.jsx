import React from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import AddressLine, { usePlaceLookup } from './AddressLine.jsx'

// TEST FIXTURES ONLY — invented points and addresses; fetch is mocked.
const GPS = { name: 'GPS-selected point', kind: 'gps', latitude: 13.340912, longitude: 74.742134, accuracy_m: 8 }
const reply = body => vi.fn(async () => ({ ok: body.status === 'available', json: async () => body }))
const OK = { status: 'available', address: '12 TEST Temple Road, TEST Ward, Udupi, Karnataka 576101', precision: 'street', place: 'TEST Ward, Udupi 576101' }
function Place({ point }) {
  const lookup = usePlaceLookup(point)
  return <><h2>{lookup.place || point?.name || 'No place'}</h2><AddressLine lookup={lookup} /></>
}
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('names a located point with its PIN code automatically, sending just the point and its accuracy', async () => {
  const fetch = reply(OK); vi.stubGlobal('fetch', fetch)
  render(<Place point={GPS} />)
  expect(await screen.findByRole('heading', { name: 'TEST Ward, Udupi 576101' })).toBeTruthy()
  const [url, options] = fetch.mock.calls[0]
  expect(url).toBe('/api/location/address')
  expect(JSON.parse(options.body)).toEqual({ latitude: 13.340912, longitude: 74.742134, accuracy_m: 8 })
  fireEvent.click(screen.getByRole('button', { name: 'Show address' }))
  expect(screen.getByText('Near: 12 TEST Temple Road, TEST Ward, Udupi, Karnataka 576101')).toBeTruthy()
  expect(screen.getByText(/not verified/)).toBeTruthy()
  expect(screen.getByRole('link', { name: '© OpenStreetMap' }).getAttribute('href')).toBe('https://www.openstreetmap.org/copyright')
  expect(fetch).toHaveBeenCalledTimes(1)   // the full address comes from the same answer
})

it('looks nothing up for a chosen town or a network estimate', () => {
  const fetch = reply(OK); vi.stubGlobal('fetch', fetch)
  render(<><Place point={{ name: 'TEST Town', kind: 'locality', latitude: 13.3, longitude: 74.7 }} /><Place point={{ name: 'Estimate', kind: 'network', latitude: 13.3, longitude: 74.7 }} /><Place point={null} /></>)
  expect(fetch).not.toHaveBeenCalled()
  expect(screen.getByRole('heading', { name: 'TEST Town' })).toBeTruthy()
  expect(screen.queryByRole('button', { name: 'Show address' })).toBeNull()
})

it('sends a tapped spot without accuracy, and a shelter start with its uncertainty; labels an area as Area', async () => {
  const fetch = reply({ ...OK, address: 'TEST Ward, Udupi', precision: 'area', place: 'TEST Ward, Udupi' }); vi.stubGlobal('fetch', fetch)
  const { rerender } = render(<Place point={{ name: 'Selected map point', kind: 'map', latitude: 13.34, longitude: 74.74 }} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Show address' }))
  expect(screen.getByText('Area: TEST Ward, Udupi')).toBeTruthy()
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ latitude: 13.34, longitude: 74.74 })
  rerender(<Place point={{ name: 'Start', kind: 'map', latitude: 13.35, longitude: 74.75, uncertainty_m: 50 }} />)
  await screen.findByRole('button', { name: 'Show address' })
  expect(JSON.parse(fetch.mock.calls[1][1].body).accuracy_m).toBe(50)
})

it('keeps the original name and shows the reason when the lookup fails, and can try again', async () => {
  vi.stubGlobal('fetch', reply({ status: 'too_imprecise', message: 'Your location is only known to ±2500 m, too rough for an address.' }))
  render(<Place point={{ ...GPS, accuracy_m: 2500 }} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Show address' }))
  expect(screen.getByText(/too rough for an address/)).toBeTruthy()
  expect(screen.getByRole('heading', { name: 'GPS-selected point' })).toBeTruthy()
  const ok = reply(OK); vi.stubGlobal('fetch', ok)
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByRole('heading', { name: 'TEST Ward, Udupi 576101' })).toBeTruthy()
})

it('a new location drops the old name and ignores a late answer for the old point', async () => {
  const answers = []; vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => answers.push(resolve))))
  const { rerender } = render(<Place point={GPS} />)
  rerender(<Place point={{ ...GPS, latitude: 13.5, name: 'Second point' }} />)
  answers[0]({ ok: true, json: async () => OK })
  await Promise.resolve(); await Promise.resolve()
  expect(screen.getByRole('heading', { name: 'Second point' })).toBeTruthy()
  answers[1]({ ok: true, json: async () => ({ ...OK, place: 'TEST Second, Udupi 576102' }) })
  expect(await screen.findByRole('heading', { name: 'TEST Second, Udupi 576102' })).toBeTruthy()
})
