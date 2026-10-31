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
Worker process ──claim/check/persist + dispatch──────────┘
```

See `docs/architecture.md` for the architecture and `docs/alerting.md` for
the v0.2 webhook delivery design, event contract, security rules, and retry
semantics. See `docs/benchmark.md` for measured performance.

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
cp .env.example .env
set -a
. ./.env
set +a
uv sync --all-extras
uv run python scripts/migrate.py
uv run uvicorn backend.app.main:app --reload
```

API on `http://localhost:8000` — interactive docs at `/docs`.

### 3. Run the worker (separate process)

```bash
set -a
. ./.env
set +a
uv run python -m backend.app.worker.main
```

The worker claims due monitors, performs safe bounded checks, persists
results and incident transitions, then dispatches due webhook deliveries.

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
| `POST` | `/monitors` | Create a monitor |
| `GET` | `/monitors` | List monitors with derived status |
| `GET` | `/monitors/{id}` | Retrieve a monitor |
| `PATCH` | `/monitors/{id}` | Update interval / enabled state |
| `DELETE` | `/monitors/{id}` | Delete monitor + cascaded history |
| `GET` | `/monitors/{id}/checks` | Recent check history |
| `GET` | `/monitors/{id}/incidents` | Incident history |
| `GET` | `/incidents?state=open` | Filterable incident list |
| `POST` | `/webhooks` | Create signed webhook endpoint |
| `GET` | `/webhooks` | List webhook endpoints |
| `PATCH` | `/webhooks/{id}` | Update webhook endpoint |
| `DELETE` | `/webhooks/{id}` | Disable endpoint and cancel pending deliveries |
| `GET` | `/webhooks/{id}/deliveries` | Delivery and attempt history |
| `GET` | `/health/live` | Process liveness |
| `GET` | `/health/ready` | Database readiness (503 if down) |

### Create a monitor

```bash
curl -X POST http://localhost:8000/api/v1/monitors \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "interval_seconds": 60}'
```

### Create a webhook

```bash
curl -X POST http://localhost:8000/api/v1/webhooks \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Operations receiver",
    "url": "https://hooks.example.com/pulse",
    "event_types": ["incident.opened", "incident.resolved"]
  }'
```

Pulse generates a random signing secret if one is not supplied. Save the
secret from the create response: subsequent list and update responses never
reveal it. Requests include `X-Pulse-Signature`, an HMAC-SHA256 signature of
the raw JSON body. See `docs/alerting.md` for verification instructions.

## Tests

```bash
uv run ruff check backend/ scripts/
uv run pytest -q
cd frontend && npm ci && npm run lint && npm run build && npm test
```

## Configuration

See `.env.example` for the complete local configuration.

| Variable | Default | Meaning |
|---|---:|---|
| `DATABASE_URL` | local Postgres URL | PostgreSQL connection |
| `REQUEST_TIMEOUT_SECONDS` | `10` | Outbound HTTP timeout |
| `LEASE_DURATION_SECONDS` | `30` | Worker lease; must exceed timeout + 5s |
| `WORKER_CONCURRENCY` | `5` | Monitor claims per cycle |
| `WEBHOOK_CONCURRENCY` | `10` | Concurrent webhook deliveries per cycle |
| `WEBHOOK_MAX_ATTEMPTS` | `8` | Maximum delivery attempts |
| `FAILURE_THRESHOLD` | `3` | Consecutive failures that open an incident |
| `RETENTION_DAYS` | `30` | Check-result retention |
| `NOTIFICATION_RETENTION_DAYS` | `90` | Notification event and delivery retention |

## Security

Pulse makes outbound requests to user-supplied destinations, so SSRF
prevention is core. Monitor checks validate DNS and pin requests to public
addresses. Webhook destinations must use HTTPS in production; Pulse validates
all DNS answers, pins the destination IP, preserves Host/SNI, disables
redirects and environment proxies, and signs payloads with HMAC-SHA256.

The API has no authentication yet. Bind services to loopback and do not expose
an unauthenticated instance publicly. Webhook signing secrets are stored in
PostgreSQL; protect the database and its backups as sensitive data.

## Implemented vs. future work

**Implemented:** monitor CRUD, scheduled checks, safe HTTP checking with SSRF
defenses, check-result persistence, incident lifecycle, status derivation,
data retention, structured logging, health endpoints, dashboard, CI, signed
webhook endpoints, transactional notification events, lease-based dispatch,
retry/backoff, and delivery attempt history.

**Known limitations:**
- No authentication — local/self-hosted use only.
- Webhook signing secrets are stored in PostgreSQL without application-level encryption.
- Delivery is at-least-once; webhook receivers must deduplicate event IDs.
- Email and chat notification providers are not implemented.

**Future candidates:** email/Slack adapters, application-level secret encryption,
manual redelivery, per-endpoint rate limits, SLO analytics, and public status pages.
