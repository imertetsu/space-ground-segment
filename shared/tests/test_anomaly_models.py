"""Unit tests (no DB) for the shared anomaly model + state machine."""

from __future__ import annotations

from datetime import UTC, datetime

from sgs_shared.anomaly.models import Anomaly, AnomalyState, can_transition


def _anomaly(*, origin: str, simulated: bool, state: AnomalyState) -> Anomaly:
    now = datetime(2026, 6, 13, 10, 0, tzinfo=UTC)
    return Anomaly(
        anomaly_id="a-1",
        origin=origin,  # type: ignore[arg-type]
        simulated=simulated,
        source_ref="ref-1",
        kind="processing_failure" if origin == "payload" else "ool_alarm",
        severity="ERROR",
        state=state,
        opened_at=now,
        updated_at=now,
    )


def test_construct_payload_anomaly() -> None:
    a = _anomaly(origin="payload", simulated=False, state=AnomalyState.OPEN)
    assert a.origin == "payload"
    assert a.simulated is False
    assert a.kind == "processing_failure"
    assert a.state is AnomalyState.OPEN
    assert a.opened_at.tzinfo is not None  # tz-aware UTC


def test_construct_control_anomaly() -> None:
    a = _anomaly(origin="control", simulated=True, state=AnomalyState.OPEN)
    assert a.origin == "control"
    assert a.simulated is True
    assert a.kind == "ool_alarm"


def test_origin_label_payload() -> None:
    a = _anomaly(origin="payload", simulated=False, state=AnomalyState.OPEN)
    assert a.origin_label() == "payload"


def test_origin_label_control_simulated() -> None:
    a = _anomaly(origin="control", simulated=True, state=AnomalyState.OPEN)
    assert a.origin_label() == "control-simulated"


def test_origin_label_simulated_payload_edge() -> None:
    # A (hypothetical) simulated payload row still tags as simulated.
    a = _anomaly(origin="payload", simulated=True, state=AnomalyState.OPEN)
    assert a.origin_label() == "payload-simulated"


def test_state_values_are_strings() -> None:
    assert AnomalyState.OPEN.value == "OPEN"
    assert AnomalyState.ACKNOWLEDGED.value == "ACKNOWLEDGED"
    assert AnomalyState.REPROCESSING.value == "REPROCESSING"
    assert AnomalyState.RESOLVED.value == "RESOLVED"


def test_can_transition_legal_matrix() -> None:
    s = AnomalyState
    assert can_transition(s.OPEN, s.ACKNOWLEDGED)
    assert can_transition(s.OPEN, s.REPROCESSING)
    assert can_transition(s.OPEN, s.RESOLVED)
    assert can_transition(s.ACKNOWLEDGED, s.REPROCESSING)
    assert can_transition(s.ACKNOWLEDGED, s.RESOLVED)
    assert can_transition(s.REPROCESSING, s.RESOLVED)
    assert can_transition(s.REPROCESSING, s.OPEN)


def test_can_transition_illegal_matrix() -> None:
    s = AnomalyState
    # No transition out of the terminal state.
    assert not can_transition(s.RESOLVED, s.OPEN)
    assert not can_transition(s.RESOLVED, s.ACKNOWLEDGED)
    assert not can_transition(s.RESOLVED, s.REPROCESSING)
    assert not can_transition(s.RESOLVED, s.RESOLVED)
    # ACKNOWLEDGED cannot go back to OPEN.
    assert not can_transition(s.ACKNOWLEDGED, s.OPEN)
    # OPEN -> OPEN is a no-op, not a legal transition.
    assert not can_transition(s.OPEN, s.OPEN)
