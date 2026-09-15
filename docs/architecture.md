# Architecture

## Overview

The ALE Ticket Management Tool is a local React/Flask/PostgreSQL application for
Alcatel-Lucent Enterprise laboratory support. Phase 1 includes the database
foundation, session authentication, CSRF protection, user provisioning, ticket
workflow, comments, assignment, and status history.

## Technology Stack

- **Frontend**: React with Vite and JavaScript
- **Backend**: Python Flask application factory with blueprints
- **Database**: PostgreSQL 16, accessed with psycopg 3
- **Communication**: JSON REST APIs under `/api`
- **Local services**: PostgreSQL is supplied by `compose.yml`; Flask and Vite run locally

## Request Flow

```
Browser (React/Vite :5173)
        |
        | credentialed JSON requests + X-CSRF-Token
        v
Flask API (:5000)
  request IDs, logging, CORS, CSRF
  auth/session checks and role permissions
  validation and response envelopes
        |
        v
PostgreSQL (:5433 host / :5432 container)
  users, tickets, comments, history, attachment metadata
```

`create_app()` loads environment configuration, initializes CORS and CSRF, registers
request middleware, and mounts the health, auth, admin-user, and ticket blueprints.
Database connections are opened per operation from `DB_HOST`, `DB_PORT`, `DB_NAME`,
`DB_USER`, and `DB_PASSWORD`, with a five-second timeout.

## Component Responsibilities

- **Frontend**: Forms, session-aware views, CSRF-token handling, and API error display.
- **Request middleware**: Request ID assignment, timing logs, and JSON handlers for
  404, 405, CSRF, and 500 errors.
- **Auth blueprint**: Login, logout, current-user lookup, CSRF-token issuance, and
  password changes. The signed session stores the authenticated user ID.
- **Admin blueprint**: Admin-only local account provisioning and one-time temporary
  password generation.
- **Ticket blueprint**: Ticket creation/listing/detail, comments, assignment, status
  transition rules, ownership checks, and audit-history writes.
- **Database**: Durable account, ticket, comment, history, and attachment metadata.

## Security Boundaries

Passwords are hashed with Werkzeug and never returned by the API. New accounts start
with `must_change_password = true`; protected endpoints reject those sessions until
the password is changed, while `/api/auth/me` and the change-password endpoint remain
available. Requesters are restricted to their own tickets, and all state-changing
browser requests require a session-backed CSRF token.

## Scope

Phase 1 does not include AI integrations, SSO, ticket deletion, comment editing or
deletion, attachment upload/download routes, search, or filtering. The schema keeps
extension points for SSO and attachment metadata without exposing unfinished workflows.