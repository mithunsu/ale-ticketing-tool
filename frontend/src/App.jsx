import { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'

import { getCurrentUser, logout } from './api'
import './App.css'
import DashboardPage from './components/DashboardPage'
import TicketListPage from './components/TicketListPage'
import CreateTicketPage from './components/CreateTicketPage'
import TicketDetailPage from './components/TicketDetailPage'
import LoginPage from './components/LoginPage'
import Navigation from './components/Navigation'
import PasswordChangePage from './components/PasswordChangePage'
import AdminUsersPage from './components/AdminUsersPage'
import AdminCreateUserPage from './components/AdminCreateUserPage'
import AdminDashboardPage from './components/AdminDashboardPage'

function App() {
  const [currentUser, setCurrentUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [authError, setAuthError] = useState(null)
  const [theme, setTheme] = useState(() => document.documentElement.dataset.theme || 'dark')

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('ale_theme', theme)
  }, [theme])

  function handleThemeToggle() {
    setTheme((currentTheme) => (currentTheme === 'dark' ? 'light' : 'dark'))
  }

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

  function handlePasswordChangeSuccess() {
    setCurrentUser(null)
    setAuthError('Password changed successfully. Please sign in again.')
  }

  function handleAuthenticationExpired() {
    setCurrentUser(null)
    setAuthError('Your session has expired. Please sign in again.')
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

  return (
    <div className="app-shell">
      <Navigation
        currentUser={currentUser}
        onLogout={handleLogout}
        theme={theme}
        onThemeToggle={handleThemeToggle}
      />
      {authError && <p role="alert">{authError}</p>}
      <main className="app-content">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/tickets" element={<TicketListPage />} />
          <Route path="/tickets/:id" element={<TicketDetailPage currentUser={currentUser} />} />
          <Route path="/create" element={<CreateTicketPage />} />
          <Route path="/admin" element={<AdminDashboardPage currentUser={currentUser} />} />
          <Route
            path="/admin/users/new"
            element={
              <AdminCreateUserPage
                currentUser={currentUser}
                onAuthenticationExpired={handleAuthenticationExpired}
              />
            }
          />
          <Route
            path="/admin/users"
            element={
              <AdminUsersPage
                currentUser={currentUser}
                onAuthenticationExpired={handleAuthenticationExpired}
              />
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
