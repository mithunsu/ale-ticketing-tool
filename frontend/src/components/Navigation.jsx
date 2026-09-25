import { Link, useLocation } from 'react-router-dom'

const navigationItems = [
  { path: '/', label: 'Dashboard' },
  { path: '/tickets', label: 'Tickets' },
  { path: '/create', label: 'Create Ticket' },
]

// Exact match for "/" so Dashboard isn't active on every route; prefix match for nested routes (e.g. /tickets/:id).
function isItemActive(pathname, itemPath) {
  if (itemPath === '/') {
    return pathname === '/'
  }
  return pathname === itemPath || pathname.startsWith(`${itemPath}/`)
}

function Navigation({ currentUser, onLogout, theme, onThemeToggle }) {
  const location = useLocation()

  return (
    <header className="app-header">
      <div>
        <p className="app-title">ALE Ticket Management Tool</p>
        <p className="user-context">
          {currentUser.name} <span aria-hidden="true">·</span>{' '}
          {currentUser.role === 'admin' ? (
            <Link className="admin-role-link" to="/admin">{currentUser.role}</Link>
          ) : (
            currentUser.role
          )}
        </p>
      </div>
      <nav className="app-navigation" aria-label="Ticket views">
        {navigationItems.map((item) => {
          const active = isItemActive(location.pathname, item.path)
          return (
            <Link
              className={active ? 'navigation-button active' : 'navigation-button'}
              key={item.path}
              to={item.path}
              aria-current={active ? 'page' : undefined}
            >
              {item.label}
            </Link>
          )
        })}
        <button
          className="navigation-button theme-toggle"
          type="button"
          onClick={onThemeToggle}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          {theme === 'dark' ? '☀ Light' : '☾ Dark'}
        </button>
        <button className="navigation-button logout-button" type="button" onClick={onLogout}>
          Logout
        </button>
      </nav>
    </header>
  )
}

export default Navigation