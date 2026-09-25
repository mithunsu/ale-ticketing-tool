# Glossary

## ALE

**Alcatel-Lucent Enterprise** - The laboratory environment for which this ticket
management tool is being built.

## Ticket

A support request or task that needs to be tracked and resolved.

## Backend

The server-side Python Flask application that handles API requests, business logic,
validation, authentication, and database access.

## Frontend

The client-side React application that users interact with in their browser.

## API

**Application Programming Interface** - The REST endpoint and JSON contract between
frontend and backend.

## REST

**Representational State Transfer** - An HTTP-oriented API style using methods such as
GET, POST, and PATCH.

## JSON

**JavaScript Object Notation** - The data format used for API requests and responses.

## Blueprint

Flask's mechanism for organizing related routes into modules such as authentication,
administration, health, and tickets.

## Schema

The database structure defining tables, columns, constraints, indexes, and relations.

## Seed Data

Sample records used to populate a development database.

## Authentication

The process of verifying user identity with a local email and password, then
maintaining the authenticated browser session.

## Authorization

Rules determining which authenticated roles may perform an operation or access a
ticket. Requesters are limited to their own tickets; support engineers, managers, and
admins have broader workflow permissions.

## CSRF

**Cross-Site Request Forgery** - An attack in which a browser is tricked into sending
an authenticated state-changing request. The backend requires a session-backed token
in `X-CSRF-Token` for mutation requests.

## Temporary Password

A backend-generated first password for a newly provisioned local account. It is
returned once to the administrator, stored only as a hash, and must be replaced by
the user before normal protected operations.

## Password Change Required

The account state represented by `must_change_password = true`. The user may inspect
their session and call the password-change endpoint, but normal protected operations
return `PASSWORD_CHANGE_REQUIRED` until the change succeeds.

## Request ID

An identifier returned in `X-Request-ID` and included in backend request logs so a
client can correlate an API response with server-side diagnostics.

## Ticket History

An immutable record of ticket creation and status transitions, including the actor,
old status, new status, and timestamp.

## Setup Snapshot

The JSONB ticket field containing laboratory environment details associated with a
request, such as server, platform, DUT, console, and network endpoint information.

## UUID

**Universally Unique Identifier** - The opaque identifier used for users, tickets,
comments, history rows, and attachments instead of exposing sequential database IDs.

## PostgreSQL

The relational database used for durable accounts, tickets, comments, status history,
and attachment metadata.

## Vite

Frontend build tool and development server used with React.

## npm

**Node Package Manager** - Tool for managing JavaScript dependencies and scripts.

## pip

**Package Installer for Python** - Tool for managing Python dependencies.

## Virtual Environment

An isolated Python environment with its own dependencies, created with `venv`.

## CORS

**Cross-Origin Resource Sharing** - HTTP mechanism allowing configured frontend and
backend origins to communicate with credentials.

## CRUD

**Create, Read, Update, Delete** - Basic data operations. This API implements only a
subset for tickets and intentionally omits destructive ticket deletion.

## RBAC

**Role-Based Access Control** - Authorization based on the user's role and, for
requesters, ownership of the ticket. The backend is the enforcement boundary.

## Session

The HTTP-only Flask cookie state that identifies an authenticated browser user. The
session stores the user identity rather than a client-managed access token.

## Middleware

Cross-cutting request handling around Flask routes, including request IDs, logging,
CSRF, CORS, and JSON error responses.

## Parameterized Query

A SQL statement whose values are bound separately from the SQL text. The backend uses
this pattern to reduce SQL injection risk.

## JSONB

PostgreSQL's binary JSON type. Tickets use it for the validated `setup_snapshot`.

## E2E Test

An end-to-end check that exercises the application through the browser and its running
backend and database.

## Regression Test

A test that confirms previously working behavior remains working after a change.

## State Machine

The explicit set of allowed ticket status transitions enforced by the backend.

## Audit Log

The immutable `ticket_history` records that capture ticket creation and status changes.