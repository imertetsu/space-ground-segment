"""The unified anomaly record + its state machine (Epic 3, Phase 2).

ONE :class:`Anomaly` dataclass and ONE :class:`AnomalyState` enum cover both
segments: a payload processing failure (the ``FAILED`` dead-letter) and a control
out-of-limit (OOL) alarm. The shared state machine is:

    OPEN ──► ACKNOWLEDGED ──► REPROCESSING ──► RESOLVED (terminal)
      │            │               │
      └──► REPROCESSING            └──► OPEN (reprocess failed, re-triage)
      └──► RESOLVED                └──► RESOLVED

``REPROCESSING`` is payload-only by policy (a control anomaly cannot be
reprocessed); that rule is enforced in the repository, not here — this module only
declares which *transitions* are legal.

The ``origin`` literal is imported from the FROZEN catalogue model so anomalies and
catalogue rows agree on what ``payload`` / ``control`` mean. All datetimes are
timezone-aware UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

from sgs_shared.catalogue.models import Origin

# What an anomaly is about. ``processing_failure`` = a payload product in FAILED (the
# dead-letter); ``ool_alarm`` = a control out-of-limit alarm from Yamcs (SIMULATED).
AnomalyKind = Literal["processing_failure", "ool_alarm"]


class AnomalyState(StrEnum):
    """Lifecycle state of an anomaly (shared by both segments).

    A :class:`enum.StrEnum` so the value persists/round-trips as a plain ``TEXT``
    column and reads cleanly in operator output. ``RESOLVED`` is terminal.
    """

    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    REPROCESSING = "REPROCESSING"
    RESOLVED = "RESOLVED"


# Legal state transitions. RESOLVED is terminal (empty target set). REPROCESSING may
# fall back to OPEN (reprocess failed → re-triage) or advance to RESOLVED.
_ALLOWED_TRANSITIONS: dict[AnomalyState, frozenset[AnomalyState]] = {
    AnomalyState.OPEN: frozenset(
        {AnomalyState.ACKNOWLEDGED, AnomalyState.REPROCESSING, AnomalyState.RESOLVED}
    ),
    AnomalyState.ACKNOWLEDGED: frozenset({AnomalyState.REPROCESSING, AnomalyState.RESOLVED}),
    AnomalyState.REPROCESSING: frozenset({AnomalyState.RESOLVED, AnomalyState.OPEN}),
    AnomalyState.RESOLVED: frozenset(),
}


def can_transition(frm: AnomalyState, to: AnomalyState) -> bool:
    """Return ``True`` iff moving from state ``frm`` to state ``to`` is legal."""
    return to in _ALLOWED_TRANSITIONS[frm]


@dataclass(frozen=True)
class Anomaly:
    """A unified anomaly — one payload processing failure OR one control OOL alarm.

    Fields:

    - ``anomaly_id``: stable unique id. For control this IS the ``yamcs://`` alarm
      locator; for payload it is derived from the product id
      (``anomaly:payload:<product_id>``).
    - ``origin``: ``"payload"`` (REAL data) or ``"control"`` (SIMULATED telemetry).
    - ``simulated``: ``True`` for control alarms, ``False`` for payload failures.
    - ``source_ref``: the catalogue linkage — for control the ``yamcs://`` alarm
      locator (the same string the catalogue ``OOL_ALARM_REF`` row uses); for payload
      the catalogue product id.
    - ``kind``: :data:`AnomalyKind`.
    - ``severity``: free-text severity label (e.g. ``CRITICAL``/``WARNING`` for an
      alarm, ``ERROR`` for a payload failure).
    - ``state``: current :class:`AnomalyState`.
    - ``opened_at`` / ``updated_at``: timezone-aware UTC timestamps.
    - ``detail``: free-text note (optional).

    Frozen: state changes produce a new record (the repository rebuilds the row).
    """

    anomaly_id: str
    origin: Origin
    simulated: bool
    source_ref: str
    kind: AnomalyKind
    severity: str
    state: AnomalyState
    opened_at: datetime
    updated_at: datetime
    detail: str | None = None

    def origin_label(self) -> str:
        """Operator-facing origin label, tagging simulated rows.

        ``payload`` -> ``"payload"``; ``control`` (simulated) -> ``"control-simulated"``
        (or ``"{origin}-simulated"`` for any simulated row). Mirrors
        :meth:`sgs_shared.catalogue.models.CatalogueEntry.origin_label`.
        """
        if self.origin == "control" and self.simulated:
            return "control-simulated"
        if self.simulated:
            return f"{self.origin}-simulated"
        return self.origin
