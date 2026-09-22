import { useEffect, useState } from 'react'

import { assignTicket, getAssignableUsers, getTicket } from '../api'

function formatDate(value) {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function TicketDetailPage({ ticketId, currentUser, onBack }) {
  const [ticket, setTicket] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(Boolean(ticketId))
  const [error, setError] = useState(null)
  const [assigning, setAssigning] = useState(false)
  const [assignmentError, setAssignmentError] = useState(null)
  const [assignmentSuccess, setAssignmentSuccess] = useState(null)
  const [assignableUsers, setAssignableUsers] = useState([])
  const [assignableUsersLoading, setAssignableUsersLoading] = useState(false)
  const [assignableUsersError, setAssignableUsersError] = useState(null)
  const [selectedAssignee, setSelectedAssignee] = useState('')

  const canManageAssignment = currentUser?.role === 'manager' || currentUser?.role === 'admin'

  async function loadTicket() {
    try {
      const data = await getTicket(ticketId)
      setTicket(data.ticket)
      setHistory(data.history || [])
    } catch (requestError) {
      setAssignmentError(requestError.message)
    }
  }

  useEffect(() => {
    let active = true

    if (!ticketId) {
      setTicket(null)
      setHistory([])
      setLoading(false)
      setError('No ticket was selected.')
      return () => {
        active = false
      }
    }

    async function loadInitialTicket() {
      setLoading(true)
      setError(null)

      try {
        const data = await getTicket(ticketId)
        if (active) {
          setTicket(data.ticket)
          setHistory(data.history || [])
        }
      } catch (requestError) {
        if (active) {
          setError(
            requestError.status === 404
              ? 'Ticket not found or you do not have access to it.'
              : requestError.message,
          )
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadInitialTicket()

    return () => {
      active = false
    }
  }, [ticketId])

  useEffect(() => {
    let active = true

    if (!canManageAssignment) {
      return () => {
        active = false
      }
    }

    async function loadAssignableUsers() {
      setAssignableUsersLoading(true)
      setAssignableUsersError(null)

      try {
        const users = await getAssignableUsers()
        if (active) {
          setAssignableUsers(users)
        }
      } catch (requestError) {
        if (active) {
          setAssignableUsersError(requestError.message)
        }
      } finally {
        if (active) {
          setAssignableUsersLoading(false)
        }
      }
    }

    loadAssignableUsers()

    return () => {
      active = false
    }
  }, [canManageAssignment])

  useEffect(() => {
    setSelectedAssignee(ticket?.assigned_to || '')
  }, [ticket?.assigned_to])

  async function handleAssignToMe() {
    setAssigning(true)
    setAssignmentError(null)
    setAssignmentSuccess(null)

    try {
      await assignTicket(ticketId, currentUser.id)
      setAssignmentSuccess('Ticket assigned successfully.')
      await loadTicket()
    } catch (requestError) {
      setAssignmentError(requestError.message)
      // The server may have changed the ticket even though this request failed; reflect that state.
      await loadTicket()
    } finally {
      setAssigning(false)
    }
  }

  async function handleUpdateAssignment() {
    setAssigning(true)
    setAssignmentError(null)
    setAssignmentSuccess(null)

    try {
      await assignTicket(ticketId, selectedAssignee === '' ? null : selectedAssignee)
      setAssignmentSuccess('Ticket assignment updated successfully.')
      await loadTicket()
    } catch (requestError) {
      setAssignmentError(requestError.message)
      // The server may have changed the ticket even though this request failed; reflect that state.
      await loadTicket()
    } finally {
      setAssigning(false)
    }
  }

  if (loading) {
    return <p>Loading ticket...</p>
  }

  if (error) {
    return (
      <div className="ticket-detail-state">
        <p className="form-error" role="alert">{error}</p>
        <button type="button" onClick={onBack}>Back</button>
      </div>
    )
  }

  if (!ticket) {
    return <p className="form-error" role="alert">Ticket not found.</p>
  }

  const assignedUserFromList = assignableUsers.find((user) => user.id === ticket.assigned_to)
  const assignedToDisplay = assignedUserFromList
    ? `${assignedUserFromList.name} (${assignedUserFromList.role})`
    : ticket.assigned_to === currentUser?.id
      ? `${currentUser.name} (You)`
      : ticket.assigned_to
  const currentAssigneeIsListed = assignableUsers.some((user) => user.id === ticket.assigned_to)

  return (
    <div className="ticket-detail">
      <button type="button" className="back-button" onClick={onBack}>Back</button>

      <section className="ticket-detail-section ticket-summary">
        <div>
          <p className="ticket-number">Ticket #{ticket.ticket_number}</p>
          <h2>{ticket.title}</h2>
        </div>
        <dl className="ticket-metadata">
          <div><dt>Status</dt><dd>{ticket.status}</dd></div>
          <div><dt>Priority</dt><dd>{ticket.priority}</dd></div>
        </dl>
      </section>

      <section className="ticket-detail-section">
        <h2>Description</h2>
        <p className="ticket-description">{ticket.description}</p>
      </section>

      <section className="ticket-detail-section">
        <h2>People</h2>
        <dl className="ticket-metadata">
          <div><dt>Requester</dt><dd>{ticket.requester_name || 'Not provided'}</dd></div>
          {ticket.requester_email && <div><dt>Requester Email</dt><dd>{ticket.requester_email}</dd></div>}
          {ticket.assigned_to && (
            <div>
              <dt>Assigned To</dt>
              <dd>{assignedToDisplay}</dd>
            </div>
          )}
          {!ticket.assigned_to && <div><dt>Assigned To</dt><dd>Unassigned</dd></div>}
        </dl>
        {currentUser?.role === 'support_engineer' && !ticket.assigned_to && (
          <div className="assignment-controls">
            <button type="button" onClick={handleAssignToMe} disabled={assigning}>
              {assigning ? 'Assigning...' : 'Assign to me'}
            </button>
            {assignmentSuccess && <p className="form-success" role="status">{assignmentSuccess}</p>}
            {assignmentError && <p className="form-error" role="alert">{assignmentError}</p>}
          </div>
        )}
        {canManageAssignment && (
          <div className="assignment-controls">
            {assignableUsersError && (
              <p className="form-error" role="alert">{assignableUsersError}</p>
            )}
            {!assignableUsersError && (
              <>
                <select
                  aria-label="Assignee"
                  value={selectedAssignee}
                  onChange={(event) => setSelectedAssignee(event.target.value)}
                  disabled={assigning || assignableUsersLoading}
                >
                  <option value="">Unassigned</option>
                  {ticket.assigned_to && !currentAssigneeIsListed && (
                    <option value={ticket.assigned_to} disabled>
                      Current assignee (not currently assignable)
                    </option>
                  )}
                  {assignableUsers.map((user) => (
                    <option key={user.id} value={user.id}>
                      {user.name} — {user.role}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={handleUpdateAssignment}
                  disabled={assigning || assignableUsersLoading}
                >
                  {assigning ? 'Updating assignment...' : 'Update assignment'}
                </button>
              </>
            )}
            {assignmentSuccess && <p className="form-success" role="status">{assignmentSuccess}</p>}
            {assignmentError && <p className="form-error" role="alert">{assignmentError}</p>}
          </div>
        )}
      </section>

      <section className="ticket-detail-section">
        <h2>Dates</h2>
        <dl className="ticket-metadata">
          {ticket.created_at && <div><dt>Created</dt><dd>{formatDate(ticket.created_at)}</dd></div>}
          {ticket.updated_at && <div><dt>Updated</dt><dd>{formatDate(ticket.updated_at)}</dd></div>}
          {ticket.due_date && <div><dt>Due</dt><dd>{formatDate(ticket.due_date)}</dd></div>}
          {ticket.closed_at && <div><dt>Closed</dt><dd>{formatDate(ticket.closed_at)}</dd></div>}
        </dl>
      </section>

      {ticket.resolution && (
        <section className="ticket-detail-section">
          <h2>Resolution</h2>
          <p className="ticket-description">{ticket.resolution}</p>
        </section>
      )}

      <section className="ticket-detail-section">
        <h2>Setup Information</h2>
        {ticket.setup_snapshot && Object.keys(ticket.setup_snapshot).length > 0 ? (
          <dl className="setup-snapshot">
            {Object.entries(ticket.setup_snapshot).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{value === null || value === '' ? 'Not provided' : String(value)}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p>No setup information provided.</p>
        )}
      </section>

      <section className="ticket-detail-section">
        <h2>History</h2>
        {history.length === 0 ? (
          <p>No history entries.</p>
        ) : (
          <ol className="ticket-history">
            {history.map((entry) => (
              <li key={entry.id}>
                <strong>{entry.action}</strong>
                <span>{entry.old_status || 'None'} to {entry.new_status || 'None'}</span>
                <span>{entry.actor_name || entry.actor_email || 'System'} · {formatDate(entry.created_at)}</span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  )
}

export default TicketDetailPage