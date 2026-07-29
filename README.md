# ALE Ticket Management Tool

## Problem Statement

The ALE (Alcatel-Lucent Enterprise) laboratory needs a streamlined way to manage support tickets and tasks. This tool provides a centralized platform for creating, tracking, and resolving laboratory support issues.

## Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Frontend | React | Latest |
| Build Tool | Vite | Latest |
| Language | JavaScript | ES6+ |
| Backend | Flask | 3.0.0 |
| Python | Python | 3.8+ |
| Database | PostgreSQL | 13+ (Phase 1, upcoming) |
| API | REST + JSON | HTTP/1.1 |

## Project Structure

```
ale-ticketing-tool/
├── frontend/              # React + Vite application
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.js
├── backend/               # Python Flask application
│   ├── app/
│   │   ├── __init__.py   # Application factory
│   │   └── routes/
│   │       ├── __init__.py
│   │       └── health.py # Health check endpoint
│   ├── tests/
│   ├── run.py            # Entry point
│   ├── requirements.txt
│   └── .env.example
├── database/              # Database setup files
│   ├── schema.sql        # Table definitions (Database Foundation milestone)
│   └── seed.sql          # Sample data (Database Foundation milestone)
├── docs/                  # Project documentation
│   ├── architecture.md
│   ├── api.md
│   ├── database.md
│   ├── decisions.md
│   └── glossary.md
├── .gitignore
└── README.md
```

## Local Development Requirements

- **Node.js** 18+ and npm 9+
- **Python** 3.8+
- **pip** (Python package manager)
- **Git** for version control
- PostgreSQL 13+ (required for the Database Foundation milestone of Phase 1)

## Quick Start

### 1. Frontend Setup

```bash
# Install dependencies
cd frontend
npm install

# Start development server (runs on http://localhost:5173)
npm run dev
```

The frontend will display:
```
ALE Ticket Management Tool
Phase 1 development environment
```

### 2. Backend Setup

```bash
# Navigate to backend
cd backend

# Create Python virtual environment
python -m venv .venv

# Activate virtual environment (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Activate virtual environment (Windows CMD)
.venv\Scripts\activate.bat

# Activate virtual environment (macOS/Linux)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run Flask server (runs on http://localhost:5000)
python run.py
```

## Verify Installation

### Test GET /health Endpoint

**Option 1: Using Browser**
```
Navigate to: http://localhost:5000/health

Expected response:
{
  "status": "ok",
  "message": "Backend is running"
}
```

**Option 2: Using curl (PowerShell)**
```powershell
curl http://localhost:5000/health
```

**Option 3: Using curl (CMD)**
```cmd
curl http://localhost:5000/health
```

**Option 4: Using Python**
```python
import requests
response = requests.get('http://localhost:5000/health')
print(response.json())
```

Expected output:
```json
{
  "status": "ok",
  "message": "Backend is running"
}
```

## Current Status

### ✅ Completed (Project Setup Milestone)

- React frontend with Vite
- Flask backend with health endpoint
- Project structure and documentation
- Environment configuration files
- .gitignore setup

### 🔜 Required Phase 1 Features (Not yet implemented)

These are planned Phase 1 features, intentionally not implemented during the Project Setup milestone:

- PostgreSQL database connection (Database Foundation milestone)
- User authentication and ALE SSO
- Ticket CRUD operations
- Comments and attachments
- Ticket status and priority tracking
- Search and filtering
- Notifications
- CORS configuration

### ❌ Excluded from Phase 1

- AI/LLM features (deferred to Phase 2)
- OpenAI, Claude, Anthropic, or any AI API integrations

## Important Notes

### Phase 1 Scope

Phase 1 delivers the full ALE ticket management application across several milestones:

- **Project Setup** (current) — project foundation, React frontend, Flask backend, health endpoint
- **Database Foundation** — PostgreSQL connection, schema, seed data
- **Authentication** — internal ALE team login, session management
- **Ticket Management** — CRUD operations, comments, attachments, search, filtering

### Phase 1 Restrictions

The following are **excluded from Phase 1** and deferred to Phase 2:
- ❌ AI/LLM features
- ❌ OpenAI, Claude, Anthropic, or any AI API integrations

### Backend Status (Project Setup Milestone)

The Flask backend currently:
- ✅ Starts successfully on port 5000
- ✅ Responds to GET /health with HTTP 200
- ✅ Returns correct JSON format
- 🔜 PostgreSQL connection (Database Foundation milestone)
- 🔜 Authentication (Authentication milestone)
- 🔜 Ticket operations (Ticket Management milestone)

### Frontend Status (Project Setup Milestone)

The React frontend currently:
- ✅ Starts successfully on port 5173
- ✅ Displays "ALE Ticket Management Tool" heading
- ✅ Displays "Phase 1 development environment" text
- 🔜 Flask API calls (Database Foundation milestone)
- 🔜 Ticket views (Ticket Management milestone)
- 🔜 Authentication UI (Authentication milestone)

## Next Milestone: Database Foundation (Phase 1)

1. Connect PostgreSQL database
2. Create and apply schema.sql table definitions
3. Configure DATABASE_URL in .env
4. Verify database connection from Flask

## Documentation

Detailed documentation available in the `docs/` folder:

- [Architecture](docs/architecture.md) - System design and component overview
- [API Documentation](docs/api.md) - REST endpoint specifications
- [Database Design](docs/database.md) - Schema planning
- [Engineering Decisions](docs/decisions.md) - Key project decisions and rationale
- [Glossary](docs/glossary.md) - Project terminology

## Support

For issues or questions about this project, refer to:
1. [docs/glossary.md](docs/glossary.md) for terminology
2. [docs/architecture.md](docs/architecture.md) for system design
3. [docs/decisions.md](docs/decisions.md) for technical decisions

---

**Project Status**: Phase 1 — Project Setup milestone complete  
**Last Updated**: 2026-07-29  
**Maintainer**: ALE Lab Team
