"""Shared catalogue repository — psycopg-3-backed PostgreSQL implementation.

:class:`Catalogue` is the abstract persistence surface for the unified
:class:`~sgs_shared.catalogue.models.CatalogueEntry` (payload products + control
references behind one query surface). :class:`PostgresCatalogue` is the PostgreSQL
implementation using **psycopg 3** (``psycopg.connect``).

This mirrors the *shape* of the payload ``Catalogue`` ABC (``pdgs.catalogue.repository``)
for a clean Phase-1 alignment, but is fully independent — it does not import ``pdgs``.

Timestamps are stored as ``timestamptz`` (UTC). The provenance envelope is stored
flattened into three ``prov_*`` columns (``prov_source_version``,
``prov_source_refs`` as a native ``text[]``, ``prov_run_time``) and rebuilt into a
nested :class:`~sgs_shared.catalogue.models.Provenance` on read. The schema is
created idempotently AND forward-compatibly on construction (so an existing Phase-0
flat table upgrades cleanly). A new connection is opened per call (simple, avoids
cross-thread state). The full query surface is ``register`` / ``get`` / ``list`` /
``update_status`` / ``set_provenance``.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import psycopg

from sgs_shared.catalogue.models import CatalogueEntry, Origin, Provenance

if TYPE_CHECKING:
    from collections.abc import Iterable

# Env var holding the PostgreSQL DSN. Named to match the payload convention
# (``PDGS_PG_DSN``) so a single DSN configures both Phase-0 callers.
PG_DSN_ENV = "PDGS_PG_DSN"

# Full frozen schema. ``CREATE TABLE IF NOT EXISTS`` lays the table down with every
# Phase-1 column; the defensive ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` lines
# upgrade an existing Phase-0 flat table (which lacked the provenance columns).
_SCHEMA = """
CREATE TABLE IF NOT EXISTS catalogue_entries (
    entry_id            TEXT PRIMARY KEY,
    origin              TEXT NOT NULL CHECK (origin IN ('payload', 'control')),
    simulated           BOOLEAN NOT NULL,
    product_type        TEXT NOT NULL,
    status              TEXT NOT NULL,
    sensing_time        TIMESTAMPTZ,
    ingest_time         TIMESTAMPTZ NOT NULL,
    reference           TEXT NOT NULL,
    prov_source_version TEXT,
    prov_source_refs    TEXT[] NOT NULL DEFAULT '{}',
    prov_run_time       TIMESTAMPTZ,
    detail              TEXT
);
ALTER TABLE catalogue_entries ADD COLUMN IF NOT EXISTS prov_source_version TEXT;
ALTER TABLE catalogue_entries
    ADD COLUMN IF NOT EXISTS prov_source_refs TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE catalogue_entries ADD COLUMN IF NOT EXISTS prov_run_time TIMESTAMPTZ;
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
    "reference",
    "prov_source_version",
    "prov_source_refs",
    "prov_run_time",
    "detail",
)


class CatalogueError(RuntimeError):
    """Raised when a catalogue operation cannot complete (e.g. a backend error)."""


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

    @abstractmethod
    def update_status(self, entry_id: str, status: str) -> None:
        """Update an entry's ``status``; raise :class:`CatalogueError` if unknown."""

    @abstractmethod
    def set_provenance(self, entry_id: str, provenance: Provenance) -> None:
        """Overwrite an entry's provenance envelope; raise on unknown ``entry_id``."""


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
        prov = entry.provenance
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO catalogue_entries (
                        entry_id, origin, simulated, product_type, status,
                        sensing_time, ingest_time, reference,
                        prov_source_version, prov_source_refs, prov_run_time, detail
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (entry_id) DO UPDATE SET
                        origin = EXCLUDED.origin,
                        simulated = EXCLUDED.simulated,
                        product_type = EXCLUDED.product_type,
                        status = EXCLUDED.status,
                        sensing_time = EXCLUDED.sensing_time,
                        ingest_time = EXCLUDED.ingest_time,
                        reference = EXCLUDED.reference,
                        prov_source_version = EXCLUDED.prov_source_version,
                        prov_source_refs = EXCLUDED.prov_source_refs,
                        prov_run_time = EXCLUDED.prov_run_time,
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
                        entry.reference,
                        prov.source_version,
                        list(prov.source_refs),
                        _as_utc(prov.run_time) if prov.run_time is not None else None,
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

    def update_status(self, entry_id: str, status: str) -> None:
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE catalogue_entries SET status = %s WHERE entry_id = %s",
                    (status, entry_id),
                )
                rowcount = cur.rowcount
                conn.commit()
        except psycopg.Error as exc:
            raise CatalogueError(f"failed to update status of entry {entry_id!r}: {exc}") from exc
        if rowcount == 0:
            raise CatalogueError(f"unknown entry_id {entry_id!r}")

    def set_provenance(self, entry_id: str, provenance: Provenance) -> None:
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    UPDATE catalogue_entries SET
                        prov_source_version = %s,
                        prov_source_refs = %s,
                        prov_run_time = %s
                    WHERE entry_id = %s
                    """,
                    (
                        provenance.source_version,
                        list(provenance.source_refs),
                        _as_utc(provenance.run_time) if provenance.run_time is not None else None,
                        entry_id,
                    ),
                )
                rowcount = cur.rowcount
                conn.commit()
        except psycopg.Error as exc:
            raise CatalogueError(f"failed to set provenance of entry {entry_id!r}: {exc}") from exc
        if rowcount == 0:
            raise CatalogueError(f"unknown entry_id {entry_id!r}")


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
        reference,
        prov_source_version,
        prov_source_refs,
        prov_run_time,
        detail,
    ) = row
    if origin not in ("payload", "control"):  # pragma: no cover - guarded by CHECK
        raise CatalogueError(f"corrupt row: unexpected origin {origin!r}")
    sensing = _as_utc(sensing_time) if isinstance(sensing_time, datetime) else None
    if not isinstance(ingest_time, datetime):  # pragma: no cover - NOT NULL column
        raise CatalogueError(f"corrupt row {entry_id!r}: missing ingest_time")
    run_time = _as_utc(prov_run_time) if isinstance(prov_run_time, datetime) else None
    source_refs: tuple[str, ...] = (
        tuple(str(ref) for ref in prov_source_refs)
        if isinstance(prov_source_refs, (list, tuple))
        else ()
    )
    provenance = Provenance(
        source_version=str(prov_source_version) if prov_source_version is not None else None,
        source_refs=source_refs,
        run_time=run_time,
    )
    return CatalogueEntry(
        entry_id=str(entry_id),
        origin=origin,
        simulated=bool(simulated),
        product_type=str(product_type),
        status=str(status),
        sensing_time=sensing,
        ingest_time=_as_utc(ingest_time),
        reference=str(reference),
        provenance=provenance,
        detail=str(detail) if detail is not None else None,
    )
