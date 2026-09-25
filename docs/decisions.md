# Engineering Decisions

## Current Phase 1 decisions

**Status**: Adopted unless marked deferred. These entries summarize the current
implementation and supersede contradictory planning notes while older records below
remain for historical context.

### Flask is the current backend

The current implementation uses Python Flask with blueprints and a JSON REST API.
Any earlier Node.js/Express backend plan is superseded and retained only as history.

### PostgreSQL is the primary datastore

PostgreSQL 16 remains the durable store for users, tickets, comments, history, and
attachment metadata. Tickets use UUID primary keys plus generated sequential
`ticket_number` values.

### Backend RBAC is the security boundary

Flask enforces roles and requester ownership; the React frontend mirrors permissions
by hiding controls for usability. This prevents direct API callers from bypassing
frontend visibility rules.

### Local MVP authentication

Phase 1 uses admin-created local email/password accounts, temporary passwords, forced
first-password change, HTTP-only sessions, and CSRF protection. ALE SSO is deferred to
future integration.

### Public comments only in Phase 1

The accepted Phase 1 comment workflow is public comments. `internal` and `system`
comment types remain schema/backend groundwork for later work; internal notes are not
an MVP blocker or current user-facing requirement.

### Search and filtering are Phase 1.1

Ticket-number/title search, status filtering, priority filtering, and browser RBAC
validation for those controls are post-MVP work, not failed Phase 1 acceptance.

### Deterministic browser testing

Five disposable local E2E identities (Requester A, Requester B, Support Engineer,
Manager, and Admin) support repeatable role and persistence checks. Credentials remain
in the gitignored local E2E environment file and are never documented.

### Core browser acceptance passed

The current milestone is **Phase 1 MVP core workflow browser acceptance: PASS**. This
does not claim that Phase 1.1 search/filter work is complete.

---

## Decision: Python Flask for Backend

**Date**: 2026-07-28
**Status**: Adopted

### Decision

Use Python Flask for the backend.

### Rationale

- Matches the developer's workplace and career goals
- Provides a lightweight framework for a learning-focused application
- Has a strong ecosystem for backend development and automation

---

## Decision: React with Vite for Frontend

**Date**: 2026-07-28
**Status**: Adopted

### Decision

Use React with Vite for the frontend.

### Rationale

- Fast development server and build tooling
- Industry-standard component model
- Small initial dependency surface with room to grow

---

## Decision: PostgreSQL for Database

**Date**: 2026-07-28
**Status**: Adopted

### Decision

Use PostgreSQL as the primary relational database.

### Rationale

- Robust open-source relational database
- Strong support for constraints, JSONB, and audit queries
- Good Python integration through psycopg

---

## Decision: Session Authentication with CSRF Protection

**Date**: 2026-09-15
**Status**: Adopted

### Decision

Use Flask's signed, HTTP-only session cookie for browser authentication and Flask-WTF
CSRF protection for state-changing requests.

### Rationale

- Fits the credentialed React-to-Flask browser workflow
- Stores only the authenticated user ID in the session
- Avoids token refresh and client-side token storage during Phase 1

### Impact

The frontend must fetch a CSRF token before mutations. Login and password change clear
the session, so clients must fetch a fresh token after those operations.

---

## Decision: Temporary Passwords for Administrator-Provisioned Accounts

**Date**: 2026-09-15
**Status**: Adopted

### Decision

Administrators provision local accounts with a backend-generated temporary password.
The password is returned once in the creation response, stored only as a hash, and
the new user must change it before using protected ticket workflows.

### Rationale

- Prevents administrators from choosing or storing permanent user passwords
- Works without an email-delivery system in Phase 1
- Enforces replacement of credentials known to the provisioner

### Impact

The API exposes `must_change_password`, restricts normal authenticated routes while
it is true, and clears the session after a successful password change.

---

## Decision: Immutable Ticket Audit Records

**Date**: 2026-09-15
**Status**: Adopted

### Decision

Record ticket creation and status changes in `ticket_history`; comments are append-only.
Normal API workflows do not delete tickets or edit/delete comments.

### Rationale

- Preserves operational history for support work
- Prevents accidental loss of audit evidence
- Keeps status transitions explicit and reviewable

### Impact

Status updates validate an allow-list of transitions and write a history row in the
same database transaction as the ticket update.

---

## Decision: No External AI Services in Phase 1

**Date**: 2026-07-28
**Status**: Adopted

Phase 1 excludes OpenAI, Anthropic, Claude, and other LLM-based features. AI-assisted
triage and summarization remain future-phase options.

---

## Decision: Local Development Only

**Date**: 2026-07-28
**Status**: Adopted

Phase 1 targets local development. Production deployment, scaling, and operational
hardening are intentionally deferred.