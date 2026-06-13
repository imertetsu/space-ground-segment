"""Unit tests (no DB) for the now-LIVE ``sgs-ops`` operator CLI.

The ``SGS_SHARED`` dark flag is GONE (Epic 3 closed — the surface is live by
default). These tests stay hermetic: with ``PDGS_PG_DSN`` unset, the DB-backed
commands construct ``PostgresCatalogue(dsn=None)`` / ``PostgresAnomalyStore(dsn=None)``
which raise immediately, so the command returns 1 and prints a "no PostgreSQL DSN"
error to stderr — no live Postgres is ever contacted. Arg-parsing tests assert the
new ``sync-payload`` subcommand requires ``--sqlite``.
"""

from __future__ import annotations

import pytest

from sgs_shared.cli.main import main


def _assert_no_dsn_error(rc: int, captured: pytest.CaptureFixture[str]) -> None:
    """A DB-backed command with no DSN returns 1 and reports the missing DSN on stderr."""
    assert rc == 1
    err = captured.readouterr().err
    assert "sgs-ops:" in err
    assert "no PostgreSQL DSN" in err


def test_status_without_dsn_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PDGS_PG_DSN", raising=False)
    _assert_no_dsn_error(main(["status"]), capsys)


def test_overview_without_dsn_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PDGS_PG_DSN", raising=False)
    _assert_no_dsn_error(main(["overview"]), capsys)


def test_anomalies_without_dsn_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PDGS_PG_DSN", raising=False)
    _assert_no_dsn_error(main(["anomalies"]), capsys)


def test_seed_demo_without_dsn_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PDGS_PG_DSN", raising=False)
    _assert_no_dsn_error(main(["seed-demo"]), capsys)


def test_bridge_without_dsn_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PDGS_PG_DSN", raising=False)
    _assert_no_dsn_error(main(["bridge"]), capsys)


def test_ack_without_dsn_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PDGS_PG_DSN", raising=False)
    _assert_no_dsn_error(main(["ack", "anomaly:payload:p-1"]), capsys)


def test_resolve_without_dsn_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PDGS_PG_DSN", raising=False)
    _assert_no_dsn_error(main(["resolve", "anomaly:payload:p-1"]), capsys)


def test_sync_payload_without_dsn_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # --sqlite is supplied so argparse passes; the missing DSN short-circuits first.
    monkeypatch.delenv("PDGS_PG_DSN", raising=False)
    _assert_no_dsn_error(main(["sync-payload", "--sqlite", "nonexistent.sqlite"]), capsys)


def test_sync_payload_requires_sqlite_flag() -> None:
    # argparse exits with code 2 when the required --sqlite is missing.
    with pytest.raises(SystemExit) as excinfo:
        main(["sync-payload"])
    assert excinfo.value.code == 2


@pytest.mark.postgres
def test_overview_prints_three_sections(pg_dsn: str, capsys: pytest.CaptureFixture[str]) -> None:
    """Seed one payload + one control entry + one anomaly; overview shows all sections."""
    import uuid
    from datetime import UTC, datetime

    import psycopg

    from sgs_shared.anomaly.mappers import anomaly_from_yamcs_alarm
    from sgs_shared.anomaly.repository import PostgresAnomalyStore
    from sgs_shared.catalogue.mappers import (
        entry_from_control_alarm,
        entry_from_payload_product,
    )
    from sgs_shared.catalogue.repository import PostgresCatalogue

    cat = PostgresCatalogue(dsn=pg_dsn)
    store = PostgresAnomalyStore(dsn=pg_dsn)
    prefix = f"test-{uuid.uuid4().hex[:8]}"
    payload_id = f"{prefix}-payload"
    alarm_ref = f"yamcs://myproject/alarms/SGS/{prefix}/1"

    payload = entry_from_payload_product(
        product_id=payload_id,
        product_type="SST_L2_DERIVED",
        status="VALIDATED",
        sensing_time=datetime(2026, 6, 13, 9, 30, tzinfo=UTC),
        ingest_time=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
        reference=f"SST_L2_DERIVED/{payload_id}.nc",
        processor_version="pdgs-sst-1.0",
        input_product_ids=("L1-0001",),
        run_time=datetime(2026, 6, 13, 9, 45, tzinfo=UTC),
    )
    control = entry_from_control_alarm(
        alarm_id=alarm_ref,
        parameter="/SGS/obc_temp",
        severity="CRITICAL",
        status="TRIGGERED",
        trigger_time=datetime(2026, 6, 13, 9, 31, tzinfo=UTC),
        ingest_time=datetime(2026, 6, 13, 10, 1, tzinfo=UTC),
        reference=alarm_ref,
        detail="SIMULATED alarm; severity=CRITICAL",
    )
    anomaly = anomaly_from_yamcs_alarm(
        alarm_ref=alarm_ref,
        parameter="/SGS/obc_temp",
        severity="CRITICAL",
        trigger_time=datetime(2026, 6, 13, 9, 31, tzinfo=UTC),
        acknowledged=False,
        detail="SIMULATED OOL alarm",
    )

    try:
        cat.register(payload)
        cat.register(control)
        store.record(anomaly)

        # Point at an unreachable Yamcs so the live-state poll degrades gracefully.
        rc = main(["overview", "--yamcs-url", "http://127.0.0.1:1"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "== Current state ==" in out
        assert "== Anomalies ==" in out
        assert "== Last results ==" in out
        assert "control-simulated" in out  # control anomaly row is labelled simulated
        assert payload_id in out
    finally:
        with psycopg.connect(pg_dsn) as conn:
            conn.execute(
                "DELETE FROM catalogue_entries WHERE entry_id = ANY(%s)",
                ([payload_id, alarm_ref],),
            )
            conn.execute("DELETE FROM anomalies WHERE anomaly_id = %s", (alarm_ref,))
            conn.commit()
