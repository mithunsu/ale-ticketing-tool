# Backend (Flask)

## Local startup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

## Run tests

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pytest -q
```

## Configuration

Create `backend/.env` or set these process environment variables before starting:

```text
FLASK_SECRET_KEY=<long-random-value>
DB_HOST=localhost
DB_PORT=5433
DB_NAME=<database-name>
DB_USER=<database-user>
DB_PASSWORD=<database-password>
```

`CORS_ALLOWED_ORIGINS` may contain a comma-separated list and defaults to
`http://localhost:5173`. `SESSION_COOKIE_SECURE` defaults to `false` for local HTTP
development. The backend refuses to start without `FLASK_SECRET_KEY` and refuses a
database connection with incomplete `DB_*` settings.

## Browser authentication flow

The frontend must first call `GET http://localhost:5000/api/auth/csrf` and retain
`data.csrf_token`. Send it in the `X-CSRF-Token` header with login and every later
`POST`, `PUT`, `PATCH`, or `DELETE` request, together with credentials. `GET`, `HEAD`,
and `OPTIONS` requests do not require CSRF validation.

Successful login clears the pre-login session while establishing the authenticated
session, so fetch a fresh CSRF token after login for subsequent mutations. Successful
password change clears the session and forces login again; fetch a fresh token before
that login. CSRF tokens are held in the Flask session and are never stored in
PostgreSQL.

## Implemented API areas

- Health check: `/api/health`
- Authentication and CSRF: `/api/auth/*`
- Admin user provisioning: `POST /api/admin/users`
- Ticket creation, listing, detail, comments, assignment, and status transitions:
  `/api/tickets/*`

All mutation requests require `X-CSRF-Token`. Protected routes use the authenticated
user's role and ticket ownership to authorize access. Password hashes, temporary
password hashes, and database connection details are never returned in API errors or
normal responses.