# Pulse — Benchmark Report

Measured results from `scripts/benchmark.py`. Targets come from PRD §4.3.

## Test environment

| Item | Value |
|---|---|
| Machine | x86_64 (local dev container) |
| OS | Linux (Ubuntu-hosted) |
| Python | 3.10.12 |
| Database | PostgreSQL 16.15 (Docker Compose, localhost) |
| Driver | psycopg 3 with `psycopg_pool` |
| Client | `fastapi.testclient.TestClient` (in-process, no network hop) |
| Dataset | 50 monitors |
| Requests per endpoint | 100 |

## Reproduce

```bash
docker compose up -d postgres
DATABASE_URL=postgresql://pulse:changeme-not-a-real-secret@localhost:5432/pulse \
  uv run python scripts/benchmark.py
```

## Results

| Endpoint | p50 | p95 | mean | min | max |
|---|---|---|---|---|---|
| `GET /api/v1/monitors` | 17.5 ms | 20.2 ms | 17.7 ms | 15.9 ms | 22.6 ms |
| `GET /api/v1/monitors/{id}` | 2.6 ms | 3.1 ms | 2.6 ms | 2.2 ms | 3.4 ms |
| `GET /api/v1/monitors/{id}/checks` | 2.5 ms | 3.5 ms | 2.6 ms | 2.2 ms | 6.1 ms |

**Target: p95 < 300 ms for CRUD/list operations with 50 monitors — met**
(list p95 = 20.2 ms, ~15x under target).

## Notes and limitations

- The TestClient measures in-process ASGI dispatch plus database round-trips.
  It excludes network latency and process boundaries, so absolute numbers are
  lower than a networked client would see. The *relative* comparison and
  index effectiveness are still meaningful.
- `GET /api/v1/monitors` is the heaviest endpoint because it derives status
  per monitor (`has_open_incident` issues one indexed lookup per row). At 50
  monitors this is 50 cheap index probes — reflected in the ~15 ms overhead
  over the single-monitor endpoints. At larger scale this should be batched
  into a single query; noted as a known limitation.
- These are local-environment numbers, not production guarantees (PRD §3:
  "measured, not claimed").
