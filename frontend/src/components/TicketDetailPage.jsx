import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { assignTicket, createTicketComment, getAssignableUsers, getTicket, getTicketComments, updateTicketStatus } from '../api'

function formatDate(value) {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

// Renders the existing ticket_history.action value without inventing new semantics for actions we don't special-case.
function formatHistoryAction(entry) {
  if (entry.action === 'STATUS_CHANGED') {
    return `Changed status: ${entry.old_status || 'None'} \u2192 ${entry.new_status || 'None'}`
  }

  return entry.action
    .toLowerCase()
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

// Mirrors the backend's ALLOWED_STATUS_TRANSITIONS graph; Flask remains authoritative regardless of what is shown here.
function getStatusActions(ticket, currentUser) {
  if (!ticket || !currentUser) {
    return []
  }

  const isAssignedEngineer = currentUser.role === 'support_engineer' && ticket.assigned_to === currentUser.id
  const isManagerOrAdmin = currentUser.role === 'manager' || currentUser.role === 'admin'
  const canTransitionNormally = isAssignedEngineer || isManagerOrAdmin
  const canStartNewTicket = ticket.assigned_to === currentUser.id
    && (currentUser.role === 'support_engineer' || isManagerOrAdmin)
  const canOpenUnassignedTicket = !ticket.assigned_to
    && (currentUser.role === 'support_engineer' || isManagerOrAdmin)

  switch (ticket.status) {
    case 'New':
      return canStartNewTicket || canOpenUnassignedTicket
        ? [{ label: 'OPEN', target: 'In Progress' }]
        : []
    case 'Open':
      return canTransitionNormally ? [{ label: 'Start Progress', target: 'In Progress' }] : []
    case 'In Progress':
      return canTransitionNormally ? [{ label: 'Resolve', target: 'Resolved' }] : []
    case 'Resolved':
      return canTransitionNormally
        ? [
            { label: 'Reopen', target: 'In Progress' },
            { label: 'Close', target: 'Closed' },
          ]
        : []
    case 'Closed':
      return canTransitionNormally || currentUser.role === 'requester'
        ? [{ label: 'Reopen', target: 'In Progress' }]
        : []
    default:
      return []
  }
}

function TicketDetailPage({ currentUser }) {
  const { id: ticketId } = useParams()
  const navigate = useNavigate()
  const onBack = () => navigate('/tickets')

  const [ticket, setTicket] = useState(null)
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(Boolean(ticketId))
  const [error, setError] = useState(null)
  const [assigning, setAssigning] = useState(false)
  const [assignmentError, setAssignmentError] = useState(null)
  const [assignmentSuccess, setAssignmentSuccess] = useState(null)
  const [showAssignmentModal, setShowAssignmentModal] = useState(false)
  const [assignableUsers, setAssignableUsers] = useState([])
  const [assignableUsersLoading, setAssignableUsersLoading] = useState(false)
  const [assignableUsersError, setAssignableUsersError] = useState(null)
  const [selectedAssignee, setSelectedAssignee] = useState('')
  const [statusUpdating, setStatusUpdating] = useState(false)
  const [statusError, setStatusError] = useState(null)
  const [statusSuccess, setStatusSuccess] = useState(null)
  const [resolutionDraft, setResolutionDraft] = useState('')
  const [comments, setComments] = useState([])
  const [commentsLoading, setCommentsLoading] = useState(false)
  const [commentsError, setCommentsError] = useState(null)
  const [commentText, setCommentText] = useState('')
  const [commentSubmitting, setCommentSubmitting] = useState(false)
  const [commentSubmitError, setCommentSubmitError] = useState(null)
  const [commentSubmitSuccess, setCommentSubmitSuccess] = useState(null)
  const assignmentSectionRef = useRef(null)

  const canManageAssignment = currentUser?.role === 'manager' || currentUser?.role === 'admin'

  useEffect(() => {
    if (!showAssignmentModal) {
      return undefined
    }

    function handleKeyDown(event) {
      if (event.key === 'Escape' && !assigning) {
        setShowAssignmentModal(false)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [showAssignmentModal, assigning])

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

  // history and comments stay the source of truth; activity is only ever derived from them, never stored separately.
  const activityFeed = useMemo(() => {
    const historyActivity = history.map((entry) => ({
      activityType: 'history',
      id: entry.id,
      created_at: entry.created_at,
      data: entry,
    }))
    const commentActivity = comments.map((comment) => ({
      activityType: 'comment',
      id: comment.id,
      created_at: comment.created_at,
      data: comment,
    }))

    return [...historyActivity, ...commentActivity].sort((a, b) => {
      const aTime = new Date(a.created_at).getTime()
      const bTime = new Date(b.created_at).getTime()
      if (aTime !== bTime) {
        return bTime - aTime
      }

      // deterministic tie-breaker for equal timestamps: composite of activity type + id
      const aKey = `${a.activityType}-${a.id}`
      const bKey = `${b.activityType}-${b.id}`
      return aKey > bKey ? -1 : aKey < bKey ? 1 : 0
    })
  }, [history, comments])

  async function loadComments() {
    try {
      const data = await getTicketComments(ticketId)
      setComments(data)
    } catch (requestError) {
      setCommentsError(requestError.message)
    }
  }

  useEffect(() => {
    let active = true

    if (!ticketId) {
      setComments([])
      return () => {
        active = false
      }
    }

    async function loadInitialComments() {
      setCommentsLoading(true)
      setCommentsError(null)

      try {
        const data = await getTicketComments(ticketId)
        if (active) {
          setComments(data)
        }
      } catch (requestError) {
        if (active) {
          setCommentsError(requestError.message)
        }
      } finally {
        if (active) {
          setCommentsLoading(false)
        }
      }
    }

    loadInitialComments()

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
      setShowAssignmentModal(false)
    } catch (requestError) {
      setAssignmentError(requestError.message)
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

  async function handleStatusTransition(targetStatus) {
    let resolutionToSend

    if (targetStatus === 'Resolved') {
      const trimmedResolution = resolutionDraft.trim()
      if (!trimmedResolution) {
        setStatusError('Resolution is required to resolve a ticket.')
        return
      }
      resolutionToSend = trimmedResolution
    }

    setStatusUpdating(true)
    setStatusError(null)
    setStatusSuccess(null)

    try {
      await updateTicketStatus(ticketId, targetStatus, resolutionToSend)
      setStatusSuccess('Ticket status updated successfully.')
      setResolutionDraft('')
      await loadTicket()
      // resolving creates a ticket comment server-side, so refresh comments too
      if (targetStatus === 'Resolved') {
        await loadComments()
      }
    } catch (requestError) {
      setStatusError(requestError.message)
      // The server may have changed the ticket even though this request failed; reflect that state.
      await loadTicket()
    } finally {
      setStatusUpdating(false)
    }
  }

  function handleStatusAction(action) {
    if (ticket.status === 'New' && action.target === 'In Progress' && !ticket.assigned_to) {
      setAssignmentError(null)
      setShowAssignmentModal(true)
      return
    }

    handleStatusTransition(action.target)
  }

  function handleGoToAssignment() {
    setShowAssignmentModal(false)
    assignmentSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  async function handleSubmitComment(event) {
    event.preventDefault()

    const trimmedComment = commentText.trim()
    if (!trimmedComment) {
      setCommentSubmitError('Comment cannot be blank.')
      return
    }

    setCommentSubmitting(true)
    setCommentSubmitError(null)
    setCommentSubmitSuccess(null)

    try {
      await createTicketComment(ticketId, trimmedComment)
      setCommentText('')
      setCommentSubmitSuccess('Comment posted successfully.')
      await loadComments()
    } catch (requestError) {
      setCommentSubmitError(requestError.message)
    } finally {
      setCommentSubmitting(false)
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
  const statusActions = getStatusActions(ticket, currentUser)
  const supportAssignmentRequired = currentUser?.role === 'support_engineer' && !ticket.assigned_to

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
        {statusActions.length > 0 && (
          <div className="status-actions">
            {statusActions.some((action) => action.target === 'Resolved') && (
              <label>
                Resolution
                <textarea
                  aria-label="Resolution"
                  value={resolutionDraft}
                  onChange={(event) => setResolutionDraft(event.target.value)}
                  disabled={statusUpdating}
                  rows={3}
                  required
                />
              </label>
            )}
            {statusActions.map((action) => (
              <button
                key={action.target}
                type="button"
                onClick={() => handleStatusAction(action)}
                disabled={statusUpdating || (action.target === 'Resolved' && resolutionDraft.trim() === '')}
              >
                {statusUpdating ? 'Updating status...' : action.label}
              </button>
            ))}
          </div>
        )}
        {(statusSuccess || statusError) && (
          <div className="status-actions">
            {statusSuccess && <p className="form-success" role="status">{statusSuccess}</p>}
            {statusError && <p className="form-error" role="alert">{statusError}</p>}
          </div>
        )}
        {supportAssignmentRequired && (
          <p className="status-workflow-guidance">Assign this ticket to yourself to update its status.</p>
        )}
      </section>

      <section className="ticket-detail-section">
        <h2>Description</h2>
        <p className="ticket-description">{ticket.description}</p>
      </section>

      <section className="ticket-detail-section" ref={assignmentSectionRef}>
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
        {supportAssignmentRequired && (
          <div className="assignment-required">
            <h3>Assignment required</h3>
            <p>Assign this ticket to yourself before updating its status or resolving it.</p>
            <button className="assignment-primary-button" type="button" onClick={handleAssignToMe} disabled={assigning}>
              {assigning ? 'Assigning...' : 'Assign to me'}
            </button>
            {assignmentSuccess && <p className="form-success" role="status">{assignmentSuccess}</p>}
            {assignmentError && <p className="form-error" role="alert">{assignmentError}</p>}
          </div>
        )}
        {canManageAssignment && (
          <div className="assignment-controls">
            {!ticket.assigned_to && (
              <p className="assignment-helper-text">Assign this ticket to a support engineer before work begins.</p>
            )}
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
        <h2>Activity</h2>
        {commentsError && <p className="form-error" role="alert">{commentsError}</p>}
        {activityFeed.length === 0 && !commentsLoading && <p>No activity yet.</p>}
        {activityFeed.length > 0 && (
          <ol className="ticket-activity">
            {activityFeed.map((item) => (
              item.activityType === 'history' ? (
                <li key={`history-${item.id}`} className="activity-entry activity-entry-history">
                  <strong>{item.data.actor_name || item.data.actor_email || 'System'}</strong>
                  <span>{formatHistoryAction(item.data)}</span>
                  <span>{formatDate(item.data.created_at)}</span>
                </li>
              ) : (
                <li key={`comment-${item.id}`} className="activity-entry activity-entry-comment">
                  <strong>{item.data.author_name || item.data.author_email || 'Unknown'}</strong>
                  <p className="ticket-description">{item.data.comment}</p>
                  <span>{formatDate(item.data.created_at)}</span>
                </li>
              )
            ))}
          </ol>
        )}
        {commentsLoading && <p>Loading comments...</p>}

        <form className="comment-form" onSubmit={handleSubmitComment}>
          <textarea
            aria-label="New comment"
            value={commentText}
            onChange={(event) => setCommentText(event.target.value)}
            disabled={commentSubmitting}
            rows={3}
          />
          <button type="submit" disabled={commentSubmitting}>
            {commentSubmitting ? 'Posting...' : 'Submit'}
          </button>
          {commentSubmitSuccess && <p className="form-success" role="status">{commentSubmitSuccess}</p>}
          {commentSubmitError && <p className="form-error" role="alert">{commentSubmitError}</p>}
        </form>
      </section>

      {showAssignmentModal && (
        <div
          className="dialog-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget && !assigning) {
              setShowAssignmentModal(false)
            }
          }}
        >
          <section className="success-dialog assignment-modal" role="dialog" aria-modal="true" aria-labelledby="assignment-modal-title">
            <h2 id="assignment-modal-title">Assignment required</h2>
            <p>
              {currentUser.role === 'support_engineer'
                ? 'This ticket must be assigned before it can be opened. Assign it to yourself first.'
                : 'This ticket must be assigned before it can be opened. Assign the ticket to a support engineer first.'}
            </p>
            {currentUser.role === 'support_engineer' && assignmentError && (
              <p className="form-error" role="alert">{assignmentError}</p>
            )}
            <div className="dialog-actions">
              <button
                className="secondary-button"
                type="button"
                onClick={() => setShowAssignmentModal(false)}
                disabled={assigning}
              >
                Cancel
              </button>
              {currentUser.role === 'support_engineer' ? (
                <button
                  className="assignment-primary-button"
                  type="button"
                  onClick={handleAssignToMe}
                  disabled={assigning}
                >
                  {assigning ? 'Assigning...' : 'Assign to me'}
                </button>
              ) : (
                <button className="assignment-primary-button" type="button" onClick={handleGoToAssignment}>
                  Go to assignment
                </button>
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}

export default TicketDetailPage