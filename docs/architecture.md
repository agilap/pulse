# Pulse — Architecture

## Overview

Pulse is a self-hosted uptime monitor. A user registers a public HTTP(S)
endpoint; a background worker checks it on a schedule, persists the outcome,
tracks incidents, and a dashboard presents status and history.

```
                ┌──────────────┐
                │   Dashboard  │  React + TS (frontend/)
                │  (port 5173) │  polls /api/v1 every 5s
                └──────┬───────┘
                       │
                       ▼
┌──────────────┐   ┌──────────────┐
│  Worker proc │   │   FastAPI    │
│ (worker/main)│   │  (port 8000) │
└──────┬───────┘   └──────┬───────┘
       │                  │
       │   claim / persist│ read
       └────────┬─────────┘
                ▼
        ┌───────────────┐
        │  PostgreSQL   │
        │ (port 5432)   │
        └───────────────┘
```

The API and worker are separate processes sharing one PostgreSQL database.
The database is the single source of truth for scheduling — there is no
in-memory schedule that would be lost on restart.

## Components

| Module | Responsibility |
|---|---|
| `backend/app/api/` | FastAPI routes: monitor CRUD, webhook management, history, health |
| `backend/app/db/core.py` | psycopg connection pool (`get_conn`) |
| `backend/app/db/queries.py` | Monitor and incident SQL; transactional event enqueue |
| `backend/app/db/webhooks.py` | Webhook endpoint and delivery-history queries |
| `backend/app/monitoring/url_policy.py` | Monitor URL syntax + literal SSRF validation |
| `backend/app/monitoring/checker.py` | DNS resolution, IP pinning, safe HTTP GET, outcome classification |
| `backend/app/monitoring/webhook.py` | Signed outbound POST, webhook URL policy, DNS/IP validation |
| `backend/app/monitoring/status.py` | Status derivation — the freshness formula lives here ONLY |
| `backend/app/worker/claim.py` | Atomic due-monitor claim (`FOR UPDATE SKIP LOCKED` + lease) |
| `backend/app/worker/check_loop.py` | One check cycle: claim → check → persist |
| `backend/app/worker/webhook_dispatch.py` | Delivery claim, send, retry, and result persistence |
| `backend/app/worker/retention.py` | Batched cleanup of old check results and terminal notification events |
| `backend/app/logging_config.py` | Structured JSON logging with secret redaction |

## Worker claim + lease design

Each monitor check cycle:

1. **Claim** (short transaction): select enabled, due monitors with no live
   lease, lock with `FOR UPDATE SKIP LOCKED`, set a unique `lease_token` and
   `lease_until` (default 30s), and commit — *before* any network I/O.
   Locks are never held across an HTTP request.
2. **Check**: resolve all A/AAAA records, reject if any address is
   non-public, pin the socket to a vetted IP while preserving Host/SNI,
   perform a bounded GET (10s timeout), no redirects.
3. **Persist** (single transaction): insert the check result, update monitor
   summary fields and `consecutive_failures`, open/resolve the incident,
   clear the lease, and schedule the next check at
   `checked_at + interval_seconds`. Incident state transitions also create
   notification events and delivery rows in this transaction.
4. **Recovery**: if a worker crashes mid-check, its lease expires and another
   worker reclaims the still-due monitor. Config validation rejects any
   lease shorter than `timeout + 5s` at startup.

Concurrency bound: `worker_concurrency` (default 5) claims per cycle, so a
single worker drains backlog gradually and multiple workers get disjoint
batches.

## Incident state machine

```
        failure 1,2            failure 3+              success
            │                      │                     │
            ▼                      ▼                     ▼
        (none) ─────────────►  [OPEN]  ─────────────►  resolved
        consecutive_failures   one row per monitor     counter = 0
        incremented            (partial unique index)
```

- Below threshold: increment `consecutive_failures`, no incident.
- At threshold (3): open one incident if none is open; otherwise update
  `last_failure_at`. A partial unique index on `(monitor_id) WHERE
  resolved_at IS NULL` makes duplicate open incidents impossible.
- On success: reset the counter and resolve the open incident.
- Staleness is derived, not stored — stale data never silently resolves an
  incident.

## Status derivation (FR-08)

Defined once in `backend/app/monitoring/status.py`; the API and dashboard both
consume it.

Freshness window = `max(3 × interval, 120s) + request_timeout`.

| Status | Meaning |
|---|---|
| `pending` | No check completed yet |
| `up` | Latest check succeeded, no open incident |
| `degraded` | Recent failures, below incident threshold |
| `down` | Incident open, data fresh |
| `stale` | Data older than the freshness window — takes precedence over up/down |

## SSRF defenses

- Only absolute `http`/`https`; userinfo, non-80/443 ports, and embedded
  credentials rejected at create time (`url_policy.py`).
- At check time (`checker.py`): resolve **all** A/AAAA records; if any
  resolved address is loopback, private, link-local, multicast, reserved, or
  otherwise non-global (including IPv4-mapped IPv6), the check is recorded as
  `blocked_destination` and no connection is made.
- The socket is pinned to a vetted IP; the HTTP Host header and TLS SNI
  keep the original hostname. DNS is revalidated on every check because DNS
  can change between checks.
- Redirects are disabled; proxy environment variables are not trusted.
- Test-only loopback is gated behind `PULSE_ALLOW_LOOPBACK=1`, never on by
  default.

## Data retention

Check results older than `retention_days` (default 30) are deleted in bounded
batches of 1000 — each batch is its own short transaction, never one
long-running delete over the whole table. Incidents persist until their
monitor is deleted.

## v0.2 — Alerting Engine

The webhook dispatcher runs in the existing worker process. When an incident
opens or resolves, `persist_check_result` writes the incident transition,
a `notification_events` outbox record, and one `webhook_deliveries` row per
enabled subscribed endpoint in the same PostgreSQL transaction.

The dispatcher claims due deliveries with `FOR UPDATE SKIP LOCKED`, commits
the lease before network I/O, sends a signed HTTPS POST, then records an
attempt. Expired leases are reclaimable. Retryable network failures, timeouts,
HTTP 408/425/429, and HTTP 5xx use exponential backoff with jitter; permanent
receiver rejections, redirects, blocked destinations, and exhausted retries
become terminal failures.

Delivery is at-least-once. Receivers should deduplicate using the stable
`X-Pulse-Event-ID` header. See `docs/alerting.md` for the event contract,
API, security policy, retry rules, and operational behavior.
