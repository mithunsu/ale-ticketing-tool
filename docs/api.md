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

CORS is not yet enabled. Will be configured in Phase 1 when the frontend begins calling the backend.
