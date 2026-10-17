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
