"""Unified catalogue record — the FROZEN shared schema (Epic 3, Phase 1).

:class:`CatalogueEntry` is the single row type the shared catalogue stores: one
payload product OR one control reference, behind one query surface. **Frozen at
Phase 1** — changing the field set or semantics here is a breaking change for the
operator surface (Phase 4), the anomaly model (Phase 2, which links via
``source_ref``) and the time service (Phase 3, which stamps the UTC fields).

The type is defined HERE, independently: the dependency rule forbids importing
``pdgs``, so the field names are *aligned* with the payload ``Product`` /
``Provenance`` shape (``product_type``, ``status``, sensing/ingest times,
provenance envelope) for a clean mapping, but this module imports neither segment.

Two fields are load-bearing for data honesty (SRD §5) and MUST never be dropped by
unification:

- ``origin`` — ``"payload"`` (REAL EUMETSAT data) or ``"control"`` (SIMULATED
  telemetry references).
- ``simulated`` — ``True`` for control telemetry, ``False`` for payload products.

Every row also carries one **provenance envelope** (:class:`Provenance`): the same
shape for both segments (source version, source refs, run time), so a single query
surface can report where any row came from. All datetimes are timezone-aware UTC.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# Where a row came from. ``payload`` = PDGS EO products (REAL data); ``control`` =
# FOS telemetry/anomaly references (SIMULATED telemetry, always labelled).
Origin = Literal["payload", "control"]


@dataclass(frozen=True)
class Provenance:
    """Unified provenance envelope — one shape across both segments (FROZEN).

    The same three fields describe the origin of a payload product and a control
    reference, so the catalogue can report provenance uniformly:

    - ``source_version``: the originating processor (payload, e.g. ``pdgs-sst-1.0``)
      or MDB/instance (control, e.g. ``yamcs-mdb-SGS``) version. ``None`` if unknown.
    - ``source_refs``: the upstream identifiers a row derives from — payload input
      product ids (the payload ``Provenance.input_product_ids``) or control source
      packet / parameter references (e.g. a Yamcs parameter qualified name). A tuple
      (hashable, immutable); empty when the row is itself a source.
    - ``run_time``: the processing/observation run time (payload run timestamp;
      control archive-slice or alarm-trigger time), UTC. ``None`` if not applicable.

    Frozen: provenance describes a completed write and must not mutate afterwards.
    Distinct from :class:`CatalogueEntry.ingest_time`, which records when the row was
    written into the *shared* catalogue (a catalogue fact, not source provenance).
    """

    source_version: str | None
    source_refs: tuple[str, ...]
    run_time: datetime | None


@dataclass(frozen=True)
class CatalogueEntry:
    """A unified catalogue row — one payload product OR one control reference.

    FROZEN Phase-1 schema. Fields:

    - ``entry_id``: stable unique row id (payload product id or a control reference
      id).
    - ``origin``: ``"payload"`` or ``"control"`` — never erased by unification.
    - ``simulated``: ``True`` for control (SIMULATED telemetry), ``False`` for
      payload (REAL data). Mandatory; carried on every row.
    - ``product_type``: payload product type (e.g. ``SST_L2_DERIVED``) or the control
      reference kind (e.g. ``OOL_ALARM_REF``, ``TM_ARCHIVE_REF``).
    - ``status``: lifecycle/state label (payload ``ProductStatus`` value or control
      state, e.g. ``TRIGGERED``).
    - ``sensing_time``: observation/acquisition time (UTC) where known, else ``None``
      (a control parameter snapshot may have no sensing window).
    - ``ingest_time``: when the row was recorded into the *shared* catalogue (UTC).
    - ``reference``: the locator — a payload product id / local path, OR a control
      Yamcs locator (e.g. ``yamcs://myproject/parameters/SGS/obc_temp`` or an alarm
      reference). A **reference**, never a copy of telemetry.
    - ``provenance``: the unified :class:`Provenance` envelope (mandatory).
    - ``detail``: free-text note (optional).
    """

    entry_id: str
    origin: Origin
    simulated: bool
    product_type: str
    status: str
    sensing_time: datetime | None
    ingest_time: datetime
    reference: str
    provenance: Provenance
    detail: str | None = None

    def origin_label(self) -> str:
        """Operator-facing origin label, tagging control rows as SIMULATED.

        ``payload`` -> ``"payload"``; ``control`` -> ``"control-simulated"`` (or
        ``"{origin}-simulated"`` for any simulated row). Keeps the real-vs-simulated
        distinction explicit in operator output.
        """
        if self.origin == "control" and self.simulated:
            return "control-simulated"
        if self.simulated:
            return f"{self.origin}-simulated"
        return self.origin
