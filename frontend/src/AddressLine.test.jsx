import React from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import AddressLine from './AddressLine.jsx'

// TEST FIXTURES ONLY — invented points and addresses; fetch is mocked.
const GPS = { name: 'GPS-selected point', kind: 'gps', latitude: 13.340912, longitude: 74.742134, accuracy_m: 8 }
const reply = body => vi.fn(async () => ({ ok: body.status === 'available', json: async () => body }))
const OK = { status: 'available', address: '12 TEST Temple Road, Udupi, Karnataka 576101', precision: 'street' }
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('looks the address up only when asked, sending just the point and its accuracy', async () => {
  const fetch = reply(OK); vi.stubGlobal('fetch', fetch)
  render(<AddressLine point={GPS} />)
  expect(fetch).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Show address' }))
  expect(await screen.findByText('Near: 12 TEST Temple Road, Udupi, Karnataka 576101')).toBeTruthy()
  const [url, options] = fetch.mock.calls[0]
  expect(url).toBe('/api/location/address')
  expect(JSON.parse(options.body)).toEqual({ latitude: 13.340912, longitude: 74.742134, accuracy_m: 8 })
  expect(screen.getByText(/not verified/)).toBeTruthy()
  expect(screen.getByRole('link', { name: '© OpenStreetMap' }).getAttribute('href')).toBe('https://www.openstreetmap.org/copyright')
})

it('offers no address for a town or a network estimate', () => {
  const fetch = reply(OK); vi.stubGlobal('fetch', fetch)
  render(<><AddressLine point={{ kind: 'locality', latitude: 13.3, longitude: 74.7 }} /><AddressLine point={{ kind: 'network', latitude: 13.3, longitude: 74.7 }} /><AddressLine point={null} /></>)
  expect(screen.queryByRole('button', { name: 'Show address' })).toBeNull()
})

it('sends a tapped spot without accuracy, and a shelter start with its uncertainty; labels an area as Area', async () => {
  const fetch = reply({ ...OK, address: 'TEST Ward, Udupi', precision: 'area' }); vi.stubGlobal('fetch', fetch)
  const { rerender } = render(<AddressLine point={{ kind: 'map', latitude: 13.34, longitude: 74.74 }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Show address' }))
  expect(await screen.findByText('Area: TEST Ward, Udupi')).toBeTruthy()
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ latitude: 13.34, longitude: 74.74 })
  rerender(<AddressLine point={{ kind: 'map', latitude: 13.35, longitude: 74.75, uncertainty_m: 50 }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Show address' }))
  await screen.findByText('Area: TEST Ward, Udupi')
  expect(JSON.parse(fetch.mock.calls[1][1].body).accuracy_m).toBe(50)
})

it('shows the server reason on failure and can try again', async () => {
  vi.stubGlobal('fetch', reply({ status: 'too_imprecise', message: 'Your location is only known to ±2500 m, too rough for an address.' }))
  render(<AddressLine point={{ ...GPS, accuracy_m: 2500 }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Show address' }))
  expect(await screen.findByText(/too rough for an address/)).toBeTruthy()
  vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline') }))
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  expect(await screen.findByText(/Address lookup is unavailable right now/)).toBeTruthy()
})

it('a new location clears the old address and ignores a late answer for the old point', async () => {
  let answer; vi.stubGlobal('fetch', vi.fn(() => new Promise(resolve => { answer = resolve })))
  const { rerender } = render(<AddressLine point={GPS} />)
  fireEvent.click(screen.getByRole('button', { name: 'Show address' }))
  expect(screen.getByText('Looking up the address…')).toBeTruthy()
  rerender(<AddressLine point={{ ...GPS, latitude: 13.5 }} />)
  answer({ ok: true, json: async () => OK })
  await Promise.resolve(); await Promise.resolve()
  expect(screen.getByRole('button', { name: 'Show address' })).toBeTruthy()
  expect(screen.queryByText(/TEST Temple Road/)).toBeNull()
})
