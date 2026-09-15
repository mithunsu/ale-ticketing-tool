import { useState } from 'react'

import { login } from '../api'

function LoginPage({ onLoginSuccess }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loginLoading, setLoginLoading] = useState(false)
  const [loginError, setLoginError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    setLoginError(null)
    setLoginLoading(true)

    try {
      const user = await login({ email, password })
      setPassword('')
      onLoginSuccess(user)
    } catch (error) {
      setLoginError(
        error.code === 'INVALID_CREDENTIALS'
          ? error.message
          : 'Unable to sign in. Please try again.',
      )
    } finally {
      setLoginLoading(false)
    }
  }

  return (
    <main className="login-page">
      <h1>ALE Ticket Management Tool</h1>
      <p>Phase 1 development environment</p>
      <form className="login-form" onSubmit={handleSubmit}>
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          autoComplete="email"
          required
        />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          autoComplete="current-password"
          required
        />
        {loginError && <p className="form-error" role="alert">{loginError}</p>}
        <button type="submit" disabled={loginLoading}>
          {loginLoading ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}

export default LoginPage