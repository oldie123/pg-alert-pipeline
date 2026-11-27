"""Compare the latest metric values against the threshold rows."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone

import psycopg

from .config import DATABASE_URL
from .notify import send_message


@dataclass(frozen=True)
class Threshold:
    name: str
    warn: float | None
    crit: float | None
    direction: str
    cooldown_minutes: int
    owner: str


def severity_for(t: Threshold, value: float) -> str:
    """Return 'ok', 'warn' or 'crit'. Critical wins when both bounds match."""
    if value is None:
        return "ok"
    if t.direction == "above":
        if t.crit is not None and value >= t.crit:
            return "crit"
        if t.warn is not None and value >= t.warn:
            return "warn"
    else:
        if t.crit is not None and value <= t.crit:
            return "crit"
        if t.warn is not None and value <= t.warn:
            return "warn"
    return "ok"


def in_cooldown(last_notified: datetime | None, cooldown_minutes: int, now: datetime) -> bool:
    if last_notified is None:
        return False
    return (now - last_notified).total_seconds() < cooldown_minutes * 60


def load_state(cur, at: datetime | None = None) -> tuple[list[tuple[Threshold, float]], dict[str, dict]]:
    """Latest value per metric, optionally as of a point in time (for replays)."""
    if at is None:
        cur.execute("""
            SELECT DISTINCT ON (name) name, value
            FROM metrics
            ORDER BY name, ts DESC
        """)
    else:
        cur.execute("""
            SELECT DISTINCT ON (name) name, value
            FROM metrics
            WHERE ts <= %s
            ORDER BY name, ts DESC
        """, (at,))
    latest = {name: float(value) for name, value in cur.fetchall()}

    cur.execute("""
        SELECT name, warn, crit, direction, cooldown_minutes, owner
        FROM thresholds WHERE enabled
    """)
    thresholds = [
        (Threshold(n, w, c, d, cd, o), latest[n])
        for n, w, c, d, cd, o in cur.fetchall()
        if n in latest
    ]

    cur.execute("""
        SELECT name, id, severity, opened_at, notified_at
        FROM incidents WHERE resolved_at IS NULL
    """)
    open_incidents = {
        name: {"id": iid, "severity": sev, "opened_at": opened, "notified_at": notified}
        for name, iid, sev, opened, notified in cur.fetchall()
    }
    return thresholds, open_incidents


def evaluate(dry_run: bool = False, at: datetime | None = None) -> list[str]:
    now = at or datetime.now(timezone.utc)
    actions: list[str] = []

    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        thresholds, open_incidents = load_state(cur, at)

        for t, value in thresholds:
            severity = severity_for(t, value)
            incident = open_incidents.get(t.name)

            if severity == "ok":
                if incident:
                    cur.execute(
                        "UPDATE incidents SET resolved_at = %s WHERE id = %s",
                        (now, incident["id"]),
                    )
                    actions.append(f"resolved {t.name} (value back to {value})")
                continue

            if incident is None:
                cur.execute(
                    """INSERT INTO incidents (name, severity, value, opened_at)
                       VALUES (%s, %s, %s, %s) RETURNING id""",
                    (t.name, severity, value, now),
                )
                incident_id = cur.fetchone()[0]
                message = f"[{severity.upper()}] {t.name} = {value} (owner: {t.owner})"
                actions.append(f"opened {t.name} {severity} at {value}")
                if not dry_run:
                    send_message(message)
                    cur.execute(
                        "UPDATE incidents SET notified_at = %s WHERE id = %s",
                        (now, incident_id),
                    )
            elif severity == "crit" and incident["severity"] == "warn":
                cur.execute(
                    "UPDATE incidents SET severity = 'crit', value = %s WHERE id = %s",
                    (value, incident["id"]),
                )
                actions.append(f"escalated {t.name} to crit at {value}")
            elif not in_cooldown(incident["notified_at"], t.cooldown_minutes, now):
                if not dry_run:
                    send_message(f"[{severity.upper()}] {t.name} masih {value} (owner: {t.owner})")
                    cur.execute(
                        "UPDATE incidents SET notified_at = %s WHERE id = %s",
                        (now, incident["id"]),
                    )
                actions.append(f"renotified {t.name} at {value}")

        if dry_run:
            conn.rollback()
        else:
            conn.commit()

    return actions


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate metrics against thresholds")
    ap.add_argument("--dry-run", action="store_true", help="print actions, change nothing")
    ap.add_argument("--at", help="evaluate as of an ISO timestamp, for replays")
    args = ap.parse_args()
    at = datetime.fromisoformat(args.at) if args.at else None
    actions = evaluate(dry_run=args.dry_run, at=at)
    if not actions:
        print("all metrics inside thresholds")
    for action in actions:
        print(action)


if __name__ == "__main__":
    main()
