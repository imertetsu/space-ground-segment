"""Pure builders that map PRIMITIVE fields into a unified :class:`Anomaly`.

These are how both segments project into the single anomaly record WITHOUT either
side importing the other (the dependency rule forbids importing ``pdgs`` or
``sgs_sim``). Each builder takes only primitives — ids, severity/parameter strings,
timezone-aware UTC datetimes — and returns a frozen :class:`Anomaly`.

Conventions enforced here (data-honesty invariants, SRD §5):

- Payload anomalies: ``origin="payload"``, ``simulated=False`` (REAL EUMETSAT data),
  ``kind="processing_failure"``; ``source_ref`` is the catalogue product id.
- Control anomalies: ``origin="control"``, ``simulated=True`` (SIMULATED telemetry),
  ``kind="ool_alarm"``; ``source_ref`` is the Yamcs ``yamcs://…`` alarm locator and
  is also used as the ``anomaly_id`` (idempotent per alarm). No telemetry VALUE is
  ever copied — only the locator + state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sgs_shared.anomaly.models import Anomaly, AnomalyState

if TYPE_CHECKING:
    from datetime import datetime


def anomaly_id_for_payload(product_id: str) -> str:
    """Derive a stable anomaly id from a payload catalogue product id."""
    return f"anomaly:payload:{product_id}"


def anomaly_from_payload_failure(
    *,
    product_id: str,
    severity: str = "ERROR",
    opened_at: datetime,
    updated_at: datetime | None = None,
    detail: str | None = None,
) -> Anomaly:
    """Build a payload processing-failure anomaly (REAL data) from primitives.

    ``origin="payload"`` / ``simulated=False`` / ``kind="processing_failure"`` /
    ``state=OPEN``. ``source_ref`` is the catalogue product id; ``anomaly_id`` is
    derived from it. ``updated_at`` defaults to ``opened_at``.
    """
    return Anomaly(
        anomaly_id=anomaly_id_for_payload(product_id),
        origin="payload",
        simulated=False,
        source_ref=product_id,
        kind="processing_failure",
        severity=severity,
        state=AnomalyState.OPEN,
        opened_at=opened_at,
        updated_at=updated_at if updated_at is not None else opened_at,
        detail=detail,
    )


def anomaly_from_yamcs_alarm(
    *,
    alarm_ref: str,
    parameter: str,
    severity: str,
    trigger_time: datetime,
    acknowledged: bool,
    updated_at: datetime | None = None,
    detail: str | None = None,
) -> Anomaly:
    """Build a control OOL-alarm anomaly (SIMULATED telemetry) from primitives.

    ``origin="control"`` / ``simulated=True`` / ``kind="ool_alarm"``. The
    ``alarm_ref`` is the Yamcs ``yamcs://…`` alarm locator — used as BOTH the
    ``anomaly_id`` and the ``source_ref`` (the catalogue linkage, same string the
    catalogue ``OOL_ALARM_REF`` row carries). ``state`` is ACKNOWLEDGED if the alarm
    is already acknowledged, else OPEN. ``opened_at`` is the alarm trigger time;
    ``updated_at`` defaults to it. No telemetry VALUE is copied — ``parameter`` is the
    qualified name only.
    """
    state = AnomalyState.ACKNOWLEDGED if acknowledged else AnomalyState.OPEN
    return Anomaly(
        anomaly_id=alarm_ref,
        origin="control",
        simulated=True,
        source_ref=alarm_ref,
        kind="ool_alarm",
        severity=severity,
        state=state,
        opened_at=trigger_time,
        updated_at=updated_at if updated_at is not None else trigger_time,
        detail=detail,
    )
