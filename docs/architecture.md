# Architecture

## Current system

The tool centralizes ALE laboratory support requests that were previously tracked in
email chains. The current implementation is a local React/Vite frontend, a Python
Flask REST API, and PostgreSQL 16.

```text
Browser (React/Vite :5173)
        |
        | credentialed JSON requests and X-CSRF-Token
        v
Flask API (:5000)
  sessions, CSRF, CORS, validation, RBAC, request logging
        |
        v
PostgreSQL (:5433 host / :5432 container)
  users, tickets, comments, history, attachment metadata
```

`compose.yml` supplies PostgreSQL. Flask and Vite run locally. `create_app()` loads
`backend/.env`, configures CORS and CSRF, registers request middleware, and mounts
health, auth, admin-user, user, and ticket blueprints. Connections use the `DB_*`
environment variables and a five-second timeout.

## Responsibilities

- **Frontend**: routing, forms, session-aware views, CSRF-token handling, role-aware
  controls, ticket dashboards, and API error display.
- **Backend**: authentication, server-side validation, authorization, ticket workflow,
  ownership isolation, assignment, public comments, history writes, and response
  envelopes.
- **Middleware**: request IDs, timing logs, CORS, and JSON error handling.
- **Database**: durable users, tickets, public/comment groundwork, status history, and
  attachment metadata.

## Authentication and authorization

Phase 1 uses admin-created local email/password accounts. Login establishes an
HTTP-only Flask session; a temporary-password account is restricted until it changes
that password. CSRF protection covers state-changing requests. The backend is the
security boundary and enforces role permissions even when the frontend hides a
control. Requesters are isolated to their own tickets, including anti-enumeration
responses for another requester's ticket.

## MVP workflow

Tickets support creation, listing, detail, assignment, self-assignment where allowed,
public comments, activity/history, and persistence. Valid status transitions are
`New -> Open`, `New -> In Progress`, `Open -> In Progress`, `In Progress -> Resolved`,
`Resolved -> In Progress`, `Resolved -> Closed`, and `Closed -> In Progress`.
Resolution is required for `Resolved` and `Closed`; `closed_at` is set on close and
cleared on reopen. Requesters may reopen their own closed tickets to `In Progress`.

## Frontend and backend structure

React pages live under `frontend/src/components`; API calls are centralized in
`frontend/src/api.js`. The Flask application is under `backend/app`, with route
modules in `backend/app/routes`, shared validation/response/database helpers, and
pytest coverage in `backend/tests`.

## Scope and hosting

The core Phase 1 MVP browser workflow is accepted. Search by ticket number/title,
status filtering, priority filtering, and browser validation for those controls are
Phase 1.1. Internal comments/notes are not a Phase 1 user-facing feature even though
the schema retains `public`, `internal`, and `system` comment types as groundwork.
ALE SSO, internal hosting hardening, attachments workflows, notifications, and AI/LLM
features remain future work. See [Deployment](deployment.md) for hosting status.