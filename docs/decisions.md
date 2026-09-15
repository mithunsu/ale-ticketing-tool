# Engineering Decisions

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