# API Documentation

## Overview

The ALE Ticket Management Tool exposes JSON REST endpoints under `/api`. Successful
responses use a `data` object. Errors use an `error` object with `code` and `message`;
validation errors may also include `details`. Every response includes an `X-Request-ID`
header.

## Health

### `GET /api/health`

Runs `SELECT 1` against PostgreSQL. Returns `200` when the backend and database are
reachable, or `503` with `DATABASE_UNAVAILABLE` when the database check fails.

## Authentication

### `GET /api/auth/csrf`

Returns a session-backed CSRF token in `data.csrf_token`. Call this before the first
state-changing request and whenever the session is cleared.

### `POST /api/auth/login`

Body: `{ "email": "user@example.com", "password": "..." }`. Emails are trimmed and
compared case-insensitively. A successful response returns `data.user` and establishes
a session. The user object never includes `password_hash`. Invalid credentials return
`401 INVALID_CREDENTIALS`; inactive accounts return `403 ACCOUNT_INACTIVE`.

### `GET /api/auth/me`

Requires authentication and returns the current safe user object. It remains available
while `must_change_password` is true.

### `POST /api/auth/change-password`

Requires authentication, including users whose temporary password must be changed.
Body: `{ "current_password": "...", "new_password": "..." }`. New passwords are
12-128 characters and must differ from the current password. A successful change
clears the session and returns `200`; the client must log in again. Wrong current
passwords return `401 INVALID_CURRENT_PASSWORD`.

### `POST /api/auth/logout`

Clears the session. The operation is idempotent and returns `200`.

## User Administration

### `POST /api/admin/users`

Requires an authenticated admin whose own password-change requirement is satisfied.
Body fields are `name`, `email`, `role`, and optional `department`. Allowed roles are
`requester`, `support_engineer`, `manager`, and `admin`. The backend generates a
temporary password, stores only its hash, sets `must_change_password` to true, and
returns the one-time `temporary_password` only in this `201` response. Duplicate
email returns `409 USER_ALREADY_EXISTS`.

## Tickets

All ticket endpoints require authentication. Requesters can see and comment on only
their own tickets. Support engineers, managers, and admins can access all tickets.

### `POST /api/tickets`

Creates a ticket with `title`, `description`, `priority` (`Low`, `Medium`, `High`, or
`Critical`), and `setup_snapshot`. New tickets belong to the authenticated requester,
start with status `New`, and create a `TICKET_CREATED` history row. Returns `201`.

### `GET /api/tickets?page=1&limit=10`

Lists tickets with pagination. `limit` must be 1-20. Requesters receive their own
tickets; other roles receive all tickets. The response contains `data.tickets` and
`data.pagination` (`page`, `limit`, `total`, `total_pages`).

### `GET /api/tickets/{ticket_id}`

Returns `data.ticket` and chronological `data.history`. The ID must be a UUID.
Requesters receive `404 TICKET_NOT_FOUND` for tickets they do not own.

### `POST /api/tickets/{ticket_id}/comments`

Adds a public comment from the authenticated user. Body: `{ "comment": "..." }`.
Returns `201` with the created comment.

### `GET /api/tickets/{ticket_id}/comments`

Returns comments in chronological order. Comment responses expose `user_id` and
`comment`; the database columns are `author_id` and `comment_text`.

### `PATCH /api/tickets/{ticket_id}/status`

Body: `{ "status": "Open" }`. Allowed transitions are `New -> Open`,
`Open -> In Progress`, `In Progress -> Resolved`, `Resolved -> In Progress`,
`Resolved -> Closed`, and `Closed -> In Progress`. Resolution text is required by
the database for `Resolved` and `Closed`. Closing sets `closed_at`; reopening clears
it. Requesters may only reopen their own closed tickets. Support engineers may change
status only when assigned to the ticket.

### `PATCH /api/tickets/{ticket_id}/assignment`

Body: `{ "assigned_to": "<user-uuid>" }` or `null`. Requesters cannot assign tickets.
Admins and managers may assign active support engineers or managers; an admin may also
self-assign. Support engineers may claim an unassigned ticket for themselves.

## CSRF, CORS, and Sessions

Send the CSRF token in `X-CSRF-Token` for `POST`, `PUT`, `PATCH`, and `DELETE`,
including login, logout, password change, and user creation. `GET`, `HEAD`, and
`OPTIONS` are exempt. Missing or invalid tokens return `403 CSRF_TOKEN_INVALID`.

The local frontend origin is `http://localhost:5173`; the backend normally runs on
`http://localhost:5000`. CORS allows configured origins with credentials. Sessions use
an HTTP-only cookie with `SameSite=Lax`; `SESSION_COOKIE_SECURE` is configurable.
CSRF state is held in the Flask session, not PostgreSQL.

## Common Status Codes

- `200` Success
- `201` Resource created
- `400` Invalid JSON or validation error
- `401` Authentication or credential failure
- `403` CSRF, role, or password-change restriction
- `404` Resource not found
- `409` Duplicate data or concurrent update conflict
- `500` Masked internal server error
- `503` Database health check unavailable