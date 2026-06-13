"""Shared anomaly model — ONE record + ONE state machine for BOTH segments.

A single :class:`~sgs_shared.anomaly.models.Anomaly` record covers both halves of
the ground segment:

- payload **processing failures** — a catalogue product in the ``FAILED`` state (the
  payload dead-letter), ``kind="processing_failure"``, REAL data; and
- control **out-of-limit (OOL) alarms** from Yamcs, ``kind="ool_alarm"``, SIMULATED
  telemetry — always labelled.

Both share one :class:`~sgs_shared.anomaly.models.AnomalyState` machine and one set
of operator actions: *acknowledge* and *resolve* apply to both halves; *reprocess*
(``start_reprocess``) is payload-only — a control anomaly cannot be reprocessed.

Each anomaly links to the frozen shared catalogue (Phase 1) via ``source_ref``: for
control this is the ``yamcs://…`` alarm locator (the same string the catalogue
``OOL_ALARM_REF`` row carries); for payload it is the catalogue product id.

This package imports NEITHER ``pdgs`` NOR ``sgs_sim`` (the dependency rule); it
reuses the catalogue's :data:`~sgs_shared.catalogue.models.Origin` literal only.
"""

from __future__ import annotations

from sgs_shared.anomaly.models import (
    Anomaly,
    AnomalyKind,
    AnomalyState,
    can_transition,
)
from sgs_shared.anomaly.repository import (
    AnomalyError,
    AnomalyStore,
    PostgresAnomalyStore,
    UnsupportedActionError,
)

__all__ = [
    "Anomaly",
    "AnomalyError",
    "AnomalyKind",
    "AnomalyState",
    "AnomalyStore",
    "PostgresAnomalyStore",
    "UnsupportedActionError",
    "can_transition",
]
