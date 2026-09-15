const navigationItems = [
  { id: 'active-tickets', label: 'Active Tickets' },
  { id: 'create-ticket', label: 'Create Ticket' },
  { id: 'closed-tickets', label: 'Closed Tickets' },
]

function Navigation({ currentUser, currentView, onNavigate, onLogout }) {
  return (
    <header className="app-header">
      <div>
        <p className="app-title">ALE Ticket Management Tool</p>
        <p className="user-context">
          {currentUser.name} <span aria-hidden="true">·</span> {currentUser.role}
        </p>
      </div>
      <nav className="app-navigation" aria-label="Ticket views">
        {navigationItems.map((item) => (
          <button
            className={currentView === item.id ? 'navigation-button active' : 'navigation-button'}
            key={item.id}
            type="button"
            onClick={() => onNavigate(item.id)}
            aria-current={currentView === item.id ? 'page' : undefined}
          >
            {item.label}
          </button>
        ))}
        <button className="navigation-button logout-button" type="button" onClick={onLogout}>
          Logout
        </button>
      </nav>
    </header>
  )
}

export default Navigation