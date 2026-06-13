"""Phase-0 demo seed — one payload entry + one control entry.

``seed_demo`` registers exactly two rows so the cross-segment slice can be proven:
ONE payload product (origin=payload, simulated=False — REAL data) and ONE control
reference (origin=control, simulated=True — SIMULATED telemetry). Fixed entry ids
make it idempotent (``register`` upserts on ``entry_id``).

This is a demo seed, not a production ingest path. Phase 1 replaces it with the real
payload->catalogue mapping and the read-only Yamcs-REST control bridge.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sgs_shared.catalogue.models import CatalogueEntry

if TYPE_CHECKING:
    from sgs_shared.catalogue.repository import Catalogue

# Fixed ids => idempotent re-seeding (upsert on entry_id).
PAYLOAD_ENTRY_ID = "demo-payload-SST-0001"
CONTROL_ENTRY_ID = "demo-control-obc_temp-0001"


def seed_demo(catalogue: Catalogue) -> tuple[CatalogueEntry, CatalogueEntry]:
    """Register one payload entry and one control entry; return them.

    Idempotent: fixed ``entry_id``s mean repeated calls upsert the same two rows.
    Returns ``(payload_entry, control_entry)``.
    """
    now = datetime.now(tz=UTC)

    payload_entry = CatalogueEntry(
        entry_id=PAYLOAD_ENTRY_ID,
        origin="payload",
        simulated=False,
        product_type="SST_L2_DERIVED",
        status="VALIDATED",
        sensing_time=datetime(2026, 6, 13, 9, 30, 0, tzinfo=UTC),
        ingest_time=now,
        source_version="pdgs-sst-1.0",
        reference="SST_L2_DERIVED/demo-payload-SST-0001.nc",
        detail="Demo payload product (REAL-data shape; Phase-0 seed).",
    )

    control_entry = CatalogueEntry(
        entry_id=CONTROL_ENTRY_ID,
        origin="control",
        simulated=True,
        product_type="OOL_ALARM_REF",
        status="OPEN",
        sensing_time=datetime(2026, 6, 13, 9, 31, 0, tzinfo=UTC),
        ingest_time=now,
        source_version="yamcs-mdb-SGS",
        reference="/SGS/obc_temp",
        detail="Demo control reference (SIMULATED telemetry; Yamcs locator).",
    )

    catalogue.register(payload_entry)
    catalogue.register(control_entry)
    return payload_entry, control_entry
