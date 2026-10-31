-- 003_webhook_alerting: transactional incident events and webhook delivery.
-- Events are written in the same transaction as incident transitions.

CREATE TABLE webhook_endpoints (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 80),
    url         TEXT NOT NULL,
    secret      TEXT NOT NULL,
    event_types TEXT[] NOT NULL DEFAULT ARRAY['incident.opened', 'incident.resolved']::TEXT[],
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (cardinality(event_types) > 0),
    CHECK (event_types <@ ARRAY['incident.opened', 'incident.resolved']::TEXT[])
);

CREATE INDEX idx_webhook_endpoints_subscriptions
    ON webhook_endpoints USING GIN (event_types)
    WHERE enabled = TRUE;

CREATE TABLE notification_events (
    id          UUID PRIMARY KEY,
    event_type  TEXT NOT NULL CHECK (event_type IN ('incident.opened', 'incident.resolved')),
    incident_id BIGINT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
    monitor_id  BIGINT NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (incident_id, event_type)
);

CREATE INDEX idx_notification_events_created
    ON notification_events (created_at);

CREATE TABLE webhook_deliveries (
    id                 BIGSERIAL PRIMARY KEY,
    event_id           UUID NOT NULL REFERENCES notification_events(id) ON DELETE CASCADE,
    endpoint_id        BIGINT NOT NULL REFERENCES webhook_endpoints(id) ON DELETE RESTRICT,
    status             TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'delivering', 'delivered', 'failed')),
    attempt_count      INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lease_until        TIMESTAMPTZ,
    lease_token        TEXT,
    last_status_code   SMALLINT,
    last_error_code    TEXT,
    last_error_message TEXT,
    delivered_at       TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (lease_until IS NULL AND lease_token IS NULL)
        OR (lease_until IS NOT NULL AND lease_token IS NOT NULL)
    ),
    CHECK (status <> 'delivering' OR lease_until IS NOT NULL),
    UNIQUE (event_id, endpoint_id)
);

CREATE INDEX idx_webhook_deliveries_due
    ON webhook_deliveries (next_attempt_at, id)
    WHERE status IN ('pending', 'delivering');

CREATE INDEX idx_webhook_deliveries_endpoint_created
    ON webhook_deliveries (endpoint_id, created_at DESC);

CREATE TABLE webhook_delivery_attempts (
    id              BIGSERIAL PRIMARY KEY,
    delivery_id     BIGINT NOT NULL REFERENCES webhook_deliveries(id) ON DELETE CASCADE,
    attempt_number  INTEGER NOT NULL CHECK (attempt_number > 0),
    attempted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    outcome         TEXT NOT NULL CHECK (outcome IN ('delivered', 'retrying', 'failed')),
    response_status SMALLINT,
    duration_ms     INTEGER CHECK (duration_ms IS NULL OR duration_ms >= 0),
    error_code      TEXT,
    error_message   TEXT,
    UNIQUE (delivery_id, attempt_number)
);

CREATE INDEX idx_webhook_delivery_attempts_delivery
    ON webhook_delivery_attempts (delivery_id, attempt_number DESC);
