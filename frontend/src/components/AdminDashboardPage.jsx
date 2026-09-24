import { Link } from 'react-router-dom'

function AdminDashboardPage({ currentUser }) {
  if (currentUser.role !== 'admin') {
    return (
      <section className="admin-dashboard-page">
        <h1>Admin Dashboard</h1>
        <p className="form-error" role="alert">Access denied. Admin access is required.</p>
      </section>
    )
  }

  return (
    <section className="admin-dashboard-page">
      <h1>Admin Dashboard</h1>
      <p className="user-management-subtitle">Manage users and administrative settings for the ALE Ticket Management Tool.</p>
      <div className="admin-dashboard-cards">
        <section className="admin-dashboard-card">
          <h2>User Management</h2>
          <p>View users and manage roles, account status, and password resets.</p>
          <Link className="dashboard-view-all-link" to="/admin/users">Manage Users</Link>
        </section>
        <section className="admin-dashboard-card">
          <h2>Create User</h2>
          <p>Provision a new ALE Ticket Management Tool account.</p>
          <Link className="dashboard-view-all-link" to="/admin/users/new">Create User</Link>
        </section>
      </div>
    </section>
  )
}

export default AdminDashboardPage