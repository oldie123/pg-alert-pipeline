-- Schema for the alert pipeline demo.
-- Everything is idempotent so `docker compose up` can re-run it.

BEGIN;

CREATE TABLE IF NOT EXISTS settlement (
    id           bigserial PRIMARY KEY,
    created_at   timestamptz NOT NULL,
    merchant     text        NOT NULL,
    amount       numeric(14,2) NOT NULL,
    status       text        NOT NULL CHECK (status IN ('success', 'failed', 'pending')),
    latency_ms   integer     NOT NULL
);

CREATE INDEX IF NOT EXISTS settlement_created_at_idx ON settlement (created_at);

CREATE TABLE IF NOT EXISTS metrics (
    id     bigserial PRIMARY KEY,
    ts     timestamptz NOT NULL,
    name   text        NOT NULL,
    value  numeric(14,4) NOT NULL,
    UNIQUE (ts, name)
);

CREATE INDEX IF NOT EXISTS metrics_name_ts_idx ON metrics (name, ts DESC);

CREATE TABLE IF NOT EXISTS thresholds (
    name             text PRIMARY KEY,
    warn             numeric(14,4),
    crit             numeric(14,4),
    direction        text NOT NULL DEFAULT 'above' CHECK (direction IN ('above', 'below')),
    cooldown_minutes integer NOT NULL DEFAULT 30,
    owner            text NOT NULL DEFAULT 'platform',
    enabled          boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS incidents (
    id          bigserial PRIMARY KEY,
    name        text NOT NULL,
    severity    text NOT NULL CHECK (severity IN ('warn', 'crit')),
    value       numeric(14,4) NOT NULL,
    opened_at   timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    notified_at timestamptz
);

CREATE INDEX IF NOT EXISTS incidents_open_idx ON incidents (name) WHERE resolved_at IS NULL;

INSERT INTO thresholds (name, warn, crit, direction, cooldown_minutes, owner) VALUES
    ('settlement_failure_pct', 1.0, 2.5, 'above', 30, 'payments'),
    ('settlement_p95_latency_ms', 900, 1500, 'above', 30, 'payments'),
    ('queue_backlog', 500, 2000, 'above', 15, 'platform'),
    ('disk_used_pct', 80, 90, 'above', 120, 'infra')
ON CONFLICT (name) DO UPDATE SET
    warn = EXCLUDED.warn,
    crit = EXCLUDED.crit,
    direction = EXCLUDED.direction,
    cooldown_minutes = EXCLUDED.cooldown_minutes,
    owner = EXCLUDED.owner;

COMMIT;
