import React from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import ErrorBoundary from './ErrorBoundary.jsx'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })
function Broken() { throw Error('TEST ONLY render failure at 13.3409123') }

it('a crash shows a recovery screen with an error ID and reports only the page and a short message', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  const fetcher = vi.fn(async () => ({ ok: true })); vi.stubGlobal('fetch', fetcher)
  window.history.replaceState(null, '', '/shelters')
  render(<ErrorBoundary><Broken /></ErrorBoundary>)
  expect(screen.getByRole('heading', { name: 'Something went wrong on this page' })).toBeTruthy()
  expect(screen.getByRole('button', { name: 'Reload the page' })).toBeTruthy()
  expect(screen.getByRole('link', { name: 'Go to Home' }).getAttribute('href')).toBe('/')
  const id = (await screen.findByText(/Error ID:/)).textContent.match(/[0-9a-f]{12}/)[0]
  const [url, options] = fetcher.mock.calls[0], body = JSON.parse(options.body)
  expect(url).toBe('/api/client-errors'); expect(body).toEqual({ error_id: id, page: '/shelters', message: 'TEST ONLY render failure at 13.3409123' })
  window.history.replaceState(null, '', '/')
})
