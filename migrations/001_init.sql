-- 001_init: Initial schema for Pulse
-- Creates monitors and check_results tables with indexes.
-- Per PRD §11 data model: integer identity, parameterized-friendly, FK + cascade.

CREATE TABLE monitors (
    id                   BIGSERIAL PRIMARY KEY,
    url                  TEXT      NOT NULL,
    interval_seconds     INTEGER   NOT NULL DEFAULT 60 CHECK (interval_seconds BETWEEN 60 AND 86400),
    enabled              BOOLEAN   NOT NULL DEFAULT TRUE,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    next_check_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_until          TIMESTAMPTZ,
    lease_token          TEXT,
    last_checked_at      TIMESTAMPTZ,
    last_outcome         TEXT,
    last_status_code     SMALLINT,
    consecutive_failures INTEGER   NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    CHECK (
        (lease_until IS NULL AND lease_token IS NULL)
        OR (lease_until IS NOT NULL AND lease_token IS NOT NULL)
    )
);

CREATE INDEX idx_monitors_due ON monitors (enabled, next_check_at)
    WHERE enabled = TRUE;

CREATE INDEX idx_monitors_lease ON monitors (lease_until)
    WHERE lease_until IS NOT NULL;

CREATE TABLE check_results (
    id            BIGSERIAL PRIMARY KEY,
    monitor_id    BIGINT NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    checked_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    outcome       TEXT NOT NULL,
    status_code   SMALLINT,
    latency_ms    INTEGER CHECK (latency_ms >= 0),
    error_code    TEXT,
    error_message TEXT
);

CREATE INDEX idx_check_results_monitor_time ON check_results (monitor_id, checked_at DESC);

-- Outcome categories per PRD §12 check outcome rules:
-- success, http_error, timeout, dns_error, tls_error,
-- connection_error, blocked_destination, internal_error
