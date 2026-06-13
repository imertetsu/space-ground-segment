"""Unit tests (no DB) for the primitive-to-:class:`CatalogueEntry` mappers."""

from __future__ import annotations

from datetime import UTC, datetime

from sgs_shared.catalogue.mappers import (
    entry_from_control_alarm,
    entry_from_control_archive_ref,
    entry_from_payload_product,
)


def test_payload_mapper_sets_real_data_fields() -> None:
    entry = entry_from_payload_product(
        product_id="p-1",
        product_type="SST_L2_DERIVED",
        status="VALIDATED",
        sensing_time=datetime(2026, 6, 13, 9, 30, tzinfo=UTC),
        ingest_time=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
        reference="SST_L2_DERIVED/p-1.nc",
        processor_version="pdgs-sst-1.0",
        input_product_ids=["L1-a", "L1-b"],
        run_time=datetime(2026, 6, 13, 9, 45, tzinfo=UTC),
    )
    assert entry.origin == "payload"
    assert entry.simulated is False
    assert entry.product_type == "SST_L2_DERIVED"
    assert entry.provenance.source_version == "pdgs-sst-1.0"
    assert entry.provenance.source_refs == ("L1-a", "L1-b")
    assert entry.provenance.run_time == datetime(2026, 6, 13, 9, 45, tzinfo=UTC)


def test_control_alarm_mapper_is_simulated_reference() -> None:
    entry = entry_from_control_alarm(
        alarm_id="yamcs://myproject/alarms/SGS/obc_temp/1",
        parameter="/SGS/obc_temp",
        severity="CRITICAL",
        status="TRIGGERED",
        trigger_time=datetime(2026, 6, 13, 9, 31, tzinfo=UTC),
        ingest_time=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
        reference="yamcs://myproject/alarms/SGS/obc_temp/1",
        detail="SIMULATED alarm; severity=CRITICAL",
    )
    assert entry.origin == "control"
    assert entry.simulated is True
    assert entry.product_type == "OOL_ALARM_REF"
    assert entry.provenance.source_version == "yamcs-mdb-SGS"
    assert entry.provenance.source_refs == ("/SGS/obc_temp",)
    assert entry.provenance.run_time == datetime(2026, 6, 13, 9, 31, tzinfo=UTC)
    assert entry.sensing_time == datetime(2026, 6, 13, 9, 31, tzinfo=UTC)


def test_control_archive_mapper_is_simulated_reference() -> None:
    entry = entry_from_control_archive_ref(
        parameter="/SGS/obc_temp",
        status="ARCHIVED",
        ingest_time=datetime(2026, 6, 13, 10, 0, tzinfo=UTC),
        reference="yamcs://myproject/parameters/SGS/obc_temp",
    )
    assert entry.origin == "control"
    assert entry.simulated is True
    assert entry.product_type == "TM_ARCHIVE_REF"
    assert entry.entry_id == "yamcs://myproject/parameters/SGS/obc_temp"
    assert entry.provenance.source_version == "yamcs-mdb-SGS"
    assert entry.provenance.source_refs == ("/SGS/obc_temp",)
    assert entry.sensing_time is None
