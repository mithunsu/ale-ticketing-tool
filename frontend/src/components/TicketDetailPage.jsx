import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { assignTicket, createTicketComment, getAssignableUsers, getTicket, getTicketComments, getTickets, updateTicketStatus } from '../api'

function formatMetadataDate(value) {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  const dateOptions = date.getFullYear() === new Date().getFullYear()
    ? { month: 'short', day: 'numeric' }
    : { month: 'short', day: 'numeric', year: 'numeric' }
  const time = date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  return `${date.toLocaleDateString([], dateOptions)}, ${time}`
}

function formatActivityTime(value) {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()
  const dateOptions = date.getFullYear() === now.getFullYear()
    ? { month: 'short', day: 'numeric' }
    : { month: 'short', day: 'numeric', year: 'numeric' }
  const time = date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

  return isToday ? time : `${date.toLocaleDateString([], dateOptions)} · ${time}`
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
  const [showResolutionEditor, setShowResolutionEditor] = useState(false)
  const [comments, setComments] = useState([])
  const [commentsLoading, setCommentsLoading] = useState(false)
  const [commentsError, setCommentsError] = useState(null)
  const [commentText, setCommentText] = useState('')
  const [commentSubmitting, setCommentSubmitting] = useState(false)
  const [commentSubmitError, setCommentSubmitError] = useState(null)
  const [commentSubmitSuccess, setCommentSubmitSuccess] = useState(null)
  const [queueTickets, setQueueTickets] = useState([])
  const [queueLoading, setQueueLoading] = useState(true)
  const [queueError, setQueueError] = useState(null)
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
    setShowResolutionEditor(false)
    setResolutionDraft('')

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

  useEffect(() => {
    let active = true

    async function loadQueue() {
      setQueueLoading(true)
      setQueueError(null)

      try {
        const data = await getTickets({ limit: 10, status_not: 'Closed' })
        if (active) {
          setQueueTickets(data.tickets || [])
        }
      } catch (requestError) {
        if (active) {
          setQueueError(requestError.message)
        }
      } finally {
        if (active) {
          setQueueLoading(false)
        }
      }
    }

    loadQueue()

    return () => {
      active = false
    }
  }, [])

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
      if (targetStatus === 'Resolved') {
        setShowResolutionEditor(false)
      }
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
    if (action.target === 'Resolved') {
      setStatusError(null)
      setShowResolutionEditor(true)
      return
    }

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

  const setupLabelMap = {
    server_name: 'Server',
    server_ip: 'Server IP',
    platform: 'Platform',
    dut: 'DUT',
    aos_image_build: 'AOS Image',
    pal_server: 'PAL Server',
    emp: 'EMP',
    console: 'Console',
    console_port: 'Console Port',
    rps: 'RPS',
    rps_port: 'RPS Port',
    gateway: 'Gateway',
    gateway_port: 'Gateway Port',
    ixia: 'IXIA',
    ixia_port: 'IXIA Port',
    full_model: 'Full Model',
    notes: 'Notes',
  }

  function formatSetupValue(value) {
    if (value === null || value === undefined) {
      return 'N/A'
    }

    const text = String(value).trim()
    return text || 'N/A'
  }

  function buildSetupRows(setupSnapshot) {
    if (!setupSnapshot || typeof setupSnapshot !== 'object') {
      return []
    }

    const entries = Object.entries(setupSnapshot).filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== '')
    const primaryOrder = [
      'server_name',
      'server_ip',
      'platform',
      'dut',
      'aos_image_build',
      'emp',
      'console',
      'console_port',
      'rps',
      'rps_port',
      'gateway',
      'gateway_port',
      'ixia',
      'ixia_port',
      'pal_server',
      'full_model',
      'notes',
    ]

    const combinedKeyPatterns = [
      ['console', 'console_port'],
      ['rps', 'rps_port'],
      ['gateway', 'gateway_port'],
      ['ixia', 'ixia_port'],
    ]

    const seenKeys = new Set()
    const rows = []

    for (const [key, value] of entries) {
      if (seenKeys.has(key)) {
        continue
      }
      const pair = combinedKeyPatterns.find(([first, second]) => key === first || key === second)
      if (pair) {
        const [first, second] = pair
        const firstValue = formatSetupValue(setupSnapshot[first])
        const secondValue = formatSetupValue(setupSnapshot[second])
        const combinedValue = [firstValue === 'N/A' ? '' : firstValue, secondValue === 'N/A' ? '' : secondValue]
          .filter(Boolean)
          .join(' : ')

        if (combinedValue) {
          rows.push({ key: first, label: setupLabelMap[first], value: combinedValue })
          seenKeys.add(first)
          seenKeys.add(second)
        }
        continue
      }

      if (primaryOrder.includes(key)) {
        rows.push({ key, label: setupLabelMap[key] || key.replace(/_/g, ' '), value: formatSetupValue(value) })
        seenKeys.add(key)
      }
    }

    const optionalRows = entries
      .filter(([key]) => !seenKeys.has(key) && !primaryOrder.includes(key))
      .map(([key, value]) => ({
        key,
        label: setupLabelMap[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()),
        value: formatSetupValue(value),
      }))

    return [...rows, ...optionalRows]
  }

  const setupRows = buildSetupRows(ticket.setup_snapshot)

  function formatQueueTime(value) {
    if (!value) {
      return ''
    }

    const date = new Date(value)
    if (Number.isNaN(date.getTime())) {
      return ''
    }

    return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
  }

  return (
    <div className="ticket-detail">
      <div className="ticket-workbench">
        <aside className="ticket-workbench-left">
          <div className="ticket-context-panel">
            <div className="ticket-queue-header">
              <h2>Tickets</h2>
              <button
                type="button"
                className="ticket-queue-view-all"
                onClick={() => navigate('/tickets')}
              >
                View all
              </button>
            </div>

            {queueLoading ? (
              <p className="ticket-queue-status">Loading tickets...</p>
            ) : queueError ? (
              <p className="ticket-queue-status form-error" role="alert">Unable to load tickets.</p>
            ) : queueTickets.length === 0 ? (
              <p className="ticket-queue-status">No tickets found.</p>
            ) : (
              <ul className="ticket-queue-list">
                {queueTickets.map((queueTicket) => {
                  const isSelected = queueTicket.id != null && ticketId != null
                    && String(queueTicket.id) === String(ticketId)
                  const queueTime = formatQueueTime(queueTicket.updated_at || queueTicket.created_at)

                  return (
                    <li key={queueTicket.id}>
                      <button
                        type="button"
                        className={`ticket-queue-item${isSelected ? ' selected' : ''}`}
                        onClick={() => navigate(`/tickets/${queueTicket.id}`)}
                      >
                        <div className="ticket-queue-meta-row">
                          <span className="ticket-queue-number">#{queueTicket.ticket_number}</span>
                          {queueTime && <span className="ticket-queue-time">{queueTime}</span>}
                        </div>
                        <span className="ticket-queue-title">{queueTicket.title}</span>
                        <div className="ticket-queue-badges">
                          <span className="ticket-queue-status-pill">{queueTicket.status}</span>
                          <span className="ticket-queue-priority-pill">{queueTicket.priority}</span>
                        </div>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </aside>

        <main className="ticket-workbench-main">
          <section className="ticket-detail-section ticket-summary">
            <div className="ticket-summary-header">
              <p className="ticket-meta-line">
                #{ticket.ticket_number} · {ticket.requester_name || 'Requester unavailable'}
                {ticket.created_at ? ` · created ${new Date(ticket.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}` : ''}
              </p>
              <h1 className="ticket-title">{ticket.title}</h1>
            </div>

            <div className="ticket-workflow-row" ref={assignmentSectionRef}>
              <div className="ticket-workflow-badges">
                <span className="status-badge">{ticket.status}</span>
                <span className="priority-badge">{ticket.priority}</span>
                <span className="assignee-pill">{ticket.assigned_to ? assignedToDisplay : 'Unassigned'}</span>
              </div>

              <div className="ticket-workflow-actions">
                {supportAssignmentRequired && (
                  <div className="workflow-inline-action">
                    <button className="assignment-primary-button" type="button" onClick={handleAssignToMe} disabled={assigning}>
                      {assigning ? 'Assigning...' : 'Assign to me'}
                    </button>
                  </div>
                )}

                {canManageAssignment && (
                  <div className="workflow-inline-assignment">
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
                        <button type="button" onClick={handleUpdateAssignment} disabled={assigning || assignableUsersLoading}>
                          {assigning ? 'Assigning...' : 'Assign'}
                        </button>
                      </>
                    )}
                  </div>
                )}

                {statusActions.length > 0 && (
                  <div className="workflow-inline-status-actions">
                    {statusActions.map((action) => (
                      <button
                        key={action.target}
                        type="button"
                        onClick={() => handleStatusAction(action)}
                        disabled={statusUpdating}
                      >
                        {statusUpdating ? 'Updating status...' : action.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {showResolutionEditor && statusActions.some((action) => action.target === 'Resolved') && (
              <div className="resolution-editor">
                <label className="resolution-field">
                  Resolution
                  <textarea
                    aria-label="Resolution"
                    placeholder="Explain how the issue was resolved..."
                    value={resolutionDraft}
                    onChange={(event) => setResolutionDraft(event.target.value)}
                    disabled={statusUpdating}
                    rows={2}
                    required
                  />
                </label>
                <div className="resolution-editor-actions">
                  <button
                    type="button"
                    onClick={() => {
                      setShowResolutionEditor(false)
                      setResolutionDraft('')
                      setStatusError(null)
                    }}
                    disabled={statusUpdating}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => handleStatusTransition('Resolved')}
                    disabled={statusUpdating || resolutionDraft.trim() === ''}
                  >
                    {statusUpdating ? 'Resolving...' : 'Confirm Resolve'}
                  </button>
                </div>
              </div>
            )}

            {(statusSuccess || statusError) && (
              <div className="ticket-workflow-message">
                {statusSuccess && <p className="form-success" role="status">{statusSuccess}</p>}
                {statusError && <p className="form-error" role="alert">{statusError}</p>}
              </div>
            )}
            {supportAssignmentRequired && (
              <p className="status-workflow-guidance">Assign this ticket to yourself to update its status.</p>
            )}
            {assignmentSuccess && <p className="form-success" role="status">{assignmentSuccess}</p>}
            {assignmentError && <p className="form-error" role="alert">{assignmentError}</p>}
          </section>

          <section className="ticket-detail-section">
            <h2>Description</h2>
            <p className="ticket-description">{ticket.description}</p>
          </section>

          <section className="ticket-detail-section ticket-activity-section">
            <h2>Activity</h2>
            {commentsError && <p className="form-error" role="alert">{commentsError}</p>}
            {activityFeed.length === 0 && !commentsLoading && <p>No activity yet.</p>}
            {activityFeed.length > 0 && (
              <ol className="ticket-activity">
                {activityFeed.map((item) => {
                  if (item.activityType === 'history') {
                    return (
                      <li key={`history-${item.id}`} className="activity-entry activity-entry-history">
                        <strong>{item.data.actor_name || item.data.actor_email || 'System'}</strong>
                        <span className="activity-history-action">{formatHistoryAction(item.data)}</span>
                        <time dateTime={item.data.created_at}>{formatActivityTime(item.data.created_at)}</time>
                      </li>
                    )
                  }

                  const commentType = item.data.comment_type || 'public'
                  const commentClass = commentType === 'system' ? ' activity-comment-system' : ''

                  return (
                    <li key={`comment-${item.id}`} className={`activity-entry activity-entry-comment${commentClass}`}>
                      <div className="activity-comment-header">
                        <strong>{item.data.author_name || item.data.author_email || 'Unknown'}</strong>
                        {commentType === 'system' && <span className="activity-system-label">System</span>}
                      </div>
                      <p>{item.data.comment}</p>
                      <time dateTime={item.data.created_at}>{formatActivityTime(item.data.created_at)}</time>
                    </li>
                  )
                })}
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
        </main>

        <aside className="ticket-workbench-right">
          <section className="ticket-detail-section right-rail-section">
            <h2>Setup Information</h2>
            {setupRows.length > 0 ? (
              <dl className="setup-readout">
                {setupRows.map(({ key, label, value }) => (
                  <div key={key} className="setup-readout-row">
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p>No setup information provided.</p>
            )}
          </section>

          <section className="ticket-detail-section right-rail-section">
            <h2>Other Details</h2>
            <dl className="ticket-metadata ticket-metadata-compact">
              {ticket.created_at && <div><dt>Created</dt><dd>{formatMetadataDate(ticket.created_at)}</dd></div>}
              {ticket.updated_at && <div><dt>Updated</dt><dd>{formatMetadataDate(ticket.updated_at)}</dd></div>}
              {ticket.due_date && <div><dt>Due Date</dt><dd>{formatMetadataDate(ticket.due_date)}</dd></div>}
              {ticket.closed_at && <div><dt>Closed</dt><dd>{formatMetadataDate(ticket.closed_at)}</dd></div>}
              {ticket.resolution && <div className="ticket-detail-resolution"><dt>Resolution</dt><dd>{ticket.resolution}</dd></div>}
            </dl>
          </section>
        </aside>
      </div>

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