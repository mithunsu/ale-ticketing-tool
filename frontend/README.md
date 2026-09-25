# Frontend (React + Vite)

The frontend provides the authenticated browser experience for login, password
change, dashboards, ticket creation/list/detail, assignment, status changes, public
comments, activity history, and admin user management.

## Local development

```powershell
npm install
npm run dev
```

Vite serves on `http://localhost:5173` and proxies `/api` to
`http://localhost:5000`. Start the Flask backend and PostgreSQL first; no frontend
secrets are required for the local proxy.

## Production build

```powershell
npm run build
```

The current Vite production build passes. `npm run lint` is also available through
Oxlint.

Page and API-facing components live in `src/components`; shared API calls live in
`src/api.js`. Frontend role-based visibility improves usability, but authorization is
always enforced by Flask.