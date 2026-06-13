"""Unit tests (no DB) for the unified :class:`CatalogueEntry`."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime

import pytest

from sgs_shared.catalogue.models import CatalogueEntry, Provenance


def _payload_entry() -> CatalogueEntry:
    return CatalogueEntry(
        entry_id="p-1",
        origin="payload",
        simulated=False,
        product_type="SST_L2_DERIVED",
        status="VALIDATED",
        sensing_time=datetime(2026, 6, 13, 9, 30, tzinfo=UTC),
        ingest_time=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
        reference="SST_L2_DERIVED/p-1.nc",
        provenance=Provenance(
            source_version="pdgs-sst-1.0",
            source_refs=("L1-0001",),
            run_time=datetime(2026, 6, 13, 9, 45, tzinfo=UTC),
        ),
    )


def _control_entry() -> CatalogueEntry:
    return CatalogueEntry(
        entry_id="c-1",
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
        detail="SIMULATED telemetry",
    )


def test_construction_payload() -> None:
    entry = _payload_entry()
    assert entry.origin == "payload"
    assert entry.simulated is False
    assert entry.detail is None  # default
    assert entry.provenance.source_version == "pdgs-sst-1.0"
    assert entry.provenance.source_refs == ("L1-0001",)


def test_construction_control() -> None:
    entry = _control_entry()
    assert entry.origin == "control"
    assert entry.simulated is True
    assert entry.sensing_time is None
    assert entry.detail == "SIMULATED telemetry"


def test_origin_label_payload_is_plain() -> None:
    assert _payload_entry().origin_label() == "payload"


def test_origin_label_control_is_simulated() -> None:
    assert _control_entry().origin_label() == "control-simulated"


def test_entry_is_frozen() -> None:
    entry = _payload_entry()
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.status = "FAILED"  # type: ignore[misc]
