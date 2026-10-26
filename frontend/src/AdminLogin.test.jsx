import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import AdminLogin, { loginErrorMessage, usernameProblem } from './AdminLogin.jsx'

// TEST FIXTURES ONLY — invented usernames and passwords; no server.
afterEach(cleanup)
const SECRET = 'TEST ONLY secret pass'

it('the password can be shown and hidden, and is hidden and cleared again after an attempt', async () => {
  const onSignIn = vi.fn(async () => {})
  render(<AdminLogin busy={false} onSignIn={onSignIn} />)
  const password = screen.getByLabelText('Password'), toggle = screen.getByRole('button', { name: 'Show password' })
  fireEvent.change(password, { target: { value: SECRET } })
  expect(password.type).toBe('password'); expect(toggle.getAttribute('aria-pressed')).toBe('false')
  fireEvent.click(toggle)
  expect(password.type).toBe('text'); expect(screen.getByRole('button', { name: 'Hide password' }).getAttribute('aria-pressed')).toBe('true')
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'test.admin' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(onSignIn).toHaveBeenCalledWith('test.admin', SECRET)
  await waitFor(() => expect(password.value).toBe('')); expect(password.type).toBe('password')
})

it('says what is wrong with the entry before sending anything, without repeating it', () => {
  const onSignIn = vi.fn()
  render(<AdminLogin busy={false} onSignIn={onSignIn} />)
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(screen.getByRole('alert').textContent).toBe('Enter your username.')
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'Test.Admin' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(screen.getByRole('alert').textContent).toBe('Usernames use lowercase letters only. Check that Caps Lock is off.')
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'test.admin' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
  expect(screen.getByRole('alert').textContent).toBe('Enter your password.')
  expect(onSignIn).not.toHaveBeenCalled(); expect(document.body.textContent).not.toContain('Test.Admin')
})

it('warns when Caps Lock is on in the password field', () => {
  render(<AdminLogin busy={false} onSignIn={vi.fn()} />)
  fireEvent.keyUp(screen.getByLabelText('Password'), { key: 'A', modifierCapsLock: true })
  expect(screen.getByText('Caps Lock is on.')).toBeTruthy()
})

it.each([
  ['', 'Enter your username.'], ['test admin', 'Remove the spaces from the username.'], ['1admin', 'Usernames start with a letter.'],
  ['test@admin', 'Usernames use only lowercase letters, digits, dot (.), dash (-) and underscore (_).'], ['ab', 'Usernames are 3 to 64 characters long.'], ['test.admin', null],
])('username %j: %s', (value, message) => { expect(usernameProblem(value)).toBe(message) })

it.each([
  [{ status: 401, attemptsRemaining: '3' }, 'Username or password is incorrect. Check both and try again. 3 tries left before sign-in pauses for up to 15 minutes.'],
  [{ status: 401, attemptsRemaining: '1' }, 'Username or password is incorrect. Check both and try again. 1 try left before sign-in pauses for up to 15 minutes.'],
  [{ status: 401, attemptsRemaining: '0' }, 'Username or password is incorrect. Check both and try again. That was the last try: sign-in now pauses for up to 15 minutes.'],
  [{ status: 401, attemptsRemaining: null }, 'Username or password is incorrect. Check both and try again.'],
  [{ status: 429, retryAfter: null }, 'Too many sign-in attempts. Sign-in is paused for this username or network for up to 15 minutes.'],
  [{ status: 503 }, 'Sign-in is unavailable right now: the administrator database cannot be reached. Try again shortly.'],
  [{ status: 403 }, 'Sign-in was blocked by a security check. Open FloodPulse from its usual address, reload this page and try again.'],
  [Object.assign(new TypeError('Failed to fetch')), 'Cannot reach the FloodPulse server. Check your internet connection and try again.'],
])('server answer %j becomes a specific message', (error, message) => { expect(loginErrorMessage(error)).toBe(message) })

it('a paused sign-in says when it reopens', () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-26T15:00:00Z'))   // 8:30 pm IST
  expect(loginErrorMessage({ status: 429, retryAfter: '600' })).toBe('Too many sign-in attempts. Sign-in is paused for this username or network until about 8:40 pm IST.')
  vi.useRealTimers()
})
