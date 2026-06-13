"""Read-only consumer of the payload (PDGS) SQLite catalogue (Epic 3, Phase 4).

:class:`PayloadSqliteBridge` opens the payload segment's SQLite catalogue file
**read-only** and projects each ``products`` row into a unified payload
:class:`~sgs_shared.catalogue.models.CatalogueEntry` via
:func:`~sgs_shared.catalogue.mappers.entry_from_payload_product`. It mirrors the
read-only-consumer pattern of the Yamcs control bridge
(:mod:`sgs_shared.control_bridge.yamcs`): the bridge reads a **data file** with the
standard-library :mod:`sqlite3` driver and imports NO ``pdgs`` (or ``sgs_sim``)
code — a data dependency, not a code import, so the cross-segment isolation rule
(``lint-imports``) is upheld.

Payload products are REAL EUMETSAT data, so every entry is ``origin="payload"`` /
``simulated=False`` (the mapper enforces this). The connection is opened with a
``file:...?mode=ro`` URI so the bridge can never write to the payload catalogue.
All datetimes are parsed defensively into timezone-aware UTC.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sgs_shared.catalogue.mappers import entry_from_payload_product

if TYPE_CHECKING:
    from sgs_shared.catalogue.models import CatalogueEntry
    from sgs_shared.catalogue.repository import Catalogue

# The payload ``products`` columns this bridge reads, in SELECT order. These are the
# pdgs Epic-1 SQLite schema columns (CONTEXT) — read directly, never via a pdgs import.
_COLUMNS = (
    "product_id",
    "product_type",
    "level",
    "status",
    "sensing_start",
    "local_path",
    "created_at",
    "prov_processor_version",
    "prov_input_product_ids",
    "prov_run_timestamp",
)

_DETAIL = "payload product (REAL data) mirrored from PDGS SQLite catalogue (read-only)"


class PayloadBridgeError(RuntimeError):
    """Raised when the payload SQLite catalogue is missing, unreadable, or malformed."""


def _parse_iso_utc(value: object) -> datetime | None:
    """Parse an ISO-8601 UTC string into timezone-aware UTC (or ``None``).

    Handles a trailing ``Z`` and naive timestamps (assumed UTC). Non-string or
    unparseable values yield ``None`` so a missing/garbled column never crashes a
    read-only mirror.
    """
    if not isinstance(value, str) or not value:
        return None
    normalised = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalised)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_input_ids(value: object) -> tuple[str, ...]:
    """Parse the ``prov_input_product_ids`` JSON-array string into a tuple of ids."""
    if not isinstance(value, str) or not value:
        return ()
    try:
        loaded = json.loads(value)
    except (ValueError, TypeError):
        return ()
    if not isinstance(loaded, list):
        return ()
    return tuple(str(item) for item in loaded)


class PayloadSqliteBridge:
    """Read-only reader of the payload (PDGS) SQLite catalogue.

    Args:
        db_path: Filesystem path to the payload SQLite catalogue file.

    The file is opened lazily (per :meth:`collect`) through a ``mode=ro`` URI
    connection, so the bridge can only ever read. A missing file, an unreadable
    file, or a database without the ``products`` table raises
    :class:`PayloadBridgeError`.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        """Open the payload catalogue read-only (``file:...?mode=ro`` URI)."""
        abspath = self.db_path.resolve()
        if not abspath.exists():
            raise PayloadBridgeError(f"payload SQLite catalogue not found: {abspath}")
        uri = f"file:{abspath.as_posix()}?mode=ro"
        try:
            return sqlite3.connect(uri, uri=True)
        except (sqlite3.Error, OSError) as exc:
            raise PayloadBridgeError(
                f"failed to open payload SQLite catalogue {abspath} read-only: {exc}"
            ) from exc

    def collect(self) -> list[CatalogueEntry]:
        """Read the payload ``products`` table into payload :class:`CatalogueEntry`s.

        Each row maps via :func:`entry_from_payload_product` (origin=payload,
        simulated=False). The ``reference`` is ``local_path`` when present, else the
        ``product_id``; ``ingest_time`` falls back to *now* (UTC) when ``created_at``
        is absent/unparseable. Raises :class:`PayloadBridgeError` if the ``products``
        table is absent or the DB cannot be read.
        """
        sql = f"SELECT {', '.join(_COLUMNS)} FROM products"  # fixed column list; no user input
        try:
            conn = self._connect()
            try:
                rows = conn.execute(sql).fetchall()
            finally:
                conn.close()
        except (sqlite3.Error, OSError) as exc:
            raise PayloadBridgeError(
                f"failed to read 'products' from payload SQLite catalogue {self.db_path}: {exc}"
            ) from exc

        return [self._row_to_entry(row) for row in rows]

    @staticmethod
    def _row_to_entry(row: tuple[object, ...]) -> CatalogueEntry:
        """Map one positional ``_COLUMNS`` row to a payload :class:`CatalogueEntry`."""
        (
            product_id,
            product_type,
            _level,
            status,
            sensing_start,
            local_path,
            created_at,
            prov_processor_version,
            prov_input_product_ids,
            prov_run_timestamp,
        ) = row
        product_id_s = str(product_id)
        reference = str(local_path) if local_path else product_id_s
        ingest_time = _parse_iso_utc(created_at) or datetime.now(tz=UTC)
        processor_version = (
            str(prov_processor_version) if prov_processor_version is not None else None
        )
        return entry_from_payload_product(
            product_id=product_id_s,
            product_type=str(product_type),
            status=str(status),
            sensing_time=_parse_iso_utc(sensing_start),
            ingest_time=ingest_time,
            reference=reference,
            processor_version=processor_version,
            input_product_ids=_parse_input_ids(prov_input_product_ids),
            run_time=_parse_iso_utc(prov_run_timestamp),
            detail=_DETAIL,
        )


def record_products(catalogue: Catalogue, bridge: PayloadSqliteBridge) -> int:
    """Collect payload products from ``bridge`` and register each into ``catalogue``.

    Returns the number of products mirrored into the shared catalogue.
    """
    entries = bridge.collect()
    for entry in entries:
        catalogue.register(entry)
    return len(entries)
