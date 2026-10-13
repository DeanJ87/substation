// Sign in (design v1 01, 007-DR-11): the mark and wordmark above one card, errors under the field they concern,
// Enter submits, and the version underneath. No other copy.
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { useState, type FormEvent } from 'react'
import { signIn } from '../api/auth'
import { Button } from '../components/ui'
import { Mark } from '../components/Logo'
import s from './frame.module.css'

const VERSION = '0.1.0'

export function SignIn() {
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const qc = useQueryClient()
  const navigate = useNavigate()

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const user = await signIn(login.trim(), password)
      qc.setQueryData(['session'], user)
      await navigate({ to: '/' })
    } catch (err) {
      const msg = err instanceof Error ? err.message : ''
      setError(
        /password|match|incorrect|credential/i.test(msg) && !/refused|server/i.test(msg)
          ? 'Wrong username or password.'
          : msg || 'Wrong username or password.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className={s.signIn}>
      <div className={s.signInStack}>
        <div className={s.signInBrand}>
          <Mark size={36} />
          <span>SubStation</span>
        </div>
        <form onSubmit={submit} className={s.signInCard} aria-labelledby="sign-in-title">
          <div>
            <h2 id="sign-in-title">Sign in</h2>
            <div className="muted mono">{window.location.host}</div>
          </div>
          <label className={s.field}>
            <span className="label">Username</span>
            <input
              autoComplete="username"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              required
            />
          </label>
          <label className={`${s.field} ${error ? s.fieldError : ''}`}>
            <span className="label">Password</span>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? 'password-error' : undefined}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            {error && (
              <span id="password-error" role="alert" className={s.formError}>
                {error}
              </span>
            )}
          </label>
          <Button type="submit" variant="primary" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </Button>
        </form>
        <div className={`muted mono ${s.signInFoot}`}>SubStation {VERSION}</div>
      </div>
    </main>
  )
}
