"""Ingestion orchestration: discover -> download -> verify -> register (REQ-ING-01/02/04).

Drives a :class:`~pdgs.ingestion.datastore.DataStoreClient` through the ingestion
lifecycle, advancing each product's :class:`~pdgs.catalogue.models.ProductStatus`
(DISCOVERED -> DOWNLOADED -> VERIFIED -> REGISTERED) and persisting records in the
:class:`~pdgs.catalogue.repository.Catalogue`. The integrity check (REQ-ING-03)
gates registration: a product that fails verification — or any step that raises —
is routed to the ``FAILED`` dead-letter state (groundwork for Phase 4), and
ingestion continues with the next product.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pdgs.catalogue.models import Product, ProductLevel, ProductStatus
from pdgs.catalogue.repository import Catalogue
from pdgs.config.paths import default_download_dir
from pdgs.ingestion.datastore import DataStoreClient, ProductRef
from pdgs.ingestion.integrity import compute_sha256, product_size_bytes

# Collection id -> (product_type, level) for catalogue records.
_COLLECTION_META: dict[str, tuple[str, ProductLevel]] = {
    "EO:EUM:DAT:0411": ("SL_1_RBT", "L1"),
    "EO:EUM:DAT:0412": ("SL_2_WST", "L2"),
}

_TIMELINESS = "NTC"


@dataclass
class IngestResult:
    """Outcome of an :func:`ingest` run."""

    registered: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Total number of products attempted."""
        return len(self.registered) + len(self.failed)


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _meta_for(collection_id: str) -> tuple[str, ProductLevel]:
    return _COLLECTION_META.get(collection_id, ("UNKNOWN", "L1"))


def _failed_product(ref: ProductRef, local_path: str, checksum: str, size: int) -> Product:
    product_type, level = _meta_for(ref.collection_id)
    now = _utcnow()
    return Product(
        product_id=ref.product_id,
        collection_id=ref.collection_id,
        product_type=product_type,
        level=level,
        timeliness=_TIMELINESS,
        sensing_start=ref.sensing_start,
        sensing_end=ref.sensing_end,
        bbox=ref.bbox,
        local_path=local_path,
        checksum=checksum,
        size_bytes=size,
        status=ProductStatus.FAILED,
        provenance=None,
        created_at=now,
        updated_at=now,
    )


def ingest(
    client: DataStoreClient,
    collection_id: str,
    start: datetime,
    end: datetime,
    catalogue: Catalogue,
    *,
    dest_dir: Path | None = None,
) -> IngestResult:
    """Discover, download, verify and register products for ``collection_id``.

    Each product advances through DISCOVERED -> DOWNLOADED -> VERIFIED ->
    REGISTERED on success; any failure (download error, integrity mismatch, etc.)
    routes the product to the ``FAILED`` dead-letter state. Returns an
    :class:`IngestResult` summarising registered vs failed product ids.
    """
    dest = dest_dir if dest_dir is not None else default_download_dir()
    result = IngestResult()

    refs = client.search(collection_id, start, end)
    for ref in refs:
        product_type, level = _meta_for(ref.collection_id)
        try:
            # DISCOVERED -> register a stub so status is visible during ingest.
            stub = Product(
                product_id=ref.product_id,
                collection_id=ref.collection_id,
                product_type=product_type,
                level=level,
                timeliness=_TIMELINESS,
                sensing_start=ref.sensing_start,
                sensing_end=ref.sensing_end,
                bbox=ref.bbox,
                local_path="",
                checksum="",
                size_bytes=0,
                status=ProductStatus.DISCOVERED,
                provenance=None,
                created_at=_utcnow(),
                updated_at=_utcnow(),
            )
            catalogue.register(stub)

            # DOWNLOADED
            local_path = client.download(ref, dest)
            checksum = compute_sha256(local_path)
            size = product_size_bytes(local_path)

            # VERIFIED (REQ-ING-03): recompute and confirm the just-downloaded
            # product is self-consistent before registering it.
            from pdgs.ingestion.integrity import verify_integrity

            if not verify_integrity(local_path, checksum):
                raise OSError(f"integrity verification failed for {ref.product_id}")

            # REGISTERED (REQ-ING-04)
            now = _utcnow()
            product = Product(
                product_id=ref.product_id,
                collection_id=ref.collection_id,
                product_type=product_type,
                level=level,
                timeliness=_TIMELINESS,
                sensing_start=ref.sensing_start,
                sensing_end=ref.sensing_end,
                bbox=ref.bbox,
                local_path=str(local_path),
                checksum=checksum,
                size_bytes=size,
                status=ProductStatus.REGISTERED,
                provenance=None,
                created_at=stub.created_at,
                updated_at=now,
            )
            catalogue.register(product)
            result.registered.append(ref.product_id)
        except Exception:
            # Dead-letter the product (groundwork for Phase 4) and keep going.
            failed = _failed_product(ref, "", "", 0)
            catalogue.register(failed)
            result.failed.append(ref.product_id)

    return result
