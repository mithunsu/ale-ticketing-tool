# Engineering Decisions

## Decision: Python Flask for Backend

**Date**: 2026-07-28  
**Status**: Adopted

### Decision

Chose Python Flask over Node.js Express because Python better matches the developer's current skills, workplace environment, and backend/automation career goals.

### Rationale

- Python is the primary language used in the developer's workplace
- Python has strong ecosystem for backend development and automation
- Flask is lightweight and suitable for learning-focused projects
- Easier for workplace integration and future automation tasks
- Developer's career goals align better with Python backend development

### Alternatives Considered

- **Node.js Express**: More JavaScript-focused, less aligned with developer career goals
- **Django**: Heavier framework than needed for Phase 1
- **FastAPI**: Could be reconsidered in future phases

### Impact

- Faster development by leveraging existing Python knowledge
- Better long-term career skill alignment
- Easier maintenance by developer and team

---

## Decision: React with Vite for Frontend

**Date**: 2026-07-28  
**Status**: Adopted

### Decision

Chose React with Vite over alternatives for frontend development.

### Rationale

- Vite provides fast development server and build tooling
- React is industry standard for building UI applications
- Minimal dependencies for Phase 1 learning focus
- Easy to extend as project grows

---

## Decision: PostgreSQL for Database

**Date**: 2026-07-28  
**Status**: Planned for Phase 1 (Database Foundation milestone)

### Decision

PostgreSQL will be used as the primary relational database.

### Rationale

- Robust, open-source relational database
- Excellent support for complex queries
- Strong Python ecosystem integration
- Suitable for ticket management data model

---

## Decision: No External AI Services in Phase 1

**Date**: 2026-07-28  
**Status**: Adopted

### Decision

Phase 1 explicitly excludes OpenAI, Anthropic, Claude, or any LLM-based features.

### Rationale

- Phase 1 is foundation and learning-focused
- AI features can be added in future phases
- Keeps scope manageable and costs minimal
- Focuses on core ticket management first

---

## Decision: Local Development Only

**Date**: 2026-07-28  
**Status**: Adopted

### Decision

Phase 1 targets local development without production deployment considerations.

### Rationale

- Simplifies initial setup
- Reduces complexity for learning phase
- Focuses on core functionality
- Production considerations for Phase 3+

