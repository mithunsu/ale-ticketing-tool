# API Documentation

## Overview

The ALE Ticket Management Tool communicates via REST APIs with JSON payloads.

## Phase 1 Endpoints

### Health Check

**GET /health**

Check if the backend service is running.

**Response** (200 OK):
```json
{
  "status": "ok",
  "message": "Backend is running"
}
```

## Planned Phase 1 Endpoints

The following endpoints are required Phase 1 features, intentionally not implemented during the Project Setup milestone:

- **POST /api/tickets** - Create a new ticket
- **GET /api/tickets** - List all tickets
- **GET /api/tickets/{id}** - Get ticket details
- **PUT /api/tickets/{id}** - Update a ticket
- **DELETE /api/tickets/{id}** - Delete a ticket
- **POST /api/tickets/{id}/comments** - Add comment to ticket
- **GET /api/users** - List users (requires Authentication milestone)

## Response Format

All responses return JSON with appropriate HTTP status codes:
- `200` - Success
- `201` - Created
- `400` - Bad Request
- `401` - Unauthorized
- `404` - Not Found
- `500` - Server Error

## CORS

CORS allows the configured frontend origin with credentials. Local browser development uses `http://localhost:5173` for the frontend and `http://localhost:5000` for the backend.

## Session and CSRF

Call `GET /api/auth/csrf` before login. The response contains a session-backed token:

```json
{
  "data": {
    "csrf_token": "<token>"
  }
}
```

Send the token in `X-CSRF-Token` for `POST`, `PUT`, `PATCH`, and `DELETE`, including login, logout, password change, and admin user creation. `GET`, `HEAD`, and `OPTIONS` are exempt. Missing or invalid tokens return JSON `403` responses with code `CSRF_TOKEN_INVALID`; CSRF failures still include `X-Request-ID`.

Login rotates the session by clearing the pre-login session before setting the authenticated user, so clients should fetch a fresh token after login. Password change also clears the session and requires a fresh token before the next login. CSRF state is not persisted in PostgreSQL.
