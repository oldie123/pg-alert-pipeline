# pg-alert-pipeline

Thresholds live in the database, not in the code. This is the pattern I used to cut alert noise on a payment switch: metrics land in Postgres, the alerting rules are rows in a table, and a worker compares the two every minute.

Two things go wrong with alerts kept in config files. Nobody can change them without a deploy, and nobody remembers who set them. Moving them into a table fixed both, and made it possible to say "this rule woke us up 40 times last week, widen it" with a query instead of a pull request.

## How it works

```
settlement ──► collect.py ──► metrics (name, ts, value)
                                    │
thresholds (warn, crit, cooldown) ──┤
                                    ▼
                              evaluate.py ──► incidents ──► notifier
```

`collect.py` aggregates raw rows into a handful of numbers per minute. `evaluate.py` reads the latest value for each metric, compares it to the row in `thresholds`, and opens or resolves an incident. Nothing is hardcoded: add a metric and a threshold row, and it is monitored.

## Quickstart

```bash
docker compose up -d          # postgres 16 on :5432, schema and seed applied
pip install -r requirements.txt

python -m src.collect         # writes the last hour of metrics
python -m src.evaluate        # opens incidents for anything past its threshold
python -m src.evaluate --dry-run
```

With no `.env`, notifications print to stdout instead of calling Telegram. That is deliberate: the demo should not need credentials to be useful.

## Replay a past incident

The evaluator takes a timestamp, which is how you test a rule without waiting for production to break.

```bash
python -m src.collect --minutes 43200                    # backfill a month
python -m src.evaluate --at 2026-11-09T07:58:00+00:00 --dry-run
# opened settlement_failure_pct crit at 16.6667
```

`--dry-run` rolls the transaction back, so you can replay the same window as often as you like.

## Tables

| table | what it holds |
| --- | --- |
| `settlement` | synthetic transaction rows, one month |
| `metrics` | `(ts, name, value)`, written by `collect.py` |
| `thresholds` | `warn`, `crit`, `cooldown_minutes`, `owner` per metric |
| `incidents` | one row per open or resolved alert |

## Design notes

Cooldowns sit on the threshold row, not in memory. A restart should not re-page someone for an incident they already acknowledged, and state in a process is state you lose.

Severity is derived from the value, not from the rule that fired. `crit` wins over `warn` when both match, so a metric crossing straight to critical does not produce two incidents.

Resolving is a write, not a delete. The incidents table is the thing you query when someone asks why last Tuesday was noisy.

## Tests

```bash
pytest -q
```

The threshold logic is pure functions over `(threshold, value)`, so the tests run without a database.

## Synthetic data

`db/seed.sql` generates a month of transactions with two deliberate incidents: a spike in failed settlements around day 12, and a queue backlog on day 21. The dashboard in `docs/` is what those two days look like.
