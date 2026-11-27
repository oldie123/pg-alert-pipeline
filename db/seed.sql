-- Synthetic month of traffic, with two incidents worth finding.
-- Deterministic enough to be reproducible, random enough to look real.

BEGIN;

TRUNCATE settlement, metrics, incidents RESTART IDENTITY;

INSERT INTO settlement (created_at, merchant, amount, status, latency_ms)
SELECT
    ts,
    'merchant_' || (1 + (abs(hashtext(ts::text)) % 40))::text,
    round((20 + (abs(hashtext(ts::text || 'a')) % 4800))::numeric / 10, 2),
    CASE
        WHEN random() < CASE WHEN ts BETWEEN now() - interval '18 days' AND now() - interval '18 days' + interval '3 hours'
                             THEN 0.055 ELSE 0.004 END
        THEN 'failed' ELSE 'success'
    END,
    CASE
        WHEN ts BETWEEN now() - interval '6 days' AND now() - interval '6 days' + interval '2 hours'
        THEN 1500 + (abs(hashtext(ts::text || 'l')) % 900)
        ELSE 220 + (abs(hashtext(ts::text || 'q')) % 480)
    END
FROM generate_series(now() - interval '30 days', now(), interval '10 seconds') AS ts;

-- Host side numbers: queue backlog and disk.
CREATE TABLE IF NOT EXISTS host_samples (
    ts             timestamptz PRIMARY KEY,
    queue_backlog  integer NOT NULL,
    disk_used_pct  numeric(5,2) NOT NULL
);

TRUNCATE host_samples;

INSERT INTO host_samples (ts, queue_backlog, disk_used_pct)
SELECT
    ts,
    CASE
        WHEN ts BETWEEN now() - interval '6 days' AND now() - interval '6 days' + interval '2 hours'
        THEN 2200 + (abs(hashtext(ts::text || 'b')) % 900)
        ELSE 60 + (abs(hashtext(ts::text || 'c')) % 220)
    END,
    round((61 + (abs(hashtext(ts::text || 'd')) % 180)::numeric / 10), 2)
FROM generate_series(now() - interval '30 days', now(), interval '1 minute') AS ts;

COMMIT;

ANALYZE settlement;
ANALYZE host_samples;
