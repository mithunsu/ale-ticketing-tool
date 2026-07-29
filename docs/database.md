# Database Design

## Current Status

Project Setup milestone: Database setup files created. No tables or connections configured yet.

Database connection and schema will be implemented in the Database Foundation milestone of Phase 1.

## Files

- **schema.sql** - Will contain table definitions
- **seed.sql** - Will contain sample data

## Planned Schema (Phase 1 — Database Foundation milestone)

### Tables

**users**
- id (PK)
- username
- email
- created_at
- updated_at

**tickets**
- id (PK)
- title
- description
- status
- priority
- assignee_id (FK -> users.id)
- creator_id (FK -> users.id)
- created_at
- updated_at

**comments**
- id (PK)
- content
- ticket_id (FK -> tickets.id)
- author_id (FK -> users.id)
- created_at
- updated_at

**attachments**
- id (PK)
- filename
- file_path
- ticket_id (FK -> tickets.id)
- uploaded_by_id (FK -> users.id)
- created_at

## Connection Details

Database connection will be configured in the Database Foundation milestone of Phase 1.

## Local Development

PostgreSQL is required for local development starting from the Database Foundation milestone of Phase 1.
