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
