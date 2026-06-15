# AI Workflow Copilot

## Setup

1. Start local Postgres:
```bash
   docker run -d --name copilot-db \
     -e POSTGRES_USER=copilot -e POSTGRES_PASSWORD=copilot -e POSTGRES_DB=copilot \
     -p 5432:5432 postgres:16-alpine
```
2. Create an Upstash Redis database (TLS `rediss://` URL).
3. `cp .env.example .env` and fill in `OPENROUTER_API_KEY`, `DATABASE_URL`, `REDIS_URL`.
4. `pip install -r requirements.txt`
5. `alembic upgrade head`
6. `uvicorn app.main:app --reload`

## API

- `POST /copilot/create` — `{"instruction": "..."}`
- `POST /copilot/modify` — `{"workflow_id": "...", "instruction": "...", "session_id": "..."}`
- `POST /copilot/fix` — `{"workflow_id": "..."}`
- `POST /copilot/explain` — `{"workflow_id": "..."}`
- `GET /workflows`, `GET /workflows/{id}`, `POST /workflows`, `DELETE /workflows/{id}`
- `GET /health`, `GET /ready`

## Tests
```bash
pytest
```

## Run with Docker
```bash
docker compose up --build
```

## Architecture
FastAPI → `copilot.py` (create/modify/fix/explain + bounded repair loop) → `llm/client.py`
(OpenRouter, model fallback chain) → `validation.py` (structural/semantic/graph rules) →
`db/repository.py` (Postgres, async pooled). Redis (Upstash) handles per-key rate limiting
and explanation caching.

## Key Decisions
- Free OpenRouter models in a fallback chain — one rate-limited model doesn't break the API.
- Repair loop capped at 2 attempts to bound LLM calls per request.
- Rate limiter fails open if Upstash is unreachable — Redis outage doesn't take down the API.
- Global exception handler ensures one bad request never crashes a worker.

## Trade-offs
- No auth beyond an `X-API-Key` header used for rate limiting (not validated against a user table).
- `/modify` and `/fix` overwrite the stored workflow rather than versioning history.

## Future Improvements
- Workflow version history, diff-based `/modify` operations, JWT-based auth.