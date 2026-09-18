import { useEffect, useState } from 'react'

import { getTickets } from '../api'

const PAGE_LIMIT = 10

function formatCreatedAt(value) {
  if (!value) {
    return ''
  }

  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function ClosedTicketsPage({ onSelectTicket }) {
  const [tickets, setTickets] = useState([])
  const [pagination, setPagination] = useState(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true

    async function loadClosedTickets() {
      setLoading(true)
      setError(null)

      try {
        const data = await getTickets({ status: 'Closed', page, limit: PAGE_LIMIT })
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

    loadClosedTickets()

    return () => {
      active = false
    }
  }, [page])

  function handlePrevious() {
    setPage((current) => Math.max(1, current - 1))
  }

  function handleNext() {
    setPage((current) => (pagination && current < pagination.total_pages ? current + 1 : current))
  }

  if (loading) {
    return <p>Loading closed tickets...</p>
  }

  if (error) {
    return (
      <p className="form-error" role="alert">
        {error}
      </p>
    )
  }

  if (tickets.length === 0) {
    return <p>No closed tickets.</p>
  }

  return (
    <div className="closed-tickets-page">
      <table className="ticket-table">
        <thead>
          <tr>
            <th>Ticket #</th>
            <th>Title</th>
            <th>Status</th>
            <th>Priority</th>
            <th>Requester</th>
            <th>Assigned To</th>
            <th>Created At</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((ticket) => (
            <tr key={ticket.id}>
              <td>
                <button
                  type="button"
                  className="ticket-link"
                  onClick={() => onSelectTicket(ticket.id)}
                >
                  {ticket.ticket_number}
                </button>
              </td>
              <td>
                <button
                  type="button"
                  className="ticket-link"
                  onClick={() => onSelectTicket(ticket.id)}
                >
                  {ticket.title}
                </button>
              </td>
              <td>{ticket.status}</td>
              <td>{ticket.priority}</td>
              <td>{ticket.requester_name}</td>
              <td>{ticket.assignee_name || 'Unassigned'}</td>
              <td>{formatCreatedAt(ticket.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {pagination && (
        <div className="pagination-controls">
          <button type="button" onClick={handlePrevious} disabled={page <= 1}>
            Previous
          </button>
          <span>
            Page {pagination.page} of {pagination.total_pages || 1}
          </span>
          <button type="button" onClick={handleNext} disabled={page >= pagination.total_pages}>
            Next
          </button>
        </div>
      )}
    </div>
  )
}

export default ClosedTicketsPage
