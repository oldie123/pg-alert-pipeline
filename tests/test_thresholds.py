from datetime import datetime, timedelta, timezone

from src.evaluate import Threshold, in_cooldown, severity_for
from src.zabbix_sender import encode

SETTLEMENT = Threshold(
    name="settlement_failure_pct", warn=1.0, crit=2.5,
    direction="above", cooldown_minutes=30, owner="payments",
)
DISK = Threshold(
    name="disk_free_pct", warn=20.0, crit=10.0,
    direction="below", cooldown_minutes=120, owner="infra",
)


def test_below_warn_is_ok():
    assert severity_for(SETTLEMENT, 0.4) == "ok"


def test_between_warn_and_crit_is_warn():
    assert severity_for(SETTLEMENT, 1.0) == "warn"
    assert severity_for(SETTLEMENT, 2.49) == "warn"


def test_at_or_above_crit_is_crit():
    assert severity_for(SETTLEMENT, 2.5) == "crit"
    assert severity_for(SETTLEMENT, 9.9) == "crit"


def test_direction_below_flips_the_comparison():
    assert severity_for(DISK, 12.0) == "warn"
    assert severity_for(DISK, 5.0) == "crit"
    assert severity_for(DISK, 40.0) == "ok"


def test_missing_bound_is_skipped():
    warn_only = Threshold("cpu", 80, None, "above", 15, "infra")
    assert severity_for(warn_only, 95) == "warn"


def test_cooldown_window():
    now = datetime.now(timezone.utc)
    assert in_cooldown(now - timedelta(minutes=10), 30, now) is True
    assert in_cooldown(now - timedelta(minutes=45), 30, now) is False
    assert in_cooldown(None, 30, now) is False


def test_zabbix_payload_shape():
    raw = encode("switch-01", "settlement.failure.pct", 0.42)
    assert raw.startswith(b"ZBXD\x01")
    length = int.from_bytes(raw[5:13], "little")
    assert length == len(raw) - 13
    body = raw[13:].decode()
    assert '"request": "sender data"' in body
    assert '"host": "switch-01"' in body
