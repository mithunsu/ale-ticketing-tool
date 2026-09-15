import { useEffect, useState } from 'react'

import { getCurrentUser, logout } from './api'
import './App.css'
import LoginPage from './components/LoginPage'

function App() {
  const [currentUser, setCurrentUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [authError, setAuthError] = useState(null)

  function handleLoginSuccess(user) {
    setAuthError(null)
    setCurrentUser(user)
  }

  useEffect(() => {
    let active = true

    async function checkSession() {
      try {
        const user = await getCurrentUser()
        if (active) {
          handleLoginSuccess(user)
        }
      } catch (error) {
        if (active && error.status !== 401) {
          setAuthError(error.message)
        }
      } finally {
        if (active) {
          setAuthLoading(false)
        }
      }
    }

    checkSession()

    return () => {
      active = false
    }
  }, [])

  async function handleLogout() {
    setAuthError(null)

    try {
      await logout()
      setCurrentUser(null)
    } catch (error) {
      setAuthError(error.message)
    }
  }

  if (authLoading) {
    return <div className="container">Checking session...</div>
  }

  if (!currentUser) {
    return <LoginPage onLoginSuccess={handleLoginSuccess} />
  }

  return (
    <div className="container">
      <h1>ALE Ticket Management Tool</h1>
      <p>Phase 1 development environment</p>
      {authError && <p role="alert">{authError}</p>}
      {currentUser.must_change_password ? (
        <p>You must change your temporary password before continuing.</p>
      ) : (
        <p>Signed in as {currentUser.name} ({currentUser.role})</p>
      )}
      <button type="button" onClick={handleLogout}>Log out</button>
    </div>
  )
}

export default App
