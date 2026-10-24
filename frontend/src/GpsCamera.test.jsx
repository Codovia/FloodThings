import React from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import GpsCamera from './GpsCamera.jsx'

// TEST FIXTURES ONLY — fake camera, fake GPS fix and fake place label.
let watchCallback, stopTrack
beforeEach(() => {
  vi.stubGlobal('isSecureContext', true)
  stopTrack = vi.fn()
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: stopTrack }] })) } })
  Object.defineProperty(navigator, 'geolocation', { configurable: true, value: { watchPosition: vi.fn(ok => { watchCallback = ok; return 7 }), clearWatch: vi.fn() } })
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ locality: 'TEST Locality', city: 'Udupi', principalSubdivision: 'Karnataka', postcode: '576101', localityInfo: { administrative: [{ name: 'Udupi', description: 'district of Karnataka' }] } }) })))
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({ drawImage: vi.fn() }))
  HTMLCanvasElement.prototype.toBlob = function (cb) { cb(new Blob(['TEST'], { type: 'image/jpeg' })) }
  vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:test'), revokeObjectURL: vi.fn() })
  Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', { configurable: true, get: () => 1920 })
  Object.defineProperty(HTMLVideoElement.prototype, 'videoHeight', { configurable: true, get: () => 1080 })
  HTMLMediaElement.prototype.play = vi.fn(async () => {})
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); delete navigator.mediaDevices; delete navigator.geolocation })

it('waits for GPS, then captures the photo together with its own fix and time, and stops the camera on close', async () => {
  const onCapture = vi.fn(), onClose = vi.fn()
  render(<GpsCamera onCapture={onCapture} onClose={onClose} />)
  const shutter = await screen.findByRole('button', { name: 'Take GPS photo (waiting for GPS)' }); expect(shutter.disabled).toBe(true)
  fireEvent(screen.getByLabelText('Live camera view'), new Event('loadedmetadata'))
  act(() => watchCallback({ coords: { latitude: 13.341234, longitude: 74.742345, accuracy: 12 }, timestamp: Date.now() }))
  expect(await screen.findByText(/TEST Locality, Udupi, Karnataka 576101/)).toBeTruthy()
  expect(screen.getByText('GPS ±12 m')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Take GPS photo' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Use this photo' }))
  const shot = onCapture.mock.calls[0][0]
  expect(shot.capture.source).toBe('IN_APP_GPS_CAMERA'); expect(shot.mime).toBe('image/jpeg'); expect(shot.base64).toBeTruthy()
  expect(shot.fix).toMatchObject({ latitude: 13.341234, longitude: 74.742345, accuracy_m: 12 })
  expect(Math.abs(Date.parse(shot.capture.captured_at) - Date.parse(shot.fix.gps_at))).toBeLessThan(5000)
  expect(shot.place).toBe('TEST Locality, Udupi, Karnataka 576101')
  const [url] = fetch.mock.calls[0]; expect(url).toContain('reverse-geocode-client'); expect(url).toContain('latitude=13.341234')
  cleanup(); expect(stopTrack).toHaveBeenCalled(); expect(navigator.geolocation?.clearWatch ?? (() => {})).toBeTruthy()
})

it('explains a denied camera and never captures without a GPS fix', async () => {
  navigator.mediaDevices.getUserMedia = vi.fn(async () => { throw new Error('denied') })
  render(<GpsCamera onCapture={vi.fn()} onClose={vi.fn()} />)
  expect((await screen.findByRole('alert')).textContent).toMatch(/Camera permission was denied/)
  expect(screen.getByRole('button', { name: /Take GPS photo/ }).disabled).toBe(true)
})
