# Architecture

## Overview

The ALE (Alcatel-Lucent Enterprise) Ticket Management Tool is a web-based application designed to streamline ticket management for Alcatel-Lucent Enterprise laboratory support.

## Technology Stack

- **Frontend**: React with Vite (JavaScript)
- **Backend**: Python Flask
- **Database**: PostgreSQL (planned)
- **Communication**: REST APIs with JSON

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      User Browser                            │
├─────────────────────────────────────────────────────────────┤
│                   React Frontend (Vite)                      │
│              (Port 5173 - Development)                       │
├─────────────────────────────────────────────────────────────┤
│                    JSON REST APIs                            │
├─────────────────────────────────────────────────────────────┤
│              Flask Backend (Python)                          │
│              (Port 5000 - Development)                       │
├─────────────────────────────────────────────────────────────┤
│             PostgreSQL Database                              │
│      (Not yet connected — Database Foundation milestone)     │
└─────────────────────────────────────────────────────────────┘
```

## Project Phases

**Phase 1 (Current)**: Full ticket management application

Phase 1 is delivered across several milestones:

- **Project Setup** ✅ — project structure, React frontend, Flask backend, health endpoint
- **Database Foundation** 🔜 — PostgreSQL connection, schema, seed data
- **Authentication** 🔜 — internal Alcatel-Lucent Enterprise team login, session management
- **Ticket Management** 🔜 — ticket CRUD, comments, attachments, search, filtering

**Phase 2 (Future)**: AI-assisted features
- LLM-powered ticket triage or summarisation
- AI API integrations (not planned until Phase 1 is complete)

## Component Responsibilities

- **Frontend**: User interface, client-side routing, form handling
- **Backend**: API endpoints, business logic, data validation
- **Database**: Data persistence and retrieval
