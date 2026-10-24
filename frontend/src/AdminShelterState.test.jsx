import { expect, it } from 'vitest'
import { shelterState } from './AdminShelters.jsx'

// TEST FIXTURES ONLY — invented rows; the server alone decides publicly_available.
const now = Date.parse('2026-10-17T12:00:00Z'), h = 3600e3, at = ms => new Date(now + ms).toISOString()
const row = over => ({ status: 'open', publicly_available: true, verified_at: at(-4 * h), verification_expires_at: at(20 * h), ...over })

it('explains public visibility and flags what needs attention', () => {
  expect(shelterState(row({}), now)).toMatchObject({ tone: 'ok', attention: false, detail: 'Verification expires in 20 h' })
  expect(shelterState(row({ verified_at: at(-22 * h), verification_expires_at: at(2 * h) }), now)).toMatchObject({ tone: 'warn', attention: true })
  expect(shelterState(row({ publicly_available: false, verified_at: at(-26 * h), verification_expires_at: at(-2 * h) }), now)).toMatchObject({ label: 'Hidden: verification expired', detail: 'Expired 2 h ago — re-verify to publish again', attention: true })
  expect(shelterState(row({ publicly_available: false, verified_at: at(-26 * h), verification_expires_at: undefined }), now).label).toBe('Hidden: verification expired')
  expect(shelterState(row({ publicly_available: false, status: 'pending', verified_at: null }), now)).toMatchObject({ label: 'Hidden: pending verification', attention: true })
  expect(shelterState(row({ publicly_available: false, status: 'full' }), now)).toMatchObject({ label: 'Hidden: full', attention: false })
  expect(shelterState(row({ publicly_available: false, status: 'closed' }), now)).toMatchObject({ label: 'Hidden: closed', attention: false })
})
