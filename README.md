# ALE Ticket Management Tool

The ALE (Alcatel-Lucent Enterprise) Ticket Management Tool is a local web
application for creating, tracking, and resolving laboratory support tickets.

## Technology Stack

| Component | Technology |
|-----------|------------|
| Frontend | React with Vite and JavaScript |
| Backend | Python Flask 3 |
| Database | PostgreSQL 16 |
| Database driver | psycopg 3 |
| API | REST + JSON under `/api` |

## Project Structure

```
ale-ticketing-tool/
├── frontend/              # React + Vite application
├── backend/               # Flask application, routes, and tests
├── database/              # PostgreSQL schema, seed data, and SQL tests
├── docs/                  # Architecture, API, database, and project decisions
├── compose.yml            # Local PostgreSQL service
└── README.md
```

## Requirements

- Node.js 18+ and npm
- Python 3.14 recommended, with `venv` and `pip`
- Docker Desktop for the local PostgreSQL service

## Quick Start

### 1. Start PostgreSQL

From the repository root, provide the `POSTGRES_DB`, `POSTGRES_USER`, and
`POSTGRES_PASSWORD` values expected by `compose.yml`, then run:

```powershell
docker compose up -d postgres
```

PostgreSQL is available on `localhost:5433`.

### 2. Configure and start the backend

Create `backend/.env` with the database settings and a long random Flask secret:

```text
FLASK_SECRET_KEY=<long-random-value>
DB_HOST=localhost
DB_PORT=5433
DB_NAME=<database-name>
DB_USER=<database-user>
DB_PASSWORD=<database-password>
```

Then run:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

The backend runs on `http://localhost:5000`. `CORS_ALLOWED_ORIGINS` defaults to
`http://localhost:5173`; `SESSION_COOKIE_SECURE` defaults to `false` for local HTTP.

### 3. Start the frontend

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

The frontend runs on `http://localhost:5173`.

## Verify the Backend

The health endpoint checks both Flask and PostgreSQL:

```powershell
curl http://localhost:5000/api/health
```

Expected healthy response:

```json
{
  "status": "healthy",
  "backend": "active",
  "database": "connected"
}
```

## Authentication Flow

The browser first calls `GET /api/auth/csrf`, then sends the returned token in
`X-CSRF-Token` for state-changing requests. Login establishes a session. Accounts
created by an administrator receive a temporary password and must change it before
using normal protected workflows. A successful password change clears the session and
requires a fresh login.

## Current Status

Implemented Phase 1 capabilities include:

- PostgreSQL schema, seed data, connection handling, and health checks
- Session-based login, logout, current-user lookup, and CSRF protection
- Admin user provisioning with one-time temporary passwords
- Ticket creation, listing, detail views, comments, assignment, and status transitions
- Requester ownership checks and role-based authorization
- Immutable ticket status history and database integrity constraints
- React login and password-change screens
- Authenticated top-level navigation shell (Active Tickets, Create Ticket, Closed
  Tickets, Logout)

Not yet implemented as HTTP workflows:

- SSO integration
- Attachment upload/download
- Ticket deletion or general ticket editing
- Comment editing/deletion
- Search, filtering, and notifications
- Frontend ticket list, creation, and detail views

AI and LLM integrations are excluded from Phase 1.

## Tests

Run the backend test suite from the repository root:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q
```

## Documentation

- [Architecture](docs/architecture.md) - System design and component responsibilities
- [API Documentation](docs/api.md) - Endpoint and security contracts
- [Database Design](docs/database.md) - PostgreSQL tables and constraints
- [Engineering Decisions](docs/decisions.md) - Adopted technical decisions
- [Glossary](docs/glossary.md) - Project terminology
- [Backend README](backend/README.md) - Backend setup and configuration details

---

**Project Status**: Phase 1 implementation in progress
**Last Updated**: 2026-09-17
**Maintainer**: ALE Lab Team