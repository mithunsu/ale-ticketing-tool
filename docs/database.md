# Database Design

## Current status

PostgreSQL 16 is the primary datastore and psycopg 3 is the backend driver. The
canonical schema is `database/schema.sql`; sample data and SQL checks are in
`database/seed.sql` and `database/tests/`. Categories are deferred and are not
implemented in the current schema.

## Connection

The backend reads `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, and `DB_PASSWORD`.
Each connection uses a five-second timeout. Compose exposes PostgreSQL on host port
`5433` and container port `5432`.

## Tables

### `users`

Fields: UUID `id`, nullable `sso_id`, `name`, lowercase unique `email`, nullable
`password_hash`, `auth_provider`, `role`, nullable `department`, `status`,
`must_change_password`, `created_at`, `updated_at`, and nullable `last_login_at`.
Current local roles are `requester`, `support_engineer`, `manager`, and `admin`;
statuses are `active` and `inactive`. Local accounts require a password hash and are
admin-created. SSO columns are nullable integration groundwork, not current SSO.

### `tickets`

Fields: UUID primary key `id`, sequential generated `ticket_number`, `title`,
`description`, JSONB `setup_snapshot`, `priority`, `status`, `requester_id`, nullable
`assigned_to`, nullable `due_date`, nullable `resolution`, `created_at`, `updated_at`,
and nullable `closed_at`. UUID `id` is the stable internal/API identifier; the
sequential `ticket_number` is the human-readable ticket reference.

Database priorities are lowercase (`low`, `medium`, `high`, `critical`). Statuses are
`New`, `Open`, `In Progress`, `Resolved`, and `Closed`. Resolved/Closed tickets need
non-blank resolution; `closed_at` is required exactly for Closed tickets.

### Setup snapshot

`setup_snapshot` is required JSONB. The current API validates these required string
fields: `server_name`, `server_ip`, `platform`, `dut`, and `aos_image_build`.
Optional validated fields are `pal_server`, `emp`, `console`, `console_port`, `rps`,
`rps_port`, `gateway`, `gateway_port`, `ixia`, `ixia_port`, `full_model`, and `notes`.
Do not store passwords, tokens, or other credentials in setup data.

### `ticket_comments`

Stores immutable comments with `ticket_id`, `author_id`, `comment_text`, `comment_type`,
and `created_at`. Valid types are `public`, `internal`, and `system`; only system
comments may omit an author. The current API creates public comments and maps
`author_id`/`comment_text` to `user_id`/`comment` in JSON.

Internal notes are deferred from the Phase 1 user-facing scope. The additional types
are retained as implementation groundwork and do not imply a current internal-comment
UI.

### `ticket_history`

Stores immutable status audit events. `TICKET_CREATED` records `NULL -> New`; later
`STATUS_CHANGED` rows record the actor, old status, new status, and timestamp.

### `attachments`

Stores metadata only: original/generated names, relative storage path, MIME type, size,
ticket/comment relationship, uploader, and creation time. File bytes are not stored in
PostgreSQL. Upload/download routes are not implemented yet.

## Integrity and security

The schema uses UUID generation, unique constraints, CHECK constraints for credentials,
roles, statuses, priorities, non-blank text, comment types, and lifecycle timestamps.
Foreign keys use `ON DELETE RESTRICT` to preserve ownership and audit history.
Parameterized psycopg queries reduce SQL injection risk; server-side validation and
CHECK constraints prevent clients from bypassing frontend rules. UUIDs avoid exposing
sequential database identifiers while `ticket_number` provides a usable reference.

## Local development

Start PostgreSQL with `docker compose up -d postgres`, apply the schema and seed data
as needed, then run the backend from its virtual environment. `GET /api/health`
verifies the connection with `SELECT 1`.