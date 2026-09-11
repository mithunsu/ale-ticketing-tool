-- Enable UUID generation for primary keys.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- UUID keeps user identifiers stable and avoids exposing sequential account counts.
-- All Phase 1 accounts use local email-and-password authentication.
-- password_hash stores only a one-way hash, never the original password.
-- password_hash is nullable only because future SSO accounts will not use local passwords.
-- Local password hashes must contain a non-whitespace value.
-- Emails are stored in lowercase to keep account creation and login comparisons consistent.
-- Flask will later normalize email addresses before sending them to PostgreSQL.
-- must_change_password forces users to replace the temporary password created by an administrator.
-- auth_provider separates the authentication method from the user's application role.
-- sso_id remains nullable for future ALE SSO integration.
-- status is used so accounts can be deactivated instead of permanently deleted.
-- role and status use CHECK constraints to keep values limited to supported options.
CREATE TABLE users (
	id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
	sso_id VARCHAR(255),
	name VARCHAR(255) NOT NULL,
	email VARCHAR(255) NOT NULL,
	password_hash TEXT,
	auth_provider VARCHAR(20) NOT NULL DEFAULT 'local',
	role VARCHAR(50) NOT NULL DEFAULT 'requester',
	department VARCHAR(255),
	status VARCHAR(50) NOT NULL DEFAULT 'active',
	must_change_password BOOLEAN NOT NULL DEFAULT TRUE,
	created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
	last_login_at TIMESTAMPTZ,
	CONSTRAINT users_sso_id_unique UNIQUE (sso_id),
	CONSTRAINT users_email_unique UNIQUE (email),
	CONSTRAINT users_email_lowercase_check CHECK (email = lower(email)),
	CONSTRAINT users_auth_provider_check CHECK (auth_provider IN ('local', 'sso')),
	CONSTRAINT users_auth_credentials_check CHECK (
		(
			auth_provider = 'local'
			AND password_hash IS NOT NULL
			AND btrim(password_hash) <> ''
		)
		OR
		(
			auth_provider = 'sso'
			AND sso_id IS NOT NULL
			AND password_hash IS NULL
			AND must_change_password = FALSE
		)
	),
	CONSTRAINT users_role_check CHECK (role IN ('requester', 'support_engineer', 'manager', 'admin')),
	CONSTRAINT users_status_check CHECK (status IN ('active', 'inactive'))
);

-- id is the internal UUID identifier used by the database and API.
-- ticket_number is a PostgreSQL-generated, human-facing sequential integer.
-- The UI may later display ticket_number 42 as ALE-000042; formatting is handled in the application, not here.
-- requester_id identifies the user who submitted the ticket.
-- assigned_to is nullable because tickets can begin unassigned and an engineer is allocated later.
-- resolution is required for Resolved and Closed tickets; it is nullable while the ticket is active.
-- closed_at is populated only when status is Closed; it must be null for every other status.
-- due_date is nullable because not every ticket has a deadline at creation time.
-- Category support is deliberately deferred to a future iteration; no category_id or category field is added here.
-- Flask will later enforce allowed status transitions and role-based permissions at the application layer.
-- The application will not expose a normal ticket-deletion endpoint; records are retained for audit purposes.
CREATE TABLE tickets (
	-- Internal UUID identifier — used by the database and exposed through the API.
	id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

	-- Human-facing sequential number generated automatically by PostgreSQL.
	-- The UNIQUE constraint doubles as an index; no separate index is needed.
	ticket_number BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,

	title VARCHAR(200) NOT NULL,
	description TEXT NOT NULL,
	setup_snapshot JSONB NOT NULL,

	-- Allowed values: low, medium, high, critical.  Defaults to medium.
	priority VARCHAR(20) NOT NULL DEFAULT 'medium',

	-- Allowed values: New, Open, In Progress, Resolved, Closed.  Defaults to New.
	status VARCHAR(30) NOT NULL DEFAULT 'New',

	-- The user who submitted the ticket.  RESTRICT prevents deleting a user who owns tickets.
	requester_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

	-- The engineer currently handling the ticket.  NULL means unassigned.
	-- RESTRICT prevents deleting a user who is assigned to open tickets.
	assigned_to UUID REFERENCES users(id) ON DELETE RESTRICT,

	-- Optional deadline; not all tickets require one at creation time.
	due_date TIMESTAMPTZ,

	-- Free-text resolution summary.  Required once status reaches Resolved or Closed.
	resolution TEXT,

	created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

	-- Populated only when status transitions to Closed; must be NULL for all other statuses.
	closed_at TIMESTAMPTZ,

	CONSTRAINT tickets_priority_check
		CHECK (priority IN ('low', 'medium', 'high', 'critical')),

	CONSTRAINT tickets_status_check
		CHECK (status IN ('New', 'Open', 'In Progress', 'Resolved', 'Closed')),

	-- Reject titles that are empty strings or contain only whitespace.
	CONSTRAINT tickets_title_not_blank_check
		CHECK (btrim(title) <> ''),

	-- Reject descriptions that are empty strings or contain only whitespace.
	CONSTRAINT tickets_description_not_blank_check
		CHECK (btrim(description) <> ''),

	-- If resolution is present it must contain meaningful text, not just whitespace.
	CONSTRAINT tickets_resolution_not_blank_check
		CHECK (resolution IS NULL OR btrim(resolution) <> ''),

	-- Resolved and Closed tickets must carry a non-null, non-whitespace resolution.
	CONSTRAINT tickets_resolution_required_check
		CHECK (
			status NOT IN ('Resolved', 'Closed')
			OR (
				resolution IS NOT NULL
				AND btrim(resolution) <> ''
			)
		),

	-- Closed tickets must have closed_at set; every other status must have closed_at NULL.
	CONSTRAINT tickets_closed_at_check
		CHECK (
			(status = 'Closed' AND closed_at IS NOT NULL)
			OR
			(status <> 'Closed' AND closed_at IS NULL)
		)
);

