import { useEffect, useState } from 'react'

import { assignTicket, getTicket } from '../api'

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
              <dd>{ticket.assigned_to === currentUser?.id ? `${currentUser.name} (You)` : ticket.assigned_to}</dd>
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