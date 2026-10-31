# Pulse v0.2 — Alerting Engine

## Goal

Pulse v0.2 turns incident detection into actionable notifications. The first delivery adapter is a generic signed HTTP webhook. Email and chat integrations are deliberately out of scope for this release.

The implementation stays within the existing FastAPI + PostgreSQL + worker architecture. PostgreSQL is both the durable event store and the delivery queue; no Redis, Celery, or external broker is required.

## Scope

### Included

- Webhook endpoint create, list, update, and disable operations.
- Subscriptions to `incident.opened` and `incident.resolved`.
- Transactional notification events written with incident state transitions.
- One delivery job per subscribed endpoint and event.
- Concurrent-safe worker claims using `FOR UPDATE SKIP LOCKED` and expiring leases.
- HMAC-SHA256 request signatures.
- DNS validation and IP-pinned outbound requests.
- No redirects and no environment-provided HTTP proxies.
- Bounded retries with exponential backoff and jitter.
- Delivery and attempt history.
- Retention of terminal notification history after 90 days.

### Not included

- Email, Slack, Discord, or Teams adapters.
- User accounts, workspaces, or multi-tenant authorization.
- Exactly-once delivery.
- Custom headers or arbitrary request templates.
- A general-purpose message broker.

## Architecture

1. The check worker executes a monitor check.
2. `persist_check_result` opens or resolves an incident in its existing database transaction.
3. On a real incident transition, the same transaction inserts a `notification_events` row and fans it out to currently enabled endpoints subscribed to that event type.
4. The webhook dispatcher claims due `webhook_deliveries` rows using `FOR UPDATE SKIP LOCKED`, assigns a lease token and commits before network I/O.
5. The dispatcher validates DNS, pins the connection to a vetted public IP, signs the serialized payload, and sends an HTTP POST.
6. The dispatcher records the attempt and moves the delivery to `delivered`, `pending` (retry), or `failed`.
7. Expired leases can be reclaimed by another worker. A stale worker cannot persist an attempt after its lease has been superseded.

The incident transition, event creation, and delivery fan-out are atomic. If any database write fails, the whole transaction rolls back and no notification can be queued for an incident transition that did not commit.

## Delivery semantics

Delivery is **at least once**. A receiver may see the same event more than once if Pulse sends the request successfully but crashes before it records the success. Receivers should deduplicate using `X-Pulse-Event-ID` (or the payload's `id`).

Retryable outcomes:

- DNS resolution failures and network errors.
- Request timeouts.
- HTTP 408, 425, and 429.
- HTTP 5xx.

Permanent outcomes:

- A destination resolving to a non-public address.
- HTTP redirects (redirect following is disabled).
- HTTP 4xx responses other than 408, 425, and 429.
- Exhausting the configured maximum number of attempts.

The default maximum is 8 attempts. Retry delays use exponential backoff beginning at approximately 5 seconds, capped at one hour, with jitter. `WEBHOOK_MAX_ATTEMPTS` controls the attempt limit.

Disabling an endpoint cancels its pending or leased deliveries and prevents new claims. A request already in flight when the endpoint is disabled cannot be recalled.

## Event contract

Each event payload is JSON:

```json
{
  "id": "event-uuid",
  "type": "incident.opened",
  "occurred_at": "2026-11-01T00:00:00+00:00",
  "monitor": {
    "id": 12,
    "url": "https://status.example.com",
    "interval_seconds": 60
  },
  "incident": {
    "id": 34,
    "started_at": "2026-11-01T00:00:00+00:00",
    "last_failure_at": "2026-11-01T00:00:00+00:00",
    "failure_count_at_open": 3
  }
}
```

Resolved events use `incident.resolved` and include `resolved_at` in the incident object.

Headers:

| Header | Meaning |
|---|---|
| `X-Pulse-Event` | Event type |
| `X-Pulse-Event-ID` | Stable ID for this incident transition |
| `X-Pulse-Delivery` | Destination-specific delivery row |
| `X-Pulse-Signature` | `sha256=` plus HMAC-SHA256 of the raw request body |

Verify the signature against the exact raw request body, not a re-serialized JSON object:

```python
import hashlib
import hmac

expected = "sha256=" + hmac.new(
    webhook_secret.encode("utf-8"),
    raw_request_body,
    hashlib.sha256,
).hexdigest()

valid = hmac.compare_digest(
    expected,
    request.headers.get("X-Pulse-Signature", ""),
)
```

## Webhook security

- Production webhook destinations must use HTTPS on port 443.
- The existing URL policy rejects credentials and literal private destinations.
- At delivery time Pulse resolves all A/AAAA records and rejects the destination if any answer is non-public.
- The request connects to a vetted IP while preserving the original Host header and TLS SNI.
- Redirects are disabled to prevent a public endpoint from redirecting Pulse to an internal address.
- Environment proxy variables are ignored.
- Response bodies are not stored; only status, duration, and a bounded error description are retained.
- The endpoint signing secret is returned only when created or rotated. List and update responses never reveal it.
- v0.2 stores endpoint secrets in PostgreSQL. Protect the database and its backups as sensitive data; application-level encryption at rest is a future hardening item.
- `PULSE_ALLOW_LOOPBACK=1` is a test-only escape hatch for local integration tests and must not be enabled in a deployed instance.

## API

Base path: `/api/v1`.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/webhooks` | Create endpoint; returns signing secret once |
| `GET` | `/webhooks` | List configured endpoints without secrets |
| `PATCH` | `/webhooks/{id}` | Update name, URL, event subscriptions, enabled state, or secret |
| `DELETE` | `/webhooks/{id}` | Disable endpoint and cancel pending deliveries |
| `GET` | `/webhooks/{id}/deliveries` | Inspect recent deliveries and their attempts |

Create example:

```bash
curl -X POST http://localhost:8000/api/v1/webhooks \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Operations receiver",
    "url": "https://hooks.example.com/pulse",
    "event_types": ["incident.opened", "incident.resolved"]
  }'
```

If `secret` is omitted, Pulse generates a cryptographically random signing secret. Save it from the create response; it is not returned by subsequent list or update calls. To rotate it, send a new `secret` in a PATCH request and update the receiving service at the same time.

## Configuration

| Variable | Default | Meaning |
|---|---:|---|
| `WEBHOOK_CONCURRENCY` | `10` | Maximum delivery jobs claimed per worker cycle |
| `WEBHOOK_MAX_ATTEMPTS` | `8` | Maximum attempts before a delivery becomes terminally failed |
| `NOTIFICATION_RETENTION_DAYS` | `90` | Retention for notification events, deliveries, and attempts |
| `REQUEST_TIMEOUT_SECONDS` | `10` | Outbound webhook request timeout |
| `LEASE_DURATION_SECONDS` | `30` | Delivery lease duration, shared with monitor checks |

Apply migrations with the existing command:

```bash
uv run python scripts/migrate.py
```

The existing worker process dispatches webhook deliveries alongside monitor checks.

## Operational notes and future work

- There is no authentication on the API yet. Keep Pulse bound to loopback or behind a trusted access boundary.
- Signing secrets are stored in the database in v0.2; encrypting them at rest should be considered before exposing a hosted multi-user service.
- Delivery history is retained for 90 days by default. Pending work is never removed by retention cleanup.
- Future versions can add provider adapters (email/Slack), per-endpoint rate limits, manual redelivery, secret encryption, and a richer delivery detail UI without changing the incident transaction contract.