-- Indexes for common filtering and join operations.
-- id is covered by the primary-key index; ticket_number is covered by its UNIQUE constraint.
CREATE INDEX tickets_status_idx       ON tickets (status);
CREATE INDEX tickets_priority_idx     ON tickets (priority);
CREATE INDEX tickets_requester_id_idx ON tickets (requester_id);
CREATE INDEX tickets_assigned_to_idx  ON tickets (assigned_to);
CREATE INDEX tickets_created_at_idx   ON tickets (created_at);

-- Each row represents one independent comment attached to a ticket.
-- ticket_id identifies the parent ticket; every comment belongs to exactly one ticket.
-- author_id identifies the human who wrote the comment when applicable.
-- System-generated comments (comment_type = 'system') may have a null author_id.
-- Public and internal comments require a human author.
-- comment_type controls the intended visibility category:
--   public   — visible to all users permitted to access the ticket
--   internal — visible only to support_engineer, manager, and admin roles
--   system   — generated by the backend to record workflow events
-- Flask will enforce role-based visibility and creation permissions at the application layer.
-- Comments are immutable through the normal application workflow.
-- No normal comment update or delete endpoint will be exposed.
-- ticket_comments stores human-readable conversation and system messages.
-- ticket_history (future) will store structured, machine-readable audit events.
-- updated_at is intentionally omitted because comments cannot be edited.
CREATE TABLE ticket_comments (
	-- Internal UUID identifier.
	id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

	-- Parent ticket reference.  RESTRICT prevents deleting a ticket that has comments.
	ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE RESTRICT,

	-- Human author of the comment.  Nullable only for system-generated comments.
	-- RESTRICT prevents deleting a user who has authored comments.
	author_id UUID REFERENCES users(id) ON DELETE RESTRICT,

	-- The comment body.  Must contain at least one visible character.
	comment_text TEXT NOT NULL,

	-- Visibility category.  Defaults to public.
	comment_type VARCHAR(20) NOT NULL DEFAULT 'public',

	-- Immutable creation timestamp.  No updated_at because comments cannot be edited.
	created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

	-- Only public, internal, and system are valid comment types.
	CONSTRAINT ticket_comments_type_check
		CHECK (comment_type IN ('public', 'internal', 'system')),

	-- Reject comment_text that is empty or contains only whitespace.
	CONSTRAINT ticket_comments_text_not_blank_check
		CHECK (btrim(comment_text) <> ''),

	-- System comments may omit author_id.  Public and internal comments require one.
	CONSTRAINT ticket_comments_author_check
		CHECK (
			comment_type = 'system'
			OR author_id IS NOT NULL
		),

	-- id is already globally unique via the primary key.
	-- This two-column constraint exists specifically so attachments can enforce that a referenced
	-- comment belongs to the same ticket as the attachment, supporting relational integrity
	-- rather than relying on application-only validation.
	CONSTRAINT ticket_comments_ticket_id_id_unique UNIQUE (ticket_id, id)
);

