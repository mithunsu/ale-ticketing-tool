import { useEffect, useState } from 'react'
import {
  getAdminUsers,
  resetAdminUserPassword,
  updateAdminUserRole,
  updateAdminUserStatus,
} from '../api'

const roleOptions = [
  { value: 'requester', label: 'Requester' },
  { value: 'support_engineer', label: 'Support Engineer' },
  { value: 'manager', label: 'Manager' },
  { value: 'admin', label: 'Admin' },
]

function roleLabel(role) {
  return roleOptions.find((option) => option.value === role)?.label || role
}

function AccessDenied() {
  return (
    <section className="user-management-page">
      <h1>User Management</h1>
      <p className="form-error" role="alert">Access denied. Admin access is required.</p>
    </section>
  )
}

function AdminUsersPage({ currentUser, onAuthenticationExpired }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [accessDenied, setAccessDenied] = useState(false)
  const [error, setError] = useState(false)
  const [pendingRoleChange, setPendingRoleChange] = useState(null)
  const [roleChangeError, setRoleChangeError] = useState(null)
  const [updatingRole, setUpdatingRole] = useState(false)
  const [pendingStatusChange, setPendingStatusChange] = useState(null)
  const [statusChangeError, setStatusChangeError] = useState(null)
  const [updatingStatus, setUpdatingStatus] = useState(false)
  const [successMessage, setSuccessMessage] = useState(null)
  const [pendingPasswordReset, setPendingPasswordReset] = useState(null)
  const [passwordResetError, setPasswordResetError] = useState(null)
  const [resettingPassword, setResettingPassword] = useState(false)
  const [resetUser, setResetUser] = useState(null)
  const [temporaryPassword, setTemporaryPassword] = useState(null)
  const [copyStatus, setCopyStatus] = useState(null)

  const isAdmin = currentUser.role === 'admin'

  useEffect(() => {
    let active = true

    async function loadUsers() {
      if (!isAdmin) {
        return
      }

      setLoading(true)
      setAccessDenied(false)
      setError(false)

      try {
        const userList = await getAdminUsers()
        if (active) {
          setUsers(userList)
        }
      } catch (requestError) {
        if (!active) {
          return
        }

        if (requestError.status === 401) {
          onAuthenticationExpired()
        } else if (requestError.status === 403) {
          setAccessDenied(true)
        } else {
          setError(true)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadUsers()

    return () => {
      active = false
    }
  }, [isAdmin, onAuthenticationExpired])

  function handleRoleSelection(user, role) {
    if (role === user.role || pendingStatusChange || pendingPasswordReset) {
      return
    }

    setSuccessMessage(null)
    setRoleChangeError(null)
    setPendingRoleChange({ user, role })
  }

  function cancelRoleChange() {
    if (updatingRole) {
      return
    }

    setRoleChangeError(null)
    setPendingRoleChange(null)
  }

  function handleStatusChange(user) {
    if (pendingRoleChange || pendingStatusChange || pendingPasswordReset) {
      return
    }

    setSuccessMessage(null)
    setStatusChangeError(null)
    setPendingStatusChange({
      user,
      status: user.status === 'active' ? 'inactive' : 'active',
    })
  }

  function cancelStatusChange() {
    if (updatingStatus) {
      return
    }

    setStatusChangeError(null)
    setPendingStatusChange(null)
  }

  function handlePasswordReset(user) {
    if (pendingRoleChange || pendingStatusChange || pendingPasswordReset || resetUser) {
      return
    }

    setSuccessMessage(null)
    setPasswordResetError(null)
    setPendingPasswordReset(user)
  }

  function cancelPasswordReset() {
    if (resettingPassword) {
      return
    }

    setPasswordResetError(null)
    setPendingPasswordReset(null)
  }

  async function confirmRoleChange() {
    if (!pendingRoleChange || updatingRole) {
      return
    }

    setUpdatingRole(true)
    setRoleChangeError(null)

    try {
      const updatedUser = await updateAdminUserRole(pendingRoleChange.user.id, pendingRoleChange.role)
      setUsers((currentUsers) => currentUsers.map((user) => (
        user.id === updatedUser.id ? updatedUser : user
      )))
      setPendingRoleChange(null)
    } catch (requestError) {
      if (requestError.status === 401) {
        onAuthenticationExpired()
      } else if (requestError.status === 403 && requestError.code === 'SELF_DEMOTION_FORBIDDEN') {
        setRoleChangeError('You cannot remove your own admin role.')
      } else if (requestError.status === 403 && requestError.code === 'LAST_ACTIVE_ADMIN') {
        setRoleChangeError('This role change would leave the application without an active administrator.')
      } else if (requestError.status === 403) {
        setRoleChangeError('Access denied. Admin access is required.')
      } else if (requestError.status === 400) {
        setRoleChangeError('Please select a valid role and try again.')
      } else if (requestError.status === 404) {
        setRoleChangeError('This user no longer exists.')
      } else {
        setRoleChangeError('Unable to change the user role. Please try again.')
      }
    } finally {
      setUpdatingRole(false)
    }
  }

  async function confirmStatusChange() {
    if (!pendingStatusChange || updatingStatus) {
      return
    }

    setUpdatingStatus(true)
    setStatusChangeError(null)

    try {
      const updatedUser = await updateAdminUserStatus(pendingStatusChange.user.id, pendingStatusChange.status)
      setUsers((currentUsers) => currentUsers.map((user) => (
        user.id === updatedUser.id ? updatedUser : user
      )))
      setSuccessMessage(
        `${updatedUser.name} was ${updatedUser.status === 'inactive' ? 'deactivated' : 'reactivated'} successfully.`,
      )
      setPendingStatusChange(null)
    } catch (requestError) {
      if (requestError.status === 401) {
        onAuthenticationExpired()
      } else if (requestError.status === 403 && requestError.code === 'SELF_DEACTIVATION_FORBIDDEN') {
        setStatusChangeError('You cannot deactivate your own account.')
      } else if (requestError.status === 403 && requestError.code === 'LAST_ACTIVE_ADMIN') {
        setStatusChangeError('This account cannot be deactivated because at least one active administrator must remain.')
      } else if (requestError.status === 403) {
        setStatusChangeError('Access denied. Admin access is required.')
      } else if (requestError.status === 400) {
        setStatusChangeError('Please select a valid account status and try again.')
      } else if (requestError.status === 404) {
        setStatusChangeError('This user no longer exists.')
      } else {
        setStatusChangeError('Unable to update the account status. Please try again.')
      }
    } finally {
      setUpdatingStatus(false)
    }
  }

  async function confirmPasswordReset() {
    if (!pendingPasswordReset || resettingPassword) {
      return
    }

    setResettingPassword(true)
    setPasswordResetError(null)

    try {
      const data = await resetAdminUserPassword(pendingPasswordReset.id)
      setUsers((currentUsers) => currentUsers.map((user) => (
        user.id === data.user.id ? data.user : user
      )))
      setPendingPasswordReset(null)
      setResetUser(data.user)
      setTemporaryPassword(data.temporary_password)
    } catch (requestError) {
      if (requestError.status === 401) {
        onAuthenticationExpired()
      } else if (requestError.status === 403 && requestError.code === 'SELF_PASSWORD_RESET_FORBIDDEN') {
        setPasswordResetError('You cannot reset your own password from Admin User Management.')
      } else if (requestError.status === 403) {
        setPasswordResetError('Access denied. Admin access is required.')
      } else if (requestError.status === 400) {
        setPasswordResetError('Unable to reset this password. Please try again.')
      } else if (requestError.status === 404) {
        setPasswordResetError('This user no longer exists.')
      } else {
        setPasswordResetError('Unable to reset the password. Please try again.')
      }
    } finally {
      setResettingPassword(false)
    }
  }

  function closePasswordResetDialog() {
    setCopyStatus(null)
    setTemporaryPassword(null)
    setResetUser(null)
  }

  async function handleCopyPassword() {
    if (!navigator.clipboard || !temporaryPassword) {
      setCopyStatus('Unable to copy password.')
      return
    }

    try {
      await navigator.clipboard.writeText(temporaryPassword)
      setCopyStatus('Copied')
    } catch {
      setCopyStatus('Unable to copy password.')
    }
  }

  if (!isAdmin || accessDenied) {
    return <AccessDenied />
  }

  if (loading) {
    return <p>Loading users...</p>
  }

  if (error) {
    return <p className="form-error" role="alert">Unable to load users. Please try again.</p>
  }

  return (
    <section className="user-management-page">
      <h1>User Management</h1>
      <p className="user-management-subtitle">Manage ALE Ticket Management Tool accounts</p>
      {successMessage && <p className="form-success" role="status">{successMessage}</p>}

      {users.length === 0 ? (
        <p>No users found.</p>
      ) : (
        <table className="ticket-table user-management-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Email</th>
              <th>Department</th>
              <th>Role</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>{user.name}</td>
                <td>{user.email}</td>
                <td>{user.department || '—'}</td>
                <td>
                  <select
                    aria-label={`Role for ${user.name}`}
                    className="user-role-select"
                    value={user.role}
                    disabled={
                      Boolean(pendingStatusChange)
                      || Boolean(pendingPasswordReset)
                      || Boolean(resetUser)
                      || (updatingRole && pendingRoleChange?.user.id === user.id)
                    }
                    onChange={(event) => handleRoleSelection(user, event.target.value)}
                  >
                    {roleOptions.map((role) => (
                      <option key={role.value} value={role.value}>{role.label}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <span className={`user-status user-status-${user.status}`}>{user.status}</span>
                  {user.must_change_password && (
                    <span className="user-password-change-required">Password change required</span>
                  )}
                </td>
                <td className="user-actions">
                  {user.status === 'active' ? (
                    <button
                      type="button"
                      className="status-action-button"
                      onClick={() => handleStatusChange(user)}
                      disabled={
                        Boolean(pendingRoleChange)
                        || Boolean(pendingPasswordReset)
                        || Boolean(resetUser)
                        || (updatingStatus && pendingStatusChange?.user.id === user.id)
                        || user.id === currentUser.id
                      }
                      title={user.id === currentUser.id ? 'You cannot deactivate your own account.' : undefined}
                    >
                      Deactivate
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="status-action-button"
                      onClick={() => handleStatusChange(user)}
                      disabled={
                        Boolean(pendingRoleChange)
                        || Boolean(pendingPasswordReset)
                        || Boolean(resetUser)
                        || (updatingStatus && pendingStatusChange?.user.id === user.id)
                      }
                    >
                      Reactivate
                    </button>
                  )}
                  <button
                    type="button"
                    className="status-action-button"
                    onClick={() => handlePasswordReset(user)}
                    disabled={
                      Boolean(pendingRoleChange)
                      || Boolean(pendingStatusChange)
                      || Boolean(pendingPasswordReset)
                      || Boolean(resetUser)
                      || (resettingPassword && pendingPasswordReset?.id === user.id)
                      || user.id === currentUser.id
                    }
                    title={
                      user.id === currentUser.id
                        ? 'Use your normal password-change flow to change your own password.'
                        : undefined
                    }
                  >
                    Reset Password
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {pendingRoleChange && (
        <div className="dialog-backdrop">
          <section className="success-dialog" role="dialog" aria-modal="true" aria-labelledby="role-change-title">
            <h2 id="role-change-title">Change {pendingRoleChange.user.name}&apos;s role?</h2>
            <p>
              From {roleLabel(pendingRoleChange.user.role)} to {roleLabel(pendingRoleChange.role)}.
            </p>
            {roleChangeError && <p className="form-error" role="alert">{roleChangeError}</p>}
            <div className="dialog-actions">
              <button type="button" onClick={confirmRoleChange} disabled={updatingRole}>
                {updatingRole ? 'Changing role...' : 'Confirm'}
              </button>
              <button type="button" className="secondary-button" onClick={cancelRoleChange} disabled={updatingRole}>
                Cancel
              </button>
            </div>
          </section>
        </div>
      )}

      {pendingStatusChange && (
        <div className="dialog-backdrop">
          <section className="success-dialog" role="dialog" aria-modal="true" aria-labelledby="status-change-title">
            <h2 id="status-change-title">
              {pendingStatusChange.status === 'inactive' ? 'Deactivate' : 'Reactivate'} {pendingStatusChange.user.name}?
            </h2>
            <p>
              {pendingStatusChange.status === 'inactive'
                ? 'This user will no longer be able to access the application until reactivated.'
                : 'This user will regain access according to their existing role.'}
            </p>
            {statusChangeError && <p className="form-error" role="alert">{statusChangeError}</p>}
            <div className="dialog-actions">
              <button type="button" onClick={confirmStatusChange} disabled={updatingStatus}>
                {updatingStatus
                  ? 'Updating status...'
                  : pendingStatusChange.status === 'inactive' ? 'Deactivate' : 'Reactivate'}
              </button>
              <button type="button" className="secondary-button" onClick={cancelStatusChange} disabled={updatingStatus}>
                Cancel
              </button>
            </div>
          </section>
        </div>
      )}

      {pendingPasswordReset && (
        <div className="dialog-backdrop">
          <section className="success-dialog" role="dialog" aria-modal="true" aria-labelledby="password-reset-title">
            <h2 id="password-reset-title">Reset password for {pendingPasswordReset.name}?</h2>
            <p>A new temporary password will be generated. The user will be required to change it the next time they use the application.</p>
            {passwordResetError && <p className="form-error" role="alert">{passwordResetError}</p>}
            <div className="dialog-actions">
              <button type="button" onClick={confirmPasswordReset} disabled={resettingPassword}>
                {resettingPassword ? 'Resetting password...' : 'Reset Password'}
              </button>
              <button type="button" className="secondary-button" onClick={cancelPasswordReset} disabled={resettingPassword}>
                Cancel
              </button>
            </div>
          </section>
        </div>
      )}

      {resetUser && temporaryPassword && (
        <div className="dialog-backdrop">
          <section className="success-dialog" role="dialog" aria-modal="true" aria-labelledby="password-reset-success-title">
            <h2 id="password-reset-success-title">Password reset successful</h2>
            <dl className="created-user-details">
              <div>
                <dt>User</dt>
                <dd>{resetUser.name}</dd>
              </div>
              <div>
                <dt>Temporary password</dt>
                <dd><code>{temporaryPassword}</code></dd>
              </div>
            </dl>
            <p>This temporary password is shown only once. The user must change it after signing in.</p>
            {resetUser.status === 'inactive' && (
              <p>This account is still inactive and must be reactivated separately before the user can access the application.</p>
            )}
            <div className="dialog-actions">
              <button type="button" onClick={handleCopyPassword}>Copy password</button>
              <button type="button" className="secondary-button" onClick={closePasswordResetDialog}>Done</button>
            </div>
            {copyStatus && <p role="status">{copyStatus}</p>}
          </section>
        </div>
      )}
    </section>
  )
}

export default AdminUsersPage