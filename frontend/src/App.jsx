import { useEffect, useState } from 'react'

import { getCurrentUser, logout } from './api'
import './App.css'
import LoginPage from './components/LoginPage'
import Navigation from './components/Navigation'
import PasswordChangePage from './components/PasswordChangePage'

function App() {
  const [currentUser, setCurrentUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [authError, setAuthError] = useState(null)
  const [currentView, setCurrentView] = useState('active-tickets')

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
      setCurrentView('active-tickets')
    } catch (error) {
      setAuthError(error.message)
    }
  }

  function handlePasswordChangeSuccess() {
    setCurrentUser(null)
    setAuthError('Password changed successfully. Please sign in again.')
  }

  if (authLoading) {
    return <div className="container">Checking session...</div>
  }

  if (!currentUser) {
    return (
      <>
        {authError && <p className="session-message" role="alert">{authError}</p>}
        <LoginPage onLoginSuccess={handleLoginSuccess} />
      </>
    )
  }

  if (currentUser.must_change_password) {
    return <PasswordChangePage onPasswordChangeSuccess={handlePasswordChangeSuccess} />
  }

  const viewLabels = {
    'active-tickets': 'Active Tickets',
    'create-ticket': 'Create Ticket',
    'closed-tickets': 'Closed Tickets',
  }

  return (
    <div className="app-shell">
      <Navigation
        currentUser={currentUser}
        currentView={currentView}
        onNavigate={setCurrentView}
        onLogout={handleLogout}
      />
      {authError && <p role="alert">{authError}</p>}
      <main className="app-content">
        <h1>{viewLabels[currentView]}</h1>
      </main>
    </div>
  )
}

export default App