-- Composite index for fetching and ordering comments belonging to a single ticket.
-- Leading column ticket_id satisfies ticket-level filtering without a separate ticket_id-only index.
-- created_at supports chronological ordering.
-- id is a stable tie-breaker when two comments share the same timestamp.
CREATE INDEX ticket_comments_ticket_created_idx ON ticket_comments (ticket_id, created_at, id);

-- Index on author_id for author-based audit queries.
-- PostgreSQL does not automatically index foreign-key columns.
CREATE INDEX ticket_comments_author_id_idx ON ticket_comments (author_id);

-- Each row records one ticket status transition.
-- ticket_id identifies the ticket whose status changed.
-- changed_by identifies the user who performed the change.
-- changed_by is required because Phase 1 does not store anonymous automated status changes.
-- old_status is the status before the change.
-- new_status is the status after the change.
-- old_status and new_status must be different.
-- Flask will enforce allowed transitions and role permissions at the application layer.
-- History records are immutable through the normal application workflow.
-- ticket_comments stores human-readable conversation and system messages.
-- ticket_history stores structured status-transition audit data.
CREATE TABLE ticket_history (
	-- Internal UUID identifier.
	id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

	-- Parent ticket reference. RESTRICT prevents deleting a ticket that has history.
	ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE RESTRICT,

	-- User who performed the status change. Required for every Phase 1 history row.
	-- RESTRICT prevents deleting a user whose actions are part of the audit trail.
	changed_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

	-- TICKET_CREATED records the initial New state; STATUS_CHANGED records later transitions.
	action VARCHAR(50) NOT NULL DEFAULT 'STATUS_CHANGED',
	old_status VARCHAR(30),
	new_status VARCHAR(30) NOT NULL,

	-- Immutable creation timestamp. No updated_at because history rows are never edited.
	created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

	CONSTRAINT ticket_history_old_status_check
		CHECK (
			old_status IS NULL OR old_status IN (
				'New',
				'Open',
				'In Progress',
				'Resolved',
				'Closed'
			)
		),

	CONSTRAINT ticket_history_new_status_check
		CHECK (
			new_status IN (
				'New',
				'Open',
				'In Progress',
				'Resolved',
				'Closed'
			)
		),

	CONSTRAINT ticket_history_status_changed_check
		CHECK (
			(action = 'TICKET_CREATED' AND old_status IS NULL AND new_status = 'New')
			OR
			(action = 'STATUS_CHANGED' AND old_status IS NOT NULL AND old_status <> new_status)
		),

	CONSTRAINT ticket_history_action_check
		CHECK (action IN ('TICKET_CREATED', 'STATUS_CHANGED'))
);

-- Composite index for retrieving one ticket's status history in chronological order.
-- Leading ticket_id supports ticket-level filtering without a separate ticket_id-only index.
-- created_at supports chronological ordering and id is the deterministic tie-breaker.
CREATE INDEX ticket_history_ticket_created_idx ON ticket_history (ticket_id, created_at, id);

-- Index on changed_by for audit queries by actor.
-- PostgreSQL does not automatically index foreign-key columns.
CREATE INDEX ticket_history_changed_by_idx ON ticket_history (changed_by);

