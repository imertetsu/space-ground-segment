"""DB-backed tests for :class:`PostgresAnomalyStore` (live PostgreSQL).

All tests are ``@pytest.mark.postgres`` and depend on the ``pg_dsn`` fixture, which
skips cleanly when ``PDGS_PG_DSN`` is unset. Each test scopes its rows with a unique
id and cleans up after, so runs are repeatable against a shared database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from sgs_shared.anomaly.mappers import (
    anomaly_from_payload_failure,
    anomaly_from_yamcs_alarm,
)
from sgs_shared.anomaly.models import Anomaly, AnomalyState
from sgs_shared.anomaly.repository import (
    AnomalyError,
    PostgresAnomalyStore,
    UnsupportedActionError,
)

pytestmark = pytest.mark.postgres


def _cleanup(dsn: str, *anomaly_ids: str) -> None:
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "DELETE FROM anomalies WHERE anomaly_id = ANY(%s)",
            (list(anomaly_ids),),
        )
        conn.commit()


def _payload_anomaly(anomaly_id_suffix: str, *, state: AnomalyState = AnomalyState.OPEN) -> Anomaly:
    now = datetime(2026, 6, 13, 10, 0, tzinfo=UTC)
    return Anomaly(
        anomaly_id=f"anomaly:payload:{anomaly_id_suffix}",
        origin="payload",
        simulated=False,
        source_ref=anomaly_id_suffix,
        kind="processing_failure",
        severity="ERROR",
        state=state,
        opened_at=now,
        updated_at=now,
    )


def test_record_get_round_trip(pg_dsn: str) -> None:
    store = PostgresAnomalyStore(dsn=pg_dsn)
    a = _payload_anomaly(uuid.uuid4().hex[:8])
    try:
        store.record(a)
        got = store.get(a.anomaly_id)
        assert got == a  # full field-by-field round-trip
    finally:
        _cleanup(pg_dsn, a.anomaly_id)


def test_get_missing_returns_none(pg_dsn: str) -> None:
    store = PostgresAnomalyStore(dsn=pg_dsn)
    assert store.get(f"absent-{uuid.uuid4().hex}") is None


def test_record_is_idempotent_upsert(pg_dsn: str) -> None:
    store = PostgresAnomalyStore(dsn=pg_dsn)
    a = _payload_anomaly(uuid.uuid4().hex[:8])
    try:
        store.record(a)
        store.record(a)  # second record upserts, does not duplicate
        listed = [x for x in store.list() if x.anomaly_id == a.anomaly_id]
        assert len(listed) == 1
    finally:
        _cleanup(pg_dsn, a.anomaly_id)


def test_list_filters_by_origin_and_state(pg_dsn: str) -> None:
    store = PostgresAnomalyStore(dsn=pg_dsn)
    suffix = uuid.uuid4().hex[:8]
    payload = anomaly_from_payload_failure(
        product_id=f"prod-{suffix}",
        opened_at=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
    )
    alarm_ref = f"yamcs://myproject/alarms/SGS/test_{suffix}/1"
    control = anomaly_from_yamcs_alarm(
        alarm_ref=alarm_ref,
        parameter=f"/SGS/test_{suffix}",
        severity="CRITICAL",
        trigger_time=datetime(2026, 6, 13, 9, 31, tzinfo=UTC),
        acknowledged=False,
    )
    try:
        store.record(payload)
        store.record(control)

        payload_ids = {a.anomaly_id for a in store.list(origin="payload")}
        control_ids = {a.anomaly_id for a in store.list(origin="control")}
        assert payload.anomaly_id in payload_ids
        assert payload.anomaly_id not in control_ids
        assert control.anomaly_id in control_ids
        assert control.anomaly_id not in payload_ids

        # state filter
        open_ids = {a.anomaly_id for a in store.list(state=AnomalyState.OPEN)}
        assert payload.anomaly_id in open_ids
        assert control.anomaly_id in open_ids

        # combined filter
        open_control = store.list(origin="control", state=AnomalyState.OPEN)
        assert control.anomaly_id in {a.anomaly_id for a in open_control}
        assert payload.anomaly_id not in {a.anomaly_id for a in open_control}
    finally:
        _cleanup(pg_dsn, payload.anomaly_id, control.anomaly_id)


def test_acknowledge_open_to_acknowledged(pg_dsn: str) -> None:
    store = PostgresAnomalyStore(dsn=pg_dsn)
    a = _payload_anomaly(uuid.uuid4().hex[:8])
    try:
        store.record(a)
        store.acknowledge(a.anomaly_id)
        got = store.get(a.anomaly_id)
        assert got is not None
        assert got.state is AnomalyState.ACKNOWLEDGED
        assert got.updated_at > a.updated_at  # bumped
    finally:
        _cleanup(pg_dsn, a.anomaly_id)


def test_resolve_round_trip(pg_dsn: str) -> None:
    store = PostgresAnomalyStore(dsn=pg_dsn)
    a = _payload_anomaly(uuid.uuid4().hex[:8])
    try:
        store.record(a)
        store.resolve(a.anomaly_id)
        got = store.get(a.anomaly_id)
        assert got is not None
        assert got.state is AnomalyState.RESOLVED
    finally:
        _cleanup(pg_dsn, a.anomaly_id)


def test_illegal_transition_raises(pg_dsn: str) -> None:
    store = PostgresAnomalyStore(dsn=pg_dsn)
    a = _payload_anomaly(uuid.uuid4().hex[:8], state=AnomalyState.RESOLVED)
    try:
        store.record(a)
        # RESOLVED is terminal: acknowledging it is illegal.
        with pytest.raises(AnomalyError):
            store.acknowledge(a.anomaly_id)
    finally:
        _cleanup(pg_dsn, a.anomaly_id)


def test_acknowledge_unknown_raises(pg_dsn: str) -> None:
    store = PostgresAnomalyStore(dsn=pg_dsn)
    with pytest.raises(AnomalyError):
        store.acknowledge(f"absent-{uuid.uuid4().hex}")


def test_start_reprocess_payload(pg_dsn: str) -> None:
    store = PostgresAnomalyStore(dsn=pg_dsn)
    a = _payload_anomaly(uuid.uuid4().hex[:8])
    try:
        store.record(a)
        store.start_reprocess(a.anomaly_id)
        got = store.get(a.anomaly_id)
        assert got is not None
        assert got.state is AnomalyState.REPROCESSING
    finally:
        _cleanup(pg_dsn, a.anomaly_id)


def test_start_reprocess_control_raises_unsupported(pg_dsn: str) -> None:
    store = PostgresAnomalyStore(dsn=pg_dsn)
    suffix = uuid.uuid4().hex[:8]
    alarm_ref = f"yamcs://myproject/alarms/SGS/test_{suffix}/1"
    control = anomaly_from_yamcs_alarm(
        alarm_ref=alarm_ref,
        parameter=f"/SGS/test_{suffix}",
        severity="CRITICAL",
        trigger_time=datetime(2026, 6, 13, 9, 31, tzinfo=UTC),
        acknowledged=False,
    )
    try:
        store.record(control)
        with pytest.raises(UnsupportedActionError):
            store.start_reprocess(control.anomaly_id)
        # state unchanged after the rejected action
        got = store.get(control.anomaly_id)
        assert got is not None
        assert got.state is AnomalyState.OPEN
    finally:
        _cleanup(pg_dsn, control.anomaly_id)


def test_payload_and_control_share_one_store(pg_dsn: str) -> None:
    # Both a payload-mapped failure AND a yamcs-alarm-mapped anomaly persist in the
    # same store with the shared state set, and one list() returns both.
    store = PostgresAnomalyStore(dsn=pg_dsn)
    suffix = uuid.uuid4().hex[:8]
    payload = anomaly_from_payload_failure(
        product_id=f"prod-{suffix}",
        opened_at=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
    )
    alarm_ref = f"yamcs://myproject/alarms/SGS/test_{suffix}/1"
    control = anomaly_from_yamcs_alarm(
        alarm_ref=alarm_ref,
        parameter=f"/SGS/test_{suffix}",
        severity="WARNING",
        trigger_time=datetime(2026, 6, 13, 9, 35, tzinfo=UTC),
        acknowledged=True,
    )
    try:
        store.record(payload)
        store.record(control)

        by_id = {a.anomaly_id: a for a in store.list()}
        assert payload.anomaly_id in by_id
        assert control.anomaly_id in by_id

        # Shared state machine on both halves: acknowledge then resolve the payload,
        # resolve the (already acknowledged) control.
        store.acknowledge(payload.anomaly_id)
        store.resolve(payload.anomaly_id)
        store.resolve(control.anomaly_id)

        got_payload = store.get(payload.anomaly_id)
        got_control = store.get(control.anomaly_id)
        assert got_payload is not None
        assert got_control is not None
        assert got_payload.state is AnomalyState.RESOLVED
        assert got_control.state is AnomalyState.RESOLVED
        assert got_payload.origin == "payload"
        assert got_payload.simulated is False
        assert got_control.origin == "control"
        assert got_control.simulated is True
        assert got_control.origin_label() == "control-simulated"
    finally:
        _cleanup(pg_dsn, payload.anomaly_id, control.anomaly_id)
