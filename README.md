# ALE Ticket Management Tool

The ALE (Alcatel-Lucent Enterprise) Ticket Management Tool replaces laboratory
support email chains with a shared ticket lifecycle: request, assignment, status
updates, public conversation, and activity history.

## Current status

**Phase 1 MVP core workflow browser acceptance: PASS.** The validated workflow covers
requesters, support engineers, managers, and administrators, including persistence,
RBAC, public comments, history, and PostgreSQL consistency. Search and filtering are
deferred to Phase 1.1; SSO and AI-assisted capabilities are future work.

## Stack and architecture

React + Vite frontend -> Python Flask REST API -> PostgreSQL 16. Docker Compose
provides PostgreSQL locally; Flask and Vite run as local development processes.

Roles are `requester`, `support_engineer`, `manager`, and `admin`. Accounts are
admin-created local email/password accounts. New accounts receive a temporary password
and must change it on first login. Authentication uses an HTTP-only Flask session and
CSRF tokens. The backend enforces authorization; frontend visibility is only UX.

## Quick local setup

Requirements: Docker Desktop, Node.js/npm, and Python with `venv` and `pip`.

1. Set `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` for Compose, then run
   `docker compose up -d postgres` from the repository root. PostgreSQL is available
   at `localhost:5433`.
2. Create `backend/.env` with a secret and the matching `DB_HOST`, `DB_PORT`,
   `DB_NAME`, `DB_USER`, and `DB_PASSWORD` values. `FLASK_SECRET_KEY` is required.
3. Start Flask:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

4. In another terminal, start Vite:

```powershell
cd frontend
npm install
npm run dev
```

The backend defaults to `http://localhost:5000`; the frontend defaults to
`http://localhost:5173`. The Vite development proxy forwards `/api` to Flask.

## Useful checks

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q

cd ..\frontend
npm run build
```

The latest recorded validation is 388 backend tests passing and a passing Vite
production build. Use `GET http://localhost:5000/api/health` to check Flask and
PostgreSQL connectivity.

## MVP capabilities

- Create, list, inspect, assign, and persist tickets
- Status workflow: `New`, `Open`, `In Progress`, `Resolved`, `Closed`
- Requester reopen of an owned closed ticket
- Public comments and immutable status activity/history
- Admin user management and forced first-password change
- Backend-enforced ownership and role permissions

## Deferred scope

Phase 1.1 covers ticket-number/title search, status and priority filters, and browser
RBAC validation for those controls. Phase 2 may include internal notes, AI
classification, troubleshooting suggestions, summaries, similar-ticket recommendations,
and AI-assisted response drafting. ALE SSO and internal deployment hardening remain
future integration work.

## Documentation

- [Architecture](docs/architecture.md)
- [API](docs/api.md)
- [Database](docs/database.md)
- [Testing](docs/testing.md)
- [Deployment](docs/deployment.md)
- [Decisions](docs/decisions.md)
- [Glossary](docs/glossary.md)
- [Backend setup](backend/README.md)
- [Frontend setup](frontend/README.md)