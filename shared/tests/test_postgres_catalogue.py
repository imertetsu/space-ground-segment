"""DB-backed tests for :class:`PostgresCatalogue` (live PostgreSQL).

All tests are ``@pytest.mark.postgres`` and depend on the ``pg_dsn`` fixture, which
skips cleanly when ``PDGS_PG_DSN`` is unset. The main session runs these against the
live DB. Each test scopes its rows with a unique id prefix and cleans up after, so
runs are repeatable against a shared database.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import psycopg
import pytest

from sgs_shared.catalogue.mappers import entry_from_payload_product
from sgs_shared.catalogue.models import CatalogueEntry, Provenance
from sgs_shared.catalogue.repository import CatalogueError, PostgresCatalogue
from sgs_shared.catalogue.seed import (
    CONTROL_ENTRY_ID,
    PAYLOAD_ENTRY_ID,
    seed_demo,
)
from sgs_shared.control_bridge.yamcs import YamcsControlBridge, record_references

pytestmark = pytest.mark.postgres


def _cleanup(dsn: str, *entry_ids: str) -> None:
    with psycopg.connect(dsn) as conn:
        conn.execute(
            "DELETE FROM catalogue_entries WHERE entry_id = ANY(%s)",
            (list(entry_ids),),
        )
        conn.commit()


def test_register_get_list_round_trip(pg_dsn: str) -> None:
    cat = PostgresCatalogue(dsn=pg_dsn)
    prefix = f"test-{uuid.uuid4().hex[:8]}"
    payload_id = f"{prefix}-payload"
    control_id = f"{prefix}-control"
    try:
        payload = CatalogueEntry(
            entry_id=payload_id,
            origin="payload",
            simulated=False,
            product_type="SST_L2_DERIVED",
            status="VALIDATED",
            sensing_time=datetime(2026, 6, 13, 9, 30, tzinfo=UTC),
            ingest_time=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
            reference=f"SST_L2_DERIVED/{payload_id}.nc",
            provenance=Provenance(
                source_version="pdgs-sst-1.0",
                source_refs=("L1-a", "L1-b"),
                run_time=datetime(2026, 6, 13, 9, 45, tzinfo=UTC),
            ),
            detail="round-trip payload",
        )
        control = CatalogueEntry(
            entry_id=control_id,
            origin="control",
            simulated=True,
            product_type="OOL_ALARM_REF",
            status="OPEN",
            sensing_time=None,
            ingest_time=datetime(2026, 6, 13, 10, 1, tzinfo=UTC),
            reference="yamcs://myproject/alarms/SGS/obc_temp/1",
            provenance=Provenance(
                source_version="yamcs-mdb-SGS",
                source_refs=("/SGS/obc_temp",),
                run_time=datetime(2026, 6, 13, 10, 1, tzinfo=UTC),
            ),
            detail="round-trip control (SIMULATED)",
        )
        cat.register(payload)
        cat.register(control)

        got = cat.get(payload_id)
        assert got == payload  # full field-by-field round-trip
        assert cat.get(control_id) == control

        listed_ids = {e.entry_id for e in cat.list()}
        assert {payload_id, control_id} <= listed_ids

        # control row carries sensing_time=None through the DB
        got_control = cat.get(control_id)
        assert got_control is not None
        assert got_control.sensing_time is None
        assert got_control.origin_label() == "control-simulated"
    finally:
        _cleanup(pg_dsn, payload_id, control_id)


def test_get_missing_returns_none(pg_dsn: str) -> None:
    cat = PostgresCatalogue(dsn=pg_dsn)
    assert cat.get(f"absent-{uuid.uuid4().hex}") is None


def test_register_is_idempotent_upsert(pg_dsn: str) -> None:
    cat = PostgresCatalogue(dsn=pg_dsn)
    entry_id = f"test-{uuid.uuid4().hex[:8]}-upsert"
    try:
        prov = Provenance(
            source_version="pdgs-sst-1.0",
            source_refs=("L1-x",),
            run_time=datetime(2026, 6, 13, 9, 45, tzinfo=UTC),
        )
        base = CatalogueEntry(
            entry_id=entry_id,
            origin="payload",
            simulated=False,
            product_type="SST_L2_DERIVED",
            status="REGISTERED",
            sensing_time=None,
            ingest_time=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
            reference=f"ref/{entry_id}",
            provenance=prov,
        )
        cat.register(base)
        cat.register(
            CatalogueEntry(
                entry_id=entry_id,
                origin="payload",
                simulated=False,
                product_type="SST_L2_DERIVED",
                status="VALIDATED",  # changed
                sensing_time=None,
                ingest_time=base.ingest_time,
                reference=base.reference,
                provenance=prov,
            )
        )
        got = cat.get(entry_id)
        assert got is not None
        assert got.status == "VALIDATED"
        assert sum(1 for e in cat.list() if e.entry_id == entry_id) == 1
    finally:
        _cleanup(pg_dsn, entry_id)


def test_seed_demo_lists_one_payload_and_one_control(pg_dsn: str) -> None:
    cat = PostgresCatalogue(dsn=pg_dsn)
    try:
        payload_entry, control_entry = seed_demo(cat)

        assert payload_entry.origin == "payload"
        assert payload_entry.simulated is False
        assert control_entry.origin == "control"
        assert control_entry.simulated is True

        by_id = {e.entry_id: e for e in cat.list()}
        assert PAYLOAD_ENTRY_ID in by_id
        assert CONTROL_ENTRY_ID in by_id
        assert by_id[PAYLOAD_ENTRY_ID].origin == "payload"
        assert by_id[PAYLOAD_ENTRY_ID].simulated is False
        assert by_id[CONTROL_ENTRY_ID].origin == "control"
        assert by_id[CONTROL_ENTRY_ID].simulated is True
        assert by_id[CONTROL_ENTRY_ID].origin_label() == "control-simulated"
    finally:
        _cleanup(pg_dsn, PAYLOAD_ENTRY_ID, CONTROL_ENTRY_ID)


def test_seed_demo_is_idempotent(pg_dsn: str) -> None:
    cat = PostgresCatalogue(dsn=pg_dsn)
    try:
        seed_demo(cat)
        seed_demo(cat)  # second call upserts, does not duplicate
        ids = [e.entry_id for e in cat.list()]
        assert ids.count(PAYLOAD_ENTRY_ID) == 1
        assert ids.count(CONTROL_ENTRY_ID) == 1
    finally:
        _cleanup(pg_dsn, PAYLOAD_ENTRY_ID, CONTROL_ENTRY_ID)


def test_list_filters_by_origin(pg_dsn: str) -> None:
    cat = PostgresCatalogue(dsn=pg_dsn)
    try:
        seed_demo(cat)

        payload_rows = cat.list(origin="payload")
        control_rows = cat.list(origin="control")

        assert all(e.origin == "payload" for e in payload_rows)
        assert all(e.origin == "control" for e in control_rows)
        assert PAYLOAD_ENTRY_ID in {e.entry_id for e in payload_rows}
        assert PAYLOAD_ENTRY_ID not in {e.entry_id for e in control_rows}
        assert CONTROL_ENTRY_ID in {e.entry_id for e in control_rows}
        assert CONTROL_ENTRY_ID not in {e.entry_id for e in payload_rows}
    finally:
        _cleanup(pg_dsn, PAYLOAD_ENTRY_ID, CONTROL_ENTRY_ID)


def _register_payload(cat: PostgresCatalogue, entry_id: str) -> CatalogueEntry:
    entry = CatalogueEntry(
        entry_id=entry_id,
        origin="payload",
        simulated=False,
        product_type="SST_L2_DERIVED",
        status="REGISTERED",
        sensing_time=None,
        ingest_time=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
        reference=f"ref/{entry_id}",
        provenance=Provenance(
            source_version="pdgs-sst-1.0",
            source_refs=("L1-0001",),
            run_time=datetime(2026, 6, 13, 9, 45, tzinfo=UTC),
        ),
    )
    cat.register(entry)
    return entry


def test_update_status_round_trip(pg_dsn: str) -> None:
    cat = PostgresCatalogue(dsn=pg_dsn)
    entry_id = f"test-{uuid.uuid4().hex[:8]}-status"
    try:
        _register_payload(cat, entry_id)
        cat.update_status(entry_id, "VALIDATED")
        got = cat.get(entry_id)
        assert got is not None
        assert got.status == "VALIDATED"
    finally:
        _cleanup(pg_dsn, entry_id)


def test_update_status_unknown_raises(pg_dsn: str) -> None:
    cat = PostgresCatalogue(dsn=pg_dsn)
    with pytest.raises(CatalogueError):
        cat.update_status(f"absent-{uuid.uuid4().hex}", "VALIDATED")


def test_set_provenance_round_trip(pg_dsn: str) -> None:
    cat = PostgresCatalogue(dsn=pg_dsn)
    entry_id = f"test-{uuid.uuid4().hex[:8]}-prov"
    try:
        _register_payload(cat, entry_id)
        new_prov = Provenance(
            source_version="pdgs-sst-2.0",
            source_refs=("L1-new-a", "L1-new-b"),
            run_time=datetime(2026, 6, 14, 8, 0, tzinfo=UTC),
        )
        cat.set_provenance(entry_id, new_prov)
        got = cat.get(entry_id)
        assert got is not None
        assert got.provenance == new_prov
    finally:
        _cleanup(pg_dsn, entry_id)


def test_set_provenance_unknown_raises(pg_dsn: str) -> None:
    cat = PostgresCatalogue(dsn=pg_dsn)
    with pytest.raises(CatalogueError):
        cat.set_provenance(
            f"absent-{uuid.uuid4().hex}",
            Provenance(source_version="x", source_refs=(), run_time=None),
        )


def test_payload_mapper_write_to_postgres(pg_dsn: str) -> None:
    # AC1.4: a row built via the payload mapper registers and reads back intact.
    cat = PostgresCatalogue(dsn=pg_dsn)
    entry_id = f"test-{uuid.uuid4().hex[:8]}-mapped"
    try:
        entry = entry_from_payload_product(
            product_id=entry_id,
            product_type="SST_L2_DERIVED",
            status="VALIDATED",
            sensing_time=datetime(2026, 6, 13, 9, 30, tzinfo=UTC),
            ingest_time=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
            reference=f"SST_L2_DERIVED/{entry_id}.nc",
            processor_version="pdgs-sst-1.0",
            input_product_ids=("L1-a", "L1-b"),
            run_time=datetime(2026, 6, 13, 9, 45, tzinfo=UTC),
        )
        cat.register(entry)
        got = cat.get(entry_id)
        assert got == entry
        assert got is not None
        assert got.origin == "payload"
        assert got.simulated is False
        assert got.provenance.source_refs == ("L1-a", "L1-b")
    finally:
        _cleanup(pg_dsn, entry_id)


def test_cross_segment_listing(pg_dsn: str) -> None:
    # AC1.2: one list() returns a payload-mapped row AND a control-bridge-collected
    # row together, each with origin/simulated/provenance.
    cat = PostgresCatalogue(dsn=pg_dsn)
    prefix = f"test-{uuid.uuid4().hex[:8]}"
    payload_id = f"{prefix}-payload"

    payload = entry_from_payload_product(
        product_id=payload_id,
        product_type="SST_L2_DERIVED",
        status="VALIDATED",
        sensing_time=datetime(2026, 6, 13, 9, 30, tzinfo=UTC),
        ingest_time=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
        reference=f"SST_L2_DERIVED/{payload_id}.nc",
        processor_version="pdgs-sst-1.0",
        input_product_ids=("L1-0001",),
        run_time=datetime(2026, 6, 13, 9, 45, tzinfo=UTC),
    )

    # A control row collected via the read-only bridge against mocked Yamcs JSON.
    def fetch_json(path: str) -> dict[str, object]:
        if "/parameters" in path:
            return {"parameters": [], "totalSize": 0}
        return {
            "alarms": [
                {
                    "seqNum": 7,
                    "type": "PARAMETER",
                    "id": {"namespace": "/SGS", "name": "obc_temp"},
                    "triggerTime": "2026-06-13T09:31:00.000Z",
                    "severity": "CRITICAL",
                    "violations": 3,
                    "acknowledged": False,
                }
            ]
        }

    bridge = YamcsControlBridge(fetch_json=fetch_json)
    control_entries = bridge.collect()
    assert len(control_entries) == 1
    control = control_entries[0]

    try:
        cat.register(payload)
        cat.register(control)

        by_id = {e.entry_id: e for e in cat.list()}
        assert payload_id in by_id
        assert control.entry_id in by_id

        got_payload = by_id[payload_id]
        got_control = by_id[control.entry_id]
        assert got_payload.origin == "payload"
        assert got_payload.simulated is False
        assert got_payload.provenance.source_version == "pdgs-sst-1.0"
        assert got_control.origin == "control"
        assert got_control.simulated is True
        assert got_control.provenance.source_refs == ("/SGS/obc_temp",)
        assert got_control.reference.startswith("yamcs://")
    finally:
        _cleanup(pg_dsn, payload_id, control.entry_id)


def test_record_references_to_postgres(pg_dsn: str) -> None:
    cat = PostgresCatalogue(dsn=pg_dsn)

    def fetch_json(path: str) -> dict[str, object]:
        if "/parameters" in path:
            return {
                "parameters": [{"name": "obc_temp", "qualifiedName": "/SGS/obc_temp", "type": {}}],
                "totalSize": 1,
            }
        return {"alarms": []}

    bridge = YamcsControlBridge(fetch_json=fetch_json)
    collected = bridge.collect()
    refs = [e.reference for e in collected]
    try:
        count = record_references(cat, bridge)
        assert count == 1
        listed_refs = {e.reference for e in cat.list(origin="control")}
        assert set(refs) <= listed_refs
    finally:
        _cleanup(pg_dsn, *[e.entry_id for e in collected])
