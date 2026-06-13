"""Shared anomaly store — psycopg-3-backed PostgreSQL implementation.

:class:`AnomalyStore` is the abstract persistence surface for the unified
:class:`~sgs_shared.anomaly.models.Anomaly` (payload processing failures + control
OOL alarms behind one query surface and one state machine).
:class:`PostgresAnomalyStore` is the PostgreSQL implementation using **psycopg 3**.

This mirrors the *shape* and conventions of
:mod:`sgs_shared.catalogue.repository` (per-call connection, idempotent +
forward-compatible schema, errors wrapped in a dedicated exception) for a clean
Phase-2 alignment.

State-transition validation (:func:`~sgs_shared.anomaly.models.can_transition`) runs
in Python *before* the UPDATE. ``start_reprocess`` is payload-only: a control anomaly
raises :class:`UnsupportedActionError`. All datetimes are stored as ``timestamptz``
(UTC).
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import psycopg

from sgs_shared.anomaly.models import Anomaly, AnomalyState, can_transition

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sgs_shared.catalogue.models import Origin

# Env var holding the PostgreSQL DSN — the same one the catalogue uses, so a single
# DSN configures the whole shared layer.
PG_DSN_ENV = "PDGS_PG_DSN"

# Idempotent + forward-compatible schema. ``CREATE TABLE IF NOT EXISTS`` lays down the
# full Phase-2 table; the defensive ``ALTER ... ADD COLUMN IF NOT EXISTS`` lines let an
# older table upgrade in place.
_SCHEMA = """
CREATE TABLE IF NOT EXISTS anomalies (
    anomaly_id  TEXT PRIMARY KEY,
    origin      TEXT NOT NULL CHECK (origin IN ('payload', 'control')),
    simulated   BOOLEAN NOT NULL,
    source_ref  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    severity    TEXT NOT NULL,
    state       TEXT NOT NULL,
    opened_at   TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    detail      TEXT
);
ALTER TABLE anomalies ADD COLUMN IF NOT EXISTS source_ref TEXT;
ALTER TABLE anomalies ADD COLUMN IF NOT EXISTS kind TEXT;
ALTER TABLE anomalies ADD COLUMN IF NOT EXISTS severity TEXT;
ALTER TABLE anomalies ADD COLUMN IF NOT EXISTS detail TEXT;
"""

# Column order shared by INSERT / SELECT so row-mapping stays in lockstep.
_COLUMNS = (
    "anomaly_id",
    "origin",
    "simulated",
    "source_ref",
    "kind",
    "severity",
    "state",
    "opened_at",
    "updated_at",
    "detail",
)


class AnomalyError(RuntimeError):
    """Raised when an anomaly operation cannot complete (backend or illegal state)."""


class UnsupportedActionError(AnomalyError):
    """Raised when an action is not valid for an anomaly's origin (e.g. reprocess control)."""


