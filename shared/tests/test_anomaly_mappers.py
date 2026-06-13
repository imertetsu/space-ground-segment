"""Unit tests (no DB) for the primitive-field anomaly mappers."""

from __future__ import annotations

from datetime import UTC, datetime

from sgs_shared.anomaly.mappers import (
    anomaly_from_payload_failure,
    anomaly_from_yamcs_alarm,
    anomaly_id_for_payload,
)
from sgs_shared.anomaly.models import AnomalyState


def test_payload_failure_mapper_fields() -> None:
    opened = datetime(2026, 6, 13, 10, 0, tzinfo=UTC)
    a = anomaly_from_payload_failure(product_id="SST_L2_DERIVED/p-1", opened_at=opened)
    assert a.origin == "payload"
    assert a.simulated is False
    assert a.kind == "processing_failure"
    assert a.severity == "ERROR"  # default
    assert a.state is AnomalyState.OPEN
    assert a.source_ref == "SST_L2_DERIVED/p-1"
    assert a.anomaly_id == anomaly_id_for_payload("SST_L2_DERIVED/p-1")
    assert a.anomaly_id == "anomaly:payload:SST_L2_DERIVED/p-1"
    # updated_at defaults to opened_at
    assert a.updated_at == opened


def test_payload_failure_mapper_overrides() -> None:
    opened = datetime(2026, 6, 13, 10, 0, tzinfo=UTC)
    updated = datetime(2026, 6, 13, 11, 0, tzinfo=UTC)
    a = anomaly_from_payload_failure(
        product_id="p-2",
        severity="CRITICAL",
        opened_at=opened,
        updated_at=updated,
        detail="L1 inputs missing",
    )
    assert a.severity == "CRITICAL"
    assert a.updated_at == updated
    assert a.detail == "L1 inputs missing"


def test_yamcs_alarm_mapper_open() -> None:
    ref = "yamcs://myproject/alarms/SGS/obc_temp/1"
    trigger = datetime(2026, 6, 13, 9, 31, tzinfo=UTC)
    a = anomaly_from_yamcs_alarm(
        alarm_ref=ref,
        parameter="/SGS/obc_temp",
        severity="CRITICAL",
        trigger_time=trigger,
        acknowledged=False,
    )
    assert a.origin == "control"
    assert a.simulated is True
    assert a.kind == "ool_alarm"
    assert a.severity == "CRITICAL"
    assert a.state is AnomalyState.OPEN
    assert a.anomaly_id == ref
    assert a.source_ref == ref  # catalogue linkage == the yamcs:// locator
    assert a.opened_at == trigger
    assert a.updated_at == trigger


def test_yamcs_alarm_mapper_acknowledged() -> None:
    ref = "yamcs://myproject/alarms/SGS/battery_voltage/2"
    trigger = datetime(2026, 6, 13, 9, 35, tzinfo=UTC)
    a = anomaly_from_yamcs_alarm(
        alarm_ref=ref,
        parameter="/SGS/battery_voltage",
        severity="WARNING",
        trigger_time=trigger,
        acknowledged=True,
    )
    assert a.state is AnomalyState.ACKNOWLEDGED
