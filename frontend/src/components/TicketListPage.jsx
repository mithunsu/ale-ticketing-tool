import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { getTickets } from '../api'

const PAGE_LIMIT = 10

function formatCreatedAt(value) {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function TicketRow({ ticket, onSelect }) {
  return (
    <tr>
      <td>
        <button
          className="ticket-link-button"
          type="button"
          onClick={() => onSelect(ticket.id)}
        >
          #{ticket.ticket_number}
        </button>
      </td>
      <td>{ticket.title}</td>
      <td>{ticket.status}</td>
      <td>{ticket.priority}</td>
      <td>{ticket.assignee_name || '—'}</td>
      <td>{formatCreatedAt(ticket.created_at)}</td>
    </tr>
  )
}

function TicketListPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [tickets, setTickets] = useState([])
  const [pagination, setPagination] = useState(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Extract filter params from URL
  const statusFilter = searchParams.get('status') || ''
  const priorityFilter = searchParams.get('priority') || ''
  const assignedToFilter = searchParams.get('assigned_to') || ''

  useEffect(() => {
    let active = true

    async function loadTickets() {
      setLoading(true)
      setError(null)

      try {
        const params = { page, limit: PAGE_LIMIT }

        // Add filters from URL query params
        if (statusFilter) {
          params.status = statusFilter
        }
        if (priorityFilter) {
          params.priority = priorityFilter
        }
        if (assignedToFilter) {
          params.assigned_to = assignedToFilter
        }

        // If no explicit filter at all, exclude closed tickets by default (for active view).
        // An explicit assigned_to/priority/status filter should show its full matching set,
        // matching the counts shown on the dashboard.
        if (!statusFilter && !priorityFilter && !assignedToFilter) {
          params.status_not = 'Closed'
        }

        const data = await getTickets(params)
        if (active) {
          setTickets(data.tickets)
          setPagination(data.pagination)
        }
      } catch (requestError) {
        if (active) {
          setError(requestError.message)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    loadTickets()

    return () => {
      active = false
    }
  }, [page, statusFilter, priorityFilter, assignedToFilter])

  function handleSelectTicket(ticketId) {
    navigate(`/tickets/${ticketId}`)
  }

  function handlePrevious() {
    setPage((current) => Math.max(1, current - 1))
  }

  function handleNext() {
    setPage((current) => (pagination && current < pagination.total_pages ? current + 1 : current))
  }

  if (loading) {
    return <p>Loading tickets...</p>
  }

  if (error) {
    return (
      <p className="form-error" role="alert">
        {error}
      </p>
    )
  }

  if (tickets.length === 0) {
    const filterDesc = statusFilter ? ` with status "${statusFilter}"` : priorityFilter ? ` with priority "${priorityFilter}"` : ''
    return <p>No tickets found{filterDesc}.</p>
  }

  const pageInfo = pagination ? `${(page - 1) * PAGE_LIMIT + 1} – ${Math.min(page * PAGE_LIMIT, pagination.total)}` : '—'
  const totalInfo = pagination ? `of ${pagination.total}` : ''

  return (
    <div className="ticket-list-page">
      <table className="ticket-table">
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Title</th>
            <th>Status</th>
            <th>Priority</th>
            <th>Assigned To</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((ticket) => (
            <TicketRow key={ticket.id} ticket={ticket} onSelect={handleSelectTicket} />
          ))}
        </tbody>
      </table>

      <div className="ticket-pagination">
        <button type="button" onClick={handlePrevious} disabled={page === 1}>
          Previous
        </button>
        <span className="pagination-info">
          Page {page} ({pageInfo} {totalInfo})
        </span>
        <button
          type="button"
          onClick={handleNext}
          disabled={!pagination || page >= pagination.total_pages}
        >
          Next
        </button>
      </div>
    </div>
  )
}

export default TicketListPage
