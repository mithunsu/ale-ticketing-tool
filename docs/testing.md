# Testing and Validation

## Current result

**Phase 1 MVP core workflow browser acceptance: PASS.** The latest recorded automated
backend result is **388 tests passing** and the frontend Vite production build passes.
Search/filter acceptance is intentionally not included because those controls are
deferred to Phase 1.1.

## Backend automated tests

From `backend`, activate the virtual environment and run:

```powershell
python -m pytest -q
```

The suite covers routes, validation, authentication, CSRF, error handling, database
state, comments, status transitions, admin operations, and requester isolation.

## Frontend build check

From `frontend`:

```powershell
npm install
npm run build
```

This verifies the production Vite bundle. `npm run lint` runs the configured Oxlint
check.

## Browser acceptance

The validated browser workflow covers:

- Requester login, ticket creation, own list/detail, hidden restricted controls,
  forbidden API actions, own-ticket reopen, and isolation from another requester's ticket
- Support engineer login, self-assignment, assignment persistence, New to In Progress,
  public comments, and In Progress to Resolved
- Manager and admin login, permitted assignment, assignment persistence after refresh,
  and admin user-management access
- Resolved to Closed, requester Closed to In Progress reopen, public comment visibility,
  activity/history, refresh and login persistence, and PostgreSQL consistency

Five disposable local identities are used for deterministic browser checks: Requester
A, Requester B, Support Engineer, Manager, and Admin. Their credentials belong only in
`tests/e2e/.env.e2e.local`, which is gitignored. Populate it from
`tests/e2e/.env.e2e.example` without committing passwords.

## Security and database checks

Acceptance includes backend/API checks for CSRF, inactive users, forced password
change, role permissions, requester ownership, and admin protection. Read-only
PostgreSQL verification confirms assignment, status, comments, history, and timestamps
persist correctly. The backend remains authoritative even when the frontend hides a
control.

## Troubleshooting live validation

`FLASK_DEBUG=false` means a long-running Flask process does not reload source changes.
After backend edits, restart Flask before trusting browser results. This is a local
validation procedure, not an application defect.

## Deferred testing

Phase 1.1 will add browser coverage for ticket-number/title search, status filtering,
priority filtering, and requester RBAC through those controls.
