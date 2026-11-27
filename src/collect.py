"""Turn raw settlement and host rows into one number per metric per minute."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

import psycopg

from .config import DATABASE_URL

SETTLEMENT_SQL = """
WITH windows AS (
    SELECT date_trunc('minute', created_at) AS minute,
           count(*)                                                 AS total,
           count(*) FILTER (WHERE status = 'failed')                AS failed,
           percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)  AS p95
    FROM settlement
    WHERE created_at >= %(since)s AND created_at < %(until)s
    GROUP BY 1
)
INSERT INTO metrics (ts, name, value)
SELECT minute, 'settlement_failure_pct', round(100.0 * failed / NULLIF(total, 0), 4) FROM windows
UNION ALL
SELECT minute, 'settlement_p95_latency_ms', round(p95::numeric, 2) FROM windows
ON CONFLICT (ts, name) DO NOTHING
"""

HOST_SQL = """
INSERT INTO metrics (ts, name, value)
SELECT date_trunc('minute', ts), 'queue_backlog', max(queue_backlog) FROM host_samples
WHERE ts >= %(since)s AND ts < %(until)s GROUP BY 1
UNION ALL
SELECT date_trunc('minute', ts), 'disk_used_pct', max(disk_used_pct) FROM host_samples
WHERE ts >= %(since)s AND ts < %(until)s GROUP BY 1
ON CONFLICT (ts, name) DO NOTHING
"""


def collect(minutes: int = 60, until: datetime | None = None) -> dict[str, int]:
    end = until or datetime.now(timezone.utc)
    start = end - timedelta(minutes=minutes)
    params = {"since": start, "until": end}
    counts: dict[str, int] = {}
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        for name, sql in (("settlement", SETTLEMENT_SQL), ("host", HOST_SQL)):
            cur.execute(sql, params)
            counts[name] = cur.rowcount
        conn.commit()
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description="Collect metrics from raw tables")
    ap.add_argument("--minutes", type=int, default=60)
    ap.add_argument("--until", help="ISO timestamp, collect up to this point")
    args = ap.parse_args()
    until = datetime.fromisoformat(args.until) if args.until else None
    counts = collect(args.minutes, until)
    print(f"metrics written: settlement={counts['settlement']} host={counts['host']}")


if __name__ == "__main__":
    main()
