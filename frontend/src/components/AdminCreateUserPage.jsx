import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createAdminUser } from '../api'

const roleOptions = [
  { value: 'requester', label: 'Requester' },
  { value: 'support_engineer', label: 'Support Engineer' },
  { value: 'manager', label: 'Manager' },
  { value: 'admin', label: 'Admin' },
]

function AccessDenied() {
  return (
    <section className="user-management-page">
      <h1>User Management</h1>
      <p className="form-error" role="alert">Access denied. Admin access is required.</p>
    </section>
  )
}

function AdminCreateUserPage({ currentUser, onAuthenticationExpired }) {
  const navigate = useNavigate()
  const [formValues, setFormValues] = useState({
    name: '',
    email: '',
    role: '',
    department: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState(null)
  const [accessDenied, setAccessDenied] = useState(false)
  const [createdUser, setCreatedUser] = useState(null)
  const [temporaryPassword, setTemporaryPassword] = useState(null)
  const [copyStatus, setCopyStatus] = useState(null)

  const isAdmin = currentUser.role === 'admin'

  function handleFieldChange(event) {
    const { name, value } = event.target
    setFormValues((currentValues) => ({ ...currentValues, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    const name = formValues.name.trim()
    const email = formValues.email.trim()
    const department = formValues.department.trim()

    if (!name || !email || !formValues.role) {
      setFormError('Name, email, and role are required.')
      return
    }

    setSubmitting(true)
    setFormError(null)

    const userData = { name, email, role: formValues.role }
    if (department) {
      userData.department = department
    }

    try {
      const data = await createAdminUser(userData)
      setCreatedUser(data.user)
      setTemporaryPassword(data.temporary_password)
    } catch (requestError) {
      if (requestError.status === 401) {
        onAuthenticationExpired()
      } else if (requestError.status === 403) {
        setAccessDenied(true)
      } else if (requestError.status === 409 || requestError.code === 'USER_ALREADY_EXISTS') {
        setFormError('A user with this email already exists.')
      } else if (requestError.status === 400) {
        setFormError('Please review the user details and try again.')
      } else {
        setFormError('Unable to create the user. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  function closeSuccessDialog() {
    setCopyStatus(null)
    setTemporaryPassword(null)
    setCreatedUser(null)
    navigate('/admin/users')
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

  return (
    <section className="user-management-page admin-create-user-page">
      <h1>Create User</h1>
      <p className="user-management-subtitle">Create an ALE Ticket Management Tool account</p>

      <form className="ticket-form" onSubmit={handleSubmit}>
        <label>
          Name
          <input name="name" type="text" value={formValues.name} onChange={handleFieldChange} required />
        </label>
        <label>
          Email
          <input name="email" type="email" value={formValues.email} onChange={handleFieldChange} required />
        </label>
        <label>
          Role
          <select name="role" value={formValues.role} onChange={handleFieldChange} required>
            <option value="" disabled>Select a role</option>
            {roleOptions.map((role) => (
              <option key={role.value} value={role.value}>{role.label}</option>
            ))}
          </select>
        </label>
        <label>
          Department
          <input name="department" type="text" value={formValues.department} onChange={handleFieldChange} />
        </label>

        {formError && <p className="form-error" role="alert">{formError}</p>}
        {submitting && <p role="status">Creating user...</p>}

        <div className="admin-create-user-actions">
          <button type="submit" disabled={submitting}>{submitting ? 'Creating user...' : 'Create User'}</button>
          <button type="button" className="secondary-button" onClick={() => navigate('/admin/users')} disabled={submitting}>
            Cancel
          </button>
        </div>
      </form>

      {createdUser && temporaryPassword && (
        <div className="dialog-backdrop">
          <section className="success-dialog" role="dialog" aria-modal="true" aria-labelledby="create-user-success-title">
            <h2 id="create-user-success-title">User created successfully.</h2>
            <dl className="created-user-details">
              <div>
                <dt>Name</dt>
                <dd>{createdUser.name}</dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd>{createdUser.email}</dd>
              </div>
              <div>
                <dt>Temporary password</dt>
                <dd><code>{temporaryPassword}</code></dd>
              </div>
            </dl>
            <p>This temporary password is shown only once. The user will be required to change it after signing in.</p>
            <div className="dialog-actions">
              <button type="button" onClick={handleCopyPassword}>Copy password</button>
              <button type="button" className="secondary-button" onClick={closeSuccessDialog}>Done</button>
            </div>
            {copyStatus && <p role="status">{copyStatus}</p>}
          </section>
        </div>
      )}
    </section>
  )
}

export default AdminCreateUserPage