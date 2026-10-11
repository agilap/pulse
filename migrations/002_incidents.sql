-- 002_incidents: incident lifecycle tracking
-- Per PRD §11 and FR-09.

CREATE TABLE incidents (
    id                    BIGSERIAL PRIMARY KEY,
    monitor_id            BIGINT NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    started_at            TIMESTAMPTZ NOT NULL,
    last_failure_at       TIMESTAMPTZ NOT NULL,
    resolved_at           TIMESTAMPTZ,
    failure_count_at_open INTEGER NOT NULL
);

CREATE INDEX idx_incidents_monitor_started ON incidents (monitor_id, started_at DESC);

-- FR-09: at most one unresolved incident per monitor, enforced by the database.
CREATE UNIQUE INDEX idx_incidents_one_open_per_monitor
    ON incidents (monitor_id)
    WHERE resolved_at IS NULL;
