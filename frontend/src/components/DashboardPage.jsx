import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { getTickets } from '../api'

function formatDate(value) {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }

  const now = new Date()
  const diffMs = now - date
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

const PRIORITY_ORDER = { Critical: 0, High: 1, Medium: 2, Low: 3 }
const TERMINAL_STATUSES = new Set(['Resolved', 'Closed', 'Rejected'])

function DashboardMetricCard({ label, count, link }) {
  const navigate = useNavigate()

  function handleClick() {
    if (link) {
      navigate(link)
    }
  }

  return (
    <button
      className="dashboard-metric-card"
      onClick={handleClick}
      type="button"
      disabled={!link}
    >
      <div className="dashboard-metric-number">{count}</div>
      <div className="dashboard-metric-label">{label}</div>
    </button>
  )
}

function TicketSummaryRow({ ticket }) {
  const navigate = useNavigate()

  function handleClick() {
    navigate(`/tickets/${ticket.id}`)
  }

  return (
    <button
      className="dashboard-ticket-row"
      onClick={handleClick}
      type="button"
    >
      <div className="dashboard-ticket-number">#{ticket.ticket_number}</div>
      <div className="dashboard-ticket-title">{ticket.title}</div>
      <div className="dashboard-ticket-status">{ticket.status}</div>
      {ticket.priority && <div className="dashboard-ticket-priority">{ticket.priority}</div>}
    </button>
  )
}

function RecentTicketRow({ ticket }) {
  const navigate = useNavigate()

  function handleClick() {
    navigate(`/tickets/${ticket.id}`)
  }

  return (
    <button
      className="dashboard-ticket-row"
      onClick={handleClick}
      type="button"
    >
      <div className="dashboard-ticket-number">#{ticket.ticket_number}</div>
      <div className="dashboard-ticket-title">{ticket.title}</div>
      <div className="dashboard-ticket-status">{ticket.status}</div>
      <div className="dashboard-ticket-updated">{formatDate(ticket.updated_at)}</div>
    </button>
  )
}