-- PostgreSQL stores file metadata only, not file bytes.
-- Actual files are stored in controlled server storage by Flask.
-- ticket_id is always required; every attachment belongs to a ticket.
-- comment_id NULL means a ticket-level attachment with no parent comment.
-- comment_id populated means a comment-level attachment.
-- The composite foreign key attachments_ticket_comment_fk guarantees the comment belongs to the same ticket.
-- uploaded_by records the user who uploaded the file.
-- original_file_name is for display only and must never be used as a server-side file-system path.
-- stored_file_name and storage_path are generated by the backend before insertion.
-- storage_path is a relative path and must be unique across all attachment rows.
-- file_size_bytes is capped at 25 MiB (26,214,400 bytes) in the database.
-- Flask must validate file size before writing the file and before inserting the metadata row.
-- Flask must enforce ticket access and comment visibility when serving download requests.
-- Internal-comment attachments must not be downloadable by requesters.
-- No updated_at column exists because attachment metadata is immutable.
-- ON DELETE RESTRICT preserves attachment ownership records and prevents orphaned metadata.
-- SECURITY: Never use original_file_name directly as a file-system path.
-- Backend-generated stored paths prevent filename collisions and path-traversal attacks.
-- Backend authorization prevents users from downloading internal attachments by guessing a UUID.
CREATE TABLE attachments (
	-- Internal UUID identifier.
	id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

	-- Parent ticket reference.  Required for every attachment row.
	-- RESTRICT prevents deleting a ticket that still has attachments.
	ticket_id UUID NOT NULL REFERENCES tickets(id) ON DELETE RESTRICT,

	-- Parent comment reference.  NULL for ticket-level attachments.
	-- Validated through the composite foreign key below, not a separate single-column FK.
	comment_id UUID,

	-- User who uploaded the file.  RESTRICT prevents deleting a user who has uploaded files.
	uploaded_by UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

	-- Display name supplied by the uploader.  Must not be blank.
	-- Must never be used directly as a file-system path.
	original_file_name VARCHAR(255) NOT NULL,

	-- Server-generated file name used for storage.  Must not be blank.
	stored_file_name VARCHAR(255) NOT NULL,

	-- Server-generated relative path.  Must not be blank and must be unique.
	storage_path TEXT NOT NULL,

	-- MIME type reported at upload time.  Flask validates the allowlist.
	mime_type VARCHAR(255) NOT NULL,

	-- File size in bytes.  Must be positive and no larger than 25 MiB.
	file_size_bytes BIGINT NOT NULL,

	-- Immutable creation timestamp.  No updated_at because attachment metadata cannot be edited.
	created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

	-- When comment_id is NOT NULL, verify the comment exists and belongs to the same ticket.
	-- When comment_id is NULL (ticket-level attachment), MATCH SIMPLE skips the FK check for
	-- the null column; ticket_id is still validated by its direct FK to tickets(id).
	CONSTRAINT attachments_ticket_comment_fk
		FOREIGN KEY (ticket_id, comment_id)
		REFERENCES ticket_comments (ticket_id, id)
		ON DELETE RESTRICT,

	CONSTRAINT attachments_original_file_name_not_blank_check
		CHECK (btrim(original_file_name) <> ''),

	CONSTRAINT attachments_stored_file_name_not_blank_check
		CHECK (btrim(stored_file_name) <> ''),

	CONSTRAINT attachments_storage_path_not_blank_check
		CHECK (btrim(storage_path) <> ''),

	CONSTRAINT attachments_mime_type_not_blank_check
		CHECK (btrim(mime_type) <> ''),

	-- File size must be at least 1 byte and no more than 25 MiB.
	CONSTRAINT attachments_file_size_check
		CHECK (file_size_bytes > 0 AND file_size_bytes <= 26214400),

	-- Two rows cannot reference the same stored location.
	CONSTRAINT attachments_storage_path_unique UNIQUE (storage_path)
);

-- Composite index for retrieving all attachments for a ticket chronologically.
-- Leading ticket_id supports ticket-level filtering.
-- id is the deterministic tie-breaker.
CREATE INDEX attachments_ticket_created_idx ON attachments (ticket_id, created_at, id);

-- Partial composite index for retrieving attachments belonging to a specific comment.
-- WHERE comment_id IS NOT NULL excludes ticket-level rows that have no comment, keeping the index small.
CREATE INDEX attachments_comment_created_idx ON attachments (comment_id, created_at, id)
    WHERE comment_id IS NOT NULL;

-- Index on uploaded_by for audit queries by uploader.
-- PostgreSQL does not automatically index foreign-key columns.
CREATE INDEX attachments_uploaded_by_idx ON attachments (uploaded_by);
