"""Read-only Yamcs-REST poller that records control references into the catalogue.

:class:`YamcsControlBridge` issues GET-only requests to a running Yamcs server and
turns its MDB parameter list + archived alarms into unified :class:`CatalogueEntry`
references via :mod:`sgs_shared.catalogue.mappers`. It talks to Yamcs over HTTP using
only the standard library (``urllib.request``) — it imports NO ``control/`` code and
adds no third-party dependency.

CRITICAL data-honesty invariant (Epic 3 AC1.3): the bridge stores only **locator
strings + lifecycle state**, NEVER a copy of a telemetry value. Parameter
``triggerValue`` / ``currentValue`` payloads in the Yamcs JSON are deliberately
ignored (only an alarm's severity / violation count may be folded into the free-text
``detail`` as a human label).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.error import URLError
from urllib.request import urlopen

from sgs_shared.anomaly.mappers import anomaly_from_yamcs_alarm
from sgs_shared.catalogue.mappers import (
    entry_from_control_alarm,
    entry_from_control_archive_ref,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sgs_shared.anomaly.models import Anomaly
    from sgs_shared.anomaly.repository import AnomalyStore
    from sgs_shared.catalogue.models import CatalogueEntry
    from sgs_shared.catalogue.repository import Catalogue


class _ParsedAlarm:
    """The normalised, value-free fields of one Yamcs archive alarm.

    Holds ONLY the locator + state-bearing fields shared by the catalogue
    (``OOL_ALARM_REF``) and the anomaly (``ool_alarm``) mappers — never a copy of a
    telemetry value (AC1.3). Built by :func:`_parse_alarm` from one alarm dict.
    """

    __slots__ = (
        "acknowledged",
        "parameter",
        "reference",
        "seq_num",
        "severity",
        "trigger_time",
        "violations",
    )

    def __init__(
        self,
        *,
        parameter: str,
        reference: str,
        seq_num: object,
        severity: str,
        trigger_time: datetime | None,
        acknowledged: bool,
        violations: object,
    ) -> None:
        self.parameter = parameter
        self.reference = reference
        self.seq_num = seq_num
        self.severity = severity
        self.trigger_time = trigger_time
        self.acknowledged = acknowledged
        # A violation COUNT (not a telemetry value) — a human label only.
        self.violations = violations


class BridgeError(RuntimeError):
    """Raised when the control bridge cannot reach or parse the Yamcs REST API."""


def _parse_iso_utc(value: str) -> datetime:
    """Parse a Yamcs ISO-8601 timestamp (trailing ``Z``) into timezone-aware UTC."""
    normalised = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalised)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class YamcsControlBridge:
    """Read-only Yamcs REST poller producing control catalogue references.

    Args:
        base_url: Yamcs HTTP base URL (plain HTTP, no TLS).
        instance: Yamcs instance name (used in the ``yamcs://`` locator).
        processor: Yamcs processor name (carried for completeness; reads are archive-
            and MDB-based so it is not needed for the current endpoints).
        space_system: XTCE SpaceSystem to scope the parameter listing to (``SGS``).
        fetch_json: Injectable ``path -> dict`` fetcher for tests. When ``None`` a real
            ``urllib`` GET is used, wrapping any network/JSON error in :class:`BridgeError`.
        timeout: HTTP timeout (seconds) for the default urllib fetcher.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8090",
        instance: str = "myproject",
        processor: str = "realtime",
        space_system: str = "SGS",
        *,
        fetch_json: Callable[[str], dict[str, Any]] | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.instance = instance
        self.processor = processor
        self.space_system = space_system
        self.timeout = timeout
        self._fetch_json = fetch_json if fetch_json is not None else self._urllib_get

    def _urllib_get(self, path: str) -> dict[str, Any]:
        """Default fetcher: a plain-HTTP GET that parses a JSON object."""
        url = f"{self.base_url}{path}"
        try:
            with urlopen(url, timeout=self.timeout) as resp:
                payload = resp.read()
        except (URLError, OSError) as exc:
            raise BridgeError(f"Yamcs GET {url} failed: {exc}") from exc
        try:
            parsed: Any = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise BridgeError(f"Yamcs GET {url} returned non-JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise BridgeError(f"Yamcs GET {url} returned a non-object JSON body")
        return parsed

    def _collect_archive_refs(self, ingest_time: datetime) -> list[CatalogueEntry]:
        """One ``TM_ARCHIVE_REF`` per parameter in the ``/SGS`` MDB system."""
        system = f"/{self.space_system}"
        path = f"/api/mdb/{self.instance}/parameters?system={system}"
        body = self._fetch_json(path)
        parameters = body.get("parameters", [])
        entries: list[CatalogueEntry] = []
        for param in parameters:
            if not isinstance(param, dict):  # pragma: no cover - defensive
                continue
            qualified = param.get("qualifiedName") or f"{system}/{param.get('name', '')}"
            reference = f"yamcs://{self.instance}/parameters{qualified}"
            entries.append(
                entry_from_control_archive_ref(
                    parameter=str(qualified),
                    status="ARCHIVED",
                    ingest_time=ingest_time,
                    reference=reference,
                    run_time=None,
                    detail="SIMULATED telemetry archive reference (no value stored).",
                )
            )
        return entries

    def _fetch_alarms(self) -> list[_ParsedAlarm]:
        """GET the archive alarms and parse each into a value-free :class:`_ParsedAlarm`.

        Shared by :meth:`_collect_alarm_refs` (catalogue) and :meth:`collect_anomalies`
        (anomalies) so the id-normalisation / state logic lives in one place. Reads ONLY
        locator + state fields — never ``triggerValue`` / ``currentValue`` (AC1.3).
        """
        path = f"/api/archive/{self.instance}/alarms"
        body = self._fetch_json(path)
        alarms = body.get("alarms", [])
        parsed: list[_ParsedAlarm] = []
        for alarm in alarms:
            if not isinstance(alarm, dict):  # pragma: no cover - defensive
                continue
            parsed.append(self._parse_alarm(alarm))
        return parsed

    def _parse_alarm(self, alarm: dict[str, Any]) -> _ParsedAlarm:
        """Normalise one alarm dict into a value-free :class:`_ParsedAlarm`."""
        ident = alarm.get("id", {})
        namespace = str(ident.get("namespace", "")) if isinstance(ident, dict) else ""
        name = str(ident.get("name", "")) if isinstance(ident, dict) else ""
        seq_num = alarm.get("seqNum", 0)
        # Yamcs returns the parameter id either split (namespace + bare name) or as a
        # single fully-qualified name (real archive alarms: id={"name": "/SGS/obc_temp"},
        # no namespace). Normalise both to one qualified name so the locator never doubles
        # a slash.
        parameter = f"{namespace}/{name}" if namespace and not name.startswith(namespace) else name
        reference = f"yamcs://{self.instance}/alarms{parameter}/{seq_num}"
        trigger_raw = alarm.get("triggerTime")
        trigger_time = _parse_iso_utc(str(trigger_raw)) if isinstance(trigger_raw, str) else None
        severity = str(alarm.get("severity", "UNKNOWN"))
        # State/labels ONLY — deliberately never read triggerValue/currentValue.
        acknowledged = bool(alarm.get("acknowledged", False))
        return _ParsedAlarm(
            parameter=parameter,
            reference=reference,
            seq_num=seq_num,
            severity=severity,
            trigger_time=trigger_time,
            acknowledged=acknowledged,
            violations=alarm.get("violations"),
        )

    def _collect_alarm_refs(self, ingest_time: datetime) -> list[CatalogueEntry]:
        """One ``OOL_ALARM_REF`` per archived alarm (locator + state only)."""
        entries: list[CatalogueEntry] = []
        for alarm in self._fetch_alarms():
            status = "ACKNOWLEDGED" if alarm.acknowledged else "TRIGGERED"
            detail = f"SIMULATED alarm; severity={alarm.severity}"
            if alarm.violations is not None:
                detail += f"; violations={alarm.violations}"
            entries.append(
                entry_from_control_alarm(
                    alarm_id=alarm.reference,
                    parameter=alarm.parameter,
                    severity=alarm.severity,
                    status=status,
                    trigger_time=alarm.trigger_time,
                    ingest_time=ingest_time,
                    reference=alarm.reference,
                    detail=detail,
                )
            )
        return entries

    def collect(self) -> list[CatalogueEntry]:
        """Read-only: collect control references (TM archive + OOL alarms).

        Returns one ``TM_ARCHIVE_REF`` per ``/SGS`` MDB parameter and one
        ``OOL_ALARM_REF`` per archived alarm. ``ingest_time`` is stamped from the
        bridge clock (UTC). No telemetry value is ever read or stored.
        """
        ingest_time = datetime.now(tz=UTC)
        return self._collect_archive_refs(ingest_time) + self._collect_alarm_refs(ingest_time)

    def collect_anomalies(self) -> list[Anomaly]:
        """Read-only: one ``ool_alarm`` :class:`Anomaly` per archived Yamcs alarm.

        Reuses the same archive-alarm fetch/parse as :meth:`_collect_alarm_refs`, so the
        anomaly's ``source_ref`` (and id) is the SAME ``yamcs://…`` alarm locator the
        catalogue ``OOL_ALARM_REF`` row carries. ``trigger_time`` is parsed UTC;
        ``acknowledged`` maps OPEN/ACKNOWLEDGED. No telemetry value is ever read or stored.
        """
        anomalies: list[Anomaly] = []
        for alarm in self._fetch_alarms():
            trigger_time = (
                alarm.trigger_time if alarm.trigger_time is not None else datetime.now(tz=UTC)
            )
            detail = f"SIMULATED OOL alarm on {alarm.parameter}; severity={alarm.severity}"
            anomalies.append(
                anomaly_from_yamcs_alarm(
                    alarm_ref=alarm.reference,
                    parameter=alarm.parameter,
                    severity=alarm.severity,
                    trigger_time=trigger_time,
                    acknowledged=alarm.acknowledged,
                    detail=detail,
                )
            )
        return anomalies


def record_references(catalogue: Catalogue, bridge: YamcsControlBridge) -> int:
    """Collect control references and register each into ``catalogue``; return the count."""
    entries = bridge.collect()
    for entry in entries:
        catalogue.register(entry)
    return len(entries)


def record_anomalies(store: AnomalyStore, bridge: YamcsControlBridge) -> int:
    """Collect control OOL-alarm anomalies and record each into ``store``; return the count."""
    anomalies = bridge.collect_anomalies()
    for anomaly in anomalies:
        store.record(anomaly)
    return len(anomalies)