function DashboardPage() {
  const [metrics, setMetrics] = useState({
    open: 0,
    inProgress: 0,
    critical: 0,
    assignedToMe: 0,
  })
  const [needsAttention, setNeedsAttention] = useState([])
  const [recentlyUpdated, setRecentlyUpdated] = useState([])
  const [_loadingMetrics, setLoadingMetrics] = useState(true)
  const [loadingNeedsAttention, setLoadingNeedsAttention] = useState(true)
  const [loadingRecent, setLoadingRecent] = useState(true)
  const [_errorMetrics, setErrorMetrics] = useState(null)
  const [errorNeedsAttention, setErrorNeedsAttention] = useState(null)
  const [errorRecent, setErrorRecent] = useState(null)

  // Load metrics
  useEffect(() => {
    let active = true

    async function loadMetrics() {
      setLoadingMetrics(true)
      setErrorMetrics(null)

      try {
        const [openData, inProgressData, criticalData, assignedData] = await Promise.all([
          getTickets({ status: 'Open', limit: 1 }),
          getTickets({ status: 'In Progress', limit: 1 }),
          getTickets({ priority: 'Critical', limit: 1 }),
          getTickets({ assigned_to: 'me', limit: 1 }),
        ])

        if (active) {
          setMetrics({
            open: openData.pagination?.total || 0,
            inProgress: inProgressData.pagination?.total || 0,
            critical: criticalData.pagination?.total || 0,
            assignedToMe: assignedData.pagination?.total || 0,
          })
        }
      } catch (error) {
        if (active) {
          setErrorMetrics(error.message)
        }
      } finally {
        if (active) {
          setLoadingMetrics(false)
        }
      }
    }

    loadMetrics()
    return () => {
      active = false
    }
  }, [])

  // Load needs attention tickets
  useEffect(() => {
    let active = true

    async function loadNeedsAttention() {
      setLoadingNeedsAttention(true)
      setErrorNeedsAttention(null)

      try {
        // Exclude terminal statuses to find tickets that need attention.
        // limit is capped at 20 (backend max); local sort/filter narrows to top 5.
        const data = await getTickets({
          status_not: 'Closed',
          limit: 20,
        })

        if (active && data.tickets) {
          // Filter out terminal statuses and sort by priority then updated_at
          const filtered = data.tickets
            .filter((t) => !TERMINAL_STATUSES.has(t.status))
            .sort((a, b) => {
              const priorityDiff = (PRIORITY_ORDER[a.priority] ?? 999) - (PRIORITY_ORDER[b.priority] ?? 999)
              if (priorityDiff !== 0) return priorityDiff
              return new Date(b.updated_at || 0) - new Date(a.updated_at || 0)
            })
            .slice(0, 5)

          setNeedsAttention(filtered)
        }
      } catch (error) {
        if (active) {
          setErrorNeedsAttention(error.message)
        }
      } finally {
        if (active) {
          setLoadingNeedsAttention(false)
        }
      }
    }

    loadNeedsAttention()
    return () => {
      active = false
    }
  }, [])

  // Load recently updated tickets
  useEffect(() => {
    let active = true

    async function loadRecent() {
      setLoadingRecent(true)
      setErrorRecent(null)

      try {
        const data = await getTickets({ limit: 5 })

        if (active && data.tickets) {
          // Sort by updated_at descending (most recent first)
          const sorted = data.tickets
            .sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0))
            .slice(0, 5)

          setRecentlyUpdated(sorted)
        }
      } catch (error) {
        if (active) {
          setErrorRecent(error.message)
        }
      } finally {
        if (active) {
          setLoadingRecent(false)
        }
      }
    }

    loadRecent()
    return () => {
      active = false
    }
  }, [])

  return (
    <div className="dashboard-page">
      <section className="dashboard-section">
        <h2>Summary</h2>
        <div className="dashboard-metrics">
          <DashboardMetricCard label="Open" count={metrics.open} link="/tickets?status=Open" />
          <DashboardMetricCard label="In Progress" count={metrics.inProgress} link="/tickets?status=In%20Progress" />
          <DashboardMetricCard label="Critical" count={metrics.critical} link="/tickets?priority=Critical" />
          <DashboardMetricCard label="Assigned to Me" count={metrics.assignedToMe} link="/tickets?assigned_to=me" />
        </div>
      </section>

      <section className="dashboard-section">
        <h2>Needs My Attention</h2>
        {errorNeedsAttention && (
          <p className="form-error" role="alert">
            {errorNeedsAttention}
          </p>
        )}
        {loadingNeedsAttention ? (
          <p>Loading...</p>
        ) : needsAttention.length === 0 ? (
          <p>No tickets need your attention.</p>
        ) : (
          <>
            <div className="dashboard-ticket-list">
              {needsAttention.map((ticket) => (
                <TicketSummaryRow key={ticket.id} ticket={ticket} />
              ))}
            </div>
            <Link to="/tickets" className="dashboard-view-all-link">
              View all tickets
            </Link>
          </>
        )}
      </section>

      <section className="dashboard-section">
        <h2>Recently Updated</h2>
        {errorRecent && (
          <p className="form-error" role="alert">
            {errorRecent}
          </p>
        )}
        {loadingRecent ? (
          <p>Loading...</p>
        ) : recentlyUpdated.length === 0 ? (
          <p>No recently updated tickets.</p>
        ) : (
          <div className="dashboard-ticket-list">
            {recentlyUpdated.map((ticket) => (
              <RecentTicketRow key={ticket.id} ticket={ticket} />
            ))}
          </div>
        )}
      </section>

      <section className="dashboard-section">
        <Link to="/create" className="dashboard-create-button">
          Create Ticket
        </Link>
      </section>
    </div>
  )
}

export default DashboardPage