def _as_utc(value: datetime) -> datetime:
    """Normalise a datetime to timezone-aware UTC (assume UTC if naive)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class AnomalyStore(ABC):
    """Abstract unified-anomaly store.

    Implementations persist :class:`Anomaly` rows (payload failures AND control OOL
    alarms) and expose one query + state-transition surface over both origins.
    """

    @abstractmethod
    def record(self, anomaly: Anomaly) -> None:
        """Insert or replace an anomaly (idempotent upsert on ``anomaly_id``)."""

    @abstractmethod
    def get(self, anomaly_id: str) -> Anomaly | None:
        """Return the anomaly with ``anomaly_id`` or ``None`` if absent."""

    @abstractmethod
    def list(
        self, *, origin: Origin | None = None, state: AnomalyState | None = None
    ) -> list[Anomaly]:
        """Return anomalies (optionally filtered), ordered by ``opened_at, anomaly_id``."""

    @abstractmethod
    def acknowledge(self, anomaly_id: str) -> None:
        """Move OPEN -> ACKNOWLEDGED; raise :class:`AnomalyError` on an illegal move."""

    @abstractmethod
    def resolve(self, anomaly_id: str) -> None:
        """Move the anomaly to RESOLVED; raise :class:`AnomalyError` on an illegal move."""

    @abstractmethod
    def start_reprocess(self, anomaly_id: str) -> None:
        """Move a PAYLOAD anomaly to REPROCESSING.

        Raises :class:`UnsupportedActionError` for a control anomaly (control anomalies
        cannot be reprocessed) and :class:`AnomalyError` on an unknown id or an illegal
        transition.
        """


class PostgresAnomalyStore(AnomalyStore):
    """psycopg-3 PostgreSQL implementation of :class:`AnomalyStore`.

    The DSN comes from the ``dsn`` constructor argument or, if omitted, the
    ``PDGS_PG_DSN`` environment variable. The schema is created idempotently on
    construction. A new connection is opened per call.
    """

    def __init__(self, dsn: str | None = None) -> None:
        resolved = dsn if dsn is not None else os.environ.get(PG_DSN_ENV)
        if not resolved:
            raise AnomalyError(
                f"no PostgreSQL DSN: pass dsn= or set {PG_DSN_ENV} "
                "(e.g. postgresql://sgs:change-me@localhost:5432/sgs_catalogue)"
            )
        self.dsn: str = resolved
        try:
            with self._connect() as conn:
                conn.execute(_SCHEMA)
                conn.commit()
        except psycopg.Error as exc:  # pragma: no cover - needs a live/broken DB
            raise AnomalyError(f"failed to initialise anomaly schema: {exc}") from exc

    def _connect(self) -> psycopg.Connection[tuple[object, ...]]:
        try:
            return psycopg.connect(self.dsn)
        except psycopg.Error as exc:  # pragma: no cover - needs a live/broken DB
            raise AnomalyError(f"failed to connect to PostgreSQL: {exc}") from exc

    def record(self, anomaly: Anomaly) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO anomalies (
                        anomaly_id, origin, simulated, source_ref, kind,
                        severity, state, opened_at, updated_at, detail
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (anomaly_id) DO UPDATE SET
                        origin = EXCLUDED.origin,
                        simulated = EXCLUDED.simulated,
                        source_ref = EXCLUDED.source_ref,
                        kind = EXCLUDED.kind,
                        severity = EXCLUDED.severity,
                        state = EXCLUDED.state,
                        opened_at = EXCLUDED.opened_at,
                        updated_at = EXCLUDED.updated_at,
                        detail = EXCLUDED.detail
                    """,
                    (
                        anomaly.anomaly_id,
                        anomaly.origin,
                        anomaly.simulated,
                        anomaly.source_ref,
                        anomaly.kind,
                        anomaly.severity,
                        anomaly.state.value,
                        _as_utc(anomaly.opened_at),
                        _as_utc(anomaly.updated_at),
                        anomaly.detail,
                    ),
                )
                conn.commit()
        except psycopg.Error as exc:
            raise AnomalyError(f"failed to record anomaly {anomaly.anomaly_id!r}: {exc}") from exc

    def get(self, anomaly_id: str) -> Anomaly | None:
        sql = f"SELECT {', '.join(_COLUMNS)} FROM anomalies WHERE anomaly_id = %s"
        try:
            with self._connect() as conn:
                row = conn.execute(sql, (anomaly_id,)).fetchone()
        except psycopg.Error as exc:
            raise AnomalyError(f"failed to read anomaly {anomaly_id!r}: {exc}") from exc
        return _row_to_anomaly(row) if row is not None else None

    def list(
        self, *, origin: Origin | None = None, state: AnomalyState | None = None
    ) -> list[Anomaly]:
        clauses: list[str] = []
        params: list[object] = []
        if origin is not None:
            clauses.append("origin = %s")
            params.append(origin)
        if state is not None:
            clauses.append("state = %s")
            params.append(state.value)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT {', '.join(_COLUMNS)} FROM anomalies{where} ORDER BY opened_at, anomaly_id"
        try:
            with self._connect() as conn:
                rows: Iterable[tuple[object, ...]] = conn.execute(sql, tuple(params)).fetchall()
        except psycopg.Error as exc:
            raise AnomalyError(f"failed to list anomalies: {exc}") from exc
        return [_row_to_anomaly(row) for row in rows]

    def acknowledge(self, anomaly_id: str) -> None:
        """OPEN -> ACKNOWLEDGED."""
        self._transition(anomaly_id, AnomalyState.ACKNOWLEDGED)

    def resolve(self, anomaly_id: str) -> None:
        """<any non-terminal> -> RESOLVED."""
        self._transition(anomaly_id, AnomalyState.RESOLVED)

    def start_reprocess(self, anomaly_id: str) -> None:
        """PAYLOAD only: <triaged> -> REPROCESSING. Control raises UnsupportedActionError."""
        current = self.get(anomaly_id)
        if current is None:
            raise AnomalyError(f"unknown anomaly_id {anomaly_id!r}")
        if current.origin != "payload":
            raise UnsupportedActionError(
                f"control anomalies cannot be reprocessed (anomaly {anomaly_id!r})"
            )
        self._transition(anomaly_id, AnomalyState.REPROCESSING, known=current)

    def _transition(
        self, anomaly_id: str, target: AnomalyState, *, known: Anomaly | None = None
    ) -> None:
        """Validate (in Python) then apply a state change, bumping ``updated_at``."""
        current = known if known is not None else self.get(anomaly_id)
        if current is None:
            raise AnomalyError(f"unknown anomaly_id {anomaly_id!r}")
        if not can_transition(current.state, target):
            raise AnomalyError(
                f"illegal anomaly transition {current.state.value} -> {target.value} "
                f"for {anomaly_id!r}"
            )
        now = datetime.now(tz=UTC)
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE anomalies SET state = %s, updated_at = %s WHERE anomaly_id = %s",
                    (target.value, now, anomaly_id),
                )
                rowcount = cur.rowcount
                conn.commit()
        except psycopg.Error as exc:
            raise AnomalyError(
                f"failed to transition anomaly {anomaly_id!r} to {target.value}: {exc}"
            ) from exc
        if rowcount == 0:  # pragma: no cover - row existed at the read above
            raise AnomalyError(f"unknown anomaly_id {anomaly_id!r}")


