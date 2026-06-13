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

from sgs_shared.catalogue.models import CatalogueEntry
from sgs_shared.catalogue.repository import PostgresCatalogue
from sgs_shared.catalogue.seed import (
    CONTROL_ENTRY_ID,
    PAYLOAD_ENTRY_ID,
    seed_demo,
)

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
            source_version="pdgs-sst-1.0",
            reference=f"SST_L2_DERIVED/{payload_id}.nc",
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
            source_version="yamcs-mdb-SGS",
            reference="/SGS/obc_temp",
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
        base = CatalogueEntry(
            entry_id=entry_id,
            origin="payload",
            simulated=False,
            product_type="SST_L2_DERIVED",
            status="REGISTERED",
            sensing_time=None,
            ingest_time=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
            source_version="pdgs-sst-1.0",
            reference=f"ref/{entry_id}",
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
                source_version="pdgs-sst-1.0",
                reference=base.reference,
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
