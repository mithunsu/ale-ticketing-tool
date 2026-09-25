# Deployment and Hosting

## Current state

The supported setup is local development: Docker Compose runs PostgreSQL 16, Flask
runs the API on port 5000, and Vite runs the frontend on port 5173. The repository does
not prove that an ALE internal or production deployment is complete.

## Intended ALE internal deployment

An internal deployment should provide managed PostgreSQL, a production WSGI process
for Flask, a built frontend served through an approved web server, HTTPS, restricted
network access, secret management, backups, monitoring, and an operational migration
process. Those hosting and hardening steps remain work to be completed.

## Future integration

ALE SSO is not implemented. It should be integrated only after the identity-provider,
account-provisioning, session, and deployment decisions are agreed. Local
admin-created accounts remain the Phase 1 MVP authentication method.

## Operational limitations

Attachment upload/download, notifications, search/filter controls, internal comments,
and AI/LLM capabilities are not deployment-ready features in the current milestone.
Do not place credentials in setup snapshots, committed documentation, or source files;
use local ignored environment files during development and a proper secret manager for
internal hosting.
