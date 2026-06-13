"""Unified catalogue record — the shared superset across both segments.

:class:`CatalogueEntry` is the single row type the shared catalogue stores. It is
the unified superset that Phase 1 maps the payload ``Product``/``Provenance`` shape
**and** control references into. It is defined HERE, independently: the dependency
rule forbids importing ``pdgs``, so the field names are *aligned* with the payload
shape (``product_type``, ``status``, ``source_version``, sensing/ingest times) for a
clean Phase-1 mapping, but the type does not import the payload's ``Product``.

``origin`` and ``simulated`` are MANDATORY and load-bearing: payload data is REAL,
control telemetry is SIMULATED, and the unified surface must keep that distinction
on every row (SRD §5 data-honesty). All datetimes are timezone-aware UTC.

The dataclass is ``frozen`` so a catalogued entry is an immutable record of a write.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# Where a row came from. ``payload`` = PDGS EO products (REAL data); ``control`` =
# FOS telemetry/anomaly references (SIMULATED telemetry, always labelled).
Origin = Literal["payload", "control"]


@dataclass(frozen=True)
class CatalogueEntry:
    """A unified catalogue row — one payload product OR one control reference.

    Fields (aligned with the payload ``Product`` shape where sensible):

    - ``entry_id``: stable unique id for the row (payload product id or a control
      reference id).
    - ``origin``: ``"payload"`` or ``"control"`` — never erased by unification.
    - ``simulated``: ``True`` for control (SIMULATED telemetry), ``False`` for
      payload (REAL data). Mandatory; carried on every row.
    - ``product_type``: payload product type (e.g. ``SST_L2_DERIVED``) or the
      control reference kind (e.g. ``OOL_ALARM_REF``, ``TM_ARCHIVE_REF``).
    - ``status``: lifecycle/state label (payload status or control state).
    - ``sensing_time``: observation/acquisition time (UTC) where known, else
      ``None`` (a control parameter snapshot may have no sensing window).
    - ``ingest_time``: when the row was recorded into the shared catalogue (UTC).
    - ``source_version``: originating processor / MDB version, if known.
    - ``reference``: the locator — a payload product id / local path, OR a control
      Yamcs locator (e.g. ``/SGS/obc_temp`` or a TM-archive reference).
    - ``detail``: free-text note (optional).
    """

    entry_id: str
    origin: Origin
    simulated: bool
    product_type: str
    status: str
    sensing_time: datetime | None
    ingest_time: datetime
    source_version: str | None
    reference: str
    detail: str | None = None

    def origin_label(self) -> str:
        """Operator-facing origin label, tagging control rows as SIMULATED.

        ``payload`` -> ``"payload"``; ``control`` -> ``"control-simulated"`` (or
        ``"control"`` only if a control row were ever real, which it is not today).
        Keeps the real-vs-simulated distinction explicit in operator output.
        """
        if self.origin == "control" and self.simulated:
            return "control-simulated"
        if self.simulated:
            return f"{self.origin}-simulated"
        return self.origin
