# AI Workflow Copilot

AI Workflow Copilot is a production-oriented FastAPI service that uses LLMs to create, modify, validate, repair, and explain workflow definitions. It combines structured validation, workflow persistence, intelligent repair loops, caching, and rate limiting to provide reliable workflow automation assistance.

---

## Features

- Create workflows from natural-language instructions
- Modify existing workflows with contextual prompts
- Automatically repair invalid workflows
- Explain workflow logic in human-readable language
- Structural, semantic, and graph-based validation
- OpenRouter model fallback chain for resilience
- PostgreSQL persistence with async database access
- Redis-based rate limiting and caching
- Docker and Docker Compose support
- Alembic database migrations
- Automated test suite with Pytest
- Health and readiness endpoints for deployments

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| API Framework | FastAPI |
| Language | Python 3.11+ |
| Database | PostgreSQL |
| Cache / Rate Limiting | Upstash Redis |
| ORM / DB Layer | SQLAlchemy (Async) |
| Migrations | Alembic |
| LLM Gateway | OpenRouter |
| Testing | Pytest |
| Deployment | Docker & Nginx |

---

## Project Structure

```text
.
├── alembic/
├── app/
│   ├── core/
│   ├── db/
│   ├── llm/
│   ├── models/
│   ├── routes/
│   ├── service/
│   ├── __init__.py
│   └── main.py
├── test/
├── .env
├── alembic.ini
├── docker-compose.yml
├── Dockerfile
├── nginx.conf
├── README.md
└── requirements.txt
```

---

## Prerequisites

- Python 3.11 or newer
- Docker (optional but recommended)
- PostgreSQL 16+
- Upstash Redis account
- OpenRouter API Key

---

## Environment Configuration

Create a `.env` file and configure the following values:

```env
OPENROUTER_API_KEY=your_api_key
DATABASE_URL=postgresql+asyncpg://copilot:copilot@localhost:5432/copilot
REDIS_URL=rediss://your-upstash-url
```

---

## Local Development Setup

### 1. Start PostgreSQL

```bash
docker run -d --name copilot-db \
  -e POSTGRES_USER=copilot \
  -e POSTGRES_PASSWORD=copilot \
  -e POSTGRES_DB=copilot \
  -p 5432:5432 \
  postgres:16-alpine
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
```

Update the values inside `.env`.

### 4. Run Database Migrations

```bash
alembic upgrade head
```

### 5. Start the Application

```bash
uvicorn app.main:app --reload
```

Application URL:

```text
http://localhost:8000
```

---

## API Endpoints

### Copilot Operations

| Method | Endpoint | Description |
|----------|----------|-------------|
| POST | `/copilot/create` | Create a workflow from instructions |
| POST | `/copilot/modify` | Modify an existing workflow |
| POST | `/copilot/fix` | Repair an invalid workflow |
| POST | `/copilot/explain` | Generate workflow explanation |

### Workflow Management

| Method | Endpoint |
|----------|----------|
| GET | `/workflows` |
| GET | `/workflows/{id}` |
| POST | `/workflows` |
| DELETE | `/workflows/{id}` |

### Health Checks

| Method | Endpoint |
|----------|----------|
| GET | `/health` |
| GET | `/ready` |

---

## Running Tests

Execute all tests:

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=app
```

---

## Docker Deployment

Build and run all services:

```bash
docker compose up --build
```

Run in detached mode:

```bash
docker compose up -d
```

Stop services:

```bash
docker compose down
```

---

## Architecture Overview

```text
Client
  │
  ▼
FastAPI Routes
  │
  ▼
Service Layer
  │
  ▼
Copilot Engine
  │
  ├── OpenRouter LLM Client
  ├── Validation Engine
  ├── Repair Loop
  └── Explanation Generator
  │
  ▼
Repository Layer
  │
  ▼
PostgreSQL

Redis
 ├── Rate Limiting
 └── Explanation Cache
```

---

## Design Decisions

### Model Fallback Chain

Multiple OpenRouter models are configured in a fallback sequence. If one model becomes unavailable or rate-limited, the request automatically falls back to another model.

### Bounded Repair Loop

Workflow repair attempts are limited to two iterations to prevent excessive LLM usage and control operational costs.

### Fail-Open Rate Limiting

If Redis becomes unavailable, requests continue processing instead of bringing down the API.

### Global Exception Handling

Unexpected failures are captured and returned as controlled API responses, preventing worker crashes.

---

## Known Trade-offs

- API key header is used only for rate limiting.
- No user identity management.
- No workflow version history.
- Workflow modifications overwrite previous versions.
- Explanation cache is temporary and Redis-dependent.

---

## Future Enhancements

- JWT authentication and authorization
- Multi-user workflow ownership
- Workflow versioning and rollback
- Audit logging
- Diff-based workflow modifications
- Observability with Prometheus and Grafana
- OpenTelemetry tracing
- Background task processing
- Role-based access control (RBAC)

---

## Production Recommendations

- Enable HTTPS using Nginx and TLS certificates
- Configure PostgreSQL backups
- Add centralized logging
- Enable monitoring and alerting
- Use secrets management instead of plaintext environment variables
- Configure CI/CD pipelines
- Add database connection pooling metrics
