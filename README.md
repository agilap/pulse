# Pulse

A small, self-hosted uptime monitor. Register a public website or API
endpoint; Pulse checks it on a schedule, records the result and latency,
identifies sustained failures as incidents, and presents status and history
in a dashboard.

Built with Python, FastAPI, `psycopg`, PostgreSQL, and Docker Compose — with
a React + TypeScript dashboard. No ORM, no Redis, no AI services.

## Architecture

```
Dashboard (React, :5173) ──HTTP──▶ FastAPI API (:8000) ──┐
                                                         ├──▶ PostgreSQL (:5432)
Worker process ──claim/check/persist──────────────────────┘
```

See `docs/architecture.md` for the full design: worker claims/leases, the
incident state machine, status derivation, and SSRF defenses. See
`docs/benchmark.md` for measured performance.

## Requirements

- Docker + Docker Compose (for PostgreSQL)
- Python 3.10+ and [`uv`](https://docs.astral.sh/uv/)
- Node.js 22+ (for the dashboard)

## Quick start

### 1. Start PostgreSQL

```bash
docker compose up -d postgres
```

Postgres listens on `127.0.0.1:5432` with a persistent named volume.

### 2. Configure and run the API

```bash
cp .env.example .env        # adjust DATABASE_URL if you changed credentials
uv sync --all-extras
DATABASE_URL=postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse \
  uv run python scripts/migrate.py
DATABASE_URL=postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse \
  uv run uvicorn backend.app.main:app --reload
```

API on `http://localhost:8000` — interactive docs at `/docs`.

### 3. Run the worker (separate process)

```bash
DATABASE_URL=postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse \
  uv run python -m backend.app.worker.main
```

The worker claims due monitors, performs safe bounded checks, and persists
results + incidents.

### 4. Start the dashboard

```bash
cd frontend
npm install
npm run dev
```

Dashboard on `http://localhost:5173`. The Vite dev server proxies `/api` and
`/health` to the API on port 8000.

## API

Base path `/api/v1`. Timestamps are ISO 8601 UTC.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/monitors` | Create a monitor |
| `GET` | `/api/v1/monitors` | List monitors with derived status |
| `GET` | `/api/v1/monitors/{id}` | Retrieve a monitor |
| `PATCH` | `/api/v1/monitors/{id}` | Update interval / enabled state |
| `DELETE` | `/api/v1/monitors/{id}` | Delete monitor + cascaded history |
| `GET` | `/api/v1/monitors/{id}/checks` | Recent check history (bounded) |
| `GET` | `/api/v1/monitors/{id}/incidents` | Incident history |
| `GET` | `/api/v1/incidents?state=open` | Filterable incident list |
| `GET` | `/health/live` | Process liveness |
| `GET` | `/health/ready` | Database readiness (503 if down) |

### Create a monitor

```bash
curl -X POST http://localhost:8000/api/v1/monitors \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "interval_seconds": 60}'
```

```json
{
  "id": 1,
  "url": "https://example.com",
  "interval_seconds": 60,
  "enabled": true,
  "status": "pending",
  "created_at": "2026-10-11T01:00:00Z",
  "next_check_at": "2026-10-11T01:00:00Z"
}
```

### Error format

```json
{
  "error": {
    "code": "invalid_url",
    "message": "Enter an absolute HTTP or HTTPS URL."
  }
}
```

## Tests

```bash
DATABASE_URL=postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse \
  uv run pytest -q
```

```bash
uv run ruff check backend/ scripts/     # lint
cd frontend && npm run lint && npm run build
```

## Benchmark

```bash
DATABASE_URL=postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse \
  uv run python scripts/benchmark.py
```

## Configuration

All settings come from environment variables (see `.env.example`):

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | — | PostgreSQL connection string |
| `REQUEST_TIMEOUT_SECONDS` | `10` | Total HTTP check timeout |
| `LEASE_DURATION_SECONDS` | `30` | Worker claim lease (must exceed timeout + 5s) |
| `WORKER_CONCURRENCY` | `5` | Claims per worker cycle |
| `FAILURE_THRESHOLD` | `3` | Consecutive failures that open an incident |
| `RETENTION_DAYS` | `30` | Check-result retention window |
| `MIN_INTERVAL_SECONDS` | `60` | Minimum monitor interval |
| `MAX_INTERVAL_SECONDS` | `86400` | Maximum monitor interval |

## Security

Pulse makes outbound requests to user-supplied destinations, so SSRF
prevention is core. Only absolute HTTP(S) URLs with ports 80/443 are allowed;
at check time all resolved IPs are validated and the connection is pinned to a
vetted address; redirects are disabled. Details and limitations are in
`docs/architecture.md#ssrf-defenses`.

Bind services to loopback and do not expose an unauthenticated instance
publicly.

## Resetting local data

```bash
docker compose down -v    # stops services and deletes the Postgres volume
```

## Project layout

```
backend/app/       FastAPI API, worker, checker, status derivation
backend/tests/     unit + integration tests
migrations/        versioned SQL migrations
frontend/          React + TypeScript dashboard
scripts/           migration runner, benchmark
docs/              architecture + benchmark notes
```

## Implemented vs. future work

**Implemented:** monitor CRUD, scheduled checks, safe HTTP checking with
SSRF defenses, check-result persistence, incident lifecycle, status
derivation (pending/up/degraded/down/stale), data retention, structured
secret-safe logging, health endpoints, dashboard, CI.

**Known limitations:**
- No authentication — local/self-hosted use only.
- List status derivation issues one indexed lookup per monitor; fine at the
  50-monitor target, would need batching at larger scale.
- No notifications (email/Slack/webhook) — by design for the MVP.

**Future candidates:** notifications with rate limiting, per-monitor failure
thresholds, authentication for remote use, public status pages.
