"""Tests for the read-only payload (PDGS) SQLite catalogue bridge.

The unit tests build a temporary SQLite file with the pdgs ``products`` schema (no
``pdgs`` import — the schema is replicated locally as a data fixture) and assert the
bridge maps rows to payload :class:`CatalogueEntry`s and stays read-only. The
``postgres``-marked test mirrors products into the live shared catalogue and cleans up.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import psycopg
import pytest

from sgs_shared.catalogue.repository import PostgresCatalogue
from sgs_shared.payload_bridge.sqlite import (
    PayloadBridgeError,
    PayloadSqliteBridge,
    record_products,
)

if TYPE_CHECKING:
    from pathlib import Path

# The pdgs Epic-1 ``products`` schema (CONTEXT). Replicated here as a data fixture so
# the test never imports pdgs — the bridge reads the FILE, not the segment's code.
_PRODUCTS_DDL = """
CREATE TABLE products (
    product_id              TEXT PRIMARY KEY,
    collection_id           TEXT,
    product_type            TEXT,
    level                   TEXT,
    timeliness              TEXT,
    sensing_start           TEXT,
    sensing_end             TEXT,
    bbox_west               REAL,
    bbox_south              REAL,
    bbox_east               REAL,
    bbox_north              REAL,
    local_path              TEXT,
    checksum                TEXT,
    size_bytes              INTEGER,
    status                  TEXT,
    prov_processor_version  TEXT,
    prov_config_version     TEXT,
    prov_input_product_ids  TEXT,
    prov_run_timestamp      TEXT,
    created_at              TEXT,
    updated_at              TEXT
)
"""

_INSERT = """
INSERT INTO products (
    product_id, collection_id, product_type, level, timeliness,
    sensing_start, sensing_end, bbox_west, bbox_south, bbox_east, bbox_north,
    local_path, checksum, size_bytes, status,
    prov_processor_version, prov_config_version, prov_input_product_ids,
    prov_run_timestamp, created_at, updated_at
) VALUES (
    :product_id, :collection_id, :product_type, :level, :timeliness,
    :sensing_start, :sensing_end, :bbox_west, :bbox_south, :bbox_east, :bbox_north,
    :local_path, :checksum, :size_bytes, :status,
    :prov_processor_version, :prov_config_version, :prov_input_product_ids,
    :prov_run_timestamp, :created_at, :updated_at
)
"""


def _make_payload_db(
    path: Path, *, l2_id: str = "S3A-SST-L2-0001", l1_id: str = "S3A-L1-0001"
) -> None:
    """Create a payload SQLite catalogue at ``path`` with one L2 and one L1 row."""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(_PRODUCTS_DDL)
        conn.execute(
            _INSERT,
            {
                "product_id": l2_id,
                "collection_id": "0412",
                "product_type": "SST_L2_DERIVED",
                "level": "L2",
                "timeliness": "NT",
                "sensing_start": "2026-06-13T09:30:00Z",
                "sensing_end": "2026-06-13T09:33:00Z",
                "bbox_west": -10.0,
                "bbox_south": 30.0,
                "bbox_east": 5.0,
                "bbox_north": 45.0,
                "local_path": "/data/SST_L2/S3A-SST-L2-0001.nc",
                "checksum": "abc123",
                "size_bytes": 1024,
                "status": "VALIDATED",
                "prov_processor_version": "pdgs-sst-1.0",
                "prov_config_version": "cfg-1.0",
                "prov_input_product_ids": json.dumps([l1_id]),
                "prov_run_timestamp": "2026-06-13T09:45:00Z",
                "created_at": "2026-06-13T10:00:00Z",
                "updated_at": "2026-06-13T10:00:00Z",
            },
        )
        conn.execute(
            _INSERT,
            {
                "product_id": l1_id,
                "collection_id": "0411",
                "product_type": "SLSTR_L1B",
                "level": "L1",
                "timeliness": "NR",
                "sensing_start": "2026-06-13T09:28:00Z",
                "sensing_end": "2026-06-13T09:31:00Z",
                "bbox_west": -10.0,
                "bbox_south": 30.0,
                "bbox_east": 5.0,
                "bbox_north": 45.0,
                "local_path": "/data/L1/S3A-L1-0001.nc",
                "checksum": "def456",
                "size_bytes": 4096,
                "status": "REGISTERED",
                "prov_processor_version": None,
                "prov_config_version": None,
                "prov_input_product_ids": None,
                "prov_run_timestamp": None,
                "created_at": "2026-06-13T09:50:00Z",
                "updated_at": "2026-06-13T09:50:00Z",
            },
        )
        conn.commit()
    finally:
        conn.close()


def test_collect_maps_products_to_payload_entries(tmp_path: Path) -> None:
    db = tmp_path / "pdgs.sqlite"
    _make_payload_db(db)
    bridge = PayloadSqliteBridge(db)

    entries = bridge.collect()
    by_id = {e.entry_id: e for e in entries}
    assert set(by_id) == {"S3A-SST-L2-0001", "S3A-L1-0001"}

    # Every payload product is REAL data: origin=payload, simulated=False.
    for entry in entries:
        assert entry.origin == "payload"
        assert entry.simulated is False
        assert entry.origin_label() == "payload"
        assert entry.detail is not None
        assert "REAL data" in entry.detail

    l2 = by_id["S3A-SST-L2-0001"]
    assert l2.product_type == "SST_L2_DERIVED"
    assert l2.status == "VALIDATED"
    assert l2.reference == "/data/SST_L2/S3A-SST-L2-0001.nc"  # local_path
    assert l2.sensing_time == datetime(2026, 6, 13, 9, 30, tzinfo=UTC)
    assert l2.ingest_time == datetime(2026, 6, 13, 10, 0, tzinfo=UTC)  # created_at
    assert l2.provenance.source_version == "pdgs-sst-1.0"
    assert l2.provenance.source_refs == ("S3A-L1-0001",)  # JSON input ids
    assert l2.provenance.run_time == datetime(2026, 6, 13, 9, 45, tzinfo=UTC)
    # All datetimes timezone-aware UTC.
    assert l2.sensing_time.tzinfo is not None
    assert l2.ingest_time.tzinfo is not None
    assert l2.provenance.run_time is not None
    assert l2.provenance.run_time.tzinfo is not None

    l1 = by_id["S3A-L1-0001"]
    assert l1.product_type == "SLSTR_L1B"
    assert l1.status == "REGISTERED"
    assert l1.provenance.source_version is None  # NULL prov_processor_version
    assert l1.provenance.source_refs == ()  # NULL prov_input_product_ids
    assert l1.provenance.run_time is None  # NULL prov_run_timestamp


def test_reference_falls_back_to_product_id_when_no_local_path(tmp_path: Path) -> None:
    db = tmp_path / "pdgs.sqlite"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(_PRODUCTS_DDL)
        conn.execute(
            _INSERT,
            {
                "product_id": "S3A-NOPATH-0001",
                "collection_id": "0412",
                "product_type": "SST_L2_DERIVED",
                "level": "L2",
                "timeliness": "NT",
                "sensing_start": "2026-06-13T09:30:00Z",
                "sensing_end": "2026-06-13T09:33:00Z",
                "bbox_west": None,
                "bbox_south": None,
                "bbox_east": None,
                "bbox_north": None,
                "local_path": None,  # no path => reference falls back to product_id
                "checksum": None,
                "size_bytes": None,
                "status": "REGISTERED",
                "prov_processor_version": None,
                "prov_config_version": None,
                "prov_input_product_ids": None,
                "prov_run_timestamp": None,
                "created_at": "2026-06-13T10:00:00Z",
                "updated_at": "2026-06-13T10:00:00Z",
            },
        )
        conn.commit()
    finally:
        conn.close()

    [entry] = PayloadSqliteBridge(db).collect()
    assert entry.reference == "S3A-NOPATH-0001"


def test_missing_file_raises_bridge_error(tmp_path: Path) -> None:
    bridge = PayloadSqliteBridge(tmp_path / "does-not-exist.sqlite")
    with pytest.raises(PayloadBridgeError):
        bridge.collect()


def test_missing_products_table_raises_bridge_error(tmp_path: Path) -> None:
    db = tmp_path / "empty.sqlite"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE not_products (id TEXT)")
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(PayloadBridgeError):
        PayloadSqliteBridge(db).collect()


def test_bridge_connection_is_read_only(tmp_path: Path) -> None:
    # The bridge opens mode=ro; a write through that same URI must be rejected.
    db = tmp_path / "pdgs.sqlite"
    _make_payload_db(db)
    abspath = db.resolve().as_posix()
    ro_conn = sqlite3.connect(f"file:{abspath}?mode=ro", uri=True)
    try:
        with pytest.raises(sqlite3.OperationalError):
            ro_conn.execute("DELETE FROM products")
            ro_conn.commit()
    finally:
        ro_conn.close()

    # And the bridge itself never mutates the file: row count is unchanged after collect.
    PayloadSqliteBridge(db).collect()
    check = sqlite3.connect(str(db))
    try:
        (count,) = check.execute("SELECT COUNT(*) FROM products").fetchone()
    finally:
        check.close()
    assert count == 2


@pytest.mark.postgres
def test_record_products_round_trip(pg_dsn: str) -> None:
    cat = PostgresCatalogue(dsn=pg_dsn)
    import tempfile
    from pathlib import Path as _Path

    prefix = f"test-{uuid.uuid4().hex[:8]}"
    l2_id = f"{prefix}-SST-L2"
    l1_id = f"{prefix}-L1"
    with tempfile.TemporaryDirectory() as tmpdir:
        db = _Path(tmpdir) / "pdgs.sqlite"
        _make_payload_db(db, l2_id=l2_id, l1_id=l1_id)
        bridge = PayloadSqliteBridge(db)
        try:
            count = record_products(cat, bridge)
            assert count == 2

            got_l2 = cat.get(l2_id)
            assert got_l2 is not None
            assert got_l2.origin == "payload"
            assert got_l2.simulated is False
            assert got_l2.product_type == "SST_L2_DERIVED"
            assert got_l2.status == "VALIDATED"
            assert got_l2.provenance.source_refs == (l1_id,)

            got_l1 = cat.get(l1_id)
            assert got_l1 is not None
            assert got_l1.origin == "payload"
        finally:
            with psycopg.connect(pg_dsn) as conn:
                conn.execute(
                    "DELETE FROM catalogue_entries WHERE entry_id = ANY(%s)",
                    ([l2_id, l1_id],),
                )
                conn.commit()
