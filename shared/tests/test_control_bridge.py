"""Unit tests (no DB, no HTTP) for the read-only Yamcs control bridge.

The bridge's ``fetch_json`` is injected with realistic mocked Yamcs JSON so no real
network call is made. These tests guard the data-honesty invariant (AC1.3): the
bridge records ONLY locator strings + state — never a copy of a telemetry value.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sgs_shared.anomaly.models import Anomaly, AnomalyState
from sgs_shared.anomaly.repository import AnomalyStore
from sgs_shared.catalogue.models import CatalogueEntry, Origin, Provenance
from sgs_shared.catalogue.repository import Catalogue
from sgs_shared.control_bridge.yamcs import (
    YamcsControlBridge,
    record_anomalies,
    record_references,
)

# Mocked Yamcs JSON shaped like the real REST responses (CONTEXT).
_MDB_PARAMETERS: dict[str, Any] = {
    "parameters": [
        {"name": "obc_temp", "qualifiedName": "/SGS/obc_temp", "type": {"engType": "float"}},
        {
            "name": "battery_voltage",
            "qualifiedName": "/SGS/battery_voltage",
            "type": {"engType": "float"},
        },
        {
            "name": "reaction_wheel_speed",
            "qualifiedName": "/SGS/reaction_wheel_speed",
            "type": {"engType": "float"},
        },
    ],
    "totalSize": 3,
}

_ARCHIVE_ALARMS: dict[str, Any] = {
    "alarms": [
        {
            "seqNum": 1,
            "type": "PARAMETER",
            "id": {"namespace": "/SGS", "name": "obc_temp"},
            "triggerTime": "2026-06-13T09:31:00.000Z",
            "severity": "CRITICAL",
            "violations": 3,
            "acknowledged": False,
            # Value payloads the bridge MUST ignore (never copied into the row):
            "parameterDetail": {
                "triggerValue": {"engValue": {"floatValue": 88.5}},
                "currentValue": {"engValue": {"floatValue": 91.2}},
            },
        },
        {
            "seqNum": 2,
            "type": "PARAMETER",
            "id": {"namespace": "/SGS", "name": "battery_voltage"},
            "triggerTime": "2026-06-13T09:35:00.000Z",
            "severity": "WARNING",
            "violations": 1,
            "acknowledged": True,
            "parameterDetail": {
                "triggerValue": {"engValue": {"floatValue": 6.1}},
                "currentValue": {"engValue": {"floatValue": 6.0}},
            },
        },
    ]
}


def _fetch_json(path: str) -> dict[str, Any]:
    if "/parameters" in path:
        return _MDB_PARAMETERS
    if "/alarms" in path:
        return _ARCHIVE_ALARMS
    raise AssertionError(f"unexpected path {path!r}")  # pragma: no cover


def test_collect_yields_expected_counts_and_kinds() -> None:
    bridge = YamcsControlBridge(fetch_json=_fetch_json)
    entries = bridge.collect()

    archive = [e for e in entries if e.product_type == "TM_ARCHIVE_REF"]
    alarms = [e for e in entries if e.product_type == "OOL_ALARM_REF"]
    assert len(archive) == 3
    assert len(alarms) == 2
    assert len(entries) == 5


def test_all_control_rows_are_simulated_with_locators() -> None:
    bridge = YamcsControlBridge(fetch_json=_fetch_json)
    for entry in bridge.collect():
        assert entry.origin == "control"
        assert entry.simulated is True
        assert entry.reference.startswith("yamcs://myproject/")


def test_archive_reference_locator_format() -> None:
    bridge = YamcsControlBridge(fetch_json=_fetch_json)
    refs = {e.reference for e in bridge.collect() if e.product_type == "TM_ARCHIVE_REF"}
    assert "yamcs://myproject/parameters/SGS/obc_temp" in refs


def test_alarm_reference_locator_and_run_time_parsed_utc() -> None:
    bridge = YamcsControlBridge(fetch_json=_fetch_json)
    alarms = [e for e in bridge.collect() if e.product_type == "OOL_ALARM_REF"]
    by_ref = {e.reference: e for e in alarms}
    obc = by_ref["yamcs://myproject/alarms/SGS/obc_temp/1"]
    assert obc.provenance.source_refs == ("/SGS/obc_temp",)
    assert obc.provenance.run_time == datetime(2026, 6, 13, 9, 31, tzinfo=UTC)
    assert obc.sensing_time == datetime(2026, 6, 13, 9, 31, tzinfo=UTC)
    assert obc.provenance.run_time is not None
    assert obc.provenance.run_time.tzinfo is not None  # timezone-aware UTC


def test_alarm_id_fully_qualified_name_without_namespace() -> None:
    # Regression: real Yamcs archive alarms return id={"name": "/SGS/obc_temp"} with
    # NO namespace (the name is already fully qualified). The locator must not double
    # a slash, and source_refs must be the qualified parameter name.
    real_shape: dict[str, Any] = {
        "alarms": [
            {
                "seqNum": 0,
                "type": "PARAMETER",
                "id": {"name": "/SGS/obc_temp"},
                "triggerTime": "2026-06-13T16:32:26.893Z",
                "severity": "WARNING",
                "violations": 1,
            }
        ]
    }

    def fetch(path: str) -> dict[str, Any]:
        if "/parameters" in path:
            return {"parameters": [], "totalSize": 0}
        return real_shape

    bridge = YamcsControlBridge(fetch_json=fetch)
    [alarm] = bridge.collect()
    assert alarm.reference == "yamcs://myproject/alarms/SGS/obc_temp/0"
    assert "//" not in alarm.reference.split("://", 1)[1]  # no doubled slash in the path
    assert alarm.provenance.source_refs == ("/SGS/obc_temp",)
    assert alarm.status == "TRIGGERED"  # acknowledged absent -> not acknowledged


def test_alarm_state_is_recorded_not_value() -> None:
    bridge = YamcsControlBridge(fetch_json=_fetch_json)
    alarms = [e for e in bridge.collect() if e.product_type == "OOL_ALARM_REF"]
    by_ref = {e.reference: e for e in alarms}
    obc = by_ref["yamcs://myproject/alarms/SGS/obc_temp/1"]
    bat = by_ref["yamcs://myproject/alarms/SGS/battery_voltage/2"]
    assert obc.status == "TRIGGERED"  # acknowledged: False
    assert bat.status == "ACKNOWLEDGED"  # acknowledged: True


def test_no_telemetry_value_is_stored_anywhere() -> None:
    # AC1.3: only locators + state — never a copy of triggerValue/currentValue.
    bridge = YamcsControlBridge(fetch_json=_fetch_json)
    for entry in bridge.collect():
        haystack = " ".join(
            [
                entry.entry_id,
                entry.reference,
                entry.detail or "",
                *(entry.provenance.source_refs),
            ]
        )
        assert "triggerValue" not in haystack
        assert "currentValue" not in haystack
        assert "floatValue" not in haystack
        # The concrete mocked values must not leak into any field.
        for leaked in ("88.5", "91.2", "6.1", "6.0"):
            assert leaked not in haystack


class _FakeCatalogue(Catalogue):
    """In-memory dict-backed :class:`Catalogue` for the bridge registration test."""

    def __init__(self) -> None:
        self._rows: dict[str, CatalogueEntry] = {}

    def register(self, entry: CatalogueEntry) -> None:
        self._rows[entry.entry_id] = entry

    def get(self, entry_id: str) -> CatalogueEntry | None:
        return self._rows.get(entry_id)

    def list(self, *, origin: Origin | None = None) -> list[CatalogueEntry]:
        rows = list(self._rows.values())
        if origin is not None:
            rows = [e for e in rows if e.origin == origin]
        return sorted(rows, key=lambda e: (e.ingest_time, e.entry_id))

    def update_status(self, entry_id: str, status: str) -> None:  # pragma: no cover - unused
        raise NotImplementedError

    def set_provenance(self, entry_id: str, provenance: Provenance) -> None:
        raise NotImplementedError  # pragma: no cover - unused


class _FakeAnomalyStore(AnomalyStore):
    """In-memory dict-backed :class:`AnomalyStore` for the bridge recording test."""

    def __init__(self) -> None:
        self._rows: dict[str, Anomaly] = {}

    def record(self, anomaly: Anomaly) -> None:
        self._rows[anomaly.anomaly_id] = anomaly

    def get(self, anomaly_id: str) -> Anomaly | None:
        return self._rows.get(anomaly_id)

    def list(
        self, *, origin: Origin | None = None, state: AnomalyState | None = None
    ) -> list[Anomaly]:
        rows = list(self._rows.values())
        if origin is not None:
            rows = [a for a in rows if a.origin == origin]
        if state is not None:
            rows = [a for a in rows if a.state is state]
        return sorted(rows, key=lambda a: (a.opened_at, a.anomaly_id))

    def acknowledge(self, anomaly_id: str) -> None:  # pragma: no cover - unused here
        raise NotImplementedError

    def resolve(self, anomaly_id: str) -> None:  # pragma: no cover - unused here
        raise NotImplementedError

    def start_reprocess(self, anomaly_id: str) -> None:  # pragma: no cover - unused here
        raise NotImplementedError


def test_record_references_registers_each_collected_entry() -> None:
    bridge = YamcsControlBridge(fetch_json=_fetch_json)
    catalogue = _FakeCatalogue()
    count = record_references(catalogue, bridge)
    assert count == 5
    listed = catalogue.list()
    assert len(listed) == 5
    assert all(e.origin == "control" for e in listed)
    assert all(e.simulated is True for e in listed)


def test_collect_anomalies_yields_control_ool_alarms() -> None:
    # The anomaly view of the SAME archived alarms: origin=control, simulated=True,
    # kind=ool_alarm, and source_ref == the yamcs:// alarm locator (catalogue linkage).
    bridge = YamcsControlBridge(fetch_json=_fetch_json)
    anomalies = bridge.collect_anomalies()
    assert len(anomalies) == 2
    by_id = {a.anomaly_id: a for a in anomalies}
    obc = by_id["yamcs://myproject/alarms/SGS/obc_temp/1"]
    bat = by_id["yamcs://myproject/alarms/SGS/battery_voltage/2"]

    for a in anomalies:
        assert a.origin == "control"
        assert a.simulated is True
        assert a.kind == "ool_alarm"
        # source_ref IS the yamcs:// alarm locator (== anomaly_id for control).
        assert a.source_ref == a.anomaly_id
        assert a.source_ref.startswith("yamcs://myproject/alarms/")

    assert obc.state is AnomalyState.OPEN  # acknowledged: False
    assert obc.severity == "CRITICAL"
    assert obc.opened_at == datetime(2026, 6, 13, 9, 31, tzinfo=UTC)
    assert bat.state is AnomalyState.ACKNOWLEDGED  # acknowledged: True


def test_collect_anomalies_leaks_no_telemetry_value() -> None:
    # AC1.3 invariant for the anomaly view: only locators + state, never a value.
    bridge = YamcsControlBridge(fetch_json=_fetch_json)
    for a in bridge.collect_anomalies():
        haystack = " ".join([a.anomaly_id, a.source_ref, a.severity, a.detail or "", a.state.value])
        assert "triggerValue" not in haystack
        assert "currentValue" not in haystack
        assert "floatValue" not in haystack
        for leaked in ("88.5", "91.2", "6.1", "6.0"):
            assert leaked not in haystack


def test_record_anomalies_records_each_collected_anomaly() -> None:
    bridge = YamcsControlBridge(fetch_json=_fetch_json)
    store = _FakeAnomalyStore()
    count = record_anomalies(store, bridge)
    assert count == 2
    listed = store.list()
    assert len(listed) == 2
    assert all(a.origin == "control" for a in listed)
    assert all(a.simulated is True for a in listed)
