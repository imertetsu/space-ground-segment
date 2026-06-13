"""Catalogue repository — sqlite3-backed product registry (REQ-ING-04).

The :class:`Catalogue` abstract interface defines the persistence surface so Epic 3
can swap the stdlib-sqlite implementation (:class:`SqliteCatalogue`) for the shared
PostgreSQL catalogue without touching callers. Schema creation is idempotent.

Datetimes are stored as ISO-8601 UTC strings; the bbox as four columns;
provenance fields inline (a product has at most one provenance block). All reads
reconstruct fully-typed :class:`~pdgs.catalogue.models.Product` instances.
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path

from pdgs.catalogue.models import BBox, Product, ProductLevel, ProductStatus, Provenance
from pdgs.config.paths import default_catalogue_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    product_id        TEXT PRIMARY KEY,
    collection_id     TEXT NOT NULL,
    product_type      TEXT NOT NULL,
    level             TEXT NOT NULL,
    timeliness        TEXT NOT NULL,
    sensing_start     TEXT NOT NULL,
    sensing_end       TEXT NOT NULL,
    bbox_west         REAL,
    bbox_south        REAL,
    bbox_east         REAL,
    bbox_north        REAL,
    local_path        TEXT NOT NULL,
    checksum          TEXT NOT NULL,
    size_bytes        INTEGER NOT NULL,
    status            TEXT NOT NULL,
    prov_processor_version TEXT,
    prov_config_version    TEXT,
    prov_input_product_ids TEXT,
    prov_run_timestamp     TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
"""


def _utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(tz=UTC)


def _iso(value: datetime) -> str:
    """Serialise a datetime to an ISO-8601 string (UTC-normalised)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _parse_dt(value: str) -> datetime:
    """Parse an ISO-8601 string back to a timezone-aware UTC datetime."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class CatalogueError(RuntimeError):
    """Raised on catalogue operations that cannot complete (e.g. unknown id)."""


class Catalogue(ABC):
    """Abstract product-catalogue repository.

    Implementations persist :class:`~pdgs.catalogue.models.Product` records and
    expose a small CRUD-plus-status surface. Epic 3 provides a PostgreSQL
    implementation against this same interface.
    """

    @abstractmethod
    def register(self, product: Product) -> None:
        """Insert or replace a product record."""

    @abstractmethod
    def get(self, product_id: str) -> Product | None:
        """Return the product with ``product_id`` or ``None`` if absent."""

    @abstractmethod
    def list(
        self,
        *,
        status: ProductStatus | None = None,
        product_type: str | None = None,
    ) -> list[Product]:
        """Return products, optionally filtered by status and/or product type."""

    @abstractmethod
    def update_status(self, product_id: str, status: ProductStatus) -> None:
        """Transition a product to ``status`` and bump ``updated_at``."""

    @abstractmethod
    def set_provenance(self, product_id: str, provenance: Provenance) -> None:
        """Attach a provenance block to a product and bump ``updated_at``."""


class SqliteCatalogue(Catalogue):
    """stdlib-sqlite3 implementation of :class:`Catalogue`.

    The schema is created idempotently on construction. A new connection is opened
    per call (cheap for sqlite, avoids cross-thread issues) against the configured
    database file. Pass ``db_path=":memory:"`` is NOT supported (each connection is
    independent); use a temp file in tests instead.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path: Path = Path(db_path) if db_path is not None else default_catalogue_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def register(self, product: Product) -> None:
        bbox = product.bbox
        prov = product.provenance
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO products (
                    product_id, collection_id, product_type, level, timeliness,
                    sensing_start, sensing_end,
                    bbox_west, bbox_south, bbox_east, bbox_north,
                    local_path, checksum, size_bytes, status,
                    prov_processor_version, prov_config_version,
                    prov_input_product_ids, prov_run_timestamp,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product.product_id,
                    product.collection_id,
                    product.product_type,
                    product.level,
                    product.timeliness,
                    _iso(product.sensing_start),
                    _iso(product.sensing_end),
                    bbox[0] if bbox else None,
                    bbox[1] if bbox else None,
                    bbox[2] if bbox else None,
                    bbox[3] if bbox else None,
                    product.local_path,
                    product.checksum,
                    product.size_bytes,
                    product.status.value,
                    prov.processor_version if prov else None,
                    prov.config_version if prov else None,
                    json.dumps(list(prov.input_product_ids)) if prov else None,
                    _iso(prov.run_timestamp) if prov else None,
                    _iso(product.created_at),
                    _iso(product.updated_at),
                ),
            )

    def get(self, product_id: str) -> Product | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE product_id = ?", (product_id,)
            ).fetchone()
        return _row_to_product(row) if row is not None else None

    def list(
        self,
        *,
        status: ProductStatus | None = None,
        product_type: str | None = None,
    ) -> list[Product]:
        clauses: list[str] = []
        params: list[str] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if product_type is not None:
            clauses.append("product_type = ?")
            params.append(product_type)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM products{where} ORDER BY sensing_start, product_id"
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_product(row) for row in rows]

    def update_status(self, product_id: str, status: ProductStatus) -> None:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE products SET status = ?, updated_at = ? WHERE product_id = ?",
                (status.value, _iso(_utcnow()), product_id),
            )
            if cur.rowcount == 0:
                raise CatalogueError(f"unknown product_id: {product_id!r}")

    def set_provenance(self, product_id: str, provenance: Provenance) -> None:
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE products SET
                    prov_processor_version = ?,
                    prov_config_version = ?,
                    prov_input_product_ids = ?,
                    prov_run_timestamp = ?,
                    updated_at = ?
                WHERE product_id = ?
                """,
                (
                    provenance.processor_version,
                    provenance.config_version,
                    json.dumps(list(provenance.input_product_ids)),
                    _iso(provenance.run_timestamp),
                    _iso(_utcnow()),
                    product_id,
                ),
            )
            if cur.rowcount == 0:
                raise CatalogueError(f"unknown product_id: {product_id!r}")


def _row_to_product(row: sqlite3.Row) -> Product:
    """Reconstruct a :class:`Product` from a sqlite row."""
    bbox: BBox | None = None
    if row["bbox_west"] is not None:
        bbox = (
            float(row["bbox_west"]),
            float(row["bbox_south"]),
            float(row["bbox_east"]),
            float(row["bbox_north"]),
        )

    provenance: Provenance | None = None
    if row["prov_processor_version"] is not None:
        ids_raw = row["prov_input_product_ids"]
        input_ids: tuple[str, ...] = tuple(json.loads(ids_raw)) if ids_raw else ()
        provenance = Provenance(
            processor_version=row["prov_processor_version"],
            config_version=row["prov_config_version"],
            input_product_ids=input_ids,
            run_timestamp=_parse_dt(row["prov_run_timestamp"]),
        )

    level: ProductLevel = row["level"]
    return Product(
        product_id=row["product_id"],
        collection_id=row["collection_id"],
        product_type=row["product_type"],
        level=level,
        timeliness=row["timeliness"],
        sensing_start=_parse_dt(row["sensing_start"]),
        sensing_end=_parse_dt(row["sensing_end"]),
        bbox=bbox,
        local_path=row["local_path"],
        checksum=row["checksum"],
        size_bytes=int(row["size_bytes"]),
        status=ProductStatus(row["status"]),
        provenance=provenance,
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )
