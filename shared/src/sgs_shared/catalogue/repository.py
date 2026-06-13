"""Shared catalogue repository — psycopg-3-backed PostgreSQL implementation.

:class:`Catalogue` is the abstract persistence surface for the unified
:class:`~sgs_shared.catalogue.models.CatalogueEntry` (payload products + control
references behind one query surface). :class:`PostgresCatalogue` is the PostgreSQL
implementation using **psycopg 3** (``psycopg.connect``).

This mirrors the *shape* of the payload ``Catalogue`` ABC (``pdgs.catalogue.repository``)
for a clean Phase-1 alignment, but is fully independent — it does not import ``pdgs``.

Timestamps are stored as ``timestamptz`` (UTC). The schema is created idempotently
on construction. A new connection is opened per call (simple, avoids cross-thread
state); fine for Phase 0. Phase 0 implements the minimal contract
(``register`` / ``get`` / ``list``); ``update_status`` / ``set_provenance`` land in
Phase 1 with the frozen schema.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import psycopg

from sgs_shared.catalogue.models import CatalogueEntry, Origin

if TYPE_CHECKING:
    from collections.abc import Iterable

# Env var holding the PostgreSQL DSN. Named to match the payload convention
# (``PDGS_PG_DSN``) so a single DSN configures both Phase-0 callers.
PG_DSN_ENV = "PDGS_PG_DSN"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS catalogue_entries (
    entry_id        TEXT PRIMARY KEY,
    origin          TEXT NOT NULL CHECK (origin IN ('payload', 'control')),
    simulated       BOOLEAN NOT NULL,
    product_type    TEXT NOT NULL,
    status          TEXT NOT NULL,
    sensing_time    TIMESTAMPTZ,
    ingest_time     TIMESTAMPTZ NOT NULL,
    source_version  TEXT,
    reference       TEXT NOT NULL,
    detail          TEXT
);
"""

# Column order shared by INSERT / SELECT so row-mapping stays in lockstep.
_COLUMNS = (
    "entry_id",
    "origin",
    "simulated",
    "product_type",
    "status",
    "sensing_time",
    "ingest_time",
    "source_version",
    "reference",
    "detail",
)


class CatalogueError(RuntimeError):
    """Raised when a catalogue operation cannot complete (e.g. a backend error)."""


def _utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(tz=UTC)


def _as_utc(value: datetime) -> datetime:
    """Normalise a datetime to timezone-aware UTC (assume UTC if naive)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class Catalogue(ABC):
    """Abstract unified-catalogue repository.

    Implementations persist :class:`CatalogueEntry` rows (payload products AND
    control references) and expose one query surface over both origins.
    """

    @abstractmethod
    def register(self, entry: CatalogueEntry) -> None:
        """Insert or replace a catalogue entry (idempotent on ``entry_id``)."""

    @abstractmethod
    def get(self, entry_id: str) -> CatalogueEntry | None:
        """Return the entry with ``entry_id`` or ``None`` if absent."""

    @abstractmethod
    def list(self, *, origin: Origin | None = None) -> list[CatalogueEntry]:
        """Return entries (optionally filtered by ``origin``), ordered by ingest time."""


class PostgresCatalogue(Catalogue):
    """psycopg-3 PostgreSQL implementation of :class:`Catalogue`.

    The DSN comes from the ``dsn`` constructor argument or, if omitted, the
    ``PDGS_PG_DSN`` environment variable (e.g.
    ``postgresql://sgs:change-me@localhost:5432/sgs_catalogue``). The schema is
    created idempotently on construction. A new connection is opened per call.
    """

    def __init__(self, dsn: str | None = None) -> None:
        resolved = dsn if dsn is not None else os.environ.get(PG_DSN_ENV)
        if not resolved:
            raise CatalogueError(
                f"no PostgreSQL DSN: pass dsn= or set {PG_DSN_ENV} "
                "(e.g. postgresql://sgs:change-me@localhost:5432/sgs_catalogue)"
            )
        self.dsn: str = resolved
        try:
            with self._connect() as conn:
                conn.execute(_SCHEMA)
                conn.commit()
        except psycopg.Error as exc:  # pragma: no cover - needs a live/broken DB
            raise CatalogueError(f"failed to initialise catalogue schema: {exc}") from exc

    def _connect(self) -> psycopg.Connection[tuple[object, ...]]:
        try:
            return psycopg.connect(self.dsn)
        except psycopg.Error as exc:  # pragma: no cover - needs a live/broken DB
            raise CatalogueError(f"failed to connect to PostgreSQL: {exc}") from exc

    def register(self, entry: CatalogueEntry) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO catalogue_entries (
                        entry_id, origin, simulated, product_type, status,
                        sensing_time, ingest_time, source_version, reference, detail
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (entry_id) DO UPDATE SET
                        origin = EXCLUDED.origin,
                        simulated = EXCLUDED.simulated,
                        product_type = EXCLUDED.product_type,
                        status = EXCLUDED.status,
                        sensing_time = EXCLUDED.sensing_time,
                        ingest_time = EXCLUDED.ingest_time,
                        source_version = EXCLUDED.source_version,
                        reference = EXCLUDED.reference,
                        detail = EXCLUDED.detail
                    """,
                    (
                        entry.entry_id,
                        entry.origin,
                        entry.simulated,
                        entry.product_type,
                        entry.status,
                        _as_utc(entry.sensing_time) if entry.sensing_time is not None else None,
                        _as_utc(entry.ingest_time),
                        entry.source_version,
                        entry.reference,
                        entry.detail,
                    ),
                )
                conn.commit()
        except psycopg.Error as exc:
            raise CatalogueError(f"failed to register entry {entry.entry_id!r}: {exc}") from exc

    def get(self, entry_id: str) -> CatalogueEntry | None:
        sql = f"SELECT {', '.join(_COLUMNS)} FROM catalogue_entries WHERE entry_id = %s"
        try:
            with self._connect() as conn:
                row = conn.execute(sql, (entry_id,)).fetchone()
        except psycopg.Error as exc:
            raise CatalogueError(f"failed to read entry {entry_id!r}: {exc}") from exc
        return _row_to_entry(row) if row is not None else None

    def list(self, *, origin: Origin | None = None) -> list[CatalogueEntry]:
        params: tuple[object, ...] = ()
        where = ""
        if origin is not None:
            where = " WHERE origin = %s"
            params = (origin,)
        sql = (
            f"SELECT {', '.join(_COLUMNS)} FROM catalogue_entries{where} "
            "ORDER BY ingest_time, entry_id"
        )
        try:
            with self._connect() as conn:
                rows: Iterable[tuple[object, ...]] = conn.execute(sql, params).fetchall()
        except psycopg.Error as exc:
            raise CatalogueError(f"failed to list entries: {exc}") from exc
        return [_row_to_entry(row) for row in rows]


def _row_to_entry(row: tuple[object, ...]) -> CatalogueEntry:
    """Reconstruct a :class:`CatalogueEntry` from a positional ``_COLUMNS`` row."""
    (
        entry_id,
        origin,
        simulated,
        product_type,
        status,
        sensing_time,
        ingest_time,
        source_version,
        reference,
        detail,
    ) = row
    if origin not in ("payload", "control"):  # pragma: no cover - guarded by CHECK
        raise CatalogueError(f"corrupt row: unexpected origin {origin!r}")
    sensing = _as_utc(sensing_time) if isinstance(sensing_time, datetime) else None
    if not isinstance(ingest_time, datetime):  # pragma: no cover - NOT NULL column
        raise CatalogueError(f"corrupt row {entry_id!r}: missing ingest_time")
    return CatalogueEntry(
        entry_id=str(entry_id),
        origin=origin,
        simulated=bool(simulated),
        product_type=str(product_type),
        status=str(status),
        sensing_time=sensing,
        ingest_time=_as_utc(ingest_time),
        source_version=str(source_version) if source_version is not None else None,
        reference=str(reference),
        detail=str(detail) if detail is not None else None,
    )
