import React from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import ShelterNavigation, { embedUrl, navigateUrl } from './ShelterNavigation.jsx'
vi.mock('./ShelterMap.jsx', () => ({ default: ({ label }) => <div role="region" aria-label={label} /> }))

// TEST FIXTURES ONLY — invented shelter, origin and key shape; never a real credential.
const KEY = 'AIza' + 'T'.repeat(35)
const shelter = { id: 'fixture', name: 'DEMONSTRATION ONLY fixture', latitude: 13.5, longitude: 74.7, straight_line_km: 3.2 }
const origin = { name: 'Test origin', latitude: 13.34, longitude: 74.74 }
const base = 'https://www.google.com/maps/dir/?api=1&destination=13.5%2C74.7&origin=13.34%2C74.74'
const props = over => ({ shelter, origin, listed: true, demonstration: false, mode: 'walking', onMode: vi.fn(), link: null, onRecheck: vi.fn(), rechecking: false, onClose: vi.fn(), ...over })
const config = body => vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => body })))
beforeEach(() => vi.resetModules())
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('builds official Embed and navigate URLs from coordinates only', () => {
  const embed = new URL(embedUrl(KEY, origin, shelter, 'driving'))
  expect(embed.origin + embed.pathname).toBe('https://www.google.com/maps/embed/v1/directions')
  expect(Object.fromEntries(embed.searchParams)).toEqual({ key: KEY, origin: '13.34,74.74', destination: '13.5,74.7', mode: 'driving', units: 'metric', region: 'IN' })
  const nav = new URL(navigateUrl(base, 'walking'))
  expect(nav.searchParams.get('api')).toBe('1'); expect(nav.searchParams.get('dir_action')).toBe('navigate'); expect(nav.searchParams.get('travelmode')).toBe('walking')
})

it('shows the Google route in-app when configured, and starts navigation only with a fresh recheck', async () => {
  config({ status: 'available', embed_key: KEY })
  const { default: Nav } = await import('./ShelterNavigation.jsx')
  const p = props(); const { rerender } = render(<Nav {...p} />)
  fireEvent.click(screen.getByRole('button', { name: 'Google route' }))
  const frame = await screen.findByTitle('Google Maps route to the shelter')
  expect(new URL(frame.src).searchParams.get('mode')).toBe('walking')
  expect(screen.queryByRole('link', { name: 'Start navigation in Google Maps' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Recheck and start navigation' })); expect(p.onRecheck).toHaveBeenCalled()
  rerender(<Nav {...p} link={base} />)
  expect(new URL(screen.getByRole('link', { name: 'Start navigation in Google Maps' }).href).searchParams.get('dir_action')).toBe('navigate')
  fireEvent.click(screen.getByRole('button', { name: 'Driving' })); expect(p.onMode).toHaveBeenCalledWith('driving')
  expect(screen.getByText(/not checked for flooding/)).toBeTruthy(); expect(screen.getByText(/sent to Google/)).toBeTruthy()
})

it('falls back to the app map without a key and stops when the shelter is no longer listed', async () => {
  config({ status: 'not_configured' })
  const { default: Nav } = await import('./ShelterNavigation.jsx')
  const p = props(); const { rerender } = render(<Nav {...p} />)
  await screen.findByText(/in-app Google route preview is not set up/)
  expect(screen.queryByTitle('Google Maps route to the shelter')).toBeNull(); expect(screen.getByRole('region', { name: 'Start point and shelter entrance' })).toBeTruthy()
  rerender(<Nav {...p} listed={false} link={base} />)
  expect(screen.getByRole('alert').textContent).toMatch(/no longer listed/); expect(screen.queryByRole('link', { name: /Start navigation/ })).toBeNull()
})

it('shows the flood-aware route first, with distance, avoided reports, safety label and steps', async () => {
  const route = { status: 'available', geometry: { type: 'LineString', coordinates: [[74.74, 13.34], [74.7, 13.5]] }, distance_m: 7260, duration_s: 5220, steps: [{ instruction: 'TEST step: head north', distance_m: 120 }], avoided_reports: 1, label: 'Route avoids 1 approved flooding/blocked-drain report area(s) from the last 72 hours. It is NOT certified flood-safe: check road closures and follow local authorities.', attribution: '© openrouteservice.org by HeiGIT | Map data © OpenStreetMap contributors' }
  vi.stubGlobal('fetch', vi.fn(async (url, options) => ({ ok: true, json: async () => url === '/api/route' ? route : { status: 'not_configured' } })))
  const { default: Nav } = await import('./ShelterNavigation.jsx')
  render(<Nav {...props({ origin: { ...origin, kind: 'gps', accuracy_m: 25 } })} />)
  expect(await screen.findByText(/7.3 km · about 87 min walking/)).toBeTruthy()
  expect(screen.getByText(/avoids 1 reported flood area$/)).toBeTruthy(); expect(screen.getByText(/NOT certified flood-safe/)).toBeTruthy()
  expect(screen.getByText('TEST step: head north (120 m)')).toBeTruthy(); expect(screen.getByRole('region', { name: 'Flood-aware route to the shelter' })).toBeTruthy()
  const [, options] = fetch.mock.calls.find(([u]) => u === '/api/route'); const body = JSON.parse(options.body)
  expect(body).toEqual({ shelter_id: 'fixture', profile: 'foot-walking', origin: { latitude: 13.34, longitude: 74.74, accuracy_m: 25 } })
})

it('hides the flood-aware option when routing is not configured and shows Google directly', async () => {
  vi.stubGlobal('fetch', vi.fn(async url => ({ ok: url !== '/api/route', json: async () => url === '/api/route' ? { status: 'not_configured', message: 'In-app routing is not configured.' } : { status: 'available', embed_key: KEY } })))
  const { default: Nav } = await import('./ShelterNavigation.jsx')
  render(<Nav {...props()} />)
  expect(await screen.findByTitle('Google Maps route to the shelter')).toBeTruthy(); expect(screen.queryByRole('button', { name: 'Avoids reported flooding' })).toBeNull()
})
