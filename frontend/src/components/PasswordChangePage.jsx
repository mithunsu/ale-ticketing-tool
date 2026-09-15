import { useState } from 'react'

import { changePassword } from '../api'

function PasswordChangePage({ onPasswordChangeSuccess }) {
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [passwordError, setPasswordError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    setPasswordError(null)

    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordError('Complete all password fields.')
      return
    }

    if (newPassword !== confirmPassword) {
      setPasswordError('New passwords do not match.')
      return
    }

    setIsSubmitting(true)

    try {
      await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      })
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      onPasswordChangeSuccess()
    } catch (error) {
      setPasswordError(error.message || 'Unable to change password. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className="login-page">
      <h1>Change your password</h1>
      <p>Your temporary password must be changed before continuing.</p>
      <form className="login-form" onSubmit={handleSubmit}>
        <label htmlFor="current-password">Current Password</label>
        <input
          id="current-password"
          type="password"
          value={currentPassword}
          onChange={(event) => setCurrentPassword(event.target.value)}
          autoComplete="current-password"
          required
        />
        <label htmlFor="new-password">New Password</label>
        <input
          id="new-password"
          type="password"
          value={newPassword}
          onChange={(event) => setNewPassword(event.target.value)}
          autoComplete="new-password"
          required
        />
        <label htmlFor="confirm-password">Confirm New Password</label>
        <input
          id="confirm-password"
          type="password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          autoComplete="new-password"
          required
        />
        {passwordError && <p className="form-error" role="alert">{passwordError}</p>}
        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Changing password...' : 'Change Password'}
        </button>
      </form>
    </main>
  )
}

export default PasswordChangePage