import React, { useState } from 'react'

// Administrator sign-in. Every message says what to fix, except which of the username or password was wrong: the
// server answers an unknown username, a wrong password and a deactivated account the same way, so nobody can use
// this page to find out which usernames exist. Neither value is ever shown in a message.
export function usernameProblem(value) {
  if (!value) return 'Enter your username.'
  if (/\s/.test(value)) return 'Remove the spaces from the username.'
  if (/[A-Z]/.test(value)) return 'Usernames use lowercase letters only. Check that Caps Lock is off.'
  if (!/^[a-z]/.test(value)) return 'Usernames start with a letter.'
  if (/[^a-z0-9._-]/.test(value)) return 'Usernames use only lowercase letters, digits, dot (.), dash (-) and underscore (_).'
  if (value.length < 3 || value.length > 64) return 'Usernames are 3 to 64 characters long.'
  return null
}

const at = seconds => new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: 'numeric', minute: '2-digit' }).format(new Date(Date.now() + seconds * 1000))

export function loginErrorMessage(error) {
  const status = error?.status
  if (status === 401) {
    const left = error.attemptsRemaining === null || error.attemptsRemaining === undefined ? NaN : Number(error.attemptsRemaining)
    const tries = !Number.isInteger(left) ? '' : left === 0 ? ' That was the last try: sign-in now pauses for up to 15 minutes.'
      : ` ${left} ${left === 1 ? 'try' : 'tries'} left before sign-in pauses for up to 15 minutes.`
    return 'Username or password is incorrect. Check both and try again.' + tries
  }
  if (status === 429) {
    const seconds = Number(error.retryAfter)
    return 'Too many sign-in attempts. Sign-in is paused for this username or network ' + (seconds > 0 ? `until about ${at(seconds)} IST.` : 'for up to 15 minutes.')
  }
  if (status === 422) return 'The username or password is not in a valid format. Usernames are lowercase; passwords are at most 128 characters.'
  if (status === 403) return 'Sign-in was blocked by a security check. Open FloodPulse from its usual address, reload this page and try again.'
  if (status === 503) return 'Sign-in is unavailable right now: the administrator database cannot be reached. Try again shortly.'
  if (status >= 500) return 'The server had a problem signing you in. Try again shortly.'
  if (error?.name === 'TypeError') return 'Cannot reach the FloodPulse server. Check your internet connection and try again.'
  if (/timed out/i.test(error?.message || '')) return 'Sign-in timed out. Check your connection and try again.'
  return 'Sign-in failed. Try again.'
}

export default function AdminLogin({ busy, onSignIn }) {
  const [username, setUsername] = useState(''), [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false), [capsLock, setCapsLock] = useState(false), [problem, setProblem] = useState(null)
  const caps = event => { if (typeof event.getModifierState === 'function') setCapsLock(event.getModifierState('CapsLock')) }
  async function submit(event) {
    event.preventDefault()
    const found = usernameProblem(username) || (!password ? 'Enter your password.' : password.length > 128 ? 'Passwords are at most 128 characters.' : null)
    setProblem(found)
    if (found) return
    try { await onSignIn(username, password) } finally { setPassword(''); setVisible(false) }
  }
  return <form className="panel shelter-form admin-login" onSubmit={submit} noValidate>
    <h2>Administrator login</h2>
    <label>Username<input autoComplete="username" maxLength={64} autoCapitalize="none" spellCheck={false} value={username}
      aria-invalid={problem && problem !== 'Enter your password.' && !problem.startsWith('Passwords') ? true : undefined} onKeyUp={caps}
      onChange={e => { setUsername(e.target.value); setProblem(null) }} /></label>
    <label htmlFor="admin-password">Password</label>
    <div className="password-field">
      <input id="admin-password" type={visible ? 'text' : 'password'} autoComplete="current-password" maxLength={128} value={password}
        onKeyUp={caps} onKeyDown={caps} onChange={e => { setPassword(e.target.value); setProblem(null) }} />
      <button type="button" className="secondary" aria-pressed={visible} aria-controls="admin-password" onClick={() => setVisible(v => !v)}>{visible ? 'Hide' : 'Show'}<span className="visually-hidden"> password</span></button>
    </div>
    {capsLock && <p className="notice" role="status">Caps Lock is on.</p>}
    {problem && <p className="notice error" role="alert">{problem}</p>}
    <button disabled={busy}>Sign in</button>
  </form>
}