def _row_to_anomaly(row: tuple[object, ...]) -> Anomaly:
    """Reconstruct an :class:`Anomaly` from a positional ``_COLUMNS`` row."""
    (
        anomaly_id,
        origin,
        simulated,
        source_ref,
        kind,
        severity,
        state,
        opened_at,
        updated_at,
        detail,
    ) = row
    if origin not in ("payload", "control"):  # pragma: no cover - guarded by CHECK
        raise AnomalyError(f"corrupt row: unexpected origin {origin!r}")
    if kind not in ("processing_failure", "ool_alarm"):  # pragma: no cover - data integrity
        raise AnomalyError(f"corrupt row {anomaly_id!r}: unexpected kind {kind!r}")
    if not isinstance(opened_at, datetime):  # pragma: no cover - NOT NULL column
        raise AnomalyError(f"corrupt row {anomaly_id!r}: missing opened_at")
    if not isinstance(updated_at, datetime):  # pragma: no cover - NOT NULL column
        raise AnomalyError(f"corrupt row {anomaly_id!r}: missing updated_at")
    return Anomaly(
        anomaly_id=str(anomaly_id),
        origin=origin,
        simulated=bool(simulated),
        source_ref=str(source_ref),
        kind=kind,
        severity=str(severity),
        state=AnomalyState(str(state)),
        opened_at=_as_utc(opened_at),
        updated_at=_as_utc(updated_at),
        detail=str(detail) if detail is not None else None,
    )
