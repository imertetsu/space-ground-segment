"""Pure builders that map PRIMITIVE fields into a unified :class:`CatalogueEntry`.

These are how both segments project into the single catalogue row WITHOUT either
side importing the other (the dependency rule forbids importing ``pdgs`` or
``sgs_sim``). Each builder takes only primitives — ids, type/status strings,
timezone-aware UTC datetimes — and returns a frozen :class:`CatalogueEntry` with a
:class:`Provenance` envelope filled in.

Conventions enforced here (data-honesty invariants, SRD §5):

- Payload rows: ``origin="payload"``, ``simulated=False`` (REAL EUMETSAT data).
- Control rows: ``origin="control"``, ``simulated=True`` (SIMULATED telemetry); they
  carry a Yamcs **locator** ``reference`` and NEVER a copy of a telemetry value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sgs_shared.catalogue.models import CatalogueEntry, Provenance

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime


def entry_from_payload_product(
    *,
    product_id: str,
    product_type: str,
    status: str,
    sensing_time: datetime | None,
    ingest_time: datetime,
    reference: str,
    processor_version: str | None,
    input_product_ids: Iterable[str] = (),
    run_time: datetime | None,
    detail: str | None = None,
) -> CatalogueEntry:
    """Build a payload ``CatalogueEntry`` (REAL data) from primitive product fields.

    ``origin="payload"`` / ``simulated=False``. The provenance envelope records the
    originating processor version, the upstream input product ids, and the run time.
    """
    return CatalogueEntry(
        entry_id=product_id,
        origin="payload",
        simulated=False,
        product_type=product_type,
        status=status,
        sensing_time=sensing_time,
        ingest_time=ingest_time,
        reference=reference,
        provenance=Provenance(
            source_version=processor_version,
            source_refs=tuple(input_product_ids),
            run_time=run_time,
        ),
        detail=detail,
    )


def entry_from_control_alarm(
    *,
    alarm_id: str,
    parameter: str,
    severity: str,
    status: str,
    trigger_time: datetime | None,
    ingest_time: datetime,
    mdb_version: str = "yamcs-mdb-SGS",
    reference: str,
    detail: str | None = None,
) -> CatalogueEntry:
    """Build a control out-of-limits alarm REFERENCE (SIMULATED telemetry).

    ``origin="control"`` / ``simulated=True`` / ``product_type="OOL_ALARM_REF"``. The
    ``reference`` is a Yamcs alarm locator; ``severity`` is kept for callers to fold
    into ``detail`` if desired — no telemetry VALUE is ever copied here. The trigger
    time is recorded as both the sensing time and the provenance run time.
    """
    return CatalogueEntry(
        entry_id=alarm_id,
        origin="control",
        simulated=True,
        product_type="OOL_ALARM_REF",
        status=status,
        sensing_time=trigger_time,
        ingest_time=ingest_time,
        reference=reference,
        provenance=Provenance(
            source_version=mdb_version,
            source_refs=(parameter,),
            run_time=trigger_time,
        ),
        detail=detail,
    )


def entry_from_control_archive_ref(
    *,
    parameter: str,
    status: str,
    ingest_time: datetime,
    mdb_version: str = "yamcs-mdb-SGS",
    reference: str,
    run_time: datetime | None = None,
    detail: str | None = None,
) -> CatalogueEntry:
    """Build a control telemetry-archive REFERENCE (SIMULATED telemetry).

    ``origin="control"`` / ``simulated=True`` / ``product_type="TM_ARCHIVE_REF"``. The
    ``reference`` is a Yamcs parameter locator; the entry id is derived from it so the
    row is idempotent per parameter. No telemetry VALUE is ever copied.
    """
    return CatalogueEntry(
        entry_id=reference,
        origin="control",
        simulated=True,
        product_type="TM_ARCHIVE_REF",
        status=status,
        sensing_time=None,
        ingest_time=ingest_time,
        reference=reference,
        provenance=Provenance(
            source_version=mdb_version,
            source_refs=(parameter,),
            run_time=run_time,
        ),
        detail=detail,
    )
